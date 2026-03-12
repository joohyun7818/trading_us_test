# RAG 기반 종목/매크로 심층 분석, JSON 응답 프롬프트, qwen3:8b 호출
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from api.core.database import execute, fetch_one
from api.services.ollama_client import generate
from api.services.rag_engine import search_and_build_prompt, search_similar_news

logger = logging.getLogger(__name__)


def _parse_json_response(text: str) -> dict:
    """LLM 응답에서 JSON을 파싱한다."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    return {}


async def analyze_stock(
    symbol: str,
    current_indicators: Optional[dict] = None,
) -> dict:
    """RAG 기반 종목 심층 분석을 수행한다 (qwen3:8b)."""
    try:
        prompt = await search_and_build_prompt(
            symbol=symbol,
            current_indicators=current_indicators,
        )

        system = (
            "You are an expert financial analyst specializing in US equities. "
            "Provide precise, data-driven analysis in JSON format. "
            "Always respond with valid JSON only."
        )

        response = await generate(prompt=prompt, system=system, temperature=0.3)
        result = _parse_json_response(response)

        if not result:
            logger.warning("Empty JSON from RAG analysis for %s", symbol)
            return {
                "sentiment_score": 0.0,
                "confidence": 0.0,
                "key_issues": [],
                "is_priced_in": False,
                "outlook": "neutral",
                "rationale": "Analysis could not be completed",
            }

        return result

    except Exception as e:
        logger.error("RAG stock analysis failed for %s: %s", symbol, e)
        return {
            "sentiment_score": 0.0,
            "confidence": 0.0,
            "key_issues": [],
            "is_priced_in": False,
            "outlook": "neutral",
            "rationale": f"Error: {str(e)}",
        }


async def analyze_macro() -> dict:
    """RAG 기반 매크로 분석을 수행한다."""
    try:
        context_docs = await search_similar_news(
            query="US economy recession inflation Federal Reserve interest rate market outlook S&P 500",
            symbol=None,
            top_k=20,
        )

        context_parts = []
        for i, doc in enumerate(context_docs[:15], 1):
            meta = doc.get("metadata", {})
            context_parts.append(f"[{i}] {doc['text']}")
        context_text = "\n\n".join(context_parts) if context_parts else "No macro context available."

        prompt = f"""You are a macroeconomic analyst. Analyze the current US market regime based on recent news.

Recent Macro News:
{context_text}

Provide your analysis in the following JSON format:
{{
  "regime": "<EXTREME_FEAR|FEAR|NEUTRAL|GREED|EXTREME_GREED>",
  "regime_score": <float 0.0 to 1.0>,
  "confidence": <float 0.0 to 1.0>,
  "key_factors": [<list of key macro factors>],
  "outlook": "<bearish|neutral|bullish>",
  "rationale": "<detailed explanation>"
}}

Respond ONLY with valid JSON."""

        system = "You are an expert macroeconomic analyst. Respond with valid JSON only."
        response = await generate(prompt=prompt, system=system, temperature=0.3)
        result = _parse_json_response(response)

        if not result:
            return {
                "regime": "NEUTRAL",
                "regime_score": 0.5,
                "confidence": 0.0,
                "key_factors": [],
                "outlook": "neutral",
                "rationale": "Macro analysis could not be completed",
            }

        return result

    except Exception as e:
        logger.error("RAG macro analysis failed: %s", e)
        return {
            "regime": "NEUTRAL",
            "regime_score": 0.5,
            "confidence": 0.0,
            "key_factors": [],
            "outlook": "neutral",
            "rationale": f"Error: {str(e)}",
        }


async def get_analysis_history(symbol: str, limit: int = 10) -> list[dict]:
    """분석 캐시에서 이전 분석 기록을 조회한다."""
    from api.core.database import fetch_all

    rows = await fetch_all(
        """
        SELECT stock_symbol, analysis_type, model_used, result, created_at
        FROM analysis_cache
        WHERE stock_symbol = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        symbol, limit,
    )
    return rows
