# 2년치 과거 뉴스 백필, backfill_progress 체크포인트, 중단/재시작 지원
import hashlib
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiohttp
import feedparser
import finnhub

from api.core.config import settings
from api.core.database import execute, fetch_all, fetch_one
from api.services.sentiment import analyze_sentiment_keywords

logger = logging.getLogger(__name__)

_backfill_running = False


def is_backfill_running() -> bool:
    """백필 작업이 실행 중인지 확인한다."""
    return _backfill_running


def _url_hash(url: str) -> str:
    """URL의 SHA-256 해시를 반환한다."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


async def _ensure_progress(symbol: str, source: str) -> dict:
    """backfill_progress 레코드를 조회하거나 생성한다."""
    row = await fetch_one(
        "SELECT * FROM backfill_progress WHERE stock_symbol = $1 AND source = $2",
        symbol, source,
    )
    if row:
        return dict(row)
    await execute(
        """
        INSERT INTO backfill_progress (stock_symbol, source, status)
        VALUES ($1, $2, 'pending')
        ON CONFLICT (stock_symbol, source) DO NOTHING
        """,
        symbol, source,
    )
    row = await fetch_one(
        "SELECT * FROM backfill_progress WHERE stock_symbol = $1 AND source = $2",
        symbol, source,
    )
    return dict(row)


async def _update_progress(
    symbol: str,
    source: str,
    status: str,
    last_page: int = 0,
    last_date: Optional[datetime] = None,
    article_count: int = 0,
    error_message: Optional[str] = None,
) -> None:
    """backfill_progress를 업데이트한다."""
    await execute(
        """
        UPDATE backfill_progress
        SET status = $1, last_page = $2, last_date = $3,
            article_count = article_count + $4,
            error_message = $5, updated_at = NOW()
        WHERE stock_symbol = $6 AND source = $7
        """,
        status, last_page, last_date, article_count, error_message, symbol, source,
    )


async def _backfill_finnhub_symbol(symbol: str, years: int, batch_id: str) -> int:
    """Finnhub에서 특정 종목의 과거 뉴스를 백필한다."""
    if not settings.FINNHUB_API_KEY:
        return 0

    progress = await _ensure_progress(symbol, "finnhub")
    if progress.get("status") == "completed":
        return 0

    client = finnhub.Client(api_key=settings.FINNHUB_API_KEY)
    count = 0
    now = datetime.now(timezone.utc)
    end_date = now
    start_date = now - timedelta(days=years * 365)

    if progress.get("last_date"):
        end_date = datetime.combine(progress["last_date"], datetime.min.time()).replace(tzinfo=timezone.utc)

    await _update_progress(symbol, "finnhub", "running")

    chunk_days = 30
    current_end = end_date
    while current_end > start_date:
        current_start = max(current_end - timedelta(days=chunk_days), start_date)
        try:
            news_list = client.company_news(
                symbol,
                _from=current_start.strftime("%Y-%m-%d"),
                to=current_end.strftime("%Y-%m-%d"),
            )
            for item in (news_list or []):
                url = item.get("url", "")
                uh = _url_hash(url)
                dup = await fetch_one("SELECT id FROM news_articles WHERE url_hash = $1", uh)
                if dup:
                    continue
                pub_at = datetime.fromtimestamp(item.get("datetime", 0), tz=timezone.utc)
                text = f"{item.get('headline', '')} {item.get('summary', '')}"
                sentiment = analyze_sentiment_keywords(text)
                await execute(
                    """
                    INSERT INTO news_articles
                        (stock_symbol, title, body, source, url, url_hash,
                         published_at, sentiment_score, sentiment_label,
                         is_priced_in, crawl_source, backfill_batch_id)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                    ON CONFLICT (url_hash) DO NOTHING
                    """,
                    symbol, item.get("headline", ""), item.get("summary", ""),
                    item.get("source", "finnhub"), url, uh, pub_at,
                    sentiment["score"], sentiment["label"],
                    sentiment["is_priced_in"], "finnhub_backfill", batch_id,
                )
                count += 1

            await _update_progress(
                symbol, "finnhub", "running",
                last_date=current_start.date(),
                article_count=count,
            )
        except Exception as e:
            logger.error("Backfill Finnhub %s chunk error: %s", symbol, e)
            await _update_progress(symbol, "finnhub", "error", error_message=str(e))

        current_end = current_start
        await _rate_limit_delay()

    await _update_progress(symbol, "finnhub", "completed", article_count=0)
    return count


async def _rate_limit_delay() -> None:
    """API 레이트 리밋을 위한 딜레이."""
    import asyncio
    await asyncio.sleep(0.5)


async def backfill_all(symbols: Optional[list[str]] = None) -> dict:
    """전 종목 과거 뉴스를 백필한다."""
    global _backfill_running
    if _backfill_running:
        return {"status": "already_running"}

    _backfill_running = True
    try:
        if symbols is None:
            rows = await fetch_all("SELECT symbol FROM stocks WHERE is_sp500 = TRUE ORDER BY symbol")
            symbols = [r["symbol"] for r in rows]

        row = await fetch_one("SELECT value FROM settings WHERE key = 'backfill_years'")
        years = int(row["value"]) if row else 2

        batch_id = f"backfill_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        total_articles = 0
        start_time = time.time()

        for symbol in symbols:
            try:
                count = await _backfill_finnhub_symbol(symbol, years, batch_id)
                total_articles += count
            except Exception as e:
                logger.error("Backfill failed for %s: %s", symbol, e)

        duration = round(time.time() - start_time, 2)
        logger.info("Backfill complete: %d articles in %.1fs", total_articles, duration)

        return {
            "status": "completed",
            "batch_id": batch_id,
            "total_articles": total_articles,
            "symbols_processed": len(symbols),
            "duration_sec": duration,
        }
    finally:
        _backfill_running = False


async def get_backfill_status() -> list[dict]:
    """백필 진행 상황을 조회한다."""
    rows = await fetch_all(
        """
        SELECT stock_symbol, source, last_page, last_date, article_count,
               status, error_message, updated_at
        FROM backfill_progress
        ORDER BY stock_symbol, source
        """
    )
    return rows
