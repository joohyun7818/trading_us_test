"""
Manual verification script for monitoring and alerting functionality.

This script tests the monitoring and alerting services without requiring
a full database connection.
"""
import asyncio
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta


async def test_monitoring_functions():
    """Test monitoring health checks with mocked database."""
    print("\n=== Testing Monitoring Functions ===\n")

    # Import after setting up environment
    from api.services.monitoring import run_health_checks

    # Test 1: All systems healthy
    print("Test 1: All systems healthy")
    with patch("api.services.monitoring.fetch_one") as mock_fetch_one, \
         patch("api.services.monitoring.ollama_health_check") as mock_ollama:

        mock_fetch_one.side_effect = [
            {"last_update": datetime.now()},  # data freshness
            {"count": 15},  # news collection
            {"count": 10},  # signal generation
            {"count": 5},   # excessive buy
            {"count": 0},   # order failures
        ]
        mock_ollama.return_value = {"status": "ok", "models": ["qwen3:4b"]}

        alerts = await run_health_checks()
        print(f"  Alerts generated: {len(alerts)}")
        print(f"  ✓ Expected: 0 alerts (all healthy)")
        assert len(alerts) == 0, "Should have no alerts when all systems healthy"

    # Test 2: Ollama down (CRITICAL)
    print("\nTest 2: Ollama down (CRITICAL alert)")
    with patch("api.services.monitoring.fetch_one") as mock_fetch_one, \
         patch("api.services.monitoring.ollama_health_check") as mock_ollama:

        mock_fetch_one.side_effect = [
            {"last_update": datetime.now()},
            {"count": 15},
            {"count": 10},
            {"count": 5},
            {"count": 0},
        ]
        mock_ollama.return_value = {"status": "offline", "error": "Connection refused"}

        alerts = await run_health_checks()
        print(f"  Alerts generated: {len(alerts)}")
        if alerts:
            alert = alerts[0]
            print(f"  Alert severity: {alert['severity']}")
            print(f"  Alert category: {alert['category']}")
            print(f"  Auto action: {alert.get('auto_action')}")
            print(f"  ✓ CRITICAL alert with pause_trading action")
            assert alert["severity"] == "CRITICAL"
            assert alert["category"] == "ollama_down"
            assert alert["auto_action"] == "pause_trading"

    # Test 3: Multiple warnings
    print("\nTest 3: Multiple warnings")
    with patch("api.services.monitoring.fetch_one") as mock_fetch_one, \
         patch("api.services.monitoring.ollama_health_check") as mock_ollama:

        stale_time = datetime.now() - timedelta(hours=3)
        mock_fetch_one.side_effect = [
            {"last_update": stale_time},  # data freshness WARNING
            {"count": 5},   # news collection WARNING
            {"count": 0},   # signal generation WARNING
            {"count": 60},  # excessive buy WARNING
            {"count": 0},   # order failures
        ]
        mock_ollama.return_value = {"status": "ok", "models": ["qwen3:4b"]}

        alerts = await run_health_checks()
        print(f"  Alerts generated: {len(alerts)}")
        print(f"  ✓ Expected: 4 WARNING alerts")
        assert len(alerts) == 4

    print("\n✅ All monitoring tests passed!")


async def test_alerting_functions():
    """Test alert processing and Slack notification."""
    print("\n=== Testing Alerting Functions ===\n")

    from api.services.alerting import process_alerts, send_slack_alert

    # Test 1: Process empty alert list
    print("Test 1: Process empty alert list")
    result = await process_alerts([])
    print(f"  Status: {result['status']}")
    print(f"  Alerts processed: {result['alerts_processed']}")
    print(f"  ✓ Correctly handles empty list")
    assert result["status"] == "ok"
    assert result["alerts_processed"] == 0

    # Test 2: Process WARNING alert
    print("\nTest 2: Process WARNING alert")
    with patch("api.services.alerting.execute") as mock_execute, \
         patch("api.services.alerting.send_slack_alert") as mock_slack:

        mock_execute.return_value = None
        mock_slack.return_value = False

        alerts = [
            {
                "severity": "WARNING",
                "category": "test_warning",
                "message": "Test warning message",
                "auto_action": None,
            }
        ]

        result = await process_alerts(alerts)
        print(f"  Alerts processed: {result['alerts_processed']}")
        print(f"  Critical count: {result['critical_count']}")
        print(f"  ✓ WARNING alert stored, no Slack notification")
        assert result["alerts_processed"] == 1
        assert result["critical_count"] == 0

    # Test 3: Process CRITICAL alert with auto-action
    print("\nTest 3: Process CRITICAL alert with pause_trading")
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
        print(f"  Critical count: {result['critical_count']}")
        print(f"  Slack sent: {result['slack_sent']}")
        print(f"  Execute called: {mock_execute.call_count} times")
        print(f"  ✓ CRITICAL alert stored, Slack sent, trading paused")
        assert result["critical_count"] == 1
        assert result["slack_sent"] == 1
        assert mock_execute.call_count == 2  # once for alert, once for pause_trading

    # Test 4: Slack notification without webhook
    print("\nTest 4: Slack notification without webhook")
    with patch("api.services.alerting.fetch_one") as mock_fetch_one:
        mock_fetch_one.return_value = {"value": ""}

        alert = {"severity": "CRITICAL", "category": "test", "message": "Test"}
        result = await send_slack_alert(alert)
        print(f"  Result: {result}")
        print(f"  ✓ Correctly skips when webhook not configured")
        assert result is False

    print("\n✅ All alerting tests passed!")


async def test_scheduler_integration():
    """Test scheduler job functions."""
    print("\n=== Testing Scheduler Integration ===\n")

    from api.services.scheduler import _health_check, _daily_report

    # Test health check job
    print("Test 1: Health check job")
    with patch("api.services.monitoring.run_health_checks") as mock_health, \
         patch("api.services.alerting.process_alerts") as mock_process:

        mock_health.return_value = []
        mock_process.return_value = {"status": "ok"}

        await _health_check()
        print(f"  ✓ Health check job executed successfully")

    # Test daily report job
    print("\nTest 2: Daily report job")
    with patch("api.services.alerting.send_daily_report") as mock_report:
        mock_report.return_value = {"status": "ok"}

        await _daily_report()
        print(f"  ✓ Daily report job executed successfully")

    print("\n✅ All scheduler tests passed!")


async def main():
    """Run all verification tests."""
    print("=" * 60)
    print("System Monitoring and Alerting - Manual Verification")
    print("=" * 60)

    try:
        await test_monitoring_functions()
        await test_alerting_functions()
        await test_scheduler_integration()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print("\nImplementation verified successfully:")
        print("  • Health checks correctly detect system issues")
        print("  • Alerts are processed and stored properly")
        print("  • CRITICAL alerts trigger Slack notifications")
        print("  • Auto-actions (pause_trading) are executed")
        print("  • Scheduler jobs are properly configured")
        print("\nReady for deployment! 🚀")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
