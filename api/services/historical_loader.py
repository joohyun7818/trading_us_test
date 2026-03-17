import logging
from datetime import date
from typing import Optional

import pandas as pd
import yfinance as yf

from api.core.database import fetch_all, fetch_one, get_pool
from api.core.utils import run_sync
from api.services.price_crawler import (
    _calc_atr,
    _calc_bollinger,
    _calc_macd,
    _calc_rsi,
    _calc_sma,
    _calc_volume_ratio,
)
from api.services.sp500_loader import get_sp500_symbols

logger = logging.getLogger(__name__)


def _to_float(value: object, digits: int) -> Optional[float]:
    if pd.isna(value):
        return None
    return round(float(value), digits)


def _extract_symbol_df(data: pd.DataFrame, symbol: str, single_symbol_batch: bool) -> pd.DataFrame:
    if single_symbol_batch:
        return data
    if symbol not in data.columns.get_level_values(0):
        return pd.DataFrame()
    return data[symbol]


def _build_insert_rows(symbol: str, df: pd.DataFrame, latest_date: Optional[date]) -> list[tuple]:
    if df.empty:
        return []

    work = df.copy()
    work = work.dropna(subset=["Close"])
    if work.empty:
        return []

    closes = work["Close"].squeeze() if isinstance(work["Close"], pd.DataFrame) else work["Close"]
    highs = work["High"].squeeze() if isinstance(work["High"], pd.DataFrame) else work["High"]
    lows = work["Low"].squeeze() if isinstance(work["Low"], pd.DataFrame) else work["Low"]
    volumes = work["Volume"].squeeze() if isinstance(work["Volume"], pd.DataFrame) else work["Volume"]
    adj_closes = work["Adj Close"].squeeze() if "Adj Close" in work.columns else pd.Series(index=work.index, dtype=float)

    rows: list[tuple] = []
    for i, idx in enumerate(work.index):
        trade_date = pd.Timestamp(idx).date()
        if latest_date and trade_date <= latest_date:
            continue

        close_val = _to_float(closes.iloc[i], 4)
        if close_val is None:
            continue

        closes_slice = closes.iloc[: i + 1]
        highs_slice = highs.iloc[: i + 1]
        lows_slice = lows.iloc[: i + 1]
        volumes_slice = volumes.iloc[: i + 1]

        rsi = _calc_rsi(closes_slice)
        sma_20 = _calc_sma(closes_slice, 20)
        sma_60 = _calc_sma(closes_slice, 60)
        macd, macd_signal, macd_histogram = _calc_macd(closes_slice)
        b_upper, b_lower, b_pct = _calc_bollinger(closes_slice)
        volume_ratio = _calc_volume_ratio(volumes_slice)
        atr_14 = _calc_atr(highs_slice, lows_slice, closes_slice)

        vol_raw = volumes.iloc[i]
        volume = int(vol_raw) if pd.notna(vol_raw) else None
        adj_close = _to_float(adj_closes.iloc[i], 4) if i < len(adj_closes) else None

        rows.append(
            (
                symbol,
                trade_date,
                _to_float(work["Open"].iloc[i], 4),
                _to_float(work["High"].iloc[i], 4),
                _to_float(work["Low"].iloc[i], 4),
                close_val,
                volume,
                adj_close,
                rsi,
                sma_20,
                sma_60,
                macd,
                macd_signal,
                macd_histogram,
                b_upper,
                b_lower,
                b_pct,
                volume_ratio,
                atr_14,
            )
        )
    return rows


async def _get_latest_trade_dates(symbols: list[str]) -> dict[str, date]:
    if not symbols:
        return {}
    rows = await fetch_all(
        """
        SELECT symbol, MAX(trade_date) AS max_date
        FROM stock_daily
        WHERE symbol = ANY($1::varchar[])
        GROUP BY symbol
        """,
        symbols,
    )
    return {row["symbol"]: row["max_date"] for row in rows if row.get("max_date")}


async def load_history(incremental: bool = True, years: int = 3) -> dict:
    symbols = await get_sp500_symbols()
    if not symbols:
        return {"status": "error", "message": "No S&P 500 symbols found", "processed": 0, "inserted": 0, "errors": 0}

    latest_dates = await _get_latest_trade_dates(symbols) if incremental else {}

    batch_size = 50
    processed = 0
    inserted = 0
    errors = 0

    insert_sql = """
    INSERT INTO stock_daily (
        symbol, trade_date, open, high, low, close, volume, adj_close,
        rsi_14, sma_20, sma_60, macd, macd_signal, macd_histogram,
        bollinger_upper, bollinger_lower, bollinger_pct_b, volume_ratio, atr_14
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8,
        $9, $10, $11, $12, $13, $14,
        $15, $16, $17, $18, $19
    )
    ON CONFLICT (symbol, trade_date) DO NOTHING
    """

    pool = await get_pool()
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        logger.info("Historical load progress: %d/%d symbols", min(i + len(batch), len(symbols)), len(symbols))

        tickers_str = " ".join(batch)
        try:
            data = await run_sync(
                yf.download,
                tickers_str,
                period=f"{years}y",
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=True,
            )
        except Exception as exc:
            logger.error("yfinance download failed for batch starting at %d: %s", i, exc)
            errors += len(batch)
            continue

        args_list: list[tuple] = []
        for symbol in batch:
            try:
                df = _extract_symbol_df(data, symbol, len(batch) == 1)
                rows = _build_insert_rows(symbol, df, latest_dates.get(symbol))
                args_list.extend(rows)
                processed += 1
            except Exception as exc:
                logger.error("Historical row build failed for %s: %s", symbol, exc)
                errors += 1

        if not args_list:
            continue
        async with pool.acquire() as conn:
            await conn.executemany(insert_sql, args_list)
        inserted += len(args_list)

    logger.info("Historical load completed: processed=%d inserted=%d errors=%d", processed, inserted, errors)
    return {
        "status": "ok",
        "processed": processed,
        "inserted": inserted,
        "errors": errors,
        "incremental": incremental,
    }


async def get_history_status() -> dict:
    summary = await fetch_one(
        """
        SELECT
            COUNT(*) AS total_rows,
            COUNT(DISTINCT symbol) AS loaded_symbols,
            MIN(trade_date) AS min_trade_date,
            MAX(trade_date) AS max_trade_date
        FROM stock_daily
        """
    )
    total_symbols_row = await fetch_one("SELECT COUNT(*) AS cnt FROM stocks WHERE is_sp500 = TRUE")

    max_trade_date = summary["max_trade_date"] if summary else None
    missing_latest_row = {"cnt": 0}
    if max_trade_date:
        missing_latest_row = await fetch_one(
            """
            SELECT COUNT(*) AS cnt
            FROM stocks s
            WHERE s.is_sp500 = TRUE
              AND NOT EXISTS (
                  SELECT 1
                  FROM stock_daily d
                  WHERE d.symbol = s.symbol
                    AND d.trade_date = $1
              )
            """,
            max_trade_date,
        ) or {"cnt": 0}

    return {
        "total_symbols": total_symbols_row["cnt"] if total_symbols_row else 0,
        "loaded_symbols": summary["loaded_symbols"] if summary else 0,
        "date_range": {
            "start": summary["min_trade_date"] if summary else None,
            "end": max_trade_date,
        },
        "total_rows": summary["total_rows"] if summary else 0,
        "missing_count": missing_latest_row["cnt"],
    }
