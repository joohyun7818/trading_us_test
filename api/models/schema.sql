-- AlphaFlow US 전체 DDL + 인덱스 + Default settings
-- ============================================================
-- 섹터 테이블
-- ============================================================
   CREATE TABLE IF NOT EXISTS sectors (id SERIAL PRIMARY KEY, name VARCHAR (100) UNIQUE NOT NULL, description TEXT, created_at TIMESTAMPTZ DEFAULT NOW());

-- ============================================================
-- 종목 테이블
-- ============================================================
   CREATE TABLE IF NOT EXISTS stocks (
          id SERIAL PRIMARY KEY
        , symbol VARCHAR (10) UNIQUE NOT NULL
        , name VARCHAR (200) NOT NULL
        , sector_id INTEGER REFERENCES sectors (id)
        , market_cap BIGINT
        , current_price NUMERIC(12, 4)
        , price_change_pct NUMERIC(8, 4)
        , rsi_14 NUMERIC(8, 4)
        , sma_20 NUMERIC(12, 4)
        , sma_60 NUMERIC(12, 4)
        , macd NUMERIC(12, 6)
        , macd_signal NUMERIC(12, 6)
        , macd_histogram NUMERIC(12, 6)
        , bollinger_upper NUMERIC(12, 4)
        , bollinger_lower NUMERIC(12, 4)
        , bollinger_pct_b NUMERIC(8, 4)
        , volume_ratio NUMERIC(8, 4)
        , high_52w NUMERIC(12, 4)
        , low_52w NUMERIC(12, 4)
        , atr_14 NUMERIC(12, 4)
        , is_sp500 BOOLEAN DEFAULT TRUE
        , updated_at TIMESTAMPTZ DEFAULT NOW()
          );

CREATE INDEX IF NOT EXISTS idx_stocks_symbol ON stocks (symbol);

CREATE INDEX IF NOT EXISTS idx_stocks_sector_id ON stocks (sector_id);

CREATE INDEX IF NOT EXISTS idx_stocks_is_sp500 ON stocks (is_sp500);

-- ============================================================
-- 뉴스 기사 테이블
-- ============================================================
   CREATE TABLE IF NOT EXISTS news_articles (
          id SERIAL PRIMARY KEY
        , stock_symbol VARCHAR (10) NOT NULL
        , title VARCHAR (500) NOT NULL
        , body TEXT
        , source VARCHAR (50) NOT NULL
        , url TEXT NOT NULL
        , url_hash VARCHAR (64) UNIQUE NOT NULL
        , published_at TIMESTAMPTZ
        , crawled_at TIMESTAMPTZ DEFAULT NOW()
        , sentiment_score NUMERIC(6, 4)
        , sentiment_label VARCHAR (20)
        , is_priced_in BOOLEAN DEFAULT FALSE
        , crawl_source VARCHAR (30)
        , backfill_batch_id VARCHAR (50)
        , embedded BOOLEAN DEFAULT FALSE
          );

CREATE INDEX IF NOT EXISTS idx_news_stock_symbol ON news_articles (stock_symbol);

CREATE INDEX IF NOT EXISTS idx_news_published_at ON news_articles (published_at);

CREATE INDEX IF NOT EXISTS idx_news_url_hash ON news_articles (url_hash);

CREATE INDEX IF NOT EXISTS idx_news_embedded ON news_articles (embedded);

CREATE INDEX IF NOT EXISTS idx_news_crawl_source ON news_articles (crawl_source);

CREATE INDEX IF NOT EXISTS idx_news_sentiment_label ON news_articles (sentiment_label);

-- ============================================================
-- 뉴스 수집 로그 테이블
-- ============================================================
   CREATE TABLE IF NOT EXISTS news_collection_logs (
          id SERIAL PRIMARY KEY
        , batch_id VARCHAR (50) NOT NULL
        , stock_count INTEGER
        , article_count INTEGER
        , source VARCHAR (50)
        , duration_sec NUMERIC(8, 2)
        , status VARCHAR (20)
        , error_message TEXT
        , created_at TIMESTAMPTZ DEFAULT NOW()
          );

CREATE INDEX IF NOT EXISTS idx_ncl_batch_id ON news_collection_logs (batch_id);

CREATE INDEX IF NOT EXISTS idx_ncl_created_at ON news_collection_logs (created_at);

-- ============================================================
-- 시그널 테이블
-- ============================================================
   CREATE TABLE IF NOT EXISTS signals (
          id SERIAL PRIMARY KEY
        , stock_symbol VARCHAR (10) NOT NULL
        , signal_type VARCHAR (10) NOT NULL
        , final_score NUMERIC(8, 4)
        , text_score NUMERIC(8, 4)
        , numeric_score NUMERIC(8, 4)
        , visual_score NUMERIC(8, 4)
        , macro_score NUMERIC(8, 4)
        , analysis_mode VARCHAR (20)
        , rationale TEXT
        , adjustments JSONB
        , executed BOOLEAN DEFAULT FALSE
        , created_at TIMESTAMPTZ DEFAULT NOW()
          );

CREATE INDEX IF NOT EXISTS idx_signals_stock_symbol ON signals (stock_symbol);

CREATE INDEX IF NOT EXISTS idx_signals_signal_type ON signals (signal_type);

CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals (created_at);

CREATE INDEX IF NOT EXISTS idx_signals_executed ON signals (executed);

-- ============================================================
-- 거래 테이블
-- ============================================================
   CREATE TABLE IF NOT EXISTS trades (
          id SERIAL PRIMARY KEY
        , stock_symbol VARCHAR (10) NOT NULL
        , side VARCHAR (4) NOT NULL
        , qty NUMERIC(12, 4) NOT NULL
        , price NUMERIC(12, 4)
        , order_type VARCHAR (10) DEFAULT 'market'
        , order_id VARCHAR (100)
        , status VARCHAR (20) DEFAULT 'pending'
        , signal_id INTEGER REFERENCES signals (id)
        , pnl NUMERIC(12, 4)
        , exit_reason VARCHAR (30)
        , entry_atr FLOAT
        , created_at TIMESTAMPTZ DEFAULT NOW()
        , updated_at TIMESTAMPTZ DEFAULT NOW()
          );

CREATE INDEX IF NOT EXISTS idx_trades_stock_symbol ON trades (stock_symbol);

CREATE INDEX IF NOT EXISTS idx_trades_status ON trades (status);

CREATE INDEX IF NOT EXISTS idx_trades_created_at ON trades (created_at);

-- ============================================================
-- 포트폴리오 테이블
-- ============================================================
   CREATE TABLE IF NOT EXISTS portfolio (
          id SERIAL PRIMARY KEY
        , stock_symbol VARCHAR (10) UNIQUE NOT NULL
        , qty NUMERIC(12, 4) NOT NULL
        , avg_price NUMERIC(12, 4) NOT NULL
        , current_price NUMERIC(12, 4)
        , unrealized_pnl NUMERIC(12, 4)
        , unrealized_pnl_pct NUMERIC(8, 4)
        , highest_price FLOAT
        , entry_atr FLOAT
        , updated_at TIMESTAMPTZ DEFAULT NOW()
          );

CREATE INDEX IF NOT EXISTS idx_portfolio_stock_symbol ON portfolio (stock_symbol);

-- ============================================================
-- 매크로 레짐 테이블
-- ============================================================
   CREATE TABLE IF NOT EXISTS macro_regime (
          id SERIAL PRIMARY KEY
        , regime VARCHAR (20) NOT NULL
        , regime_score NUMERIC(6, 4) NOT NULL
        , sp500_trend NUMERIC(6, 4)
        , vix_level NUMERIC(8, 4)
        , yield_curve_spread NUMERIC(8, 4)
        , market_rsi NUMERIC(8, 4)
        , market_breadth NUMERIC(6, 4)
        , put_call_ratio NUMERIC(6, 4)
        , macro_news_sentiment NUMERIC(6, 4)
        , leveraged_action VARCHAR (20)
        , created_at TIMESTAMPTZ DEFAULT NOW()
          );

CREATE INDEX IF NOT EXISTS idx_macro_regime_created_at ON macro_regime (created_at);

-- ============================================================
-- 레버리지 포지션 테이블
-- ============================================================
   CREATE TABLE IF NOT EXISTS leveraged_positions (
          id SERIAL PRIMARY KEY
        , symbol VARCHAR (10) NOT NULL
        , side VARCHAR (4) NOT NULL
        , qty NUMERIC(12, 4) NOT NULL
        , entry_price NUMERIC(12, 4) NOT NULL
        , current_price NUMERIC(12, 4)
        , stop_loss NUMERIC(12, 4) NOT NULL
        , take_profit NUMERIC(12, 4) NOT NULL
        , entry_date DATE NOT NULL
        , max_hold_days INTEGER DEFAULT 5
        , consecutive_extreme_days INTEGER DEFAULT 0
        , status VARCHAR (20) DEFAULT 'open'
        , closed_at TIMESTAMPTZ
        , pnl NUMERIC(12, 4)
        , order_id VARCHAR (100)
        , created_at TIMESTAMPTZ DEFAULT NOW()
          );

CREATE INDEX IF NOT EXISTS idx_lp_symbol ON leveraged_positions (symbol);

CREATE INDEX IF NOT EXISTS idx_lp_status ON leveraged_positions (status);

-- ============================================================
-- 백필 진행 상황 테이블
-- ============================================================
   CREATE TABLE IF NOT EXISTS backfill_progress (
          id SERIAL PRIMARY KEY
        , stock_symbol VARCHAR (10) NOT NULL
        , source VARCHAR (30) NOT NULL
        , last_page INTEGER DEFAULT 0
        , last_date DATE
        , article_count INTEGER DEFAULT 0
        , status VARCHAR (20) DEFAULT 'pending'
        , error_message TEXT
        , updated_at TIMESTAMPTZ DEFAULT NOW()
        , UNIQUE(stock_symbol, source)
          );

CREATE INDEX IF NOT EXISTS idx_bp_stock_symbol ON backfill_progress (stock_symbol);

CREATE INDEX IF NOT EXISTS idx_bp_status ON backfill_progress (status);

-- ============================================================
-- 분석 캐시 테이블
-- ============================================================
   CREATE TABLE IF NOT EXISTS analysis_cache (
          id SERIAL PRIMARY KEY
        , stock_symbol VARCHAR (10) NOT NULL
        , analysis_type VARCHAR (20) NOT NULL
        , model_used VARCHAR (50)
        , result JSONB NOT NULL
        , created_at TIMESTAMPTZ DEFAULT NOW()
        , expires_at TIMESTAMPTZ NOT NULL
          );

CREATE INDEX IF NOT EXISTS idx_ac_stock_symbol ON analysis_cache (stock_symbol);

CREATE INDEX IF NOT EXISTS idx_ac_analysis_type ON analysis_cache (analysis_type);

CREATE INDEX IF NOT EXISTS idx_ac_expires_at ON analysis_cache (expires_at);

-- ============================================================
-- 설정 테이블
-- ============================================================
   CREATE TABLE IF NOT EXISTS settings (key VARCHAR (100) PRIMARY KEY, value TEXT NOT NULL, description TEXT, updated_at TIMESTAMPTZ DEFAULT NOW());

-- ============================================================
-- 배치 로그 테이블
-- ============================================================
   CREATE TABLE IF NOT EXISTS batch_logs (
          id SERIAL PRIMARY KEY
        , batch_type VARCHAR (30) NOT NULL
        , step VARCHAR (30)
        , status VARCHAR (20) NOT NULL
        , duration_sec NUMERIC(8, 2)
        , summary JSONB
        , error_message TEXT
        , created_at TIMESTAMPTZ DEFAULT NOW()
          );

CREATE INDEX IF NOT EXISTS idx_bl_batch_type ON batch_logs (batch_type);

CREATE INDEX IF NOT EXISTS idx_bl_created_at ON batch_logs (created_at);

-- ============================================================
-- Default settings INSERT
-- ============================================================
   INSERT INTO settings (key, value, description)
   VALUES ('analysis_mode', 'text_numeric', 'text_numeric 또는 full')
        , ('total_capital', '100000', '총 투자 자본 USD')
        , ('w_text', '0.35', '텍스트 가중치 (text_numeric 모드)')
        , ('w_numeric', '0.50', '수치 가중치 (text_numeric 모드)')
        , ('w_visual', '0.00', '시각 가중치 (text_numeric 모드)')
        , ('w_macro', '0.15', '매크로 가중치')
        , ('w_text_full', '0.25', '텍스트 가중치 (full 모드)')
        , ('w_numeric_full', '0.35', '수치 가중치 (full 모드)')
        , ('w_visual_full', '0.25', '시각 가중치 (full 모드)')
        , ('w_macro_full', '0.15', '매크로 가중치 (full 모드)')
        , ('ollama_fast_model', 'qwen3:4b', '1차 분류 모델')
        , ('ollama_deep_model', 'qwen3:8b', '2차 분석 모델')
        , ('ollama_vision_model', 'qwen3-vl:8b', '시각 분석 모델')
        , ('ollama_embed_model', 'bge-m3', '임베딩 모델')
        , ('leveraged_enabled', 'false', '레버리지 ON/OFF')
        , ('leveraged_max_pct', '0.03', '레버리지 최대 자본 비율')
        , ('leveraged_stop_loss', '0.08', '손절 비율')
        , ('leveraged_take_profit', '0.15', '익절 비율')
        , ('leveraged_max_hold_days', '5', '최대 보유일')
        , ('leveraged_min_extreme_days', '3', 'EXTREME 최소 연속일')
        , ('max_order_amount', '1000', '1회 최대 주문 USD')
        , ('daily_order_limit', '50', '일일 최대 주문 수')
        , ('max_exposure_pct', '0.70', '총 투자 한도 비율')
         , ('news_round_robin_size', '50', '뉴스 1회 종목 수')
         , ('news_interval_minutes', '10', '뉴스 수집 간격 분')
         , ('backfill_years', '2', '백필 기간 년')
         , ('hard_stop_atr_mult', '2.5', 'ATR 하드 스탑 배수')
         , ('trailing_stop_atr_mult', '2.0', 'ATR 트레일링 스탑 배수')
         , ('max_holding_days', '20', '최대 보유일')
         , ('partial_exit_atr_mult', '3.0', '부분 익절 ATR 배수')
         , ('use_atr_sizing', 'false', 'ATR 기반 포지션 사이징 사용')
         , ('risk_per_trade_pct', '1.0', '거래당 리스크 비율 (%)')
         , ('max_single_order_pct', '5.0', '단일 주문 최대 비율 (%)')
         , ('sector_cap_pct', '30.0', '섹터별 최대 노출 비율 (%)')
         , ('min_order_amount', '200', '최소 주문 금액 USD')
         , ('max_positions', '20', '최대 동시 보유 포지션 수') ON CONFLICT (key) DO NOTHING;

-- ============================================================
-- 시그널 성과 추적 테이블
-- 시그널 발생 후 1d/5d/10d/20d 실제 수익률 기록
-- ============================================================
   CREATE TABLE IF NOT EXISTS signal_performance (
          id SERIAL PRIMARY KEY
        , signal_id INTEGER REFERENCES signals (id) NOT NULL
        , stock_symbol VARCHAR (10) NOT NULL
        , signal_type VARCHAR (10) NOT NULL
        , final_score NUMERIC(8, 4)
        , signal_date DATE NOT NULL
        , price_at_signal NUMERIC(12, 4) NOT NULL
        , -- 실제 수익률 (시그널 발생 시점 대비)
          price_1d NUMERIC(12, 4)
        , price_5d NUMERIC(12, 4)
        , price_10d NUMERIC(12, 4)
        , price_20d NUMERIC(12, 4)
        , return_1d NUMERIC(8, 4)
        , return_5d NUMERIC(8, 4)
        , return_10d NUMERIC(8, 4)
        , return_20d NUMERIC(8, 4)
        , -- 시그널 적중 여부
          hit_1d BOOLEAN, -- BUY→상승 or SELL→하락이면 TRUE
          hit_5d BOOLEAN
        , hit_10d BOOLEAN
        , hit_20d BOOLEAN
        , -- 최대 유리/불리 움직임 (5d 이내)
          max_favorable NUMERIC(8, 4), -- 최대 유리 수익률
          max_adverse NUMERIC(8, 4), -- 최대 불리 수익률
          -- 추적 상태
          status VARCHAR (20) DEFAULT 'pending', -- pending / partial / completed
          last_updated TIMESTAMPTZ DEFAULT NOW()
        , created_at TIMESTAMPTZ DEFAULT NOW()
          );

CREATE INDEX IF NOT EXISTS idx_sp_signal_id ON signal_performance (signal_id);

CREATE INDEX IF NOT EXISTS idx_sp_stock_symbol ON signal_performance (stock_symbol);

CREATE INDEX IF NOT EXISTS idx_sp_signal_date ON signal_performance (signal_date);

CREATE INDEX IF NOT EXISTS idx_sp_status ON signal_performance (status);

-- ============================================================
-- 일별 포트폴리오 스냅샷
-- 매일 장 마감 시점의 포트폴리오 상태 기록
-- ============================================================
   CREATE TABLE IF NOT EXISTS daily_snapshot (
          id SERIAL PRIMARY KEY
        , snapshot_date DATE UNIQUE NOT NULL
        , total_value NUMERIC(14, 4) NOT NULL, -- 현금 + 포지션 가치
          cash_balance NUMERIC(14, 4)
        , positions_value NUMERIC(14, 4)
        , position_count INTEGER DEFAULT 0
        , daily_pnl NUMERIC(12, 4), -- 전일 대비 P&L
          daily_return_pct NUMERIC(8, 4), -- 전일 대비 수익률 %
          cumulative_pnl NUMERIC(14, 4), -- 누적 P&L
          cumulative_return NUMERIC(8, 4), -- 누적 수익률 %
          -- 당일 활동
          buy_count INTEGER DEFAULT 0
        , sell_count INTEGER DEFAULT 0
        , signals_generated INTEGER DEFAULT 0
        , signals_buy INTEGER DEFAULT 0
        , signals_sell INTEGER DEFAULT 0
        , signals_hold INTEGER DEFAULT 0
        , -- 벤치마크 (SPY)
          spy_price NUMERIC(12, 4)
        , spy_daily_return NUMERIC(8, 4)
        , spy_cumulative NUMERIC(8, 4)
        , -- 매크로
          macro_regime VARCHAR (20)
        , macro_score NUMERIC(6, 4)
        , created_at TIMESTAMPTZ DEFAULT NOW()
          );

CREATE INDEX IF NOT EXISTS idx_ds_snapshot_date ON daily_snapshot (snapshot_date);

-- ============================================================
-- 주간 모델 성능 리포트
-- 매주 일요일 rule-based / LSTM / 앙상블 성능 비교
-- ============================================================
   CREATE TABLE IF NOT EXISTS weekly_report (
          id SERIAL PRIMARY KEY
        , week_start DATE NOT NULL
        , week_end DATE NOT NULL
        , -- 시그널 통계
          total_signals INTEGER DEFAULT 0
        , buy_signals INTEGER DEFAULT 0
        , sell_signals INTEGER DEFAULT 0
        , hold_signals INTEGER DEFAULT 0
        , -- Rule-based 적중률 (5d 기준)
          rule_accuracy_5d NUMERIC(6, 4), -- 전체 적중률
          rule_precision_buy NUMERIC(6, 4), -- BUY 시그널 중 실제 상승 비율
          rule_precision_sell NUMERIC(6, 4), -- SELL 시그널 중 실제 하락 비율
          rule_avg_return_5d NUMERIC(8, 4), -- 시그널 따른 평균 수익률
          -- LSTM 적중률 (모델 있을 때만)
          lstm_accuracy_5d NUMERIC(6, 4)
        , lstm_precision_up NUMERIC(6, 4)
        , lstm_precision_down NUMERIC(6, 4)
        , lstm_avg_return_5d NUMERIC(8, 4)
        , -- 포트폴리오 성과
          portfolio_return NUMERIC(8, 4), -- 주간 포트폴리오 수익률
          spy_return NUMERIC(8, 4), -- SPY 주간 수익률
          alpha NUMERIC(8, 4), -- 포트폴리오 - SPY
          -- 위험 지표
          max_drawdown NUMERIC(8, 4)
        , sharpe_ratio NUMERIC(8, 4), -- 주간 기준
          win_rate NUMERIC(6, 4), -- 수익 거래 / 전체 거래
          report_data JSONB, -- 상세 데이터
          created_at TIMESTAMPTZ DEFAULT NOW()
          );

CREATE INDEX IF NOT EXISTS idx_wr_week_start ON weekly_report (week_start);

-- ============================================================
-- Migration: Missing Tables and Columns
-- ============================================================

-- ============================================================
-- 1. stock_daily 테이블
-- ============================================================
CREATE TABLE IF NOT EXISTS stock_daily (
      id SERIAL PRIMARY KEY
    , symbol VARCHAR(10) NOT NULL
    , trade_date DATE NOT NULL
    , open NUMERIC(12, 4)
    , high NUMERIC(12, 4)
    , low NUMERIC(12, 4)
    , close NUMERIC(12, 4)
    , volume BIGINT
    , adj_close NUMERIC(12, 4)
    , rsi_14 NUMERIC(8, 4)
    , sma_20 NUMERIC(12, 4)
    , sma_60 NUMERIC(12, 4)
    , macd NUMERIC(12, 6)
    , macd_signal NUMERIC(12, 6)
    , macd_histogram NUMERIC(12, 6)
    , bollinger_upper NUMERIC(12, 4)
    , bollinger_lower NUMERIC(12, 4)
    , bollinger_pct_b NUMERIC(8, 4)
    , volume_ratio NUMERIC(8, 4)
    , atr_14 NUMERIC(12, 4)
    , sector_id INTEGER REFERENCES sectors(id)
    , created_at TIMESTAMPTZ DEFAULT NOW()
    , UNIQUE(symbol, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_stock_daily_symbol ON stock_daily(symbol);
CREATE INDEX IF NOT EXISTS idx_stock_daily_trade_date ON stock_daily(trade_date);
CREATE INDEX IF NOT EXISTS idx_stock_daily_sector_id ON stock_daily(sector_id);
CREATE INDEX IF NOT EXISTS idx_stock_daily_symbol_date ON stock_daily(symbol, trade_date);

-- ============================================================
-- 2. geopolitical_events 테이블
-- ============================================================
CREATE TABLE IF NOT EXISTS geopolitical_events (
      id SERIAL PRIMARY KEY
    , title VARCHAR(500) NOT NULL
    , body TEXT
    , source VARCHAR(100)
    , url TEXT
    , url_hash VARCHAR(64) UNIQUE NOT NULL
    , published_at TIMESTAMPTZ
    , crawled_at TIMESTAMPTZ DEFAULT NOW()
    , category VARCHAR(50)
    , severity VARCHAR(20)
    , sentiment_score NUMERIC(6, 4)
    , market_impact_score NUMERIC(6, 4)
    , affected_sectors TEXT[]
    , is_escalation BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_geopolitical_events_url_hash ON geopolitical_events(url_hash);
CREATE INDEX IF NOT EXISTS idx_geopolitical_events_published_at ON geopolitical_events(published_at);
CREATE INDEX IF NOT EXISTS idx_geopolitical_events_category ON geopolitical_events(category);
CREATE INDEX IF NOT EXISTS idx_geopolitical_events_severity ON geopolitical_events(severity);
CREATE INDEX IF NOT EXISTS idx_geopolitical_events_is_escalation ON geopolitical_events(is_escalation);

-- ============================================================
-- 3. geopolitical_regime 테이블
-- ============================================================
CREATE TABLE IF NOT EXISTS geopolitical_regime (
      id SERIAL PRIMARY KEY
    , war_risk NUMERIC(6, 4)
    , financial_crisis_risk NUMERIC(6, 4)
    , sanctions_risk NUMERIC(6, 4)
    , pandemic_risk NUMERIC(6, 4)
    , political_risk NUMERIC(6, 4)
    , trade_war_risk NUMERIC(6, 4)
    , terrorism_risk NUMERIC(6, 4)
    , natural_disaster_risk NUMERIC(6, 4)
    , composite_risk NUMERIC(6, 4)
    , risk_regime VARCHAR(20)
    , risk_trend VARCHAR(20)
    , market_sentiment_impact NUMERIC(6, 4)
    , safe_haven_signal VARCHAR(20)
    , top_events JSONB
    , created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_geopolitical_regime_created_at ON geopolitical_regime(created_at);
CREATE INDEX IF NOT EXISTS idx_geopolitical_regime_risk_regime ON geopolitical_regime(risk_regime);

-- ============================================================
-- 4. system_alerts 테이블
-- ============================================================
CREATE TABLE IF NOT EXISTS system_alerts (
      id SERIAL PRIMARY KEY
    , severity VARCHAR(20) NOT NULL
    , category VARCHAR(50) NOT NULL
    , message TEXT NOT NULL
    , auto_action VARCHAR(100)
    , resolved BOOLEAN DEFAULT FALSE
    , created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_system_alerts_severity ON system_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_system_alerts_category ON system_alerts(category);
CREATE INDEX IF NOT EXISTS idx_system_alerts_resolved ON system_alerts(resolved);
CREATE INDEX IF NOT EXISTS idx_system_alerts_created_at ON system_alerts(created_at);

-- ============================================================
-- 5. news_articles 테이블에 컬럼 추가 (ALTER TABLE)
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='news_articles' AND column_name='full_text') THEN
        ALTER TABLE news_articles ADD COLUMN full_text TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='news_articles' AND column_name='full_text_crawled') THEN
        ALTER TABLE news_articles ADD COLUMN full_text_crawled BOOLEAN DEFAULT FALSE;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='news_articles' AND column_name='full_text_length') THEN
        ALTER TABLE news_articles ADD COLUMN full_text_length INTEGER;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='news_articles' AND column_name='gemini_embedded') THEN
        ALTER TABLE news_articles ADD COLUMN gemini_embedded BOOLEAN DEFAULT FALSE;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='news_articles' AND column_name='embedding_model') THEN
        ALTER TABLE news_articles ADD COLUMN embedding_model VARCHAR(50);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='news_articles' AND column_name='embedding_dim') THEN
        ALTER TABLE news_articles ADD COLUMN embedding_dim INTEGER;
    END IF;
END $$;

-- news_articles 인덱스 추가
CREATE INDEX IF NOT EXISTS idx_news_full_text_crawled ON news_articles(full_text_crawled);
CREATE INDEX IF NOT EXISTS idx_news_gemini_embedded ON news_articles(gemini_embedded);

-- ============================================================
-- 6. macro_regime 테이블에 컬럼 추가 (ALTER TABLE)
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='macro_regime' AND column_name='geopolitical_risk') THEN
        ALTER TABLE macro_regime ADD COLUMN geopolitical_risk NUMERIC(6, 4);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='macro_regime' AND column_name='geopolitical_regime') THEN
        ALTER TABLE macro_regime ADD COLUMN geopolitical_regime VARCHAR(20);
    END IF;
END $$;
