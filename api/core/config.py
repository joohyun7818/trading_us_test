# pydantic BaseSettings로 .env 환경변수 로드
import os
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """AlphaFlow US 전체 환경변수 설정"""

    # ── Security ────────────────────────────────────────────
    API_KEY: str = ""
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

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
    OLLAMA_FAST_MODEL: str = "qwen3.5:4b"       # 변경: qwen3:4b → qwen3.5:4b
    OLLAMA_DEEP_MODEL: str = "qwen3.5:4b"       # 변경: qwen3:8b → qwen3.5:4b
    OLLAMA_VISION_MODEL: str = "qwen3.5:4b"     # 변경: qwen3-vl:8b → qwen3.5:4b
    OLLAMA_EMBED_MODEL: str = "bge-m3"           # 유지
    OLLAMA_KEEP_ALIVE: str = "0"
    OLLAMA_TIMEOUT_GENERATE: int = 120
    OLLAMA_TIMEOUT_EMBED: int = 60
    OLLAMA_TIMEOUT_VISION: int = 120             # 변경: 180 → 120 (4B는 더 빠름)

    # ── Gemini ──────────────────────────────────────────────
    GEMINI_API_KEY: str = ""
    GEMINI_EMBED_MODEL: str = "gemini-embedding-001"   # 유지
    GEMINI_EMBED_DIM: int = 768                         # 유지
    GEMINI_FLASH_MODEL: str = "gemini-2.5-flash"        # 유지

    # ── Analysis ────────────────────────────────────────────
    ANALYSIS_MODE: str = "full"                  # 변경: text_numeric → full

    # ── Application ─────────────────────────────────────────
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    @property
    def cors_origins_list(self) -> list[str]:
        """CORS_ORIGINS를 쉼표로 분리하여 리스트로 반환한다."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
