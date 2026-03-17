"""
Tests for api/services/trading_engine.py

Tests signal determination, adjustment logic, and pattern-based adjustments.
"""
import pytest
from api.services.trading_engine import (
    _determine_signal,
    _apply_adjustments,
)


class TestDetermineSignal:
    """Tests for _determine_signal function."""

    def test_score_70_returns_buy(self):
        """Score of 70 should return BUY signal."""
        result = _determine_signal(70.0)
        assert result == "BUY", "Score 70 should return BUY"

    def test_score_30_returns_sell(self):
        """Score of 30 should return SELL signal."""
        result = _determine_signal(30.0)
        assert result == "SELL", "Score 30 should return SELL"

    def test_score_50_returns_hold(self):
        """Score of 50 should return HOLD signal."""
        result = _determine_signal(50.0)
        assert result == "HOLD", "Score 50 should return HOLD"

    def test_boundary_70_returns_buy(self):
        """Boundary score of exactly 70.0 should return BUY."""
        result = _determine_signal(70.0)
        assert result == "BUY", "Score 70.0 (boundary) should return BUY"

    def test_boundary_30_returns_sell(self):
        """Boundary score of exactly 30.0 should return SELL."""
        result = _determine_signal(30.0)
        assert result == "SELL", "Score 30.0 (boundary) should return SELL"

    def test_score_above_70_returns_buy(self):
        """Score above 70 should return BUY."""
        result = _determine_signal(85.0)
        assert result == "BUY", "Score 85 should return BUY"

    def test_score_below_30_returns_sell(self):
        """Score below 30 should return SELL."""
        result = _determine_signal(15.0)
        assert result == "SELL", "Score 15 should return SELL"


class TestApplyAdjustments:
    """Tests for _apply_adjustments function."""

    def test_priced_in_adjustment_minus_15(self):
        """Priced-in flag should reduce score by 15."""
        text_result = {"is_priced_in": True}
        adjusted, adjustments = _apply_adjustments(
            base_score=60.0,
            text_result=text_result,
            numeric_result=None,
            visual_result=None,
        )
        assert adjusted == 45.0, f"Priced-in should reduce 60 to 45, got {adjusted}"
        assert len(adjustments) == 1, "Should have 1 adjustment"
        assert adjustments[0]["type"] == "priced_in", "Adjustment type should be priced_in"
        assert adjustments[0]["delta"] == -15, "Delta should be -15"

    def test_rsi_overbought_adjustment_minus_10(self):
        """RSI >= 75 should reduce score by 10."""
        numeric_result = {
            "components": {
                "rsi": {"value": 78.0}
            }
        }
        adjusted, adjustments = _apply_adjustments(
            base_score=60.0,
            text_result=None,
            numeric_result=numeric_result,
            visual_result=None,
        )
        assert adjusted == 50.0, f"RSI overbought should reduce 60 to 50, got {adjusted}"
        assert any(adj["type"] == "overbought_rsi" for adj in adjustments), "Should have overbought_rsi adjustment"

    def test_rsi_oversold_adjustment_plus_10(self):
        """RSI <= 25 should increase score by 10."""
        numeric_result = {
            "components": {
                "rsi": {"value": 22.0}
            }
        }
        adjusted, adjustments = _apply_adjustments(
            base_score=60.0,
            text_result=None,
            numeric_result=numeric_result,
            visual_result=None,
        )
        assert adjusted == 70.0, f"RSI oversold should increase 60 to 70, got {adjusted}"
        assert any(adj["type"] == "oversold_rsi" for adj in adjustments), "Should have oversold_rsi adjustment"

    def test_combined_adjustments_with_clamping(self):
        """Combined adjustments should clamp score to [0, 100]."""
        text_result = {"is_priced_in": True}
        numeric_result = {
            "components": {
                "rsi": {"value": 78.0}
            }
        }
        adjusted, adjustments = _apply_adjustments(
            base_score=72.0,
            text_result=text_result,
            numeric_result=numeric_result,
            visual_result=None,
        )
        # 72 - 15 (priced_in) - 10 (overbought) = 47
        assert adjusted == 47.0, f"Combined adjustments: 72-15-10=47, got {adjusted}"
        assert len(adjustments) == 2, "Should have 2 adjustments"

    def test_double_bottom_pattern_plus_8(self):
        """Double bottom pattern with confidence >= 0.7 should add 8."""
        visual_result = {
            "patterns": [
                {"name": "double_bottom", "confidence": 0.8, "signal": "bullish"}
            ]
        }
        adjusted, adjustments = _apply_adjustments(
            base_score=60.0,
            text_result=None,
            numeric_result=None,
            visual_result=visual_result,
        )
        assert adjusted == 68.0, f"Double bottom should increase 60 to 68, got {adjusted}"
        assert any("double_bottom" in adj["type"] for adj in adjustments), "Should have double_bottom adjustment"

    def test_double_top_pattern_minus_8(self):
        """Double top pattern with confidence >= 0.7 should reduce by 8."""
        visual_result = {
            "patterns": [
                {"name": "double_top", "confidence": 0.75, "signal": "bearish"}
            ]
        }
        adjusted, adjustments = _apply_adjustments(
            base_score=60.0,
            text_result=None,
            numeric_result=None,
            visual_result=visual_result,
        )
        assert adjusted == 52.0, f"Double top should reduce 60 to 52, got {adjusted}"
        assert any("double_top" in adj["type"] for adj in adjustments), "Should have double_top adjustment"

    def test_combination_scenario_priced_in_changes_signal(self):
        """Base=72, priced_in -15 => 57 => should change from BUY to HOLD."""
        text_result = {"is_priced_in": True}
        adjusted, adjustments = _apply_adjustments(
            base_score=72.0,
            text_result=text_result,
            numeric_result=None,
            visual_result=None,
        )
        assert adjusted == 57.0, f"72 - 15 = 57, got {adjusted}"
        signal = _determine_signal(adjusted)
        assert signal == "HOLD", f"Score 57 should be HOLD, got {signal}"

    def test_clamping_at_zero(self):
        """Negative adjusted score should be clamped to 0."""
        text_result = {"is_priced_in": True}
        numeric_result = {
            "components": {
                "rsi": {"value": 78.0}
            }
        }
        visual_result = {
            "patterns": [
                {"name": "double_top", "confidence": 0.8, "signal": "bearish"}
            ]
        }
        adjusted, adjustments = _apply_adjustments(
            base_score=20.0,
            text_result=text_result,
            numeric_result=numeric_result,
            visual_result=visual_result,
        )
        # 20 - 15 - 10 - 8 = -13, should clamp to 0
        assert adjusted == 0.0, f"Negative score should clamp to 0, got {adjusted}"

    def test_clamping_at_100(self):
        """Score above 100 should be clamped to 100."""
        numeric_result = {
            "components": {
                "rsi": {"value": 22.0}
            }
        }
        visual_result = {
            "patterns": [
                {"name": "double_bottom", "confidence": 0.9, "signal": "bullish"},
                {"name": "hammer", "confidence": 0.8, "signal": "bullish"},
            ]
        }
        adjusted, adjustments = _apply_adjustments(
            base_score=90.0,
            text_result=None,
            numeric_result=numeric_result,
            visual_result=visual_result,
        )
        # 90 + 10 + 8 + 8 = 116, should clamp to 100
        assert adjusted == 100.0, f"Score above 100 should clamp to 100, got {adjusted}"
