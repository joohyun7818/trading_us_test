"""
Tests for system monitoring and alerting services.
"""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.monitoring import run_health_checks
from api.services.alerting import process_alerts, send_slack_alert, send_daily_report


class TestMonitoring:
    """Test health check functions."""

    @pytest.mark.asyncio
    async def test_run_health_checks_all_healthy(self):
        """Test health checks when all systems are healthy."""
        with patch("api.services.monitoring.fetch_one") as mock_fetch_one, \
             patch("api.services.monitoring.ollama_health_check") as mock_ollama:

            # Mock all checks to return healthy status
            mock_fetch_one.side_effect = [
                {"last_update": datetime.now()},  # data freshness
                {"count": 15},  # news collection
                {"count": 10},  # signal generation
                {"count": 5},   # excessive buy
                {"count": 0},   # order failures
            ]
            mock_ollama.return_value = {"status": "ok", "models": ["qwen3:4b"]}

            alerts = await run_health_checks()

            assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_run_health_checks_data_freshness_warning(self):
        """Test data freshness warning when stocks are stale."""
        with patch("api.services.monitoring.fetch_one") as mock_fetch_one, \
             patch("api.services.monitoring.ollama_health_check") as mock_ollama:

            # Mock stale data
            stale_time = datetime.now() - timedelta(hours=3)
            mock_fetch_one.side_effect = [
                {"last_update": stale_time},  # data freshness
                {"count": 15},  # news collection
                {"count": 10},  # signal generation
                {"count": 5},   # excessive buy
                {"count": 0},   # order failures
            ]
            mock_ollama.return_value = {"status": "ok", "models": ["qwen3:4b"]}

            alerts = await run_health_checks()

            assert len(alerts) == 1
            assert alerts[0]["severity"] == "WARNING"
            assert alerts[0]["category"] == "data_freshness"

    @pytest.mark.asyncio
    async def test_run_health_checks_ollama_down_critical(self):
        """Test CRITICAL alert when Ollama is down."""
        with patch("api.services.monitoring.fetch_one") as mock_fetch_one, \
             patch("api.services.monitoring.ollama_health_check") as mock_ollama:

            mock_fetch_one.side_effect = [
                {"last_update": datetime.now()},  # data freshness
                {"count": 15},  # news collection
                {"count": 10},  # signal generation
                {"count": 5},   # excessive buy
                {"count": 0},   # order failures
            ]
            # Ollama is offline
            mock_ollama.return_value = {"status": "offline", "error": "Connection refused"}

            alerts = await run_health_checks()

            assert len(alerts) == 1
            assert alerts[0]["severity"] == "CRITICAL"
            assert alerts[0]["category"] == "ollama_down"
            assert alerts[0]["auto_action"] == "pause_trading"

    @pytest.mark.asyncio
    async def test_run_health_checks_order_failures_critical(self):
        """Test CRITICAL alert when order failures exceed threshold."""
        with patch("api.services.monitoring.fetch_one") as mock_fetch_one, \
             patch("api.services.monitoring.ollama_health_check") as mock_ollama:

            mock_fetch_one.side_effect = [
                {"last_update": datetime.now()},  # data freshness
                {"count": 15},  # news collection
                {"count": 10},  # signal generation
                {"count": 5},   # excessive buy
                {"count": 5},   # order failures >= 3
            ]
            mock_ollama.return_value = {"status": "ok", "models": ["qwen3:4b"]}

            alerts = await run_health_checks()

            assert len(alerts) == 1
            assert alerts[0]["severity"] == "CRITICAL"
            assert alerts[0]["category"] == "order_failures"
            assert alerts[0]["auto_action"] == "pause_trading"


class TestAlerting:
    """Test alert processing and notifications."""

    @pytest.mark.asyncio
    async def test_process_alerts_empty_list(self):
        """Test processing empty alert list."""
        result = await process_alerts([])

        assert result["status"] == "ok"
        assert result["alerts_processed"] == 0
        assert result["critical_count"] == 0

    @pytest.mark.asyncio
    async def test_process_alerts_stores_in_database(self):
        """Test that alerts are stored in database."""
        with patch("api.services.alerting.execute") as mock_execute, \
             patch("api.services.alerting.send_slack_alert") as mock_slack:

            mock_execute.return_value = None
            mock_slack.return_value = False

            alerts = [
                {
                    "severity": "WARNING",
                    "category": "test_alert",
                    "message": "Test message",
                    "auto_action": None,
                }
            ]

            result = await process_alerts(alerts)

            assert result["alerts_processed"] == 1
            assert result["critical_count"] == 0
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_alerts_critical_pauses_trading(self):
        """Test that CRITICAL alerts pause auto-trading."""
        with patch("api.services.alerting.execute") as mock_execute, \
             patch("api.services.alerting.send_slack_alert") as mock_slack:

            mock_execute.return_value = None
            mock_slack.return_value = True

            alerts = [
                {
                    "severity": "CRITICAL",
                    "category": "ollama_down",
                    "message": "Ollama is offline",
                    "auto_action": "pause_trading",
                }
            ]

            result = await process_alerts(alerts)

            assert result["critical_count"] == 1
            assert result["slack_sent"] == 1
            # Should be called twice: once for alert, once for pause_trading
            assert mock_execute.call_count == 2

    @pytest.mark.asyncio
    async def test_send_slack_alert_no_webhook(self):
        """Test Slack alert when webhook URL is not configured."""
        with patch("api.services.alerting.fetch_one") as mock_fetch_one:
            mock_fetch_one.return_value = {"value": ""}

            alert = {
                "severity": "WARNING",
                "category": "test",
                "message": "Test message",
            }

            result = await send_slack_alert(alert)

            assert result is False

    @pytest.mark.asyncio
    async def test_send_slack_alert_success(self):
        """Test successful Slack alert sending."""
        with patch("api.services.alerting.fetch_one") as mock_fetch_one, \
             patch("httpx.AsyncClient") as mock_client:

            mock_fetch_one.return_value = {"value": "https://hooks.slack.com/test"}

            mock_response = AsyncMock()
            mock_response.status_code = 200

            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            alert = {
                "severity": "CRITICAL",
                "category": "test_alert",
                "message": "Test critical message",
            }

            result = await send_slack_alert(alert)

            assert result is True
            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_daily_report_no_webhook(self):
        """Test daily report when webhook is not configured."""
        with patch("api.services.alerting.fetch_one") as mock_fetch_one:
            mock_fetch_one.return_value = {"value": ""}

            result = await send_daily_report()

            assert result["status"] == "skipped"
            assert result["reason"] == "no_webhook_url"

    @pytest.mark.asyncio
    async def test_send_daily_report_success(self):
        """Test successful daily report generation and sending."""
        with patch("api.services.alerting.fetch_one") as mock_fetch_one, \
             patch("httpx.AsyncClient") as mock_client:

            # Mock webhook URL and data
            mock_fetch_one.side_effect = [
                {"value": "https://hooks.slack.com/test"},
                {"total_trades": 10, "buy_count": 6, "sell_count": 4, "total_pnl": 125.50},
                {"total_alerts": 5, "critical_count": 1, "warning_count": 4},
            ]

            mock_response = AsyncMock()
            mock_response.status_code = 200

            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            result = await send_daily_report()

            assert result["status"] == "ok"
            assert result["trades"] == 10
            assert result["pnl"] == 125.50
            mock_post.assert_called_once()
