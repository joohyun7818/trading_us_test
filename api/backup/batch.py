# Step 0-4 배치 프로세서, batch_logs 기록
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from api.core.database import execute, fetch_all, fetch_one
from api.services.macro_engine import calculate_regime
from api.services.news_crawler import crawl_news_round_robin
from api.services.news_indexer import index_unembedded_articles
from api.services.numeric_analyzer import calculate_numeric_score
from api.services.price_crawler import crawl_prices
from api.services.sp500_loader import load_sp500
from api.services.trading_engine import analyze_and_signal

logger = logging.getLogger(__name__)


async def _log_batch(
    batch_type: str,
    step: str,
    status: str,
    duration_sec: float,
    summary: Optional[dict] = None,
    error_message: Optional[str] = None,
) -> None:
    """배치 로그를 기록한다."""
    try:
        await execute(
            """
            INSERT INTO batch_logs (batch_type, step, status, duration_sec, summary, error_message)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            batch_type, step, status, round(duration_sec, 2),
            json.dumps(summary) if summary else None,
            error_message,
        )
    except Exception as e:
        logger.error("Batch log insert failed: %s", e)


async def step0_load_and_crawl() -> dict:
    """Step 0: S&P 500 목록 로드 + 가격 크롤링."""
    start = time.time()
    try:
        sp500_result = await load_sp500()
        price_result = await crawl_prices()

        duration = time.time() - start
        summary = {"sp500": sp500_result, "prices": price_result}
        await _log_batch("morning", "step0", "completed", duration, summary)

        logger.info("Step 0 completed in %.1fs", duration)
        return {"status": "ok", "duration_sec": round(duration, 2), **summary}

    except Exception as e:
        duration = time.time() - start
        await _log_batch("morning", "step0", "error", duration, error_message=str(e))
        logger.error("Step 0 failed: %s", e)
        return {"status": "error", "error": str(e)}


async def step1_screen() -> dict:
    """Step 1: 기술적 지표 기반 스크리닝."""
    start = time.time()
    try:
        rows = await fetch_all(
            """
            SELECT symbol FROM stocks
            WHERE is_sp500 = TRUE AND current_price IS NOT NULL
            ORDER BY symbol
            """
        )

        screened = []
        for row in rows:
            symbol = row["symbol"]
            result = await calculate_numeric_score(symbol)
            score = result.get("score", 50)
            if score >= 60 or score <= 35:
                screened.append({"symbol": symbol, "numeric_score": score})

        duration = time.time() - start
        summary = {"screened_count": len(screened), "total_stocks": len(rows)}
        await _log_batch("morning", "step1", "completed", duration, summary)

        logger.info("Step 1: %d stocks screened from %d in %.1fs", len(screened), len(rows), duration)
        return {"status": "ok", "screened": screened, "duration_sec": round(duration, 2)}

    except Exception as e:
        duration = time.time() - start
        await _log_batch("morning", "step1", "error", duration, error_message=str(e))
        logger.error("Step 1 failed: %s", e)
        return {"status": "error", "error": str(e)}


async def step2_news_sentiment() -> dict:
    """Step 2: 뉴스 수집 + 1차 감성 분석."""
    start = time.time()
    try:
        news_result = await crawl_news_round_robin()
        index_result = await index_unembedded_articles()

        duration = time.time() - start
        summary = {"news": news_result, "indexing": index_result}
        await _log_batch("morning", "step2", "completed", duration, summary)

        logger.info("Step 2 completed in %.1fs", duration)
        return {"status": "ok", "duration_sec": round(duration, 2), **summary}

    except Exception as e:
        duration = time.time() - start
        await _log_batch("morning", "step2", "error", duration, error_message=str(e))
        logger.error("Step 2 failed: %s", e)
        return {"status": "error", "error": str(e)}


async def step3_deep_analysis(screened_symbols: Optional[list[str]] = None) -> dict:
    """Step 3: 2차 RAG 분석 + 시각 분석."""
    start = time.time()
    try:
        if screened_symbols is None:
            step1_result = await step1_screen()
            screened_symbols = [s["symbol"] for s in step1_result.get("screened", [])]

        if not screened_symbols:
            duration = time.time() - start
            await _log_batch("morning", "step3", "completed", duration, {"analyzed": 0})
            return {"status": "ok", "analyzed": 0}

        regime_result = await calculate_regime()
        macro_score = regime_result.get("regime_score", 0.5) * 100

        analyzed = []
        for symbol in screened_symbols:
            try:
                result = await analyze_and_signal(symbol, macro_score=macro_score)
                analyzed.append(result)
            except Exception as e:
                logger.error("Analysis failed for %s: %s", symbol, e)

        duration = time.time() - start
        summary = {
            "analyzed_count": len(analyzed),
            "buy_signals": sum(1 for a in analyzed if a.get("signal_type") == "BUY"),
            "sell_signals": sum(1 for a in analyzed if a.get("signal_type") == "SELL"),
            "hold_signals": sum(1 for a in analyzed if a.get("signal_type") == "HOLD"),
        }
        await _log_batch("morning", "step3", "completed", duration, summary)

        logger.info("Step 3: %d analyzed in %.1fs", len(analyzed), duration)
        return {"status": "ok", "analyzed": analyzed, "duration_sec": round(duration, 2), **summary}

    except Exception as e:
        duration = time.time() - start
        await _log_batch("morning", "step3", "error", duration, error_message=str(e))
        logger.error("Step 3 failed: %s", e)
        return {"status": "error", "error": str(e)}


async def step4_execute_orders() -> dict:
    """Step 4: 종합 판단 기반 주문 실행."""
    start = time.time()
    try:
        from api.services.auto_trader import auto_trade_loop
        trade_result = await auto_trade_loop()

        duration = time.time() - start
        await _log_batch("morning", "step4", "completed", duration, trade_result)

        logger.info("Step 4 completed in %.1fs", duration)
        return {"status": "ok", "duration_sec": round(duration, 2), **trade_result}

    except Exception as e:
        duration = time.time() - start
        await _log_batch("morning", "step4", "error", duration, error_message=str(e))
        logger.error("Step 4 failed: %s", e)
        return {"status": "error", "error": str(e)}


async def run_full_batch() -> dict:
    """Step 0-4 전체 배치를 순차 실행한다."""
    total_start = time.time()
    results = {}

    results["step0"] = await step0_load_and_crawl()
    results["step1"] = await step1_screen()
    results["step2"] = await step2_news_sentiment()

    screened = [s["symbol"] for s in results["step1"].get("screened", [])]
    results["step3"] = await step3_deep_analysis(screened)
    results["step4"] = await step4_execute_orders()

    total_duration = round(time.time() - total_start, 2)
    logger.info("Full batch completed in %.1fs", total_duration)

    return {
        "status": "ok",
        "total_duration_sec": total_duration,
        "steps": results,
    }
