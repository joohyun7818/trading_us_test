# pydantic BaseSettings로 .env 환경변수 로드
import os
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """AlphaFlow US 전체 환경변수 설정"""

    # ── PostgreSQL ──────────────────────────────────────────
    DATABASE_URL: str = "postgresql://alphaflow:alphaflow123@localhost:5432/alphaflow_us"

    # ── Alpaca API ──────────────────────────────────────────
    ALPACA_API_KEY: str = ""
    ALPACA_SECRET_KEY: str = ""
    ALPACA_BASE_URL: str = "https://paper-api.alpaca.markets"

    # ── Finnhub ─────────────────────────────────────────────
    FINNHUB_API_KEY: str = ""

    # ── Ollama ──────────────────────────────────────────────
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_FAST_MODEL: str = "qwen3:4b"
    OLLAMA_DEEP_MODEL: str = "qwen3:8b"
    OLLAMA_VISION_MODEL: str = "qwen3-vl:8b"
    OLLAMA_EMBED_MODEL: str = "bge-m3"
    OLLAMA_KEEP_ALIVE: str = "0"
    OLLAMA_TIMEOUT_GENERATE: int = 120
    OLLAMA_TIMEOUT_EMBED: int = 60
    OLLAMA_TIMEOUT_VISION: int = 180

    # ── Analysis ────────────────────────────────────────────
    ANALYSIS_MODE: str = "text_numeric"

    # ── Application ─────────────────────────────────────────
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
