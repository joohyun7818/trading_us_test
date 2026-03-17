-- 파일: scripts/migrate_001_fulltext_and_geopolitical.sql
-- ============================================================
-- 1) news_articles에 전문 저장 + Gemini 임베딩 컬럼 추가
-- ============================================================
    ALTER TABLE news_articles
      ADD COLUMN IF NOT EXISTS full_text TEXT;

    ALTER TABLE news_articles
      ADD COLUMN IF NOT EXISTS full_text_crawled BOOLEAN DEFAULT FALSE;

    ALTER TABLE news_articles
      ADD COLUMN IF NOT EXISTS full_text_length INTEGER DEFAULT 0;

    ALTER TABLE news_articles
      ADD COLUMN IF NOT EXISTS gemini_embedded BOOLEAN DEFAULT FALSE;

    ALTER TABLE news_articles
      ADD COLUMN IF NOT EXISTS embedding_model VARCHAR (50);

    ALTER TABLE news_articles
      ADD COLUMN IF NOT EXISTS embedding_dim INTEGER;

CREATE INDEX IF NOT EXISTS idx_news_full_text_crawled ON news_articles (full_text_crawled);

CREATE INDEX IF NOT EXISTS idx_news_gemini_embedded ON news_articles (gemini_embedded);

-- ============================================================
-- 2) 국제 정세 (Geopolitical Risk) 테이블
-- ============================================================
   CREATE TABLE IF NOT EXISTS geopolitical_events (
          id SERIAL PRIMARY KEY
        , title VARCHAR (500) NOT NULL
        , body TEXT
        , full_text TEXT
        , source VARCHAR (50) NOT NULL
        , url TEXT
        , url_hash VARCHAR (64) UNIQUE NOT NULL
        , published_at TIMESTAMPTZ
        , crawled_at TIMESTAMPTZ DEFAULT NOW()
        , -- 카테고리 분류
          category VARCHAR (30) NOT NULL, -- war, financial_crisis, sanctions, terrorism, pandemic, political, natural_disaster, trade_war
          severity NUMERIC(4, 2), -- 0~10 심각도
          -- 감성/영향 분석
          sentiment_score NUMERIC(6, 4)
        , market_impact_score NUMERIC(6, 4), -- -1(극심한 악영향) ~ +1(호영향)
          affected_regions TEXT[], -- {'US','EU','Asia','Middle East',...}
          affected_sectors TEXT[], -- {'Energy','Defense','Technology',...}
          -- 임베딩
          gemini_embedded BOOLEAN DEFAULT FALSE
        , embedding_model VARCHAR (50)
        , -- 메타
          is_escalation BOOLEAN DEFAULT FALSE, -- 위기 확대 여부
          crisis_id VARCHAR (50) -- 같은 위기 이벤트 그룹핑
          );

CREATE INDEX IF NOT EXISTS idx_geo_category ON geopolitical_events (category);

CREATE INDEX IF NOT EXISTS idx_geo_published_at ON geopolitical_events (published_at);

CREATE INDEX IF NOT EXISTS idx_geo_severity ON geopolitical_events (severity);

CREATE INDEX IF NOT EXISTS idx_geo_crisis_id ON geopolitical_events (crisis_id);

-- ============================================================
-- 3) 국제 정세 레짐 (일별 스냅샷)
-- ============================================================
   CREATE TABLE IF NOT EXISTS geopolitical_regime (
          id SERIAL PRIMARY KEY
        , -- 개별 리스크 점수 (0~1, 1=최대 위험)
          war_risk NUMERIC(6, 4) DEFAULT 0.0
        , financial_crisis_risk NUMERIC(6, 4) DEFAULT 0.0
        , sanctions_risk NUMERIC(6, 4) DEFAULT 0.0
        , pandemic_risk NUMERIC(6, 4) DEFAULT 0.0
        , political_risk NUMERIC(6, 4) DEFAULT 0.0
        , trade_war_risk NUMERIC(6, 4) DEFAULT 0.0
        , terrorism_risk NUMERIC(6, 4) DEFAULT 0.0
        , natural_disaster_risk NUMERIC(6, 4) DEFAULT 0.0
        , -- 종합
          composite_risk NUMERIC(6, 4) DEFAULT 0.0, -- 가중 합산
          risk_regime VARCHAR (20), -- STABLE / ELEVATED / HIGH / CRISIS
          risk_trend VARCHAR (20), -- IMPROVING / STABLE / DETERIORATING
          -- 시장 영향 추정
          market_sentiment_impact NUMERIC(6, 4), -- 매크로 점수에 적용할 조정값 (-0.3 ~ +0.1)
          safe_haven_signal BOOLEAN DEFAULT FALSE, -- 안전자산 신호 (금, 채권, USD 강세)
          -- 상세
          top_events JSONB, -- 주요 이벤트 요약
          created_at TIMESTAMPTZ DEFAULT NOW()
          );

CREATE INDEX IF NOT EXISTS idx_georegime_created_at ON geopolitical_regime (created_at);

-- ============================================================
-- 4) macro_regime에 국제정세 점수 컬럼 추가
-- ============================================================
    ALTER TABLE macro_regime
      ADD COLUMN IF NOT EXISTS geopolitical_risk NUMERIC(6, 4);

    ALTER TABLE macro_regime
      ADD COLUMN IF NOT EXISTS geopolitical_regime VARCHAR (20);

-- ============================================================
-- 5) settings 추가
-- ============================================================
   INSERT INTO settings (key, value, description)
   VALUES ('gemini_api_key', '', 'Gemini API Key')
        , ('gemini_embed_model', 'gemini-embedding-001', 'Gemini 임베딩 모델')
        , ('gemini_embed_dim', '768', 'Gemini 임베딩 차원 (768/1536/3072)')
        , ('gemini_embed_enabled', 'false', 'Gemini 임베딩 활성화')
        , ('geopolitical_enabled', 'true', '국제정세 분석 활성화')
        , ('geopolitical_weight', '0.10', '매크로 레짐 내 국제정세 가중치')
        , ('fulltext_crawl_enabled', 'true', '기사 전문 크롤링 활성화')
        , ('fulltext_crawl_batch_size', '20', '전문 크롤링 1회 배치 크기')
        , ('fulltext_max_length', '10000', '전문 최대 저장 길이') ON CONFLICT (key) DO NOTHING;