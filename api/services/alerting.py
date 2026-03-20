"""
Alert processing and notification service.

Handles alert storage, Slack notifications, and automatic actions.
"""
import logging
from datetime import datetime

import httpx

from api.core.database import execute, fetch_one

logger = logging.getLogger(__name__)


async def process_alerts(alerts: list[dict]) -> dict:
    """
    Process a list of alerts by:
    1. Storing all alerts in the system_alerts table
    2. Sending CRITICAL alerts to Slack
    3. Executing auto_actions for CRITICAL alerts

    Args:
        alerts: List of alert dictionaries with severity, category, message, auto_action

    Returns:
        Dictionary with processing statistics
    """
    if not alerts:
        return {"status": "ok", "alerts_processed": 0, "critical_count": 0, "slack_sent": 0}

    stored = 0
    critical = 0
    slack_sent = 0

    for alert in alerts:
        severity = alert.get("severity", "WARNING")
        category = alert.get("category", "unknown")
        message = alert.get("message", "")
        auto_action = alert.get("auto_action")

        # Store alert in database
        try:
            await execute(
                """
                INSERT INTO system_alerts (severity, category, message, auto_action, resolved)
                VALUES ($1, $2, $3, $4, $5)
                """,
                severity,
                category,
                message,
                auto_action,
                False,
            )
            stored += 1
            logger.info("Alert stored: %s - %s - %s", severity, category, message)
        except Exception as e:
            logger.error("Failed to store alert: %s", e)
            continue

        # Process CRITICAL alerts
        if severity == "CRITICAL":
            critical += 1

            # Send to Slack
            slack_success = await send_slack_alert(alert)
            if slack_success:
                slack_sent += 1

            # Execute auto_action if specified
            if auto_action == "pause_trading":
                try:
                    await execute(
                        """
                        INSERT INTO settings (key, value, description)
                        VALUES ('auto_trade_enabled', 'false', 'Enable/disable auto trading')
                        ON CONFLICT (key) DO UPDATE SET value = 'false', updated_at = NOW()
                        """
                    )
                    logger.warning("Auto-trading paused due to CRITICAL alert: %s", category)
                except Exception as e:
                    logger.error("Failed to pause auto-trading: %s", e)

    return {
        "status": "ok",
        "alerts_processed": stored,
        "critical_count": critical,
        "slack_sent": slack_sent,
    }


async def send_slack_alert(alert: dict) -> bool:
    """
    Send an alert to Slack using the webhook URL from settings.

    Args:
        alert: Alert dictionary with severity, category, message

    Returns:
        True if successfully sent, False otherwise
    """
    try:
        # Get Slack webhook URL from settings
        row = await fetch_one("SELECT value FROM settings WHERE key = 'slack_webhook_url'")
        if not row or not row["value"]:
            logger.warning("Slack webhook URL not configured, skipping notification")
            return False

        webhook_url = row["value"]

        # Format alert message for Slack
        severity = alert.get("severity", "WARNING")
        category = alert.get("category", "unknown")
        message = alert.get("message", "")

        emoji = "🔴" if severity == "CRITICAL" else "⚠️"

        slack_message = {
            "text": f"{emoji} *{severity}* Alert",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{emoji} {severity} Alert: {category}",
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Message:*\n{message}",
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} EST"
                        }
                    ]
                }
            ]
        }

        # Send to Slack
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(webhook_url, json=slack_message)
            if response.status_code == 200:
                logger.info("Slack notification sent successfully for %s alert", category)
                return True
            else:
                logger.error("Slack notification failed with status %d: %s",
                           response.status_code, response.text)
                return False

    except Exception as e:
        logger.error("Failed to send Slack notification: %s", e)
        return False


async def send_daily_report() -> dict:
    """
    Generate and send a daily trading report to Slack.

    Aggregates:
    - Total trades
    - BUY/SELL counts
    - Total P&L
    - Alert counts

    Returns:
        Dictionary with report status
    """
    try:
        # Get Slack webhook URL
        row = await fetch_one("SELECT value FROM settings WHERE key = 'slack_webhook_url'")
        if not row or not row["value"]:
            logger.warning("Slack webhook URL not configured, skipping daily report")
            return {"status": "skipped", "reason": "no_webhook_url"}

        webhook_url = row["value"]

        # Aggregate today's trade data
        trade_stats = await fetch_one(
            """
            SELECT
                COUNT(*) as total_trades,
                COUNT(*) FILTER (WHERE side = 'BUY') as buy_count,
                COUNT(*) FILTER (WHERE side = 'SELL') as sell_count,
                COALESCE(SUM(pnl), 0) as total_pnl
            FROM trades
            WHERE DATE(created_at AT TIME ZONE 'America/New_York') = CURRENT_DATE
            """
        )

        # Aggregate today's alerts
        alert_stats = await fetch_one(
            """
            SELECT
                COUNT(*) as total_alerts,
                COUNT(*) FILTER (WHERE severity = 'CRITICAL') as critical_count,
                COUNT(*) FILTER (WHERE severity = 'WARNING') as warning_count
            FROM system_alerts
            WHERE DATE(created_at AT TIME ZONE 'America/New_York') = CURRENT_DATE
            """
        )

        # Format report message
        total_trades = trade_stats.get("total_trades", 0) if trade_stats else 0
        buy_count = trade_stats.get("buy_count", 0) if trade_stats else 0
        sell_count = trade_stats.get("sell_count", 0) if trade_stats else 0
        total_pnl = float(trade_stats.get("total_pnl", 0)) if trade_stats else 0.0

        total_alerts = alert_stats.get("total_alerts", 0) if alert_stats else 0
        critical_count = alert_stats.get("critical_count", 0) if alert_stats else 0
        warning_count = alert_stats.get("warning_count", 0) if alert_stats else 0

        pnl_emoji = "📈" if total_pnl >= 0 else "📉"

        slack_message = {
            "text": "📊 Daily Trading Report",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"📊 Daily Trading Report - {datetime.now().strftime('%Y-%m-%d')}",
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Total Trades:*\n{total_trades}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*BUY / SELL:*\n{buy_count} / {sell_count}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Total P&L:*\n{pnl_emoji} ${total_pnl:.2f}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Alerts:*\n{total_alerts} ({critical_count} critical, {warning_count} warning)"
                        }
                    ]
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Report generated at {datetime.now().strftime('%H:%M:%S')} EST"
                        }
                    ]
                }
            ]
        }

        # Send to Slack
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(webhook_url, json=slack_message)
            if response.status_code == 200:
                logger.info("Daily report sent successfully to Slack")
                return {
                    "status": "ok",
                    "trades": total_trades,
                    "pnl": total_pnl,
                    "alerts": total_alerts,
                }
            else:
                logger.error("Failed to send daily report: HTTP %d", response.status_code)
                return {"status": "error", "code": response.status_code}

    except Exception as e:
        logger.error("Failed to generate/send daily report: %s", e)
        return {"status": "error", "error": str(e)}
