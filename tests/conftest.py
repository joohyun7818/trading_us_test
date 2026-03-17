"""
Common test fixtures and configuration for AlphaFlow US tests.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import Any, Dict, Optional


@pytest.fixture
def mock_db_fetch_one():
    """Mock for database fetch_one function."""
    async def _fetch_one(query: str, *args) -> Optional[Dict[str, Any]]:
        return None
    return AsyncMock(side_effect=_fetch_one)


@pytest.fixture
def mock_db_fetch_all():
    """Mock for database fetch_all function."""
    async def _fetch_all(query: str, *args) -> list:
        return []
    return AsyncMock(side_effect=_fetch_all)


@pytest.fixture
def mock_db_execute():
    """Mock for database execute function."""
    async def _execute(query: str, *args) -> None:
        pass
    return AsyncMock(side_effect=_execute)


@pytest.fixture
def sample_stock_data():
    """Sample stock data for testing."""
    return {
        "current_price": 150.0,
        "rsi_14": 45.0,
        "sma_20": 145.0,
        "sma_60": 140.0,
        "macd": 1.5,
        "macd_signal": 1.0,
        "macd_histogram": 0.5,
        "bollinger_upper": 160.0,
        "bollinger_lower": 140.0,
        "bollinger_pct_b": 0.5,
        "volume_ratio": 1.2,
        "high_52w": 200.0,
        "low_52w": 100.0,
        "atr_14": 4.5,
    }


@pytest.fixture
def mock_ollama_generate():
    """Mock for Ollama generate function."""
    async def _generate(prompt: str, system: str = None, temperature: float = 0.3, num_predict: int = 2048) -> str:
        return '{"sentiment_score": 0.5, "confidence": 0.8, "outlook": "neutral", "rationale": "Test"}'
    return AsyncMock(side_effect=_generate)


@pytest.fixture
def mock_search_similar_news():
    """Mock for search_similar_news function."""
    async def _search(query: str, symbol: Optional[str] = None, top_k: int = 3) -> list:
        if symbol:
            return [{"text": f"News about {symbol}", "score": 0.9}]
        return []
    return AsyncMock(side_effect=_search)


@pytest.fixture
def mock_search_and_build_prompt():
    """Mock for search_and_build_prompt function."""
    async def _search_and_build(symbol: str, current_indicators: Optional[dict] = None) -> str:
        return f"Analyze {symbol} stock with the following data..."
    return AsyncMock(side_effect=_search_and_build)
