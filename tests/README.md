# AlphaFlow US Trading System - Test Suite

## Overview

Comprehensive pytest test suite for the AlphaFlow US trading system with **67 passing tests** covering core trading logic, sentiment analysis, and signal generation.

## Test Coverage

### 1. `test_numeric_analyzer.py` (26 tests)
Tests for technical indicator scoring functions in `api/services/numeric_analyzer.py`:

- **RSI Scoring** (5 tests): Validates RSI scoring at different levels (20→95, 50→50, 80→20)
- **MACD Scoring** (4 tests): Golden cross, dead cross, and null handling
- **Bollinger Bands** (4 tests): %B scoring at different positions
- **Volume Analysis** (3 tests): Volume ratio scoring
- **52-Week Position** (4 tests): Price position relative to 52-week high/low
- **ATR Volatility** (4 tests): Optimal vs excessive volatility scoring
- **Integration Tests** (2 tests): Full numeric score calculation with DB mocking

### 2. `test_sentiment.py` (14 tests)
Tests for keyword-based sentiment analysis in `api/services/sentiment.py`:

- **Sentiment Analysis** (9 tests): Positive, negative, neutral, mixed, and empty text
- **False Positive Detection**: "outstanding debt" context handling
- **Priced-in Detection** (5 tests): Multiple pattern variations (priced in, already factored, baked into, old news)

### 3. `test_trading_engine.py` (16 tests)
Tests for signal determination and adjustment logic in `api/services/trading_engine.py`:

- **Signal Determination** (7 tests): BUY/SELL/HOLD thresholds and boundaries
- **Adjustments** (9 tests):
  - Priced-in adjustment (-15)
  - RSI overbought/oversold adjustments (±10)
  - Visual pattern adjustments (double bottom/top ±8)
  - Combined adjustments with score clamping [0, 100]

### 4. `test_rag_analyzer.py` (11 tests)
Tests for JSON parsing from LLM responses in `api/services/rag_analyzer.py`:

- **JSON Parsing** (11 tests): Normal JSON, code fences, trailing commas, think tag removal, partial field extraction, edge cases

## Running Tests

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Run All Tests
```bash
pytest tests/
```

### Run Specific Test File
```bash
pytest tests/test_numeric_analyzer.py -v
pytest tests/test_sentiment.py -v
pytest tests/test_trading_engine.py -v
pytest tests/test_rag_analyzer.py -v
```

### Run with Verbose Output
```bash
pytest tests/ -v
```

### Run Specific Test Class or Function
```bash
pytest tests/test_numeric_analyzer.py::TestScoreRSI -v
pytest tests/test_sentiment.py::TestAnalyzeSentimentKeywords::test_priced_in_pattern_detection -v
```

## Test Configuration

Configuration is in `pyproject.toml`:
- Async mode: auto
- Test paths: `tests/`
- Test pattern: `test_*.py`
- Warnings: disabled for cleaner output

## Mocking Strategy

All external dependencies are mocked using `unittest.mock.AsyncMock`:
- Database calls (`fetch_one`, `fetch_all`, `execute`)
- External APIs (Ollama, Alpaca, yfinance)
- No external service dependencies required

Common fixtures are defined in `tests/conftest.py`:
- `mock_db_fetch_one`, `mock_db_fetch_all`, `mock_db_execute`
- `sample_stock_data`
- `mock_ollama_generate`, `mock_search_similar_news`

## Test Results

✅ **67 tests passing (100% success rate)**

```
tests/test_numeric_analyzer.py: 26 passed
tests/test_sentiment.py: 14 passed
tests/test_trading_engine.py: 16 passed
tests/test_rag_analyzer.py: 11 passed
```

## Future Additions

Consider adding tests for:
- `api/services/chart_analyzer.py` (visual pattern detection)
- `api/services/macro_engine.py` (macro regime calculation)
- Integration tests with real database fixtures
- Performance/load tests for batch processing
