# api/services/hybrid_search.py
"""Hybrid search combining BGE-M3 (Ollama) and Gemini embeddings with Reciprocal Rank Fusion."""
import logging
from typing import Optional

from api.services.news_indexer import get_collection
from api.services.gemini_indexer import get_gemini_collection, search_gemini_news
from api.services.ollama_client import embed

logger = logging.getLogger(__name__)


async def hybrid_search(
    query: str,
    symbol: Optional[str] = None,
    top_k: int = 5,
) -> list[dict]:
    """
    Hybrid search combining BGE-M3 and Gemini embeddings using Reciprocal Rank Fusion.

    Args:
        query: Search query text
        symbol: Optional stock symbol filter
        top_k: Number of final results to return

    Returns:
        List of documents with rrf_score, sorted by score descending.
        Each result contains: {id, text, metadata, rrf_score, source}

    Algorithm:
        1. Query both collections with top_k * 2 results each
        2. Apply RRF: score(doc) = Σ 1/(60 + rank_i) for each source
        3. Sort by rrf_score descending and return top_k

    Graceful Fallback:
        - If one collection is empty or embedding fails, use the other collection only
        - If both fail, return empty list
    """
    # Fetch results from both sources
    bge_results = await _search_bge_collection(query, symbol, top_k * 2)
    gemini_results = await _search_gemini_collection(query, symbol, top_k * 2)

    # Handle graceful fallback
    if not bge_results and not gemini_results:
        logger.warning("Both BGE and Gemini searches returned no results")
        return []

    if not bge_results:
        logger.info("BGE search returned no results, using Gemini only")
        return _format_single_source_results(gemini_results, "gemini", top_k)

    if not gemini_results:
        logger.info("Gemini search returned no results, using BGE only")
        return _format_single_source_results(bge_results, "bge", top_k)

    # Apply Reciprocal Rank Fusion
    rrf_results = _apply_rrf(bge_results, gemini_results)

    # Sort by rrf_score descending and take top_k
    rrf_results.sort(key=lambda x: x["rrf_score"], reverse=True)

    logger.info(
        "Hybrid search: %d BGE results, %d Gemini results -> %d RRF results",
        len(bge_results), len(gemini_results), len(rrf_results[:top_k])
    )

    return rrf_results[:top_k]


async def _search_bge_collection(
    query: str,
    symbol: Optional[str],
    n_results: int,
) -> list[dict]:
    """Search the BGE-M3 (Ollama) collection."""
    try:
        query_embedding = await embed(query)
        if not query_embedding:
            logger.warning("Empty embedding from Ollama for query")
            return []

        collection = get_collection()

        where_filter = None
        if symbol:
            where_filter = {"stock_symbol": {"$eq": symbol}}

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]

        output = []
        for doc, meta, dist in zip(docs, metas, dists):
            # Use article_id as the unique identifier for deduplication
            article_id = meta.get("article_id", "")
            if not article_id:
                continue

            output.append({
                "id": article_id,
                "text": doc,
                "metadata": meta,
                "similarity": round(1 - dist, 4) if dist is not None else 0,
                "source": "bge",
            })

        return output

    except Exception as e:
        logger.error("BGE collection search failed: %s", e)
        return []


async def _search_gemini_collection(
    query: str,
    symbol: Optional[str],
    n_results: int,
) -> list[dict]:
    """Search the Gemini embeddings collection."""
    try:
        # Reuse existing search_gemini_news function
        results = await search_gemini_news(query, symbol, n_results)

        # Add source field and extract article_id as id
        for result in results:
            result["source"] = "gemini"
            article_id = result.get("metadata", {}).get("article_id", "")
            result["id"] = article_id

        return results

    except Exception as e:
        logger.error("Gemini collection search failed: %s", e)
        return []


def _apply_rrf(bge_results: list[dict], gemini_results: list[dict]) -> list[dict]:
    """
    Apply Reciprocal Rank Fusion to combine results from both sources.

    RRF formula: score(doc) = Σ 1/(k + rank_i)
    where k = 60 (standard constant) and rank_i is the rank in source i (1-indexed)
    """
    K = 60
    doc_scores = {}  # article_id -> {"score": float, "sources": list, "docs": list}

    # Process BGE results
    for rank, result in enumerate(bge_results, start=1):
        article_id = result["id"]
        if not article_id:
            continue

        rrf_contribution = 1.0 / (K + rank)

        if article_id not in doc_scores:
            doc_scores[article_id] = {
                "score": 0.0,
                "sources": [],
                "docs": [],
            }

        doc_scores[article_id]["score"] += rrf_contribution
        doc_scores[article_id]["sources"].append("bge")
        doc_scores[article_id]["docs"].append(result)

    # Process Gemini results
    for rank, result in enumerate(gemini_results, start=1):
        article_id = result["id"]
        if not article_id:
            continue

        rrf_contribution = 1.0 / (K + rank)

        if article_id not in doc_scores:
            doc_scores[article_id] = {
                "score": 0.0,
                "sources": [],
                "docs": [],
            }

        doc_scores[article_id]["score"] += rrf_contribution
        doc_scores[article_id]["sources"].append("gemini")
        doc_scores[article_id]["docs"].append(result)

    # Build final output
    output = []
    for article_id, data in doc_scores.items():
        # Prefer the first document's data (arbitrary choice, could be improved)
        doc = data["docs"][0]

        output.append({
            "id": article_id,
            "text": doc["text"],
            "metadata": doc["metadata"],
            "rrf_score": round(data["score"], 6),
            "source": "+".join(sorted(set(data["sources"]))),  # e.g., "bge+gemini"
        })

    return output


def _format_single_source_results(
    results: list[dict],
    source: str,
    top_k: int,
) -> list[dict]:
    """
    Format results from a single source to match hybrid search output format.
    Add rrf_score field based on similarity score.
    """
    output = []
    for result in results[:top_k]:
        # Convert similarity to rrf_score (use similarity as a proxy)
        similarity = result.get("similarity", 0)
        rrf_score = similarity / 10.0  # Scale down to match RRF range

        output.append({
            "id": result.get("id", ""),
            "text": result["text"],
            "metadata": result["metadata"],
            "rrf_score": round(rrf_score, 6),
            "source": source,
        })

    return output
