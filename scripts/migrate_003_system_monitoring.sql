-- ============================================================
-- Migration 003: System Monitoring and Slack Alerts
-- ============================================================
-- Add system_alerts table and slack_webhook_url setting

-- ============================================================
-- system_alerts 테이블
-- ============================================================
CREATE TABLE IF NOT EXISTS system_alerts (
    id SERIAL PRIMARY KEY,
    severity VARCHAR(10) NOT NULL,
    category VARCHAR(30) NOT NULL,
    message TEXT NOT NULL,
    auto_action VARCHAR(30),
    resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_system_alerts_severity ON system_alerts (severity);
CREATE INDEX IF NOT EXISTS idx_system_alerts_category ON system_alerts (category);
CREATE INDEX IF NOT EXISTS idx_system_alerts_resolved ON system_alerts (resolved);
CREATE INDEX IF NOT EXISTS idx_system_alerts_created_at ON system_alerts (created_at);

-- ============================================================
-- Slack 설정 추가
-- ============================================================
INSERT INTO settings (key, value, description)
VALUES
    ('slack_webhook_url', '', 'Slack Webhook URL for system alerts'),
    ('auto_trade_enabled', 'true', 'Enable/disable auto trading')
ON CONFLICT (key) DO NOTHING;
