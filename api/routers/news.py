# GET news/{symbol}, sentiment, trigger, status, backfill 뉴스 라우터
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Query

from api.core.database import fetch_all, fetch_one
from api.services.backfill_crawler import backfill_all, get_backfill_status, is_backfill_running
from api.services.news_crawler import crawl_news_round_robin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("/sentiment/overview")
async def get_sentiment_overview() -> dict:
    """전체 감성 분석 요약을 반환한다."""
    total = await fetch_one("SELECT COUNT(*) as cnt FROM news_articles")
    positive = await fetch_one(
        "SELECT COUNT(*) as cnt FROM news_articles WHERE sentiment_label = 'positive'"
    )
    negative = await fetch_one(
        "SELECT COUNT(*) as cnt FROM news_articles WHERE sentiment_label = 'negative'"
    )
    neutral = await fetch_one(
        "SELECT COUNT(*) as cnt FROM news_articles WHERE sentiment_label = 'neutral'"
    )
    avg_score = await fetch_one(
        "SELECT ROUND(AVG(sentiment_score)::numeric, 4) as avg FROM news_articles WHERE sentiment_score IS NOT NULL"
    )
    recent_avg = await fetch_one(
        """
        SELECT ROUND(AVG(sentiment_score)::numeric, 4) as avg
        FROM news_articles
        WHERE sentiment_score IS NOT NULL
          AND published_at > NOW() - INTERVAL '24 hours'
        """
    )

    return {
        "total_articles": total["cnt"] if total else 0,
        "positive": positive["cnt"] if positive else 0,
        "negative": negative["cnt"] if negative else 0,
        "neutral": neutral["cnt"] if neutral else 0,
        "avg_sentiment": float(avg_score["avg"]) if avg_score and avg_score["avg"] else 0,
        "recent_24h_avg": float(recent_avg["avg"]) if recent_avg and recent_avg["avg"] else 0,
    }


@router.post("/trigger")
async def trigger_news_crawl() -> dict:
    """수동 뉴스 수집을 트리거한다."""
    result = await crawl_news_round_robin()
    return result


@router.get("/status/collection")
async def get_collection_status(
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict]:
    """뉴스 수집 로그를 반환한다."""
    rows = await fetch_all(
        """
        SELECT batch_id, stock_count, article_count, source,
               duration_sec, status, error_message, created_at
        FROM news_collection_logs
        ORDER BY created_at DESC
        LIMIT $1
        """,
        limit,
    )
    return rows


@router.post("/backfill/start")
async def start_backfill(background_tasks: BackgroundTasks) -> dict:
    """과거 뉴스 백필을 시작한다."""
    if is_backfill_running():
        return {"status": "already_running"}
    background_tasks.add_task(backfill_all)
    return {"status": "started"}


@router.get("/backfill/status")
async def get_backfill_progress() -> dict:
    """백필 진행 상황을 반환한다."""
    progress = await get_backfill_status()
    running = is_backfill_running()
    total = len(progress)
    completed = sum(1 for p in progress if p.get("status") == "completed")
    errors = sum(1 for p in progress if p.get("status") == "error")

    return {
        "is_running": running,
        "total": total,
        "completed": completed,
        "errors": errors,
        "progress": progress,
    }


@router.get("/{symbol}")
async def get_news_by_symbol(
    symbol: str,
    limit: int = Query(default=50, ge=1, le=200),
    days: int = Query(default=7, ge=1, le=90),
) -> list[dict]:
    """종목별 뉴스 기사를 반환한다."""
    rows = await fetch_all(
        """
        SELECT id, stock_symbol, title, body, source, url,
               published_at, crawled_at, sentiment_score, sentiment_label,
               is_priced_in, crawl_source
        FROM news_articles
        WHERE stock_symbol = $1
          AND published_at > NOW() - ($2 || ' days')::INTERVAL
        ORDER BY published_at DESC
        LIMIT $3
        """,
        symbol, str(days), limit,
    )
    return rows


@router.post("/fulltext-crawl")
async def trigger_fulltext_crawl() -> dict:
    """기사 원문(full_text) 크롤링을 수동 실행한다."""
    from api.services.fulltext_crawler import crawl_fulltext_batch
    result = await crawl_fulltext_batch()
    return result


@router.post("/gemini-index")
async def trigger_gemini_index() -> dict:
    """Gemini 임베딩 인덱싱을 수동 실행한다."""
    from api.services.gemini_indexer import index_with_gemini
    result = await index_with_gemini()
    return result


@router.get("/fulltext/status")
async def get_fulltext_status() -> dict:
    """Full-text 크롤링 및 Gemini 임베딩 현황을 반환한다."""
    total = await fetch_one("SELECT COUNT(*) as cnt FROM news_articles")
    crawled = await fetch_one(
        "SELECT COUNT(*) as cnt FROM news_articles WHERE full_text_crawled = TRUE"
    )
    has_fulltext = await fetch_one(
        "SELECT COUNT(*) as cnt FROM news_articles WHERE full_text IS NOT NULL"
    )
    gemini_embedded = await fetch_one(
        "SELECT COUNT(*) as cnt FROM news_articles WHERE gemini_embedded = TRUE"
    )
    return {
        "total_articles": total["cnt"] if total else 0,
        "fulltext_crawled": crawled["cnt"] if crawled else 0,
        "has_fulltext": has_fulltext["cnt"] if has_fulltext else 0,
        "gemini_embedded": gemini_embedded["cnt"] if gemini_embedded else 0,
    }
