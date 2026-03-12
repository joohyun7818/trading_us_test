# ChromaDB "stock_news" 컬렉션 similarity search, 프롬프트 조립
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from api.services.news_indexer import get_collection
from api.services.ollama_client import embed

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 15
DEFAULT_DAYS = 7


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
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        where_filter = {
            "$and": [
                {"stock_symbol": {"$eq": symbol}},
                {"published_at": {"$gte": cutoff}},
            ]
        }

    try:
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:
        logger.error("ChromaDB query failed: %s", e)
        if where_filter and symbol:
            try:
                results = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=top_k,
                    where={"stock_symbol": {"$eq": symbol}},
                    include=["documents", "metadatas", "distances"],
                )
            except Exception as e2:
                logger.error("ChromaDB fallback query failed: %s", e2)
                return []
        else:
            return []

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    output = []
    for doc, meta, dist in zip(docs, metas, dists):
        output.append({
            "text": doc,
            "metadata": meta,
            "similarity": round(1 - dist, 4) if dist is not None else 0,
        })

    return output


def build_rag_prompt(
    symbol: str,
    question: str,
    context_docs: list[dict],
    current_indicators: Optional[dict] = None,
) -> str:
    """RAG 분석용 프롬프트를 조립한다."""
    context_parts = []
    for i, doc in enumerate(context_docs, 1):
        meta = doc.get("metadata", {})
        pub_date = meta.get("published_at", "unknown")
        sentiment = meta.get("sentiment_label", "neutral")
        score = meta.get("sentiment_score", "0")
        context_parts.append(
            f"[{i}] Date: {pub_date} | Sentiment: {sentiment} ({score})\n{doc['text']}"
        )

    context_text = "\n\n".join(context_parts) if context_parts else "No recent news context available."

    indicators_text = ""
    if current_indicators:
        indicator_lines = []
        for key, val in current_indicators.items():
            indicator_lines.append(f"  {key}: {val}")
        indicators_text = "\nCurrent Technical Indicators:\n" + "\n".join(indicator_lines)

    prompt = f"""You are an expert financial analyst. Analyze the stock {symbol} based on recent news and data.

Question: {question}

Recent News Context (sorted by relevance):
{context_text}
{indicators_text}

Provide your analysis in the following JSON format:
{{
  "sentiment_score": <float -1.0 to 1.0>,
  "confidence": <float 0.0 to 1.0>,
  "key_issues": [<list of key issues/themes>],
  "is_priced_in": <boolean>,
  "outlook": "<bullish|bearish|neutral>",
  "rationale": "<detailed explanation in 2-3 sentences>"
}}

Respond ONLY with valid JSON, no markdown or explanation."""

    return prompt


async def search_and_build_prompt(
    symbol: str,
    question: Optional[str] = None,
    current_indicators: Optional[dict] = None,
) -> str:
    """유사 뉴스 검색 + 프롬프트 조립을 한 번에 수행한다."""
    if question is None:
        question = f"What is the current outlook for {symbol}? Analyze recent news sentiment and key factors."

    context_docs = await search_similar_news(
        query=f"{symbol} stock news analysis outlook",
        symbol=symbol,
    )

    prompt = build_rag_prompt(symbol, question, context_docs, current_indicators)
    return prompt
