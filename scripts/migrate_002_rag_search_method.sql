-- ============================================================
-- Migration 002: RAG Search Method Setting
-- ============================================================
-- Add rag_search_method setting to support hybrid search

INSERT INTO settings (key, value, description)
VALUES ('rag_search_method', 'bge', 'RAG 검색 방법 (bge/gemini/hybrid)')
ON CONFLICT (key) DO NOTHING;
