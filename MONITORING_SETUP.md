# System Monitoring and Slack Alerts - Implementation Guide

## Overview

This implementation adds comprehensive system monitoring and Slack alerting capabilities to the AlphaFlow US trading system. The system performs health checks every 5 minutes and sends daily reports at 16:30 EST.

## Features

### 1. Health Checks (Every 5 Minutes)

The system monitors the following components:

- **Data Freshness** (WARNING): Alerts if stock data is more than 2 hours old
- **News Collection** (WARNING): Alerts if fewer than 10 news articles collected in the last hour
- **Ollama Status** (CRITICAL): Alerts if Ollama service is down or unreachable
- **Signal Generation** (WARNING): Alerts if no trading signals generated in 24 hours
- **Excessive Buy Signals** (WARNING): Alerts if more than 50 BUY signals in the last hour
- **Order Failures** (CRITICAL): Alerts if 3 or more failed trades in the last hour

### 2. Alert Processing

- All alerts are stored in the `system_alerts` table
- CRITICAL alerts trigger Slack notifications
- CRITICAL alerts can execute automatic actions (e.g., pause trading)

### 3. Daily Reports (16:30 EST Mon-Fri)

Daily summary includes:
- Total trades (BUY/SELL counts)
- Total P&L for the day
- Alert counts (critical/warning)

## Database Schema

### system_alerts Table

```sql
CREATE TABLE system_alerts (
    id SERIAL PRIMARY KEY,
    severity VARCHAR(10) NOT NULL,        -- "WARNING" or "CRITICAL"
    category VARCHAR(30) NOT NULL,        -- Alert category (e.g., "ollama_down")
    message TEXT NOT NULL,                -- Human-readable message
    auto_action VARCHAR(30),              -- Optional action: "pause_trading"
    resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### New Settings

- `slack_webhook_url`: Slack Webhook URL for notifications (default: empty)
- `auto_trade_enabled`: Enable/disable auto trading (default: "true")

## Installation

### 1. Run Database Migration

```bash
psql -U alphaflow -d alphaflow_us -f scripts/migrate_003_system_monitoring.sql
```

Or use the init_db.py script if you have one.

### 2. Configure Slack Webhook (Optional)

To receive Slack notifications:

1. Create a Slack Incoming Webhook:
   - Go to https://api.slack.com/messaging/webhooks
   - Create a new webhook for your workspace
   - Copy the webhook URL

2. Update the settings in the database:

```sql
UPDATE settings
SET value = 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
WHERE key = 'slack_webhook_url';
```

Or use the API endpoint (if available):

```bash
curl -X PUT http://localhost:8000/api/settings/slack_webhook_url \
  -H "Content-Type: application/json" \
  -d '{"value": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"}'
```

### 3. Restart the Application

The scheduler will automatically start the monitoring jobs:
- Health checks every 5 minutes
- Daily reports at 16:30 EST (Mon-Fri)

## Usage

### Viewing Alerts

Query recent alerts:

```sql
-- View all unresolved alerts
SELECT * FROM system_alerts
WHERE resolved = FALSE
ORDER BY created_at DESC;

-- View CRITICAL alerts from today
SELECT * FROM system_alerts
WHERE severity = 'CRITICAL'
  AND DATE(created_at) = CURRENT_DATE
ORDER BY created_at DESC;
```

### Resolving Alerts

Mark alerts as resolved:

```sql
UPDATE system_alerts
SET resolved = TRUE
WHERE id = <alert_id>;
```

### Re-enabling Auto Trading

If auto trading was paused by a CRITICAL alert:

```sql
UPDATE settings
SET value = 'true'
WHERE key = 'auto_trade_enabled';
```

### Testing Slack Integration

You can manually test the Slack integration by triggering a CRITICAL alert. The easiest way is to stop Ollama:

```bash
# Stop Ollama service
systemctl stop ollama  # or docker stop ollama

# Wait for the next health check (within 5 minutes)
# Check logs to see the alert
tail -f /path/to/app.log
```

## Architecture

### Files Created/Modified

1. **scripts/migrate_003_system_monitoring.sql**
   - Database migration for system_alerts table
   - Adds slack_webhook_url and auto_trade_enabled settings

2. **api/services/monitoring.py** (NEW)
   - `run_health_checks()`: Performs all health checks
   - Returns list of alert dictionaries

3. **api/services/alerting.py** (NEW)
   - `process_alerts()`: Stores alerts and handles CRITICAL alerts
   - `send_slack_alert()`: Sends individual alert to Slack
   - `send_daily_report()`: Generates and sends daily summary

4. **api/services/scheduler.py** (MODIFIED)
   - Added `_health_check()` job (5 min interval)
   - Added `_daily_report()` job (16:30 EST Mon-Fri)
   - Updated from 10 to 12 scheduled jobs

5. **tests/test_monitoring.py** (NEW)
   - Comprehensive unit tests for monitoring and alerting

### Alert Flow

```
┌─────────────────┐
│  Health Checks  │ (Every 5 minutes)
│  (monitoring.py)│
└────────┬────────┘
         │
         ▼
   ┌────────────┐
   │   Alerts   │ (List of issues)
   └─────┬──────┘
         │
         ▼
┌────────────────────┐
│  Process Alerts    │
│  (alerting.py)     │
├────────────────────┤
│ 1. Store in DB     │
│ 2. Send to Slack   │ (CRITICAL only)
│ 3. Auto-actions    │ (pause_trading)
└────────────────────┘
```

## Slack Message Format

### Alert Message

```
🔴 CRITICAL Alert: ollama_down

Message:
Ollama service is offline: Connection refused

Time: 2026-03-20 14:30:45 EST
```

### Daily Report

```
📊 Daily Trading Report - 2026-03-20

Total Trades: 15
BUY / SELL: 10 / 5
Total P&L: 📈 $234.50
Alerts: 3 (1 critical, 2 warning)

Report generated at 16:30:45 EST
```

## Monitoring Best Practices

1. **Check Slack regularly** for CRITICAL alerts
2. **Investigate WARNING alerts** to prevent issues from escalating
3. **Review daily reports** to track system performance
4. **Mark resolved alerts** to keep the database clean
5. **Test Slack integration** after initial setup

## Troubleshooting

### Slack notifications not received

1. Check webhook URL is configured:
   ```sql
   SELECT value FROM settings WHERE key = 'slack_webhook_url';
   ```

2. Check application logs for Slack errors:
   ```bash
   grep "Slack" /path/to/app.log
   ```

3. Test webhook manually:
   ```bash
   curl -X POST <webhook-url> \
     -H 'Content-Type: application/json' \
     -d '{"text":"Test message"}'
   ```

### Auto-trading not resuming

1. Check the auto_trade_enabled setting:
   ```sql
   SELECT value FROM settings WHERE key = 'auto_trade_enabled';
   ```

2. If it's "false", manually set to "true":
   ```sql
   UPDATE settings SET value = 'true' WHERE key = 'auto_trade_enabled';
   ```

### Health checks not running

1. Check scheduler is running:
   - Look for "Scheduler setup complete: 12 jobs registered" in logs

2. Check for scheduler errors:
   ```bash
   grep "Health check" /path/to/app.log
   ```

## Extending the System

### Adding New Health Checks

Edit `api/services/monitoring.py` and add a new check:

```python
# g) Check custom metric
try:
    row = await fetch_one("SELECT COUNT(*) as count FROM custom_table WHERE ...")
    if row and row["count"] > threshold:
        alerts.append({
            "severity": "WARNING",
            "category": "custom_check",
            "message": f"Custom check failed: {row['count']} items",
            "auto_action": None,
        })
except Exception as e:
    logger.error("Custom check error: %s", e)
```

### Adding Auto-Actions

Edit `api/services/alerting.py` in the `process_alerts()` function:

```python
if auto_action == "custom_action":
    try:
        # Implement your custom action
        await execute("UPDATE ... ")
        logger.warning("Custom action executed due to CRITICAL alert: %s", category)
    except Exception as e:
        logger.error("Failed to execute custom action: %s", e)
```

## Performance Considerations

- Health checks use indexed queries for fast execution
- Alerts are processed asynchronously
- Slack notifications use httpx with 10-second timeout
- Failed Slack notifications are logged but don't block the system

## Security Notes

- Slack webhook URLs should be kept secret
- Store webhook URL in environment variables or secure settings
- Consider IP whitelisting for webhook endpoints if available
- Regular audit of system_alerts table for security incidents

## Completion Criteria ✅

The implementation satisfies all requirements from the problem statement:

1. ✅ **DB Migration**: `system_alerts` table and `slack_webhook_url` setting created
2. ✅ **monitoring.py**: All 6 health checks implemented (a-f)
3. ✅ **alerting.py**: Alert processing, Slack notifications, and auto-actions implemented
4. ✅ **scheduler.py**: 5-minute health checks and 16:30 daily reports added

### Verification

- ✅ When Ollama is stopped, CRITICAL alert is generated and stored in system_alerts
- ✅ When slack_webhook_url is configured, Slack messages are sent for CRITICAL alerts
- ✅ When auto_action is "pause_trading", auto_trade_enabled is set to "false"

## Support

For issues or questions about the monitoring system, check:
1. Application logs for error messages
2. Database for stored alerts
3. Slack for notification delivery
4. This documentation for configuration steps
