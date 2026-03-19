# mplfinance 캔들차트 PNG 생성 → qwen3.5:4b 패턴 분석, analysis_cache 캐싱
import io
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import mplfinance as mpf
import pandas as pd
import yfinance as yf

from api.core.config import settings                       # 추가
from api.core.database import execute, fetch_one
from api.core.utils import run_sync
from api.services.ollama_client import generate_with_image

logger = logging.getLogger(__name__)


async def _get_analysis_mode() -> str:
    """현재 분석 모드를 settings에서 조회한다."""
    row = await fetch_one("SELECT value FROM settings WHERE key = 'analysis_mode'")
    return row["value"] if row else "text_numeric"


async def _check_cache(symbol: str) -> Optional[dict]:
    """analysis_cache에서 유효한 캐시를 확인한다."""
    row = await fetch_one(
        """
        SELECT result FROM analysis_cache
        WHERE stock_symbol = $1 AND analysis_type = 'visual'
          AND expires_at > NOW()
        ORDER BY created_at DESC
        LIMIT 1
        """,
        symbol,
    )
    if row and row.get("result"):
        return row["result"] if isinstance(row["result"], dict) else json.loads(row["result"])
    return None


async def _save_cache(symbol: str, result: dict) -> None:
    """분석 결과를 analysis_cache에 4시간 캐싱한다."""
    try:
        await execute(
            """
            INSERT INTO analysis_cache (stock_symbol, analysis_type, model_used, result, expires_at)
            VALUES ($1, 'visual', $2, $3, NOW() + INTERVAL '4 hours')
            """,
            symbol,
            settings.OLLAMA_VISION_MODEL,    # 변경: 하드코딩 "qwen3-vl:8b" → settings 참조
            json.dumps(result),
        )
    except Exception as e:
        logger.error("Cache save failed for %s: %s", symbol, e)


def _generate_candlestick_chart(symbol: str, days: int = 60) -> Optional[bytes]:
    """mplfinance로 캔들차트 PNG를 생성한다."""
    try:
        ticker = yf.Ticker(symbol)
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        df = ticker.history(start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"))

        if df.empty or len(df) < 10:
            logger.warning("Insufficient data for chart: %s (%d rows)", symbol, len(df))
            return None

        mc = mpf.make_marketcolors(
            up="#26a69a", down="#ef5350",
            edge="inherit", wick="inherit",
            volume={"up": "#26a69a", "down": "#ef5350"},
        )
        style = mpf.make_mpf_style(
            marketcolors=mc,
            base_mpf_style="nightclouds",
            gridcolor="#2a2a2a",
            facecolor="#0f172a",
            figcolor="#0f172a",
            rc={"font.size": 8},
        )

        add_plots = []
        if len(df) >= 20:
            sma20 = df["Close"].rolling(20).mean()
            add_plots.append(mpf.make_addplot(sma20, color="#3b82f6", width=1))
        if len(df) >= 50:
            sma50 = df["Close"].rolling(50).mean()
            add_plots.append(mpf.make_addplot(sma50, color="#f59e0b", width=1))

        buf = io.BytesIO()
        mpf.plot(
            df,
            type="candle",
            style=style,
            volume=True,
            addplot=add_plots if add_plots else None,
            title=f"\n{symbol} - {days}D Candlestick",
            savefig=dict(fname=buf, dpi=150, bbox_inches="tight"),
            figsize=(12, 8),
        )
        buf.seek(0)
        return buf.read()

    except Exception as e:
        logger.error("Chart generation failed for %s: %s", symbol, e)
        return None


async def analyze_chart(symbol: str) -> Optional[dict]:
    """캔들차트 시각 분석을 수행한다. text_numeric 모드이면 None 반환."""
    mode = await _get_analysis_mode()
    if mode == "text_numeric":
        logger.info("Visual analysis skipped (mode=%s) for %s", mode, symbol)
        return None

    cached = await _check_cache(symbol)
    if cached:
        logger.info("Cache hit for visual analysis of %s", symbol)
        return cached

    chart_bytes = await run_sync(_generate_candlestick_chart, symbol)
    if chart_bytes is None:
        return None

    prompt = f"""Analyze this candlestick chart for {symbol}. Identify:

1. Overall trend (uptrend, downtrend, sideways)
2. Key candlestick patterns (doji, hammer, engulfing, etc.)
3. Support and resistance levels
4. Volume analysis
5. Moving average crossovers (if visible)

Provide your analysis in JSON format:
{{
  "trend": "<uptrend|downtrend|sideways>",
  "patterns": [
    {{"name": "<pattern_name>", "confidence": <0.0-1.0>, "signal": "<bullish|bearish|neutral>"}}
  ],
  "support_level": <float or null>,
  "resistance_level": <float or null>,
  "volume_trend": "<increasing|decreasing|stable>",
  "visual_score": <float 0-100, 50=neutral, >50=bullish, <50=bearish>,
  "rationale": "<brief analysis summary>"
}}

Respond ONLY with valid JSON."""

    system = "You are a technical analyst expert. Analyze stock charts precisely. Respond with JSON only."

    try:
        response = await generate_with_image(
            prompt=prompt,
            image_bytes=chart_bytes,
            system=system,
        )

        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[:-3]

        try:
            result = json.loads(text.strip())
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(text[start:end])
            else:
                result = {"visual_score": 50, "trend": "neutral", "patterns": [], "rationale": "Parse error"}

        await _save_cache(symbol, result)
        logger.info("Visual analysis completed for %s: score=%s", symbol, result.get("visual_score"))
        return result

    except Exception as e:
        logger.error("Chart analysis failed for %s: %s", symbol, e)
        return None
