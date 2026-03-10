# 3축 가중 합산, analysis_mode별 가중치, 조정, BUY/SELL/HOLD 판단, signals INSERT
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from api.core.database import execute, fetch_all, fetch_one
from api.services.chart_analyzer import analyze_chart
from api.services.numeric_analyzer import calculate_numeric_score
from api.services.rag_analyzer import analyze_stock

logger = logging.getLogger(__name__)


async def _get_weights() -> dict:
    """settings 테이블에서 가중치를 로드한다."""
    mode_row = await fetch_one("SELECT value FROM settings WHERE key = 'analysis_mode'")
    mode = mode_row["value"] if mode_row else "text_numeric"

    if mode == "full":
        keys = ["w_text_full", "w_numeric_full", "w_visual_full", "w_macro_full"]
    else:
        keys = ["w_text", "w_numeric", "w_visual", "w_macro"]

    weights = {}
    for k in keys:
        row = await fetch_one("SELECT value FROM settings WHERE key = $1", k)
        clean_key = k.replace("_full", "")
        weights[clean_key] = float(row["value"]) if row else 0.0

    return {"mode": mode, "weights": weights}


def _apply_adjustments(
    base_score: float,
    text_result: Optional[dict],
    numeric_result: Optional[dict],
    visual_result: Optional[dict],
) -> tuple[float, list[dict]]:
    """조정 로직을 적용한다."""
    adjustments = []
    adjusted = base_score

    if text_result and text_result.get("is_priced_in"):
        adjustments.append({"type": "priced_in", "delta": -15})
        adjusted -= 15

    rsi_val = None
    if numeric_result and numeric_result.get("components", {}).get("rsi", {}).get("value"):
        rsi_val = numeric_result["components"]["rsi"]["value"]

    if rsi_val is not None and rsi_val >= 75:
        adjustments.append({"type": "overbought_rsi", "delta": -10, "rsi": rsi_val})
        adjusted -= 10
    elif rsi_val is not None and rsi_val <= 25:
        adjustments.append({"type": "oversold_rsi", "delta": +10, "rsi": rsi_val})
        adjusted += 10

    if visual_result:
        patterns = visual_result.get("patterns", [])
        for p in patterns:
            name = p.get("name", "").lower()
            confidence = p.get("confidence", 0)
            signal = p.get("signal", "neutral")
            if confidence >= 0.7:
                if "double_bottom" in name or "hammer" in name or "morning_star" in name:
                    adjustments.append({"type": f"pattern_{name}", "delta": +8})
                    adjusted += 8
                elif "double_top" in name or "shooting_star" in name or "evening_star" in name:
                    adjustments.append({"type": f"pattern_{name}", "delta": -8})
                    adjusted -= 8
                elif "engulfing" in name:
                    if signal == "bullish":
                        adjustments.append({"type": "bullish_engulfing", "delta": +6})
                        adjusted += 6
                    elif signal == "bearish":
                        adjustments.append({"type": "bearish_engulfing", "delta": -6})
                        adjusted -= 6

    adjusted = max(0.0, min(100.0, adjusted))
    return round(adjusted, 4), adjustments


def _determine_signal(score: float) -> str:
    """최종 점수에 따라 BUY/SELL/HOLD를 판단한다."""
    if score >= 70:
        return "BUY"
    elif score <= 30:
        return "SELL"
    return "HOLD"


async def analyze_and_signal(
    symbol: str,
    macro_score: Optional[float] = None,
) -> dict:
    """3축 분석 + 가중 합산 + 시그널 생성을 수행한다."""
    config = await _get_weights()
    mode = config["mode"]
    w = config["weights"]

    text_result = await analyze_stock(symbol)
    text_sentiment = text_result.get("sentiment_score", 0)
    text_score = ((text_sentiment + 1) / 2) * 100

    numeric_result = await calculate_numeric_score(symbol)
    numeric_score = numeric_result.get("score", 50.0)

    visual_result = None
    visual_score = 50.0
    if mode == "full":
        visual_result = await analyze_chart(symbol)
        if visual_result:
            visual_score = visual_result.get("visual_score", 50.0)

    if macro_score is None:
        macro_score = 50.0

    base_score = (
        text_score * w.get("w_text", 0.35)
        + numeric_score * w.get("w_numeric", 0.50)
        + visual_score * w.get("w_visual", 0.0)
        + macro_score * w.get("w_macro", 0.15)
    )

    final_score, adjustments = _apply_adjustments(
        base_score, text_result, numeric_result, visual_result
    )

    signal_type = _determine_signal(final_score)

    rationale_parts = []
    rationale_parts.append(f"Text: {text_score:.1f} (sentiment={text_sentiment:.3f})")
    rationale_parts.append(f"Numeric: {numeric_score:.1f}")
    if mode == "full":
        rationale_parts.append(f"Visual: {visual_score:.1f}")
    rationale_parts.append(f"Macro: {macro_score:.1f}")
    if text_result.get("rationale"):
        rationale_parts.append(f"Analysis: {text_result['rationale']}")
    rationale = " | ".join(rationale_parts)

    try:
        await execute(
            """
            INSERT INTO signals
                (stock_symbol, signal_type, final_score, text_score,
                 numeric_score, visual_score, macro_score,
                 analysis_mode, rationale, adjustments)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            """,
            symbol, signal_type, final_score,
            round(text_score, 4), round(numeric_score, 4),
            round(visual_score, 4) if mode == "full" else None,
            round(macro_score, 4),
            mode, rationale, json.dumps(adjustments),
        )
    except Exception as e:
        logger.error("Signal insert failed for %s: %s", symbol, e)

    logger.info(
        "Signal for %s: %s (%.2f) mode=%s",
        symbol, signal_type, final_score, mode,
    )

    return {
        "symbol": symbol,
        "signal_type": signal_type,
        "final_score": final_score,
        "text_score": round(text_score, 4),
        "numeric_score": round(numeric_score, 4),
        "visual_score": round(visual_score, 4) if mode == "full" else None,
        "macro_score": round(macro_score, 4),
        "analysis_mode": mode,
        "adjustments": adjustments,
        "rationale": rationale,
    }


async def check_exit(symbol: str) -> Optional[dict]:
    """보유 종목의 청산 여부를 확인한다."""
    position = await fetch_one("SELECT * FROM portfolio WHERE stock_symbol = $1", symbol)
    if not position:
        return None

    numeric_result = await calculate_numeric_score(symbol)
    score = numeric_result.get("score", 50.0)

    if score <= 30:
        return {
            "symbol": symbol,
            "action": "SELL",
            "reason": f"Exit signal: numeric_score={score:.1f}",
            "qty": float(position["qty"]),
        }

    unrealized_pnl_pct = float(position.get("unrealized_pnl_pct", 0) or 0)
    if unrealized_pnl_pct <= -8.0:
        return {
            "symbol": symbol,
            "action": "SELL",
            "reason": f"Stop-loss triggered: P&L={unrealized_pnl_pct:.2f}%",
            "qty": float(position["qty"]),
        }

    if unrealized_pnl_pct >= 15.0 and score <= 50:
        return {
            "symbol": symbol,
            "action": "SELL",
            "reason": f"Take-profit: P&L={unrealized_pnl_pct:.2f}%, score={score:.1f}",
            "qty": float(position["qty"]),
        }

    return None
