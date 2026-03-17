# 파일: api/services/fulltext_crawler.py
"""뉴스 기사 원문을 크롤링하여 full_text 컬럼에 저장한다."""
import asyncio
import logging
import re
import time
from typing import Optional

import aiohttp

from api.core.database import execute, fetch_all, fetch_one

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<script[^>]*>.*?</script>", re.DOTALL | re.IGNORECASE)
_STYLE_RE = re.compile(r"<style[^>]*>.*?</style>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_MULTI_SPACE_RE = re.compile(r"\s+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def _extract_article_text(html: str) -> str:
    """HTML에서 기사 본문 텍스트를 추출한다 (경량 파서)."""
    if not html:
        return ""
    # script, style 제거
    text = _HTML_TAG_RE.sub("", html)
    text = _STYLE_RE.sub("", text)

    # <p>, <article>, <div> 기반 본문 추출 시도
    # 간단한 접근: <p> 태그 내용만 추출
    paragraphs = re.findall(
        r"<(?:p|article)[^>]*>(.*?)</(?:p|article)>",
        text,
        re.DOTALL | re.IGNORECASE,
    )

    if paragraphs:
        text = "\n".join(paragraphs)

    # 모든 HTML 태그 제거
    text = _TAG_RE.sub(" ", text)
    text = _MULTI_SPACE_RE.sub(" ", text)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


async def _crawl_single_article(
    session: aiohttp.ClientSession,
    article_id: int,
    url: str,
    max_length: int,
) -> Optional[str]:
    """단일 기사 URL을 크롤링하여 본문을 반환한다."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with session.get(url, headers=headers, allow_redirects=True) as resp:
            if resp.status != 200:
                logger.debug("Article %d: HTTP %d for %s", article_id, resp.status, url[:80])
                return None
            content_type = resp.headers.get("Content-Type", "")
            if "text/html" not in content_type:
                return None
            html = await resp.text(errors="replace")

        text = _extract_article_text(html)
        if len(text) < 100:
            # 너무 짧으면 본문 추출 실패로 판단
            return None
        return text[:max_length]

    except asyncio.TimeoutError:
        logger.debug("Article %d: timeout for %s", article_id, url[:80])
        return None
    except Exception as e:
        logger.debug("Article %d: crawl error: %s", article_id, str(e)[:100])
        return None


async def crawl_fulltext_batch() -> dict:
    """full_text_crawled=FALSE인 기사의 원문을 배치 크롤링한다."""
    batch_size_row = await fetch_one(
        "SELECT value FROM settings WHERE key = 'fulltext_crawl_batch_size'"
    )
    batch_size = int(batch_size_row["value"]) if batch_size_row else 20

    max_len_row = await fetch_one(
        "SELECT value FROM settings WHERE key = 'fulltext_max_length'"
    )
    max_length = int(max_len_row["value"]) if max_len_row else 10000

    articles = await fetch_all(
        """
        SELECT id, url FROM news_articles
        WHERE full_text_crawled = FALSE
          AND url IS NOT NULL AND url != ''
        ORDER BY published_at DESC
        LIMIT $1
        """,
        batch_size,
    )

    if not articles:
        return {"status": "ok", "crawled": 0, "success": 0, "failed": 0}

    start_time = time.time()
    success = 0
    failed = 0

    timeout = aiohttp.ClientTimeout(total=15, connect=5)
    connector = aiohttp.TCPConnector(limit=5, ssl=False)

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        for article in articles:
            article_id = article["id"]
            url = article["url"]

            full_text = await _crawl_single_article(session, article_id, url, max_length)

            if full_text:
                await execute(
                    """
                    UPDATE news_articles
                    SET full_text = $1,
                        full_text_crawled = TRUE,
                        full_text_length = $2
                    WHERE id = $3
                    """,
                    full_text, len(full_text), article_id,
                )
                success += 1
            else:
                # 크롤링 실패해도 재시도 방지를 위해 마킹
                await execute(
                    "UPDATE news_articles SET full_text_crawled = TRUE WHERE id = $1",
                    article_id,
                )
                failed += 1

            # rate limiting: 0.5초 간격
            await asyncio.sleep(0.5)

    duration = round(time.time() - start_time, 2)
    logger.info(
        "Fulltext crawl: %d success, %d failed in %.1fs",
        success, failed, duration,
    )
    return {
        "status": "ok",
        "crawled": len(articles),
        "success": success,
        "failed": failed,
        "duration_sec": duration,
    }
