# 파일: api/services/gemini_indexer.py
"""Gemini Embedding API로 뉴스 기사를 임베딩하고 ChromaDB에 upsert한다."""
import asyncio
import logging
from typing import Optional

import chromadb

from api.core.database import execute, fetch_all, fetch_one
from api.services.gemini_client import gemini_embed

logger = logging.getLogger(__name__)

COLLECTION_NAME = "stock_news_gemini"
BATCH_SIZE = 10

_chroma_client: Optional[chromadb.ClientAPI] = None
_collection: Optional[chromadb.Collection] = None


def get_chroma_client() -> chromadb.ClientAPI:
    """ChromaDB persistent 클라이언트를 반환한다."""
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path="./chroma_data")
    return _chroma_client


def get_gemini_collection() -> chromadb.Collection:
    """Gemini 임베딩용 ChromaDB 컬렉션을 반환한다."""
    global _collection
    if _collection is None:
        client = get_chroma_client()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("ChromaDB collection '%s' ready", COLLECTION_NAME)
    return _collection


async def index_with_gemini() -> dict:
    """gemini_embedded=FALSE인 기사를 Gemini 임베딩 → ChromaDB upsert."""
    enabled_row = await fetch_one(
        "SELECT value FROM settings WHERE key = 'gemini_embed_enabled'"
    )
    if not enabled_row or enabled_row["value"].lower() != "true":
        return {"status": "disabled", "indexed": 0}

    collection = get_gemini_collection()
    total_indexed = 0
    total_errors = 0

    while True:
        # full_text 우선, 없으면 title+body 사용
        articles = await fetch_all(
            """
            SELECT id, stock_symbol, title, body, full_text,
                   published_at, sentiment_score, sentiment_label
            FROM news_articles
            WHERE gemini_embedded = FALSE
            ORDER BY published_at DESC
            LIMIT $1
            """,
            BATCH_SIZE,
        )

        if not articles:
            break

        for article in articles:
            try:
                # 임베딩할 텍스트 선택: full_text > title+body
                full_text = article.get("full_text") or ""
                title = article.get("title") or ""
                body = article.get("body") or ""

                if full_text and len(full_text) > 100:
                    embed_text = f"{title}\n\n{full_text}"
                else:
                    embed_text = f"{title} {body}".strip()

                if not embed_text or len(embed_text) < 10:
                    await execute(
                        "UPDATE news_articles SET gemini_embedded = TRUE WHERE id = $1",
                        article["id"],
                    )
                    continue

                embedding = await gemini_embed(
                    text=embed_text,
                    task_type="RETRIEVAL_DOCUMENT",
                )

                if not embedding:
                    total_errors += 1
                    continue

                doc_id = f"gemini_article_{article['id']}"
                pub_at = article.get("published_at")
                pub_str = pub_at.isoformat() if pub_at else ""

                collection.upsert(
                    ids=[doc_id],
                    embeddings=[embedding],
                    documents=[embed_text[:2000]],  # ChromaDB 저장용 축약
                    metadatas=[{
                        "article_id": str(article["id"]),
                        "stock_symbol": article["stock_symbol"],
                        "published_at": pub_str,
                        "sentiment_score": str(article.get("sentiment_score", 0)),
                        "sentiment_label": article.get("sentiment_label", "neutral"),
                        "has_fulltext": str(bool(full_text and len(full_text) > 100)),
                    }],
                )

                await execute(
                    """
                    UPDATE news_articles
                    SET gemini_embedded = TRUE,
                        embedding_model = 'gemini-embedding-001',
                        embedding_dim = $1
                    WHERE id = $2
                    """,
                    len(embedding), article["id"],
                )
                total_indexed += 1

                # RPM 제한 대비 (무료: ~15 RPM, 안전하게 5초 대기)
                await asyncio.sleep(5.0)

            except Exception as e:
                logger.error("Gemini indexing failed for article %d: %s", article["id"], e)
                total_errors += 1

        logger.info("Gemini indexing batch: %d indexed so far", total_indexed)

    logger.info("Gemini indexing complete: %d indexed, %d errors", total_indexed, total_errors)
    return {"status": "ok", "indexed": total_indexed, "errors": total_errors}


async def search_gemini_news(
    query: str,
    symbol: Optional[str] = None,
    top_k: int = 5,
) -> list[dict]:
    """Gemini 임베딩으로 유사 뉴스를 검색한다."""
    query_embedding = await gemini_embed(
        text=query,
        task_type="RETRIEVAL_QUERY",
    )
    if not query_embedding:
        return []

    collection = get_gemini_collection()
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
        logger.error("Gemini ChromaDB query failed: %s", e)
        return []

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    return [
        {
            "text": doc,
            "metadata": meta,
            "similarity": round(1 - dist, 4) if dist is not None else 0,
        }
        for doc, meta, dist in zip(docs, metas, dists)
    ]
