# 뉴스 → 청킹 → bge-m3 임베딩 → ChromaDB upsert, embedded=FALSE 기사 처리
import logging
from datetime import datetime, timezone
from typing import Optional

import chromadb

from api.core.database import execute, fetch_all
from api.services.ollama_client import embed

logger = logging.getLogger(__name__)

COLLECTION_NAME = "stock_news"
BATCH_SIZE = 50
CHUNK_MAX_LENGTH = 1000

_chroma_client: Optional[chromadb.ClientAPI] = None
_collection: Optional[chromadb.Collection] = None


def get_chroma_client() -> chromadb.ClientAPI:
    """ChromaDB 클라이언트를 반환한다 (persistent)."""
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path="./chroma_data")
        logger.info("ChromaDB persistent client initialized")
    return _chroma_client


def get_collection() -> chromadb.Collection:
    """stock_news 컬렉션을 반환한다."""
    global _collection
    if _collection is None:
        client = get_chroma_client()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("ChromaDB collection '%s' ready", COLLECTION_NAME)
    return _collection


def _chunk_text(text: str, max_length: int = CHUNK_MAX_LENGTH) -> list[str]:
    """텍스트를 청크로 분할한다."""
    if not text:
        return []
    if len(text) <= max_length:
        return [text]

    chunks = []
    sentences = text.replace("\n", " ").split(". ")
    current_chunk = ""

    for sentence in sentences:
        candidate = f"{current_chunk}. {sentence}" if current_chunk else sentence
        if len(candidate) <= max_length:
            current_chunk = candidate
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks if chunks else [text[:max_length]]


async def index_unembedded_articles() -> dict:
    """embedded=FALSE인 뉴스 기사를 임베딩하여 ChromaDB에 upsert한다."""
    articles = await fetch_all(
        """
        SELECT id, stock_symbol, title, body, published_at, sentiment_score, sentiment_label
        FROM news_articles
        WHERE embedded = FALSE
        ORDER BY id
        LIMIT $1
        """,
        BATCH_SIZE,
    )

    if not articles:
        return {"status": "ok", "indexed": 0}

    collection = get_collection()
    indexed = 0
    errors = 0

    for article in articles:
        try:
            text = f"{article['title']} {article.get('body', '') or ''}"
            chunks = _chunk_text(text)

            for idx, chunk in enumerate(chunks):
                if not chunk.strip():
                    continue

                embedding = await embed(chunk)
                if not embedding:
                    continue

                doc_id = f"article_{article['id']}_chunk_{idx}"
                pub_at = article.get("published_at")
                pub_str = pub_at.isoformat() if pub_at else ""

                collection.upsert(
                    ids=[doc_id],
                    embeddings=[embedding],
                    documents=[chunk],
                    metadatas=[{
                        "article_id": str(article["id"]),
                        "stock_symbol": article["stock_symbol"],
                        "published_at": pub_str,
                        "sentiment_score": str(article.get("sentiment_score", 0)),
                        "sentiment_label": article.get("sentiment_label", "neutral"),
                        "chunk_index": str(idx),
                    }],
                )

            await execute(
                "UPDATE news_articles SET embedded = TRUE WHERE id = $1",
                article["id"],
            )
            indexed += 1

        except Exception as e:
            logger.error("Indexing failed for article %d: %s", article["id"], e)
            errors += 1

    logger.info("News indexing: %d indexed, %d errors", indexed, errors)
    return {"status": "ok", "indexed": indexed, "errors": errors}


async def get_index_status() -> dict:
    """인덱싱 상태를 조회한다."""
    total = await fetch_all("SELECT COUNT(*) as cnt FROM news_articles")
    embedded = await fetch_all("SELECT COUNT(*) as cnt FROM news_articles WHERE embedded = TRUE")
    unembedded = await fetch_all("SELECT COUNT(*) as cnt FROM news_articles WHERE embedded = FALSE")

    collection = get_collection()
    chroma_count = collection.count()

    return {
        "total_articles": total[0]["cnt"] if total else 0,
        "embedded": embedded[0]["cnt"] if embedded else 0,
        "unembedded": unembedded[0]["cnt"] if unembedded else 0,
        "chroma_documents": chroma_count,
    }
