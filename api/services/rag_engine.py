# ChromaDB "stock_news" 컬렉션 similarity search, 프롬프트 조립
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from api.core.database import fetch_one
from api.services.news_indexer import get_collection
from api.services.ollama_client import embed
from api.services.gemini_indexer import search_gemini_news
from api.services.hybrid_search import hybrid_search

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 5
DEFAULT_DAYS = 7

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MULTI_SPACE_RE = re.compile(r"\s+")


def _clean_text(text: str) -> str:
    """HTML 태그 제거 및 공백 정리."""
    if not text:
        return ""
    text = _HTML_TAG_RE.sub(" ", text)
    text = _MULTI_SPACE_RE.sub(" ", text)
    return text.strip()


async def search_similar_news(
    query: str,
    symbol: Optional[str] = None,
    top_k: int = DEFAULT_TOP_K,
    days: int = DEFAULT_DAYS,
) -> list[dict]:
    """ChromaDB에서 유사 뉴스를 검색한다."""
    query_embedding = await embed(query)
    if not query_embedding:
        logger.warning("Empty embedding for query, returning empty results")
        return []

    collection = get_collection()

    where_filter = None
    if symbol:
        where_filter = {"stock_symbol": {"$eq": symbol}}

    try:
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:
        logger.error("ChromaDB query failed: %s", e)
        return []

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    output = []
    for doc, meta, dist in zip(docs, metas, dists):
        output.append({
            "text": _clean_text(doc),
            "metadata": meta,
            "similarity": round(1 - dist, 4) if dist is not None else 0,
        })

    return output


def _truncate_text(text: str, max_chars: int = 200) -> str:
    """뉴스 본문을 max_chars 자로 잘라낸다."""
    if not text or len(text) <= max_chars:
        return text or ""
    return text[:max_chars].rsplit(" ", 1)[0] + "..."


def build_rag_prompt(
    symbol: str,
    question: str,
    context_docs: list[dict],
    current_indicators: Optional[dict] = None,
) -> str:
    """RAG 분석용 프롬프트를 조립한다 (축소형)."""
    context_parts = []
    for i, doc in enumerate(context_docs, 1):
        meta = doc.get("metadata", {})
        pub_date = str(meta.get("published_at", "unknown"))[:10]
        sentiment = meta.get("sentiment_label", "neutral")
        score = meta.get("sentiment_score", "0")
        truncated = _truncate_text(doc["text"])
        context_parts.append(
            f"[{i}] {pub_date} | {sentiment}({score}) | {truncated}"
        )

    context_text = "\n".join(context_parts) if context_parts else "No recent news."

    indicators_text = ""
    if current_indicators:
        items = [f"{k}:{v}" for k, v in current_indicators.items()]
        indicators_text = "\nIndicators: " + ", ".join(items)

    prompt = f"""Analyze {symbol} stock. Answer in JSON only. No markdown, no explanation.

News:
{context_text}
{indicators_text}

Respond with ONLY this JSON:
{{"sentiment_score": 0.0, "confidence": 0.0, "key_issues": [], "is_priced_in": false, "outlook": "neutral", "rationale": ""}}

Fill in the values based on the news above."""

    return prompt


async def search_and_build_prompt(
    symbol: str,
    question: Optional[str] = None,
    current_indicators: Optional[dict] = None,
) -> str:
    """유사 뉴스 검색 + 프롬프트 조립을 한 번에 수행한다."""
    if question is None:
        question = f"{symbol} outlook"

    # Get search method from settings
    search_method = await _get_rag_search_method()
    query = f"{symbol} stock news"

    # Branch based on search method
    if search_method == "gemini":
        logger.info("Using Gemini search method")
        context_docs = await search_gemini_news(query, symbol)
    elif search_method == "hybrid":
        logger.info("Using hybrid search method")
        context_docs = await hybrid_search(query, symbol)
        # Clean text for hybrid results (if not already cleaned)
        for doc in context_docs:
            doc["text"] = _clean_text(doc["text"])
    else:  # Default to "bge"
        logger.info("Using BGE search method")
        context_docs = await search_similar_news(query, symbol)

    prompt = build_rag_prompt(symbol, question, context_docs, current_indicators)
    return prompt


async def _get_rag_search_method() -> str:
    """
    Get the RAG search method from settings table.
    Returns "bge" (default), "gemini", or "hybrid".
    """
    try:
        row = await fetch_one(
            "SELECT value FROM settings WHERE key = 'rag_search_method'"
        )
        if row:
            method = row["value"].lower()
            if method in ("bge", "gemini", "hybrid"):
                return method
        return "bge"  # Default
    except Exception as e:
        logger.warning("Failed to fetch rag_search_method from settings: %s", e)
        return "bge"  # Default on error
