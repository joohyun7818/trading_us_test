-- AlphaFlow US 전체 DDL + 인덱스 + Default settings

-- ============================================================
-- 섹터 테이블
-- ============================================================
CREATE TABLE IF NOT EXISTS sectors (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- 종목 테이블
-- ============================================================
CREATE TABLE IF NOT EXISTS stocks (
    id                SERIAL PRIMARY KEY,
    symbol            VARCHAR(10) UNIQUE NOT NULL,
    name              VARCHAR(200) NOT NULL,
    sector_id         INTEGER REFERENCES sectors(id),
    market_cap        BIGINT,
    current_price     NUMERIC(12,4),
    price_change_pct  NUMERIC(8,4),
    rsi_14            NUMERIC(8,4),
    sma_20            NUMERIC(12,4),
    sma_60            NUMERIC(12,4),
    macd              NUMERIC(12,6),
    macd_signal       NUMERIC(12,6),
    macd_histogram    NUMERIC(12,6),
    bollinger_upper   NUMERIC(12,4),
    bollinger_lower   NUMERIC(12,4),
    bollinger_pct_b   NUMERIC(8,4),
    volume_ratio      NUMERIC(8,4),
    high_52w          NUMERIC(12,4),
    low_52w           NUMERIC(12,4),
    atr_14            NUMERIC(12,4),
    is_sp500          BOOLEAN DEFAULT TRUE,
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stocks_symbol ON stocks(symbol);
CREATE INDEX IF NOT EXISTS idx_stocks_sector_id ON stocks(sector_id);
CREATE INDEX IF NOT EXISTS idx_stocks_is_sp500 ON stocks(is_sp500);

-- ============================================================
-- 뉴스 기사 테이블
-- ============================================================
CREATE TABLE IF NOT EXISTS news_articles (
    id               SERIAL PRIMARY KEY,
    stock_symbol     VARCHAR(10) NOT NULL,
    title            VARCHAR(500) NOT NULL,
    body             TEXT,
    source           VARCHAR(50) NOT NULL,
    url              TEXT NOT NULL,
    url_hash         VARCHAR(64) UNIQUE NOT NULL,
    published_at     TIMESTAMPTZ,
    crawled_at       TIMESTAMPTZ DEFAULT NOW(),
    sentiment_score  NUMERIC(6,4),
    sentiment_label  VARCHAR(20),
    is_priced_in     BOOLEAN DEFAULT FALSE,
    crawl_source     VARCHAR(30),
    backfill_batch_id VARCHAR(50),
    embedded         BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_news_stock_symbol ON news_articles(stock_symbol);
CREATE INDEX IF NOT EXISTS idx_news_published_at ON news_articles(published_at);
CREATE INDEX IF NOT EXISTS idx_news_url_hash ON news_articles(url_hash);
CREATE INDEX IF NOT EXISTS idx_news_embedded ON news_articles(embedded);
CREATE INDEX IF NOT EXISTS idx_news_crawl_source ON news_articles(crawl_source);
CREATE INDEX IF NOT EXISTS idx_news_sentiment_label ON news_articles(sentiment_label);

-- ============================================================
-- 뉴스 수집 로그 테이블
-- ============================================================
CREATE TABLE IF NOT EXISTS news_collection_logs (
    id             SERIAL PRIMARY KEY,
    batch_id       VARCHAR(50) NOT NULL,
    stock_count    INTEGER,
    article_count  INTEGER,
    source         VARCHAR(50),
    duration_sec   NUMERIC(8,2),
    status         VARCHAR(20),
    error_message  TEXT,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ncl_batch_id ON news_collection_logs(batch_id);
CREATE INDEX IF NOT EXISTS idx_ncl_created_at ON news_collection_logs(created_at);

-- ============================================================
-- 시그널 테이블
-- ============================================================
CREATE TABLE IF NOT EXISTS signals (
    id              SERIAL PRIMARY KEY,
    stock_symbol    VARCHAR(10) NOT NULL,
    signal_type     VARCHAR(10) NOT NULL,
    final_score     NUMERIC(8,4),
    text_score      NUMERIC(8,4),
    numeric_score   NUMERIC(8,4),
    visual_score    NUMERIC(8,4),
    macro_score     NUMERIC(8,4),
    analysis_mode   VARCHAR(20),
    rationale       TEXT,
    adjustments     JSONB,
    executed        BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signals_stock_symbol ON signals(stock_symbol);
CREATE INDEX IF NOT EXISTS idx_signals_signal_type ON signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals(created_at);
CREATE INDEX IF NOT EXISTS idx_signals_executed ON signals(executed);

-- ============================================================
-- 거래 테이블
-- ============================================================
CREATE TABLE IF NOT EXISTS trades (
    id            SERIAL PRIMARY KEY,
    stock_symbol  VARCHAR(10) NOT NULL,
    side          VARCHAR(4) NOT NULL,
    qty           NUMERIC(12,4) NOT NULL,
    price         NUMERIC(12,4),
    order_type    VARCHAR(10) DEFAULT 'market',
    order_id      VARCHAR(100),
    status        VARCHAR(20) DEFAULT 'pending',
    signal_id     INTEGER REFERENCES signals(id),
    pnl           NUMERIC(12,4),
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trades_stock_symbol ON trades(stock_symbol);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_created_at ON trades(created_at);

-- ============================================================
-- 포트폴리오 테이블
-- ============================================================
CREATE TABLE IF NOT EXISTS portfolio (
    id                  SERIAL PRIMARY KEY,
    stock_symbol        VARCHAR(10) UNIQUE NOT NULL,
    qty                 NUMERIC(12,4) NOT NULL,
    avg_price           NUMERIC(12,4) NOT NULL,
    current_price       NUMERIC(12,4),
    unrealized_pnl      NUMERIC(12,4),
    unrealized_pnl_pct  NUMERIC(8,4),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_portfolio_stock_symbol ON portfolio(stock_symbol);

-- ============================================================
-- 매크로 레짐 테이블
-- ============================================================
CREATE TABLE IF NOT EXISTS macro_regime (
    id                    SERIAL PRIMARY KEY,
    regime                VARCHAR(20) NOT NULL,
    regime_score          NUMERIC(6,4) NOT NULL,
    sp500_trend           NUMERIC(6,4),
    vix_level             NUMERIC(8,4),
    yield_curve_spread    NUMERIC(8,4),
    market_rsi            NUMERIC(8,4),
    market_breadth        NUMERIC(6,4),
    put_call_ratio        NUMERIC(6,4),
    macro_news_sentiment  NUMERIC(6,4),
    leveraged_action      VARCHAR(20),
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_macro_regime_created_at ON macro_regime(created_at);

-- ============================================================
-- 레버리지 포지션 테이블
-- ============================================================
CREATE TABLE IF NOT EXISTS leveraged_positions (
    id                        SERIAL PRIMARY KEY,
    symbol                    VARCHAR(10) NOT NULL,
    side                      VARCHAR(4) NOT NULL,
    qty                       NUMERIC(12,4) NOT NULL,
    entry_price               NUMERIC(12,4) NOT NULL,
    current_price             NUMERIC(12,4),
    stop_loss                 NUMERIC(12,4) NOT NULL,
    take_profit               NUMERIC(12,4) NOT NULL,
    entry_date                DATE NOT NULL,
    max_hold_days             INTEGER DEFAULT 5,
    consecutive_extreme_days  INTEGER DEFAULT 0,
    status                    VARCHAR(20) DEFAULT 'open',
    closed_at                 TIMESTAMPTZ,
    pnl                       NUMERIC(12,4),
    order_id                  VARCHAR(100),
    created_at                TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lp_symbol ON leveraged_positions(symbol);
CREATE INDEX IF NOT EXISTS idx_lp_status ON leveraged_positions(status);

-- ============================================================
-- 백필 진행 상황 테이블
-- ============================================================
CREATE TABLE IF NOT EXISTS backfill_progress (
    id             SERIAL PRIMARY KEY,
    stock_symbol   VARCHAR(10) NOT NULL,
    source         VARCHAR(30) NOT NULL,
    last_page      INTEGER DEFAULT 0,
    last_date      DATE,
    article_count  INTEGER DEFAULT 0,
    status         VARCHAR(20) DEFAULT 'pending',
    error_message  TEXT,
    updated_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (stock_symbol, source)
);

CREATE INDEX IF NOT EXISTS idx_bp_stock_symbol ON backfill_progress(stock_symbol);
CREATE INDEX IF NOT EXISTS idx_bp_status ON backfill_progress(status);

-- ============================================================
-- 분석 캐시 테이블
-- ============================================================
CREATE TABLE IF NOT EXISTS analysis_cache (
    id             SERIAL PRIMARY KEY,
    stock_symbol   VARCHAR(10) NOT NULL,
    analysis_type  VARCHAR(20) NOT NULL,
    model_used     VARCHAR(50),
    result         JSONB NOT NULL,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    expires_at     TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ac_stock_symbol ON analysis_cache(stock_symbol);
CREATE INDEX IF NOT EXISTS idx_ac_analysis_type ON analysis_cache(analysis_type);
CREATE INDEX IF NOT EXISTS idx_ac_expires_at ON analysis_cache(expires_at);

-- ============================================================
-- 설정 테이블
-- ============================================================
CREATE TABLE IF NOT EXISTS settings (
    key          VARCHAR(100) PRIMARY KEY,
    value        TEXT NOT NULL,
    description  TEXT,
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- 배치 로그 테이블
-- ============================================================
CREATE TABLE IF NOT EXISTS batch_logs (
    id             SERIAL PRIMARY KEY,
    batch_type     VARCHAR(30) NOT NULL,
    step           VARCHAR(30),
    status         VARCHAR(20) NOT NULL,
    duration_sec   NUMERIC(8,2),
    summary        JSONB,
    error_message  TEXT,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bl_batch_type ON batch_logs(batch_type);
CREATE INDEX IF NOT EXISTS idx_bl_created_at ON batch_logs(created_at);

-- ============================================================
-- Default settings INSERT
-- ============================================================
INSERT INTO settings (key, value, description) VALUES
    ('analysis_mode',           'text_numeric',  'text_numeric 또는 full'),
    ('total_capital',           '100000',        '총 투자 자본 USD'),
    ('w_text',                  '0.35',          '텍스트 가중치 (text_numeric 모드)'),
    ('w_numeric',               '0.50',          '수치 가중치 (text_numeric 모드)'),
    ('w_visual',                '0.00',          '시각 가중치 (text_numeric 모드)'),
    ('w_macro',                 '0.15',          '매크로 가중치'),
    ('w_text_full',             '0.25',          '텍스트 가중치 (full 모드)'),
    ('w_numeric_full',          '0.35',          '수치 가중치 (full 모드)'),
    ('w_visual_full',           '0.25',          '시각 가중치 (full 모드)'),
    ('w_macro_full',            '0.15',          '매크로 가중치 (full 모드)'),
    ('ollama_fast_model',       'qwen3:4b',      '1차 분류 모델'),
    ('ollama_deep_model',       'qwen3:8b',      '2차 분석 모델'),
    ('ollama_vision_model',     'qwen3-vl:8b',   '시각 분석 모델'),
    ('ollama_embed_model',      'bge-m3',        '임베딩 모델'),
    ('leveraged_enabled',       'false',         '레버리지 ON/OFF'),
    ('leveraged_max_pct',       '0.03',          '레버리지 최대 자본 비율'),
    ('leveraged_stop_loss',     '0.08',          '손절 비율'),
    ('leveraged_take_profit',   '0.15',          '익절 비율'),
    ('leveraged_max_hold_days', '5',             '최대 보유일'),
    ('leveraged_min_extreme_days', '3',          'EXTREME 최소 연속일'),
    ('max_order_amount',        '1000',          '1회 최대 주문 USD'),
    ('daily_order_limit',       '50',            '일일 최대 주문 수'),
    ('max_exposure_pct',        '0.70',          '총 투자 한도 비율'),
    ('news_round_robin_size',   '50',            '뉴스 1회 종목 수'),
    ('news_interval_minutes',   '10',            '뉴스 수집 간격 분'),
    ('backfill_years',          '2',             '백필 기간 년')
ON CONFLICT (key) DO NOTHING;
