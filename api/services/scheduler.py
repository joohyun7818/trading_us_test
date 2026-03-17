import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="America/New_York")
    return _scheduler


async def _morning_batch() -> None:
    from api.services.batch import run_full_batch
    logger.info("Morning batch started")
    try:
        result = await run_full_batch()
        logger.info("Morning batch completed: %s", result.get("total_duration_sec"))
    except Exception as e:
        logger.error("Morning batch failed: %s", e)


async def _close_batch() -> None:
    from api.services.alpaca_client import get_positions
    from api.core.database import execute
    logger.info("Close batch started")
    try:
        positions = await get_positions()
        for pos in positions:
            await execute(
                """
                INSERT INTO portfolio (stock_symbol, qty, avg_price, current_price,
                                       unrealized_pnl, unrealized_pnl_pct)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (stock_symbol) DO UPDATE SET
                    qty = EXCLUDED.qty,
                    avg_price = EXCLUDED.avg_price,
                    current_price = EXCLUDED.current_price,
                    unrealized_pnl = EXCLUDED.unrealized_pnl,
                    unrealized_pnl_pct = EXCLUDED.unrealized_pnl_pct,
                    updated_at = NOW()
                """,
                pos["symbol"],
                float(pos["qty"]),
                float(pos["avg_entry_price"]),
                float(pos["current_price"]),
                float(pos["unrealized_pl"]),
                float(pos["unrealized_plpc"]),
            )
        logger.info("Close batch: %d positions updated", len(positions))
    except Exception as e:
        logger.error("Close batch failed: %s", e)


async def _news_crawl() -> None:
    from api.services.news_crawler import crawl_news_round_robin
    try:
        result = await crawl_news_round_robin()
        logger.info("News crawl: %d articles", result.get("articles", 0))
    except Exception as e:
        logger.error("News crawl failed: %s", e)


async def _auto_trade() -> None:
    from api.services.auto_trader import auto_trade_loop
    try:
        result = await auto_trade_loop()
        logger.info("Auto-trade: %s", result.get("status"))
    except Exception as e:
        logger.error("Auto-trade failed: %s", e)


async def _macro_check() -> None:
    from api.services.macro_engine import calculate_regime
    from api.services.auto_trader import leveraged_loop
    try:
        regime = await calculate_regime()
        logger.info("Macro: %s (%.4f)", regime.get("regime"), regime.get("regime_score"))
        lev_result = await leveraged_loop()
        logger.info("Leveraged: %s", lev_result.get("status"))
    except Exception as e:
        logger.error("Macro check failed: %s", e)


async def _rag_index() -> None:
    from api.services.news_indexer import index_unembedded_articles
    try:
        result = await index_unembedded_articles()
        logger.info("RAG index: %d indexed", result.get("indexed", 0))
    except Exception as e:
        logger.error("RAG index failed: %s", e)


async def _sp500_weekly() -> None:
    from api.services.sp500_loader import load_sp500
    try:
        result = await load_sp500()
        logger.info("SP500 weekly: %d upserted", result.get("upserted", 0))
    except Exception as e:
        logger.error("SP500 weekly failed: %s", e)


# ── 신규 작업 3개 ──

async def _fulltext_crawl() -> None:
    """30분 주기: 기사 원문 크롤링."""
    from api.services.fulltext_crawler import crawl_fulltext_batch
    try:
        result = await crawl_fulltext_batch()
        logger.info("Full-text crawl: %d crawled, %d success",
                     result.get("attempted", 0), result.get("success", 0))
    except Exception as e:
        logger.error("Full-text crawl failed: %s", e)


async def _gemini_index() -> None:
    """1시간 주기: Gemini 임베딩 인덱싱."""
    from api.services.gemini_indexer import index_with_gemini
    try:
        result = await index_with_gemini()
        logger.info("Gemini index: %d embedded", result.get("embedded", 0))
    except Exception as e:
        logger.error("Gemini index failed: %s", e)


async def _geopolitical_crawl() -> None:
    """1시간 주기: 국제정세 뉴스 수집 + 레짐 계산."""
    from api.services.geopolitical_engine import (
        crawl_geopolitical_news,
        calculate_geopolitical_regime,
    )
    try:
        crawl_result = await crawl_geopolitical_news()
        logger.info("Geopolitical crawl: %d events", crawl_result.get("new_events", 0))
        regime_result = await calculate_geopolitical_regime()
        logger.info("Geopolitical regime: %s (%.4f)",
                     regime_result.get("risk_regime"), regime_result.get("composite_risk", 0))
    except Exception as e:
        logger.error("Geopolitical crawl failed: %s", e)


def setup_scheduler() -> AsyncIOScheduler:
    """10개 스케줄 작업을 등록하고 스케줄러를 반환한다."""
    scheduler = get_scheduler()

    # 기존 7개
    scheduler.add_job(
        _morning_batch,
        CronTrigger(hour=8, minute=0, day_of_week="mon-fri"),
        id="morning_batch",
        name="Morning Batch (Step 0-4)",
        replace_existing=True,
    )
    scheduler.add_job(
        _close_batch,
        CronTrigger(hour=15, minute=30, day_of_week="mon-fri"),
        id="close_batch",
        name="Close Batch (Portfolio Update)",
        replace_existing=True,
    )
    scheduler.add_job(
        _news_crawl,
        IntervalTrigger(minutes=10),
        id="news_crawl",
        name="News Round-Robin Crawl (10min)",
        replace_existing=True,
    )
    scheduler.add_job(
        _auto_trade,
        IntervalTrigger(minutes=5),
        id="auto_trade",
        name="Auto Trade Loop (5min)",
        replace_existing=True,
    )
    scheduler.add_job(
        _macro_check,
        IntervalTrigger(minutes=30),
        id="macro_check",
        name="Macro Regime Check (30min)",
        replace_existing=True,
    )
    scheduler.add_job(
        _rag_index,
        IntervalTrigger(hours=1),
        id="rag_index",
        name="RAG News Index (1hr)",
        replace_existing=True,
    )
    scheduler.add_job(
        _sp500_weekly,
        CronTrigger(day_of_week="sun", hour=20, minute=0),
        id="sp500_weekly",
        name="S&P 500 Weekly Refresh",
        replace_existing=True,
    )

    # 신규 3개
    scheduler.add_job(
        _fulltext_crawl,
        IntervalTrigger(minutes=30),
        id="fulltext_crawl",
        name="Full Text Crawl (30min)",
        replace_existing=True,
    )
    scheduler.add_job(
        _gemini_index,
        IntervalTrigger(hours=1),
        id="gemini_index",
        name="Gemini Embedding Index (1hr)",
        replace_existing=True,
    )
    scheduler.add_job(
        _geopolitical_crawl,
        IntervalTrigger(hours=1),
        id="geopolitical_crawl",
        name="Geopolitical News Crawl (1hr)",
        replace_existing=True,
    )

    logger.info("Scheduler setup complete: 10 jobs registered")
    return scheduler
