# RAG 기반 종목/매크로 심층 분석, JSON 응답 프롬프트, LLM 호출
import json
import re
import logging
from typing import Optional

from api.services.ollama_client import generate
from api.services.rag_engine import search_and_build_prompt, search_similar_news

logger = logging.getLogger(__name__)

_DEFAULT_RESULT = {
    "sentiment_score": 0.0,
    "confidence": 0.0,
    "key_issues": [],
    "is_priced_in": False,
    "outlook": "neutral",
    "rationale": "",
}


def _parse_json_response(text: str) -> dict:
    """LLM 응답에서 JSON을 파싱한다. thinking 제거 + 다단계 파싱."""
    if not text:
        return {}
    # Remove <think>...</think> blocks
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # Remove unclosed <think> tags
    text = re.sub(r'<think>.*', '', text, flags=re.DOTALL)
    text = text.strip()
    if not text:
        return {}
    # Remove markdown code fences
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # Attempt 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Attempt 2: find first { ... last }
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        candidate = text[start:end]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            # Attempt 3: fix common issues (trailing commas, single quotes)
            fixed = re.sub(r',\s*}', '}', candidate)
            fixed = re.sub(r",\s*]", ']', fixed)
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass

    # Attempt 4: extract individual fields with regex
    result = {}
    score_match = re.search(r'"sentiment_score"\s*:\s*(-?[\d.]+)', text)
    if score_match:
        result["sentiment_score"] = float(score_match.group(1))
    conf_match = re.search(r'"confidence"\s*:\s*([\d.]+)', text)
    if conf_match:
        result["confidence"] = float(conf_match.group(1))
    outlook_match = re.search(r'"outlook"\s*:\s*"(bullish|bearish|neutral)"', text)
    if outlook_match:
        result["outlook"] = outlook_match.group(1)
    rationale_match = re.search(r'"rationale"\s*:\s*"([^"]*)"', text)
    if rationale_match:
        result["rationale"] = rationale_match.group(1)
    priced_match = re.search(r'"is_priced_in"\s*:\s*(true|false)', text, re.IGNORECASE)
    if priced_match:
        result["is_priced_in"] = priced_match.group(1).lower() == "true"
    if result:
        logger.info("Extracted partial JSON fields: %s", list(result.keys()))
    return result


async def analyze_stock(
    symbol: str,
    current_indicators: Optional[dict] = None,
) -> dict:
    """RAG 기반 종목 심층 분석. 뉴스 없으면 LLM 호출 스킵."""
    try:
        # 먼저 뉴스 존재 여부 확인
        context_docs = await search_similar_news(
            query=f"{symbol} stock news",
            symbol=symbol,
        )

        if not context_docs:
            logger.info("No news for %s, skipping LLM call", symbol)
            return {
                **_DEFAULT_RESULT,
                "rationale": "No recent news available, skipped LLM analysis",
            }

        prompt = await search_and_build_prompt(
            symbol=symbol,
            current_indicators=current_indicators,
        )

        system = "Expert financial analyst. Respond with valid JSON only."

        response = await generate(
            prompt=prompt,
            system=system,
            temperature=0.3,
            num_predict=2048,
        )
        result = _parse_json_response(response)

        if not result:
            logger.warning("Empty JSON from RAG analysis for %s", symbol)
            return {
                **_DEFAULT_RESULT,
                "rationale": "Analysis could not be completed",
            }

        return result

    except Exception as e:
        logger.error("RAG stock analysis failed for %s: %s", symbol, e)
        return {
            **_DEFAULT_RESULT,
            "rationale": f"Error: {str(e)}",
        }


async def analyze_macro() -> dict:
    """RAG 기반 매크로 분석."""
    try:
        context_docs = await search_similar_news(
            query="US economy recession inflation Federal Reserve interest rate S&P 500",
            symbol=None,
            top_k=5,
        )

        if not context_docs:
            return {
                "regime": "NEUTRAL",
                "regime_score": 0.5,
                "confidence": 0.0,
                "key_factors": [],
                "outlook": "neutral",
                "rationale": "No macro news available",
            }

        context_parts = []
        for i, doc in enumerate(context_docs, 1):
            text = doc["text"][:200] if doc["text"] else ""
            context_parts.append(f"[{i}] {text}")
        context_text = "\n".join(context_parts)

        prompt = f"""Analyze US market regime from news. JSON only.

News:
{context_text}

JSON: {{"regime":"<EXTREME_FEAR|FEAR|NEUTRAL|GREED|EXTREME_GREED>","regime_score":<0~1>,"confidence":<0~1>,"key_factors":[<str>],"outlook":"<bearish|neutral|bullish>","rationale":"<1 sentence>"}}"""

        system = "Macroeconomic analyst. JSON only."
        response = await generate(
            prompt=prompt,
            system=system,
            temperature=0.3,
            num_predict=2048,
        )
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
