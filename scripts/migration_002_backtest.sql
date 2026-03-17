CREATE TABLE stock_daily (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    trade_date DATE NOT NULL,
    open NUMERIC(12,4),
    high NUMERIC(12,4),
    low NUMERIC(12,4),
    close NUMERIC(12,4) NOT NULL,
    volume BIGINT,
    adj_close NUMERIC(12,4),
    -- 사전 계산 기술지표
    rsi_14 NUMERIC(8,4),
    sma_20 NUMERIC(12,4),
    sma_60 NUMERIC(12,4),
    macd NUMERIC(12,6),
    macd_signal NUMERIC(12,6),
    macd_histogram NUMERIC(12,6),
    bollinger_upper NUMERIC(12,4),
    bollinger_lower NUMERIC(12,4),
    bollinger_pct_b NUMERIC(8,4),
    volume_ratio NUMERIC(8,4),
    atr_14 NUMERIC(12,4),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(symbol, trade_date)
);

CREATE INDEX idx_stock_daily_symbol_date ON stock_daily(symbol, trade_date);
CREATE INDEX idx_stock_daily_date ON stock_daily(trade_date);
