# yfinance로 전 종목 가격 및 기술지표 수집, pandas+numpy 직접 계산
import logging
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from api.core.database import execute, fetch_all
from api.core.utils import run_sync_yf_download

logger = logging.getLogger(__name__)


def _calc_rsi(closes: pd.Series, period: int = 14) -> Optional[float]:
    """RSI(Relative Strength Index)를 직접 계산한다."""
    if len(closes) < period + 1:
        return None
    delta = closes.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return round(float(val), 4) if pd.notna(val) else None


def _calc_macd(closes: pd.Series) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """MACD, MACD Signal, MACD Histogram을 계산한다."""
    if len(closes) < 35:
        return None, None, None
    ema12 = closes.ewm(span=12, adjust=False).mean()
    ema26 = closes.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line
    m = macd_line.iloc[-1]
    s = signal_line.iloc[-1]
    h = histogram.iloc[-1]
    return (
        round(float(m), 6) if pd.notna(m) else None,
        round(float(s), 6) if pd.notna(s) else None,
        round(float(h), 6) if pd.notna(h) else None,
    )


def _calc_sma(closes: pd.Series, period: int) -> Optional[float]:
    """단순이동평균(SMA)을 계산한다."""
    if len(closes) < period:
        return None
    val = closes.rolling(window=period).mean().iloc[-1]
    return round(float(val), 4) if pd.notna(val) else None


def _calc_bollinger(closes: pd.Series, period: int = 20, num_std: float = 2.0) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """볼린저 밴드(상단, 하단, %B)를 계산한다."""
    if len(closes) < period:
        return None, None, None
    sma = closes.rolling(window=period).mean()
    std = closes.rolling(window=period).std()
    upper = sma + num_std * std
    lower = sma - num_std * std
    pct_b_series = (closes - lower) / (upper - lower)
    u = upper.iloc[-1]
    l_val = lower.iloc[-1]
    pb = pct_b_series.iloc[-1]
    return (
        round(float(u), 4) if pd.notna(u) else None,
        round(float(l_val), 4) if pd.notna(l_val) else None,
        round(float(pb), 4) if pd.notna(pb) else None,
    )


def _calc_volume_ratio(volumes: pd.Series, period: int = 20) -> Optional[float]:
    """거래량 비율(현재 거래량 / 20일 평균)을 계산한다."""
    if len(volumes) < period + 1:
        return None
    avg_vol = volumes.iloc[-period - 1 : -1].mean()
    if avg_vol == 0 or pd.isna(avg_vol):
        return None
    ratio = volumes.iloc[-1] / avg_vol
    return round(float(ratio), 4)


def _calc_52w_high_low(closes: pd.Series) -> tuple[Optional[float], Optional[float]]:
    """52주 최고가/최저가를 계산한다."""
    if len(closes) < 5:
        return None, None
    period = min(252, len(closes))
    window = closes.iloc[-period:]
    high = float(window.max())
    low = float(window.min())
    return round(high, 4), round(low, 4)


def _calc_atr(highs: pd.Series, lows: pd.Series, closes: pd.Series, period: int = 14) -> Optional[float]:
    """ATR(Average True Range)을 계산한다."""
    if len(closes) < period + 1:
        return None
    prev_close = closes.shift(1)
    tr1 = highs - lows
    tr2 = (highs - prev_close).abs()
    tr3 = (lows - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    val = atr.iloc[-1]
    return round(float(val), 4) if pd.notna(val) else None


async def crawl_prices(symbols: Optional[list[str]] = None) -> dict:
    """전 종목(또는 지정 종목) 가격과 기술지표를 수집하여 stocks 테이블을 UPDATE한다."""
    if symbols is None:
        rows = await fetch_all("SELECT symbol FROM stocks WHERE is_sp500 = TRUE ORDER BY symbol")
        symbols = [r["symbol"] for r in rows]

    if not symbols:
        return {"status": "ok", "updated": 0, "errors": 0}

    updated = 0
    errors = 0

    batch_size = 50
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        tickers_str = " ".join(batch)
        try:
            data = await run_sync_yf_download(
                yf.download,
                tickers_str,
                period="1y",
                group_by="ticker",
                progress=False,
                threads=True,
            )
        except Exception as e:
            logger.error("yfinance download failed for batch %d: %s", i, e)
            errors += len(batch)
            continue

        for symbol in batch:
            try:
                if len(batch) == 1:
                    df = data
                else:
                    if symbol not in data.columns.get_level_values(0):
                        continue
                    df = data[symbol]

                if df.empty or len(df) < 5:
                    continue

                df = df.dropna(subset=["Close"])
                if df.empty:
                    continue

                closes = df["Close"].squeeze() if isinstance(df["Close"], pd.DataFrame) else df["Close"]
                highs = df["High"].squeeze() if isinstance(df["High"], pd.DataFrame) else df["High"]
                lows = df["Low"].squeeze() if isinstance(df["Low"], pd.DataFrame) else df["Low"]
                volumes = df["Volume"].squeeze() if isinstance(df["Volume"], pd.DataFrame) else df["Volume"]

                current_price = round(float(closes.iloc[-1]), 4) if pd.notna(closes.iloc[-1]) else None
                prev_price = float(closes.iloc[-2]) if len(closes) >= 2 and pd.notna(closes.iloc[-2]) else None
                price_change_pct = round(((current_price - prev_price) / prev_price) * 100, 4) if current_price and prev_price and prev_price != 0 else None

                rsi = _calc_rsi(closes)
                macd_val, macd_sig, macd_hist = _calc_macd(closes)
                sma_20 = _calc_sma(closes, 20)
                sma_60 = _calc_sma(closes, 60)
                b_upper, b_lower, b_pct = _calc_bollinger(closes)
                vol_ratio = _calc_volume_ratio(volumes)
                high_52w, low_52w = _calc_52w_high_low(closes)
                atr = _calc_atr(highs, lows, closes)

                await execute(
                    """
                    UPDATE stocks SET
                        current_price = $1, price_change_pct = $2,
                        rsi_14 = $3, sma_20 = $4, sma_60 = $5,
                        macd = $6, macd_signal = $7, macd_histogram = $8,
                        bollinger_upper = $9, bollinger_lower = $10, bollinger_pct_b = $11,
                        volume_ratio = $12, high_52w = $13, low_52w = $14,
                        atr_14 = $15, updated_at = NOW()
                    WHERE symbol = $16
                    """,
                    current_price, price_change_pct,
                    rsi, sma_20, sma_60,
                    macd_val, macd_sig, macd_hist,
                    b_upper, b_lower, b_pct,
                    vol_ratio, high_52w, low_52w,
                    atr, symbol,
                )
                updated += 1
            except Exception as e:
                logger.error("Price crawl failed for %s: %s", symbol, e)
                errors += 1

    logger.info("Price crawl complete: %d updated, %d errors", updated, errors)
    return {"status": "ok", "updated": updated, "errors": errors}
