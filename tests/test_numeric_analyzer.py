"""
Tests for api/services/numeric_analyzer.py

Tests the pure functions that score technical indicators from 0-100.
"""
import pytest
from unittest.mock import AsyncMock, patch
from api.services.numeric_analyzer import (
    _score_rsi,
    _score_macd,
    _score_sma,
    _score_bollinger,
    _score_volume,
    _score_52w_position,
    _score_atr,
    calculate_numeric_score,
)


class TestScoreRSI:
    """Tests for _score_rsi function."""

    def test_rsi_20_returns_95(self):
        """RSI at oversold level (20) should return 95.0 (strong buy signal)."""
        result = _score_rsi(20.0)
        assert result == 95.0, "RSI 20 should return 95.0"

    def test_rsi_50_returns_50(self):
        """RSI at neutral level (50) should return 50.0."""
        result = _score_rsi(50.0)
        assert result == 50.0, "RSI 50 should return 50.0"

    def test_rsi_80_returns_20(self):
        """RSI at overbought level (80) should return 20.0 (weak signal)."""
        result = _score_rsi(80.0)
        assert result == 20.0, "RSI 80 should return 20.0"

    def test_rsi_none_returns_50(self):
        """RSI None should return default neutral score 50.0."""
        result = _score_rsi(None)
        assert result == 50.0, "RSI None should return 50.0"

    def test_rsi_30_in_oversold_range(self):
        """RSI at 30 should return score in oversold range (>80)."""
        result = _score_rsi(30.0)
        assert 80.0 <= result <= 95.0, f"RSI 30 should return score 80-95, got {result}"


class TestScoreMACD:
    """Tests for _score_macd function."""

    def test_macd_golden_cross(self):
        """MACD > signal (golden cross) should return score > 50."""
        result = _score_macd(macd=2.0, macd_signal=1.0, macd_histogram=1.0)
        assert result > 50.0, f"Golden cross should return score > 50, got {result}"

    def test_macd_dead_cross(self):
        """MACD < signal (dead cross) should return score < 50."""
        result = _score_macd(macd=1.0, macd_signal=2.0, macd_histogram=-1.0)
        assert result < 50.0, f"Dead cross should return score < 50, got {result}"

    def test_macd_none_returns_50(self):
        """MACD None should return default neutral score 50.0."""
        result = _score_macd(None, None, None)
        assert result == 50.0, "MACD None should return 50.0"

    def test_macd_signal_none_returns_50(self):
        """MACD signal None should return default neutral score 50.0."""
        result = _score_macd(1.5, None, None)
        assert result == 50.0, "MACD signal None should return 50.0"


class TestScoreBollinger:
    """Tests for _score_bollinger function."""

    def test_pct_b_0_returns_90(self):
        """Bollinger %B at 0 (price at lower band) should return 90.0."""
        result = _score_bollinger(0.0)
        assert result == 90.0, "Bollinger %B 0.0 should return 90.0"

    def test_pct_b_0_5_returns_50(self):
        """Bollinger %B at 0.5 (price at middle) should return 50.0."""
        result = _score_bollinger(0.5)
        assert result == 50.0, "Bollinger %B 0.5 should return 50.0"

    def test_pct_b_1_returns_20(self):
        """Bollinger %B at 1.0 (price at upper band) should return 20.0."""
        result = _score_bollinger(1.0)
        assert abs(result - 20.0) < 0.01, f"Bollinger %B 1.0 should return ~20.0, got {result}"

    def test_pct_b_none_returns_50(self):
        """Bollinger %B None should return default neutral score 50.0."""
        result = _score_bollinger(None)
        assert result == 50.0, "Bollinger %B None should return 50.0"


class TestScoreVolume:
    """Tests for _score_volume function."""

    def test_volume_ratio_2_returns_80(self):
        """Volume ratio 2.0 (high volume) should return 80.0."""
        result = _score_volume(2.0)
        assert result == 80.0, "Volume ratio 2.0 should return 80.0"

    def test_volume_ratio_0_3_returns_30(self):
        """Volume ratio 0.3 (low volume) should return 30.0."""
        result = _score_volume(0.3)
        assert result == 30.0, "Volume ratio 0.3 should return 30.0"

    def test_volume_ratio_none_returns_50(self):
        """Volume ratio None should return default neutral score 50.0."""
        result = _score_volume(None)
        assert result == 50.0, "Volume ratio None should return 50.0"


class TestScore52wPosition:
    """Tests for _score_52w_position function."""

    def test_near_52w_low_returns_85(self):
        """Price near 52-week low (position <= 0.1) should return 85.0."""
        result = _score_52w_position(price=105.0, high_52w=200.0, low_52w=100.0)
        assert result == 85.0, "Price near 52w low should return 85.0"

    def test_near_52w_high_returns_20(self):
        """Price near 52-week high (position > 0.9) should return 20.0."""
        result = _score_52w_position(price=195.0, high_52w=200.0, low_52w=100.0)
        assert result == 20.0, "Price near 52w high should return 20.0"

    def test_52w_position_none_returns_50(self):
        """52-week position with None values should return 50.0."""
        result = _score_52w_position(None, None, None)
        assert result == 50.0, "52w position None should return 50.0"

    def test_52w_high_equals_low_returns_50(self):
        """When 52w high equals low, should return 50.0."""
        result = _score_52w_position(price=100.0, high_52w=100.0, low_52w=100.0)
        assert result == 50.0, "52w high equals low should return 50.0"


class TestScoreATR:
    """Tests for _score_atr function."""

    def test_atr_optimal_volatility_returns_70(self):
        """ATR at optimal volatility (2-3.5%) should return 70.0."""
        # ATR 3.0, price 100.0 => atr_pct = 3.0%
        result = _score_atr(atr=3.0, price=100.0)
        assert result == 70.0, "ATR at optimal volatility (3%) should return 70.0"

    def test_atr_excessive_volatility_returns_25(self):
        """ATR at excessive volatility (7%+) should return 25.0."""
        # ATR 8.0, price 100.0 => atr_pct = 8.0%
        result = _score_atr(atr=8.0, price=100.0)
        assert result == 25.0, "ATR at excessive volatility (8%+) should return 25.0"

    def test_atr_none_returns_50(self):
        """ATR None should return default neutral score 50.0."""
        result = _score_atr(None, 100.0)
        assert result == 50.0, "ATR None should return 50.0"

    def test_atr_price_zero_returns_50(self):
        """ATR with price=0 should return 50.0 to avoid division by zero."""
        result = _score_atr(3.0, 0.0)
        assert result == 50.0, "ATR with price=0 should return 50.0"


class TestCalculateNumericScore:
    """Tests for calculate_numeric_score function (integration test with mocking)."""

    @pytest.mark.asyncio
    async def test_calculate_numeric_score_with_data(self):
        """Should calculate weighted numeric score when data exists."""
        mock_row = {
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

        with patch('api.services.numeric_analyzer.fetch_one', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_row
            result = await calculate_numeric_score("AAPL")

        assert result["symbol"] == "AAPL", "Symbol should be AAPL"
        assert result["status"] == "ok", "Status should be ok"
        assert "score" in result, "Result should contain score"
        assert 0 <= result["score"] <= 100, "Score should be between 0 and 100"
        assert "components" in result, "Result should contain components"

    @pytest.mark.asyncio
    async def test_calculate_numeric_score_no_data(self):
        """Should return default score when no data exists."""
        with patch('api.services.numeric_analyzer.fetch_one', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None
            result = await calculate_numeric_score("UNKNOWN")

        assert result["symbol"] == "UNKNOWN", "Symbol should be UNKNOWN"
        assert result["score"] == 50.0, "Default score should be 50.0"
        assert result["status"] == "no_data", "Status should be no_data"
