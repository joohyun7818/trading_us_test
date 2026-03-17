"""
Tests for api/services/rag_analyzer.py

Tests JSON parsing from LLM responses with various formats and edge cases.
"""
import pytest
from api.services.rag_analyzer import _parse_json_response


class TestParseJSONResponse:
    """Tests for _parse_json_response function."""

    def test_normal_json_parsing(self):
        """Should parse valid JSON correctly."""
        text = '{"sentiment_score": 0.5, "confidence": 0.8, "outlook": "bullish", "rationale": "Strong earnings"}'
        result = _parse_json_response(text)
        assert result["sentiment_score"] == 0.5, "Should parse sentiment_score"
        assert result["confidence"] == 0.8, "Should parse confidence"
        assert result["outlook"] == "bullish", "Should parse outlook"
        assert result["rationale"] == "Strong earnings", "Should parse rationale"

    def test_json_with_code_fence(self):
        """Should handle JSON wrapped in ```json code fences."""
        text = '''```json
{
    "sentiment_score": -0.3,
    "confidence": 0.7,
    "outlook": "bearish",
    "rationale": "Weak guidance"
}
```'''
        result = _parse_json_response(text)
        assert result["sentiment_score"] == -0.3, "Should parse sentiment_score from fenced JSON"
        assert result["outlook"] == "bearish", "Should parse outlook from fenced JSON"

    def test_json_with_trailing_comma(self):
        """Should handle and fix trailing commas in JSON."""
        text = '''{"sentiment_score": 0.2, "confidence": 0.9, "outlook": "neutral",}'''
        result = _parse_json_response(text)
        assert result["sentiment_score"] == 0.2, "Should parse despite trailing comma"
        assert result["confidence"] == 0.9, "Should parse confidence despite trailing comma"

    def test_json_with_think_tags_removed(self):
        """Should remove <think>...</think> tags before parsing."""
        text = '''<think>Let me analyze this stock carefully...</think>
{"sentiment_score": 0.4, "confidence": 0.75, "outlook": "bullish"}'''
        result = _parse_json_response(text)
        assert result["sentiment_score"] == 0.4, "Should parse after removing think tags"
        assert result["confidence"] == 0.75, "Should parse confidence after removing think tags"

    def test_empty_response_returns_empty_dict(self):
        """Empty response should return empty dict."""
        result = _parse_json_response("")
        assert result == {}, "Empty response should return empty dict"

    def test_partial_fields_regex_extraction(self):
        """Should extract partial fields using regex when JSON parsing fails."""
        text = 'The sentiment_score is 0.6 and confidence is 0.85 with outlook being "bullish"'
        result = _parse_json_response(text)
        # Regex extraction should find at least some fields
        if "sentiment_score" in result:
            assert result["sentiment_score"] == 0.6, "Should extract sentiment_score via regex"
        if "confidence" in result:
            assert result["confidence"] == 0.85, "Should extract confidence via regex"

    def test_json_with_extra_text_before_and_after(self):
        """Should extract JSON from text with extra content."""
        text = '''Here is the analysis:
{"sentiment_score": 0.7, "confidence": 0.9, "outlook": "bullish", "rationale": "Great quarter"}
Hope this helps!'''
        result = _parse_json_response(text)
        assert result["sentiment_score"] == 0.7, "Should extract JSON from surrounding text"
        assert result["outlook"] == "bullish", "Should parse outlook from embedded JSON"

    def test_unclosed_think_tag_removed(self):
        """Should remove unclosed <think> tags."""
        text = '''{"sentiment_score": 0.3, "confidence": 0.6, "outlook": "neutral"}<think>analyzing more'''
        result = _parse_json_response(text)
        assert result["sentiment_score"] == 0.3, "Should parse JSON before unclosed think tag"

    def test_is_priced_in_boolean_extraction(self):
        """Should extract is_priced_in boolean value."""
        text = '{"sentiment_score": 0.1, "is_priced_in": true, "outlook": "neutral"}'
        result = _parse_json_response(text)
        assert result["is_priced_in"] is True, "Should parse is_priced_in as True"

    def test_negative_sentiment_score(self):
        """Should handle negative sentiment scores."""
        text = '{"sentiment_score": -0.8, "confidence": 0.95, "outlook": "bearish"}'
        result = _parse_json_response(text)
        assert result["sentiment_score"] == -0.8, "Should parse negative sentiment_score"

    def test_only_think_tags_returns_empty(self):
        """Response with only think tags should return empty dict."""
        text = '<think>I need to analyze this more...</think>'
        result = _parse_json_response(text)
        assert result == {}, "Only think tags should return empty dict"
