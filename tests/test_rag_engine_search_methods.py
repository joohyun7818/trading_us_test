"""
Tests for rag_engine.py search method branching functionality.

Tests that rag_engine correctly routes to bge/gemini/hybrid search based on settings.
"""
import pytest
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.asyncio

from api.services.rag_engine import search_and_build_prompt, _get_rag_search_method


class TestGetRAGSearchMethod:
    """Tests for _get_rag_search_method function."""

    @pytest.mark.asyncio
    async def test_returns_bge_when_setting_is_bge(self):
        """Should return 'bge' when setting is 'bge'."""
        with patch("api.services.rag_engine.fetch_one", new=AsyncMock(return_value={"value": "bge"})):
            method = await _get_rag_search_method()
            assert method == "bge", "Should return 'bge'"

    @pytest.mark.asyncio
    async def test_returns_gemini_when_setting_is_gemini(self):
        """Should return 'gemini' when setting is 'gemini'."""
        with patch("api.services.rag_engine.fetch_one", new=AsyncMock(return_value={"value": "gemini"})):
            method = await _get_rag_search_method()
            assert method == "gemini", "Should return 'gemini'"

    @pytest.mark.asyncio
    async def test_returns_hybrid_when_setting_is_hybrid(self):
        """Should return 'hybrid' when setting is 'hybrid'."""
        with patch("api.services.rag_engine.fetch_one", new=AsyncMock(return_value={"value": "hybrid"})):
            method = await _get_rag_search_method()
            assert method == "hybrid", "Should return 'hybrid'"

    @pytest.mark.asyncio
    async def test_returns_bge_when_setting_not_found(self):
        """Should default to 'bge' when setting is not found."""
        with patch("api.services.rag_engine.fetch_one", new=AsyncMock(return_value=None)):
            method = await _get_rag_search_method()
            assert method == "bge", "Should default to 'bge' when setting not found"

    @pytest.mark.asyncio
    async def test_returns_bge_when_setting_is_invalid(self):
        """Should default to 'bge' when setting value is invalid."""
        with patch("api.services.rag_engine.fetch_one", new=AsyncMock(return_value={"value": "invalid"})):
            method = await _get_rag_search_method()
            assert method == "bge", "Should default to 'bge' when setting is invalid"

    @pytest.mark.asyncio
    async def test_handles_uppercase_setting(self):
        """Should handle uppercase setting values."""
        with patch("api.services.rag_engine.fetch_one", new=AsyncMock(return_value={"value": "HYBRID"})):
            method = await _get_rag_search_method()
            assert method == "hybrid", "Should convert to lowercase and return 'hybrid'"

    @pytest.mark.asyncio
    async def test_returns_bge_on_database_error(self):
        """Should default to 'bge' when database query fails."""
        with patch("api.services.rag_engine.fetch_one", new=AsyncMock(side_effect=Exception("DB error"))):
            method = await _get_rag_search_method()
            assert method == "bge", "Should default to 'bge' on database error"


class TestSearchAndBuildPrompt:
    """Tests for search_and_build_prompt function with search method branching."""

    @pytest.mark.asyncio
    async def test_uses_bge_search_when_method_is_bge(self):
        """Should use search_similar_news when method is 'bge'."""
        mock_bge_results = [
            {
                "text": "BGE article",
                "metadata": {"article_id": "1", "stock_symbol": "AAPL"},
                "similarity": 0.9,
            }
        ]

        with patch("api.services.rag_engine._get_rag_search_method", new=AsyncMock(return_value="bge")), \
             patch("api.services.rag_engine.search_similar_news", new=AsyncMock(return_value=mock_bge_results)) as mock_bge, \
             patch("api.services.rag_engine.search_gemini_news", new=AsyncMock()) as mock_gemini, \
             patch("api.services.rag_engine.hybrid_search", new=AsyncMock()) as mock_hybrid:

            prompt = await search_and_build_prompt("AAPL")

            # Should call BGE search
            mock_bge.assert_called_once()
            # Should not call other search methods
            mock_gemini.assert_not_called()
            mock_hybrid.assert_not_called()
            # Prompt should contain the article text
            assert "AAPL" in prompt, "Prompt should contain symbol"

    @pytest.mark.asyncio
    async def test_uses_gemini_search_when_method_is_gemini(self):
        """Should use search_gemini_news when method is 'gemini'."""
        mock_gemini_results = [
            {
                "text": "Gemini article",
                "metadata": {"article_id": "1", "stock_symbol": "AAPL"},
                "similarity": 0.9,
            }
        ]

        with patch("api.services.rag_engine._get_rag_search_method", new=AsyncMock(return_value="gemini")), \
             patch("api.services.rag_engine.search_similar_news", new=AsyncMock()) as mock_bge, \
             patch("api.services.rag_engine.search_gemini_news", new=AsyncMock(return_value=mock_gemini_results)) as mock_gemini, \
             patch("api.services.rag_engine.hybrid_search", new=AsyncMock()) as mock_hybrid:

            prompt = await search_and_build_prompt("AAPL")

            # Should call Gemini search
            mock_gemini.assert_called_once()
            # Should not call other search methods
            mock_bge.assert_not_called()
            mock_hybrid.assert_not_called()
            # Prompt should contain the article text
            assert "AAPL" in prompt, "Prompt should contain symbol"

    @pytest.mark.asyncio
    async def test_uses_hybrid_search_when_method_is_hybrid(self):
        """Should use hybrid_search when method is 'hybrid'."""
        mock_hybrid_results = [
            {
                "text": "Hybrid article with <html>tags</html>",
                "metadata": {"article_id": "1", "stock_symbol": "AAPL"},
                "rrf_score": 0.05,
                "source": "bge+gemini",
            }
        ]

        with patch("api.services.rag_engine._get_rag_search_method", new=AsyncMock(return_value="hybrid")), \
             patch("api.services.rag_engine.search_similar_news", new=AsyncMock()) as mock_bge, \
             patch("api.services.rag_engine.search_gemini_news", new=AsyncMock()) as mock_gemini, \
             patch("api.services.rag_engine.hybrid_search", new=AsyncMock(return_value=mock_hybrid_results)) as mock_hybrid:

            prompt = await search_and_build_prompt("AAPL")

            # Should call hybrid search
            mock_hybrid.assert_called_once()
            # Should not call other search methods
            mock_bge.assert_not_called()
            mock_gemini.assert_not_called()
            # Prompt should contain the article text (cleaned)
            assert "AAPL" in prompt, "Prompt should contain symbol"
            # HTML tags should be cleaned from hybrid results
            assert "<html>" not in prompt, "HTML tags should be cleaned"

    @pytest.mark.asyncio
    async def test_passes_correct_parameters_to_search_functions(self):
        """Should pass symbol and query to search functions."""
        with patch("api.services.rag_engine._get_rag_search_method", new=AsyncMock(return_value="bge")), \
             patch("api.services.rag_engine.search_similar_news", new=AsyncMock(return_value=[])) as mock_bge:

            await search_and_build_prompt("TSLA", current_indicators={"rsi": 45})

            # Check that search was called with correct parameters
            mock_bge.assert_called_once()
            args, kwargs = mock_bge.call_args
            # Check query contains symbol (first positional arg)
            if args:
                assert "TSLA" in args[0], "Query should contain symbol"
            # Check symbol is passed (second positional arg or keyword arg)
            if len(args) > 1:
                assert args[1] == "TSLA", "Should pass symbol parameter"
            else:
                assert kwargs.get("symbol") == "TSLA", "Should pass symbol parameter"

    @pytest.mark.asyncio
    async def test_handles_empty_search_results(self):
        """Should handle empty search results gracefully."""
        with patch("api.services.rag_engine._get_rag_search_method", new=AsyncMock(return_value="bge")), \
             patch("api.services.rag_engine.search_similar_news", new=AsyncMock(return_value=[])):

            prompt = await search_and_build_prompt("AAPL")

            # Should generate a prompt even with no news
            assert "AAPL" in prompt, "Prompt should contain symbol"
            assert "No recent news" in prompt or "news" in prompt.lower(), \
                "Prompt should indicate no news available"

    @pytest.mark.asyncio
    async def test_includes_current_indicators_in_prompt(self):
        """Should include current indicators in the generated prompt."""
        mock_results = [
            {
                "text": "Article text",
                "metadata": {"article_id": "1"},
                "similarity": 0.9,
            }
        ]
        indicators = {"rsi_14": 45.0, "macd": 1.5}

        with patch("api.services.rag_engine._get_rag_search_method", new=AsyncMock(return_value="bge")), \
             patch("api.services.rag_engine.search_similar_news", new=AsyncMock(return_value=mock_results)):

            prompt = await search_and_build_prompt("AAPL", current_indicators=indicators)

            # Prompt should contain indicators
            assert "rsi_14" in prompt or "45" in prompt, "Prompt should include indicators"
