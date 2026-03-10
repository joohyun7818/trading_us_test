# 10분 라운드로빈 뉴스 수집기 - Finnhub, Yahoo RSS, Google News RSS
import hashlib
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import aiohttp
import feedparser
import finnhub

from api.core.config import settings
from api.core.database import execute, fetch_all, fetch_one
from api.services.sentiment import analyze_sentiment_keywords

logger = logging.getLogger(__name__)

_round_robin_offset = 0


def _url_hash(url: str) -> str:
    """URL의 SHA-256 해시를 반환한다."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


async def _is_duplicate(url_hash: str) -> bool:
    """URL 해시로 중복 여부를 확인한다."""
    row = await fetch_one("SELECT id FROM news_articles WHERE url_hash = $1", url_hash)
    return row is not None


async def _insert_article(
    symbol: str,
    title: str,
    body: Optional[str],
    source: str,
    url: str,
    published_at: Optional[datetime],
    crawl_source: str,
    batch_id: Optional[str] = None,
) -> bool:
    """뉴스 기사를 삽입하고 1차 감성 분석을 수행한다."""
    uh = _url_hash(url)
    if await _is_duplicate(uh):
        return False

    text_for_analysis = f"{title} {body}" if body else title
    sentiment = analyze_sentiment_keywords(text_for_analysis)

    try:
        await execute(
            """
            INSERT INTO news_articles
                (stock_symbol, title, body, source, url, url_hash,
                 published_at, sentiment_score, sentiment_label,
                 is_priced_in, crawl_source, backfill_batch_id)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
            ON CONFLICT (url_hash) DO NOTHING
            """,
            symbol, title, body, source, url, uh,
            published_at,
            sentiment["score"],
            sentiment["label"],
            sentiment["is_priced_in"],
            crawl_source,
            batch_id,
        )
        return True
    except Exception as e:
        logger.error("Insert article failed: %s", e)
        return False


async def _crawl_finnhub(symbols: list[str], batch_id: str) -> int:
    """Finnhub News API로 뉴스를 수집한다."""
    if not settings.FINNHUB_API_KEY:
        logger.warning("Finnhub API key not configured")
        return 0

    count = 0
    client = finnhub.Client(api_key=settings.FINNHUB_API_KEY)

    for symbol in symbols:
        try:
            news_list = client.company_news(
                symbol,
                _from=(datetime.now(timezone.utc).strftime("%Y-%m-%d")),
                to=(datetime.now(timezone.utc).strftime("%Y-%m-%d")),
            )
            for item in (news_list or [])[:10]:
                pub_at = datetime.fromtimestamp(item.get("datetime", 0), tz=timezone.utc)
                inserted = await _insert_article(
                    symbol=symbol,
                    title=item.get("headline", ""),
                    body=item.get("summary", ""),
                    source=item.get("source", "finnhub"),
                    url=item.get("url", ""),
                    published_at=pub_at,
                    crawl_source="finnhub",
                    batch_id=batch_id,
                )
                if inserted:
                    count += 1
        except Exception as e:
            logger.error("Finnhub crawl failed for %s: %s", symbol, e)

    return count


async def _crawl_yahoo_rss(symbols: list[str], batch_id: str) -> int:
    """Yahoo Finance RSS로 뉴스를 수집한다."""
    count = 0
    for symbol in symbols:
        try:
            url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        continue
                    text = await resp.text()
            feed = feedparser.parse(text)
            for entry in feed.entries[:10]:
                pub_at = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                inserted = await _insert_article(
                    symbol=symbol,
                    title=entry.get("title", ""),
                    body=entry.get("summary", ""),
                    source="yahoo_rss",
                    url=entry.get("link", ""),
                    published_at=pub_at,
                    crawl_source="yahoo_rss",
                    batch_id=batch_id,
                )
                if inserted:
                    count += 1
        except Exception as e:
            logger.error("Yahoo RSS failed for %s: %s", symbol, e)

    return count


async def _crawl_google_rss(symbols: list[str], batch_id: str) -> int:
    """Google News RSS로 뉴스를 수집한다."""
    count = 0
    for symbol in symbols:
        try:
            url = f"https://news.google.com/rss/search?q={symbol}+stock&hl=en-US&gl=US&ceid=US:en"
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        continue
                    text = await resp.text()
            feed = feedparser.parse(text)
            for entry in feed.entries[:10]:
                pub_at = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                inserted = await _insert_article(
                    symbol=symbol,
                    title=entry.get("title", ""),
                    body=entry.get("summary", ""),
                    source="google_news",
                    url=entry.get("link", ""),
                    published_at=pub_at,
                    crawl_source="google_rss",
                    batch_id=batch_id,
                )
                if inserted:
                    count += 1
        except Exception as e:
            logger.error("Google RSS failed for %s: %s", symbol, e)

    return count


async def crawl_news_round_robin() -> dict:
    """라운드로빈 방식으로 뉴스를 수집한다. 10분마다 50종목씩 순환."""
    global _round_robin_offset

    row = await fetch_one("SELECT value FROM settings WHERE key = 'news_round_robin_size'")
    batch_size = int(row["value"]) if row else 50

    all_symbols = await fetch_all(
        "SELECT symbol FROM stocks WHERE is_sp500 = TRUE ORDER BY symbol"
    )
    symbols = [r["symbol"] for r in all_symbols]
    if not symbols:
        return {"status": "ok", "articles": 0, "message": "No symbols"}

    start_idx = _round_robin_offset % len(symbols)
    batch_symbols = []
    for i in range(batch_size):
        idx = (start_idx + i) % len(symbols)
        batch_symbols.append(symbols[idx])
    _round_robin_offset = (start_idx + batch_size) % len(symbols)

    batch_id = f"news_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    start_time = time.time()

    finnhub_count = await _crawl_finnhub(batch_symbols, batch_id)
    yahoo_count = await _crawl_yahoo_rss(batch_symbols, batch_id)
    google_count = await _crawl_google_rss(batch_symbols, batch_id)
    total_count = finnhub_count + yahoo_count + google_count
    duration = round(time.time() - start_time, 2)

    try:
        await execute(
            """
            INSERT INTO news_collection_logs (batch_id, stock_count, article_count, source, duration_sec, status)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            batch_id, len(batch_symbols), total_count, "all", duration, "completed",
        )
    except Exception as e:
        logger.error("Log insert failed: %s", e)

    logger.info(
        "News round-robin batch=%s: finnhub=%d yahoo=%d google=%d total=%d duration=%.1fs",
        batch_id, finnhub_count, yahoo_count, google_count, total_count, duration,
    )
    return {
        "status": "ok",
        "batch_id": batch_id,
        "stock_count": len(batch_symbols),
        "articles": total_count,
        "finnhub": finnhub_count,
        "yahoo": yahoo_count,
        "google": google_count,
        "duration_sec": duration,
    }
