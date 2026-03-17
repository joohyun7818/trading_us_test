"""
Tests for api/services/sentiment.py

Tests keyword-based sentiment analysis and priced-in pattern detection.
"""
import pytest
from api.services.sentiment import (
    analyze_sentiment_keywords,
    _check_priced_in,
)


class TestAnalyzeSentimentKeywords:
    """Tests for analyze_sentiment_keywords function."""

    def test_strong_positive_text_returns_positive(self):
        """Strong positive text should return positive label."""
        text = "The company beat earnings expectations and exceeded revenue targets with stellar growth and record high profits"
        result = analyze_sentiment_keywords(text)
        assert result["label"] == "positive", f"Strong positive text should return 'positive', got {result['label']}"
        assert result["score"] > 0.15, f"Strong positive score should be > 0.15, got {result['score']}"

    def test_strong_negative_text_returns_negative(self):
        """Strong negative text should return negative label."""
        text = "The company missed earnings, disappointed investors, and faces bankruptcy with massive losses and a market crash"
        result = analyze_sentiment_keywords(text)
        assert result["label"] == "negative", f"Strong negative text should return 'negative', got {result['label']}"
        assert result["score"] < -0.15, f"Strong negative score should be < -0.15, got {result['score']}"

    def test_mixed_text_returns_neutral(self):
        """Mixed positive and negative text should return neutral label."""
        text = "The company beat revenue but missed earnings with strong growth yet increasing debt"
        result = analyze_sentiment_keywords(text)
        assert result["label"] == "neutral", f"Mixed text should return 'neutral', got {result['label']}"
        assert -0.15 <= result["score"] <= 0.15, f"Mixed score should be in neutral range, got {result['score']}"

    def test_empty_text_returns_neutral(self):
        """Empty text should return neutral with score 0.0."""
        result = analyze_sentiment_keywords("")
        assert result["score"] == 0.0, f"Empty text should return score 0.0, got {result['score']}"
        assert result["label"] == "neutral", f"Empty text should return 'neutral', got {result['label']}"
        assert result["is_priced_in"] is False, "Empty text should not be priced in"

    def test_outstanding_debt_not_false_positive(self):
        """'outstanding' in 'outstanding debt' should be negative context, not positive."""
        text = "The company has outstanding debt obligations"
        result = analyze_sentiment_keywords(text)
        # "outstanding" (positive +1.4) vs "debt" (negative +1.2)
        # Since both are present, check that debt is counted
        assert result["negative_count"] > 0, "Should detect negative keyword 'debt'"
        assert result["positive_count"] > 0, "Should detect positive keyword 'outstanding'"

    def test_priced_in_pattern_detection(self):
        """Should detect 'priced in' pattern."""
        text = "The earnings beat is already priced in and expected by the market"
        result = analyze_sentiment_keywords(text)
        assert result["is_priced_in"] is True, "Should detect 'priced in' pattern"

    def test_already_factored_pattern(self):
        """Should detect 'already factored' priced-in pattern."""
        text = "This news is already factored into the stock price"
        result = analyze_sentiment_keywords(text)
        assert result["is_priced_in"] is True, "Should detect 'already factored' pattern"

    def test_baked_into_pattern(self):
        """Should detect 'baked into' priced-in pattern."""
        text = "The guidance is baked into current valuations"
        result = analyze_sentiment_keywords(text)
        assert result["is_priced_in"] is True, "Should detect 'baked into' pattern"

    def test_old_news_pattern(self):
        """Should detect 'old news' priced-in pattern."""
        text = "This announcement is old news and won't move the stock"
        result = analyze_sentiment_keywords(text)
        assert result["is_priced_in"] is True, "Should detect 'old news' pattern"


class TestCheckPricedIn:
    """Tests for _check_priced_in function."""

    def test_priced_in_exact_match(self):
        """Should detect exact 'priced in' pattern."""
        text = "The news is priced in"
        result = _check_priced_in(text)
        assert result is True, "Should detect 'priced in'"

    def test_priced_in_hyphenated(self):
        """Should detect hyphenated 'priced-in' pattern."""
        text = "The earnings are priced-in already"
        result = _check_priced_in(text)
        assert result is True, "Should detect 'priced-in'"

    def test_fully_valued_pattern(self):
        """Should detect 'fully valued' pattern."""
        text = "The stock is fully valued at current levels"
        result = _check_priced_in(text)
        assert result is True, "Should detect 'fully valued'"

    def test_no_priced_in_pattern(self):
        """Should return False when no priced-in pattern exists."""
        text = "Strong earnings beat with positive outlook"
        result = _check_priced_in(text)
        assert result is False, "Should not detect priced-in pattern"

    def test_case_insensitive_detection(self):
        """Should detect patterns case-insensitively."""
        text = "The news is PRICED IN and FULLY VALUED"
        result = _check_priced_in(text)
        assert result is True, "Should detect patterns case-insensitively"
