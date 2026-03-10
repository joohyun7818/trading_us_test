# 기술적 지표 0-100 점수화 (Python만, LLM 불필요)
# RSI 25% + MACD 20% + SMA 15% + 볼린저 15% + 거래량 10% + 52주 10% + ATR 5%
import logging
from typing import Optional

from api.core.database import fetch_one

logger = logging.getLogger(__name__)

WEIGHTS = {
    "rsi": 0.25,
    "macd": 0.20,
    "sma": 0.15,
    "bollinger": 0.15,
    "volume": 0.10,
    "week52": 0.10,
    "atr": 0.05,
}


def _score_rsi(rsi: Optional[float]) -> float:
    """RSI를 0-100 점수로 변환한다. 과매도=높은점수(매수기회), 과매수=낮은점수."""
    if rsi is None:
        return 50.0
    if rsi <= 20:
        return 95.0
    elif rsi <= 30:
        return 80.0 + (30 - rsi) * 1.5
    elif rsi <= 40:
        return 65.0 + (40 - rsi) * 1.5
    elif rsi <= 60:
        return 50.0
    elif rsi <= 70:
        return 50.0 - (rsi - 60) * 1.5
    elif rsi <= 80:
        return 35.0 - (rsi - 70) * 1.5
    else:
        return max(5.0, 20.0 - (rsi - 80) * 1.5)


def _score_macd(macd: Optional[float], macd_signal: Optional[float], macd_histogram: Optional[float]) -> float:
    """MACD를 0-100 점수로 변환한다."""
    if macd is None or macd_signal is None:
        return 50.0

    score = 50.0

    if macd > macd_signal:
        score += 15.0
    else:
        score -= 15.0

    if macd_histogram is not None:
        if macd_histogram > 0:
            score += min(15.0, abs(macd_histogram) * 100)
        else:
            score -= min(15.0, abs(macd_histogram) * 100)

    if macd > 0:
        score += 5.0
    else:
        score -= 5.0

    return max(0.0, min(100.0, score))


def _score_sma(price: Optional[float], sma_20: Optional[float], sma_60: Optional[float]) -> float:
    """SMA 대비 가격 위치를 0-100 점수로 변환한다."""
    if price is None:
        return 50.0

    score = 50.0

    if sma_20 is not None and sma_20 > 0:
        pct_from_sma20 = ((price - sma_20) / sma_20) * 100
        score += min(15.0, max(-15.0, pct_from_sma20 * 3))

    if sma_60 is not None and sma_60 > 0:
        pct_from_sma60 = ((price - sma_60) / sma_60) * 100
        score += min(10.0, max(-10.0, pct_from_sma60 * 2))

    if sma_20 is not None and sma_60 is not None:
        if sma_20 > sma_60:
            score += 5.0
        else:
            score -= 5.0

    return max(0.0, min(100.0, score))


def _score_bollinger(pct_b: Optional[float]) -> float:
    """볼린저 %B를 0-100 점수로 변환한다."""
    if pct_b is None:
        return 50.0

    if pct_b <= 0.0:
        return 90.0
    elif pct_b <= 0.2:
        return 75.0 + (0.2 - pct_b) * 75
    elif pct_b <= 0.4:
        return 60.0 + (0.4 - pct_b) * 75
    elif pct_b <= 0.6:
        return 50.0
    elif pct_b <= 0.8:
        return 50.0 - (pct_b - 0.6) * 75
    elif pct_b <= 1.0:
        return 35.0 - (pct_b - 0.8) * 75
    else:
        return 10.0


def _score_volume(volume_ratio: Optional[float]) -> float:
    """거래량 비율을 0-100 점수로 변환한다."""
    if volume_ratio is None:
        return 50.0

    if volume_ratio >= 2.0:
        return 80.0
    elif volume_ratio >= 1.5:
        return 70.0
    elif volume_ratio >= 1.0:
        return 55.0 + (volume_ratio - 1.0) * 30
    elif volume_ratio >= 0.5:
        return 40.0 + (volume_ratio - 0.5) * 30
    else:
        return 30.0


def _score_52w_position(price: Optional[float], high_52w: Optional[float], low_52w: Optional[float]) -> float:
    """52주 고저가 대비 위치를 0-100 점수로 변환한다."""
    if price is None or high_52w is None or low_52w is None:
        return 50.0
    if high_52w == low_52w:
        return 50.0

    position = (price - low_52w) / (high_52w - low_52w)

    if position <= 0.1:
        return 85.0
    elif position <= 0.3:
        return 70.0
    elif position <= 0.5:
        return 55.0
    elif position <= 0.7:
        return 45.0
    elif position <= 0.9:
        return 35.0
    else:
        return 20.0


def _score_atr(atr: Optional[float], price: Optional[float]) -> float:
    """ATR/가격 비율을 0-100 점수로 변환한다. 적절한 변동성=높은 점수."""
    if atr is None or price is None or price == 0:
        return 50.0

    atr_pct = (atr / price) * 100

    if atr_pct <= 1.0:
        return 40.0
    elif atr_pct <= 2.0:
        return 60.0
    elif atr_pct <= 3.5:
        return 70.0
    elif atr_pct <= 5.0:
        return 55.0
    elif atr_pct <= 7.0:
        return 40.0
    else:
        return 25.0


async def calculate_numeric_score(symbol: str) -> dict:
    """종목의 기술적 지표를 0-100 종합 점수로 산출한다."""
    row = await fetch_one(
        """
        SELECT current_price, rsi_14, sma_20, sma_60,
               macd, macd_signal, macd_histogram,
               bollinger_upper, bollinger_lower, bollinger_pct_b,
               volume_ratio, high_52w, low_52w, atr_14
        FROM stocks WHERE symbol = $1
        """,
        symbol,
    )

    if not row:
        logger.warning("No stock data found for %s", symbol)
        return {"symbol": symbol, "score": 50.0, "components": {}, "status": "no_data"}

    price = float(row["current_price"]) if row["current_price"] else None
    rsi = float(row["rsi_14"]) if row["rsi_14"] else None
    sma_20 = float(row["sma_20"]) if row["sma_20"] else None
    sma_60 = float(row["sma_60"]) if row["sma_60"] else None
    macd_val = float(row["macd"]) if row["macd"] else None
    macd_sig = float(row["macd_signal"]) if row["macd_signal"] else None
    macd_hist = float(row["macd_histogram"]) if row["macd_histogram"] else None
    b_pct = float(row["bollinger_pct_b"]) if row["bollinger_pct_b"] else None
    vol_ratio = float(row["volume_ratio"]) if row["volume_ratio"] else None
    high_52w = float(row["high_52w"]) if row["high_52w"] else None
    low_52w = float(row["low_52w"]) if row["low_52w"] else None
    atr = float(row["atr_14"]) if row["atr_14"] else None

    rsi_score = _score_rsi(rsi)
    macd_score = _score_macd(macd_val, macd_sig, macd_hist)
    sma_score = _score_sma(price, sma_20, sma_60)
    bollinger_score = _score_bollinger(b_pct)
    volume_score = _score_volume(vol_ratio)
    week52_score = _score_52w_position(price, high_52w, low_52w)
    atr_score = _score_atr(atr, price)

    final_score = (
        rsi_score * WEIGHTS["rsi"]
        + macd_score * WEIGHTS["macd"]
        + sma_score * WEIGHTS["sma"]
        + bollinger_score * WEIGHTS["bollinger"]
        + volume_score * WEIGHTS["volume"]
        + week52_score * WEIGHTS["week52"]
        + atr_score * WEIGHTS["atr"]
    )
    final_score = round(final_score, 4)

    components = {
        "rsi": {"score": round(rsi_score, 2), "value": rsi, "weight": WEIGHTS["rsi"]},
        "macd": {"score": round(macd_score, 2), "value": macd_val, "weight": WEIGHTS["macd"]},
        "sma": {"score": round(sma_score, 2), "price": price, "sma_20": sma_20, "sma_60": sma_60, "weight": WEIGHTS["sma"]},
        "bollinger": {"score": round(bollinger_score, 2), "pct_b": b_pct, "weight": WEIGHTS["bollinger"]},
        "volume": {"score": round(volume_score, 2), "ratio": vol_ratio, "weight": WEIGHTS["volume"]},
        "week52": {"score": round(week52_score, 2), "high": high_52w, "low": low_52w, "weight": WEIGHTS["week52"]},
        "atr": {"score": round(atr_score, 2), "value": atr, "weight": WEIGHTS["atr"]},
    }

    logger.info("Numeric score for %s: %.2f", symbol, final_score)
    return {
        "symbol": symbol,
        "score": final_score,
        "components": components,
        "status": "ok",
    }
