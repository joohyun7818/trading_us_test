# 7개 매크로 지표 → regime_score, EXTREME_GREED/FEAR 판단, TQQQ/SQQQ 전략
import logging
from datetime import datetime, date, timedelta, timezone
from typing import Optional

import yfinance as yf

from api.core.database import execute, fetch_all, fetch_one
from api.core.utils import run_sync

logger = logging.getLogger(__name__)

# 국제정세 가중치 추가 시 기존 가중치 재조정
MACRO_WEIGHTS = {
    "sp500_trend": 0.18,
    "vix": 0.18,
    "yield_curve": 0.13,
    "market_rsi": 0.13,
    "breadth": 0.08,
    "put_call": 0.08,
    "macro_sentiment": 0.10,
    "geopolitical": 0.12,  # 신규
}


async def _calc_geopolitical_score() -> float:
    """geopolitical_regime의 최신 리스크를 0~1 매크로 점수로 변환한다.
    높은 리스크 → 낮은 점수 (공포). STABLE → 0.7, CRISIS → 0.1"""
    try:
        from api.services.geopolitical_engine import calculate_geopolitical_regime
        result = await calculate_geopolitical_regime()
        composite = result.get("composite_risk", 0.0)
        # composite_risk 0~1을 반전: 높은 리스크 = 낮은 매크로 점수
        score = max(0.0, min(1.0, 1.0 - composite))
        # 시장 영향 조정 적용
        impact = result.get("market_sentiment_impact", 0.0)
        score = max(0.0, min(1.0, score + impact))
        return round(score, 4)
    except Exception as e:
        logger.error("Geopolitical score calc failed: %s", e)
        return 0.5


async def calculate_regime() -> dict:
    """8개 매크로 지표 → regime_score → 레짐을 판단한다. (국제정세 포함)"""
    sp500_trend = await _calc_sp500_trend()
    vix_score = await _calc_vix_score()
    yield_curve = await _calc_yield_curve()
    market_rsi = await _calc_market_rsi()
    breadth = await _calc_breadth()
    put_call = _calc_put_call()
    macro_sentiment = await _calc_macro_sentiment()
    geopolitical = await _calc_geopolitical_score()  # 신규

    values = {
        "sp500_trend": sp500_trend or 0.5,
        "vix": vix_score or 0.5,
        "yield_curve": yield_curve or 0.5,
        "market_rsi": market_rsi or 0.5,
        "breadth": breadth or 0.5,
        "put_call": put_call or 0.5,
        "macro_sentiment": macro_sentiment,
        "geopolitical": geopolitical,  # 신규
    }

    regime_score = sum(values[k] * MACRO_WEIGHTS[k] for k in MACRO_WEIGHTS)
    regime_score = round(max(0.0, min(1.0, regime_score)), 4)

    if regime_score >= 0.8:
        regime = "EXTREME_GREED"
    elif regime_score >= 0.6:
        regime = "GREED"
    elif regime_score >= 0.4:
        regime = "NEUTRAL"
    elif regime_score >= 0.2:
        regime = "FEAR"
    else:
        regime = "EXTREME_FEAR"

    leveraged_action = await _evaluate_leveraged_action(regime, regime_score)

    try:
        await execute(
            """
            INSERT INTO macro_regime
                (regime, regime_score, sp500_trend, vix_level,
                 yield_curve_spread, market_rsi, market_breadth,
                 put_call_ratio, macro_news_sentiment,
                 geopolitical_risk, geopolitical_regime,
                 leveraged_action)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
            """,
            regime, regime_score,
            values["sp500_trend"], values["vix"],
            values["yield_curve"], values["market_rsi"],
            values["breadth"], values["put_call"],
            values["macro_sentiment"],
            values["geopolitical"],  # 신규
            None,  # geopolitical_regime 문자열 (별도 조회 가능)
            leveraged_action,
        )
    except Exception as e:
        logger.error("Macro regime insert failed: %s", e)

    logger.info(
        "Macro regime: %s (%.4f) geo=%.4f action=%s",
        regime, regime_score, geopolitical, leveraged_action,
    )

    return {
        "regime": regime,
        "regime_score": regime_score,
        "indicators": values,
        "leveraged_action": leveraged_action,
    }


async def _calc_sp500_trend() -> Optional[float]:
    """S&P 500 트렌드 점수를 계산한다 (0-1, 1=강세)."""
    try:
        spy = yf.Ticker("SPY")
        hist = await run_sync(spy.history, period="3mo")
        if hist.empty or len(hist) < 20:
            return None
        closes = hist["Close"]
        sma20 = closes.rolling(20).mean().iloc[-1]
        sma50 = closes.rolling(50).mean().iloc[-1] if len(closes) >= 50 else sma20
        current = closes.iloc[-1]
        score = 0.5
        if current > sma20:
            score += 0.15
        if current > sma50:
            score += 0.15
        if sma20 > sma50:
            score += 0.1
        pct_change = ((current - closes.iloc[-20]) / closes.iloc[-20]) * 100
        score += max(-0.1, min(0.1, pct_change / 100))
        return max(0.0, min(1.0, round(score, 4)))
    except Exception as e:
        logger.error("SP500 trend calc failed: %s", e)
        return None


async def _calc_vix_score() -> Optional[float]:
    """VIX를 0-1 점수로 변환한다 (높은 VIX = 낮은 점수 = 공포)."""
    try:
        vix = yf.Ticker("^VIX")
        hist = await run_sync(vix.history, period="5d")
        if hist.empty:
            return None
        vix_val = float(hist["Close"].iloc[-1])
        if vix_val <= 12:
            return 0.9
        elif vix_val <= 15:
            return 0.8
        elif vix_val <= 20:
            return 0.6
        elif vix_val <= 25:
            return 0.4
        elif vix_val <= 30:
            return 0.25
        elif vix_val <= 40:
            return 0.15
        else:
            return 0.05
    except Exception as e:
        logger.error("VIX calc failed: %s", e)
        return None


async def _calc_yield_curve() -> Optional[float]:
    """수익률 곡선 스프레드 점수 (0-1)."""
    try:
        tnx = yf.Ticker("^TNX")
        irx = yf.Ticker("^IRX")
        tnx_hist = await run_sync(tnx.history, period="5d")
        irx_hist = await run_sync(irx.history, period="5d")
        if tnx_hist.empty or irx_hist.empty:
            return 0.5
        ten_year = float(tnx_hist["Close"].iloc[-1])
        two_year = float(irx_hist["Close"].iloc[-1])
        spread = ten_year - two_year
        if spread > 1.5:
            return 0.85
        elif spread > 0.5:
            return 0.7
        elif spread > 0:
            return 0.55
        elif spread > -0.5:
            return 0.35
        else:
            return 0.15
    except Exception as e:
        logger.error("Yield curve calc failed: %s", e)
        return None


async def _calc_market_rsi() -> Optional[float]:
    """S&P 500 RSI를 0-1 점수로 변환한다."""
    try:
        spy = yf.Ticker("SPY")
        hist = await run_sync(spy.history, period="3mo")
        if hist.empty or len(hist) < 15:
            return None
        closes = hist["Close"]
        delta = closes.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.rolling(14).mean().iloc[-1]
        avg_loss = loss.rolling(14).mean().iloc[-1]
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        return max(0.0, min(1.0, round(rsi / 100, 4)))
    except Exception as e:
        logger.error("Market RSI calc failed: %s", e)
        return None


async def _calc_breadth() -> Optional[float]:
    """시장 너비 (NYSE advance/decline 근사)."""
    try:
        spy = yf.Ticker("SPY")
        hist = await run_sync(spy.history, period="1mo")
        if hist.empty or len(hist) < 10:
            return None
        closes = hist["Close"]
        up_days = sum(1 for i in range(1, len(closes)) if closes.iloc[i] > closes.iloc[i - 1])
        total_days = len(closes) - 1
        return round(up_days / total_days, 4) if total_days > 0 else 0.5
    except Exception as e:
        logger.error("Breadth calc failed: %s", e)
        return None


def _calc_put_call() -> Optional[float]:
    """풋콜 비율 기반 점수 (0-1, 높은 P/C = 공포 = 낮은 점수).
    실시간 풋콜 비율 데이터 소스 미연동으로 중립값 반환."""
    return 0.5


async def _calc_macro_sentiment() -> float:
    """DB에서 최근 24시간 매크로 뉴스 감성 평균을 0-1 범위로 반환한다."""
    try:
        row = await fetch_one(
            """
            SELECT AVG(sentiment_score) as avg_sentiment
            FROM news_articles
            WHERE published_at > NOW() - INTERVAL '24 hours'
              AND sentiment_score IS NOT NULL
            """
        )
        if row and row["avg_sentiment"] is not None:
            avg = float(row["avg_sentiment"])
            # sentiment_score is in [-1, 1]; convert to [0, 1] range
            return round(max(0.0, min(1.0, (avg + 1.0) / 2.0)), 4)
    except Exception as e:
        logger.error("Macro sentiment DB query failed: %s", e)
    return 0.5


async def _evaluate_leveraged_action(regime: str, regime_score: float) -> str:
    """레버리지 TQQQ/SQQQ 전략을 평가한다."""
    enabled_row = await fetch_one("SELECT value FROM settings WHERE key = 'leveraged_enabled'")
    if not enabled_row or enabled_row["value"].lower() != "true":
        return "disabled"

    min_days_row = await fetch_one("SELECT value FROM settings WHERE key = 'leveraged_min_extreme_days'")
    min_days = int(min_days_row["value"]) if min_days_row else 3

    recent = await fetch_all(
        """
        SELECT regime FROM macro_regime
        ORDER BY created_at DESC LIMIT $1
        """,
        min_days,
    )

    open_positions = await fetch_all(
        "SELECT * FROM leveraged_positions WHERE status = 'open'"
    )

    if open_positions:
        return await _check_leveraged_exit(open_positions)

    if len(recent) < min_days:
        return "waiting"

    all_extreme_greed = all(r["regime"] == "EXTREME_GREED" for r in recent)
    all_extreme_fear = all(r["regime"] == "EXTREME_FEAR" for r in recent)

    if all_extreme_greed:
        return "buy_tqqq"
    elif all_extreme_fear:
        return "buy_sqqq"

    return "hold"


async def _check_leveraged_exit(positions: list[dict]) -> str:
    """오픈 레버리지 포지션의 청산 여부를 확인한다."""
    for pos in positions:
        symbol = pos["symbol"]
        entry_price = float(pos["entry_price"])
        stop_loss = float(pos["stop_loss"])
        take_profit = float(pos["take_profit"])
        max_hold = pos.get("max_hold_days", 5)
        entry_date = pos["entry_date"]

        try:
            ticker = yf.Ticker(symbol)
            hist = await run_sync(ticker.history, period="1d")
            if not hist.empty:
                current_price = float(hist["Close"].iloc[-1])
            else:
                continue
        except Exception:
            continue

        days_held = (date.today() - entry_date).days if isinstance(entry_date, date) else 0

        if current_price <= stop_loss:
            return f"close_{symbol}_stoploss"
        if current_price >= take_profit:
            return f"close_{symbol}_takeprofit"
        if days_held >= max_hold:
            return f"close_{symbol}_maxhold"

    return "hold_leveraged"


async def get_regime_history(limit: int = 30) -> list[dict]:
    """매크로 레짐 이력을 조회한다."""
    rows = await fetch_all(
        """
        SELECT regime, regime_score, sp500_trend, vix_level,
               yield_curve_spread, market_rsi, market_breadth,
               put_call_ratio, macro_news_sentiment,
               geopolitical_risk, geopolitical_regime,
               leveraged_action, created_at
        FROM macro_regime
        ORDER BY created_at DESC
        LIMIT $1
        """,
        limit,
    )
    return rows
