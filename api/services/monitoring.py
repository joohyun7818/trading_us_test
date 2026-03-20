"""
System health monitoring service.

Checks various system components and returns alerts for issues.
"""
import logging
from datetime import datetime, timedelta

from api.core.database import fetch_all, fetch_one
from api.services.ollama_client import health_check as ollama_health_check

logger = logging.getLogger(__name__)


async def run_health_checks() -> list[dict]:
    """
    Run all system health checks and return a list of alerts.

    Returns:
        List of alert dictionaries with keys:
        - severity: "WARNING" or "CRITICAL"
        - category: alert category identifier
        - message: human-readable message
        - auto_action: optional automatic action to take
    """
    alerts = []

    # a) Check data freshness: stocks.updated_at > 2 hours old
    try:
        row = await fetch_one(
            """
            SELECT MAX(updated_at) as last_update
            FROM stocks
            WHERE is_sp500 = TRUE
            """
        )
        if row and row["last_update"]:
            age = datetime.now(row["last_update"].tzinfo) - row["last_update"]
            if age > timedelta(hours=2):
                alerts.append({
                    "severity": "WARNING",
                    "category": "data_freshness",
                    "message": f"Stock data is {age.total_seconds()/3600:.1f} hours old (last update: {row['last_update']})",
                    "auto_action": None,
                })
                logger.warning("Data freshness check failed: %s hours old", age.total_seconds()/3600)
    except Exception as e:
        logger.error("Data freshness check error: %s", e)

    # b) Check news collection: < 10 new articles in last hour
    try:
        row = await fetch_one(
            """
            SELECT COUNT(*) as count
            FROM news_articles
            WHERE crawled_at > NOW() - INTERVAL '1 hour'
            """
        )
        if row and row["count"] < 10:
            alerts.append({
                "severity": "WARNING",
                "category": "news_collection",
                "message": f"Only {row['count']} news articles collected in the last hour (expected >= 10)",
                "auto_action": None,
            })
            logger.warning("News collection check failed: %d articles", row["count"])
    except Exception as e:
        logger.error("News collection check error: %s", e)

    # c) Check Ollama health
    try:
        health = await ollama_health_check()
        if health.get("status") != "ok":
            alerts.append({
                "severity": "CRITICAL",
                "category": "ollama_down",
                "message": f"Ollama service is {health.get('status')}: {health.get('error', 'Unknown error')}",
                "auto_action": "pause_trading",
            })
            logger.error("Ollama health check failed: %s", health)
    except Exception as e:
        logger.error("Ollama health check error: %s", e)
        alerts.append({
            "severity": "CRITICAL",
            "category": "ollama_down",
            "message": f"Ollama health check failed: {str(e)}",
            "auto_action": "pause_trading",
        })

    # d) Check signal generation: 0 signals in last 24 hours
    try:
        row = await fetch_one(
            """
            SELECT COUNT(*) as count
            FROM signals
            WHERE created_at > NOW() - INTERVAL '24 hours'
            """
        )
        if row and row["count"] == 0:
            alerts.append({
                "severity": "WARNING",
                "category": "no_signals",
                "message": "No signals generated in the last 24 hours",
                "auto_action": None,
            })
            logger.warning("No signals generated in last 24 hours")
    except Exception as e:
        logger.error("Signal generation check error: %s", e)

    # e) Check excessive BUY signals: > 50 BUY signals in last hour
    try:
        row = await fetch_one(
            """
            SELECT COUNT(*) as count
            FROM signals
            WHERE signal_type = 'BUY'
            AND created_at > NOW() - INTERVAL '1 hour'
            """
        )
        if row and row["count"] > 50:
            alerts.append({
                "severity": "WARNING",
                "category": "excessive_buy",
                "message": f"Excessive BUY signals: {row['count']} in the last hour (threshold: 50)",
                "auto_action": None,
            })
            logger.warning("Excessive BUY signals: %d", row["count"])
    except Exception as e:
        logger.error("Excessive BUY signals check error: %s", e)

    # f) Check order failures: >= 3 failed trades in last hour
    try:
        row = await fetch_one(
            """
            SELECT COUNT(*) as count
            FROM trades
            WHERE status = 'failed'
            AND created_at > NOW() - INTERVAL '1 hour'
            """
        )
        if row and row["count"] >= 3:
            alerts.append({
                "severity": "CRITICAL",
                "category": "order_failures",
                "message": f"Multiple order failures: {row['count']} failed trades in the last hour",
                "auto_action": "pause_trading",
            })
            logger.error("Order failures detected: %d", row["count"])
    except Exception as e:
        logger.error("Order failures check error: %s", e)

    logger.info("Health checks completed: %d alerts generated", len(alerts))
    return alerts
