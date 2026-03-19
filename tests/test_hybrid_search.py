"""
Tests for api/services/hybrid_search.py

Tests hybrid search combining BGE-M3 and Gemini embeddings using Reciprocal Rank Fusion.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.asyncio

from api.services.hybrid_search import (
    hybrid_search,
    _search_bge_collection,
    _search_gemini_collection,
    _apply_rrf,
    _format_single_source_results,
)


class TestHybridSearch:
    """Tests for hybrid_search function."""

    @pytest.mark.asyncio
    async def test_hybrid_search_both_sources_available(self):
        """Should combine results from both BGE and Gemini using RRF."""
        # Mock BGE results
        bge_results = [
            {
                "id": "1",
                "text": "Article 1 text",
                "metadata": {"article_id": "1", "stock_symbol": "AAPL"},
                "similarity": 0.9,
                "source": "bge",
            },
            {
                "id": "2",
                "text": "Article 2 text",
                "metadata": {"article_id": "2", "stock_symbol": "AAPL"},
                "similarity": 0.8,
                "source": "bge",
            },
        ]

        # Mock Gemini results
        gemini_results = [
            {
                "id": "2",  # Same article appears in both
                "text": "Article 2 text",
                "metadata": {"article_id": "2", "stock_symbol": "AAPL"},
                "similarity": 0.85,
                "source": "gemini",
            },
            {
                "id": "3",
                "text": "Article 3 text",
                "metadata": {"article_id": "3", "stock_symbol": "AAPL"},
                "similarity": 0.75,
                "source": "gemini",
            },
        ]

        with patch("api.services.hybrid_search._search_bge_collection", new=AsyncMock(return_value=bge_results)), \
             patch("api.services.hybrid_search._search_gemini_collection", new=AsyncMock(return_value=gemini_results)):

            results = await hybrid_search("test query", "AAPL", top_k=3)

            assert len(results) == 3, "Should return 3 results"
            # Article 2 should have highest RRF score (appears in both)
            assert results[0]["id"] == "2", "Article 2 should rank first (in both sources)"
            assert "rrf_score" in results[0], "Should have rrf_score field"
            assert "source" in results[0], "Should have source field"
            # Check that Article 2 is marked as coming from both sources
            assert "bge" in results[0]["source"] and "gemini" in results[0]["source"], \
                "Article 2 should show both sources"

    @pytest.mark.asyncio
    async def test_hybrid_search_bge_only_fallback(self):
        """Should use BGE only when Gemini returns no results."""
        bge_results = [
            {
                "id": "1",
                "text": "Article 1 text",
                "metadata": {"article_id": "1", "stock_symbol": "AAPL"},
                "similarity": 0.9,
                "source": "bge",
            },
        ]

        with patch("api.services.hybrid_search._search_bge_collection", new=AsyncMock(return_value=bge_results)), \
             patch("api.services.hybrid_search._search_gemini_collection", new=AsyncMock(return_value=[])):

            results = await hybrid_search("test query", "AAPL", top_k=5)

            assert len(results) == 1, "Should return 1 result from BGE"
            assert results[0]["source"] == "bge", "Should indicate BGE source"
            assert "rrf_score" in results[0], "Should have rrf_score field"

    @pytest.mark.asyncio
    async def test_hybrid_search_gemini_only_fallback(self):
        """Should use Gemini only when BGE returns no results."""
        gemini_results = [
            {
                "id": "1",
                "text": "Article 1 text",
                "metadata": {"article_id": "1", "stock_symbol": "AAPL"},
                "similarity": 0.9,
                "source": "gemini",
            },
        ]

        with patch("api.services.hybrid_search._search_bge_collection", new=AsyncMock(return_value=[])), \
             patch("api.services.hybrid_search._search_gemini_collection", new=AsyncMock(return_value=gemini_results)):

            results = await hybrid_search("test query", "AAPL", top_k=5)

            assert len(results) == 1, "Should return 1 result from Gemini"
            assert results[0]["source"] == "gemini", "Should indicate Gemini source"
            assert "rrf_score" in results[0], "Should have rrf_score field"

    @pytest.mark.asyncio
    async def test_hybrid_search_both_sources_empty(self):
        """Should return empty list when both sources return no results."""
        with patch("api.services.hybrid_search._search_bge_collection", new=AsyncMock(return_value=[])), \
             patch("api.services.hybrid_search._search_gemini_collection", new=AsyncMock(return_value=[])):

            results = await hybrid_search("test query", "AAPL", top_k=5)

            assert results == [], "Should return empty list when both sources are empty"

    @pytest.mark.asyncio
    async def test_hybrid_search_respects_top_k(self):
        """Should return exactly top_k results."""
        # Generate many results
        bge_results = [
            {
                "id": str(i),
                "text": f"Article {i}",
                "metadata": {"article_id": str(i)},
                "similarity": 0.9 - (i * 0.01),
                "source": "bge",
            }
            for i in range(10)
        ]

        gemini_results = [
            {
                "id": str(i + 100),
                "text": f"Article {i + 100}",
                "metadata": {"article_id": str(i + 100)},
                "similarity": 0.85 - (i * 0.01),
                "source": "gemini",
            }
            for i in range(10)
        ]

        with patch("api.services.hybrid_search._search_bge_collection", new=AsyncMock(return_value=bge_results)), \
             patch("api.services.hybrid_search._search_gemini_collection", new=AsyncMock(return_value=gemini_results)):

            results = await hybrid_search("test query", "AAPL", top_k=5)

            assert len(results) == 5, "Should return exactly 5 results"


class TestApplyRRF:
    """Tests for _apply_rrf function."""

    def test_rrf_combines_scores(self):
        """Should combine scores using RRF formula."""
        bge_results = [
            {"id": "1", "text": "Article 1", "metadata": {}, "similarity": 0.9, "source": "bge"},
        ]
        gemini_results = [
            {"id": "1", "text": "Article 1", "metadata": {}, "similarity": 0.85, "source": "gemini"},
        ]

        rrf_results = _apply_rrf(bge_results, gemini_results)

        assert len(rrf_results) == 1, "Should have 1 unique article"
        assert rrf_results[0]["id"] == "1", "Should be article 1"
        # RRF score should be 1/(60+1) + 1/(60+1) = 2/61
        expected_score = 2 / 61
        assert abs(rrf_results[0]["rrf_score"] - expected_score) < 0.0001, \
            "RRF score should be sum of contributions from both sources"
        assert "bge" in rrf_results[0]["source"] and "gemini" in rrf_results[0]["source"], \
            "Should indicate both sources"

    def test_rrf_handles_different_articles(self):
        """Should handle articles that appear in only one source."""
        bge_results = [
            {"id": "1", "text": "Article 1", "metadata": {}, "similarity": 0.9, "source": "bge"},
        ]
        gemini_results = [
            {"id": "2", "text": "Article 2", "metadata": {}, "similarity": 0.85, "source": "gemini"},
        ]

        rrf_results = _apply_rrf(bge_results, gemini_results)

        assert len(rrf_results) == 2, "Should have 2 unique articles"
        article_ids = {r["id"] for r in rrf_results}
        assert article_ids == {"1", "2"}, "Should include both articles"

    def test_rrf_handles_empty_inputs(self):
        """Should handle empty inputs gracefully."""
        assert _apply_rrf([], []) == [], "Empty inputs should return empty list"

        bge_results = [
            {"id": "1", "text": "Article 1", "metadata": {}, "similarity": 0.9, "source": "bge"},
        ]

        assert len(_apply_rrf(bge_results, [])) == 1, "Should handle empty Gemini results"
        assert len(_apply_rrf([], bge_results)) == 1, "Should handle empty BGE results"

    def test_rrf_ranks_by_score(self):
        """Should rank articles by RRF score."""
        # Article 1 in both sources (rank 1 + rank 1)
        # Article 2 in BGE only (rank 2)
        # Article 3 in Gemini only (rank 2)
        bge_results = [
            {"id": "1", "text": "Article 1", "metadata": {}, "similarity": 0.9, "source": "bge"},
            {"id": "2", "text": "Article 2", "metadata": {}, "similarity": 0.8, "source": "bge"},
        ]
        gemini_results = [
            {"id": "1", "text": "Article 1", "metadata": {}, "similarity": 0.85, "source": "gemini"},
            {"id": "3", "text": "Article 3", "metadata": {}, "similarity": 0.75, "source": "gemini"},
        ]

        rrf_results = _apply_rrf(bge_results, gemini_results)

        # Article 1 should have highest score (appears in both, rank 1 in both)
        scores = {r["id"]: r["rrf_score"] for r in rrf_results}
        assert scores["1"] > scores["2"], "Article 1 (both sources) should rank higher than Article 2 (BGE only)"
        assert scores["1"] > scores["3"], "Article 1 (both sources) should rank higher than Article 3 (Gemini only)"


class TestFormatSingleSourceResults:
    """Tests for _format_single_source_results function."""

    def test_formats_results_with_rrf_score(self):
        """Should format results with rrf_score field."""
        results = [
            {
                "id": "1",
                "text": "Article 1",
                "metadata": {"article_id": "1"},
                "similarity": 0.9,
                "source": "bge",
            },
        ]

        formatted = _format_single_source_results(results, "bge", top_k=5)

        assert len(formatted) == 1, "Should return 1 result"
        assert "rrf_score" in formatted[0], "Should have rrf_score field"
        assert formatted[0]["source"] == "bge", "Should preserve source"

    def test_respects_top_k_limit(self):
        """Should limit results to top_k."""
        results = [
            {
                "id": str(i),
                "text": f"Article {i}",
                "metadata": {"article_id": str(i)},
                "similarity": 0.9 - (i * 0.01),
                "source": "bge",
            }
            for i in range(10)
        ]

        formatted = _format_single_source_results(results, "bge", top_k=3)

        assert len(formatted) == 3, "Should return exactly 3 results"


class TestSearchBGECollection:
    """Tests for _search_bge_collection function."""

    @pytest.mark.asyncio
    async def test_search_bge_handles_embedding_failure(self):
        """Should return empty list when embedding fails."""
        with patch("api.services.hybrid_search.embed", new=AsyncMock(return_value=[])):
            results = await _search_bge_collection("test query", None, 5)
            assert results == [], "Should return empty list when embedding fails"

    @pytest.mark.asyncio
    async def test_search_bge_handles_chromadb_error(self):
        """Should return empty list when ChromaDB query fails."""
        with patch("api.services.hybrid_search.embed", new=AsyncMock(return_value=[0.1] * 768)), \
             patch("api.services.hybrid_search.get_collection") as mock_collection:

            # Mock collection to raise an exception
            mock_col = MagicMock()
            mock_col.query.side_effect = Exception("ChromaDB error")
            mock_collection.return_value = mock_col

            results = await _search_bge_collection("test query", None, 5)
            assert results == [], "Should return empty list on ChromaDB error"


class TestSearchGeminiCollection:
    """Tests for _search_gemini_collection function."""

    @pytest.mark.asyncio
    async def test_search_gemini_adds_source_field(self):
        """Should add source field to results."""
        mock_results = [
            {
                "text": "Article 1",
                "metadata": {"article_id": "1"},
                "similarity": 0.9,
            },
        ]

        with patch("api.services.hybrid_search.search_gemini_news", new=AsyncMock(return_value=mock_results)):
            results = await _search_gemini_collection("test query", None, 5)

            assert len(results) == 1, "Should return 1 result"
            assert results[0]["source"] == "gemini", "Should add gemini source"
            assert results[0]["id"] == "1", "Should extract article_id as id"

    @pytest.mark.asyncio
    async def test_search_gemini_handles_error(self):
        """Should return empty list when search fails."""
        with patch("api.services.hybrid_search.search_gemini_news", new=AsyncMock(side_effect=Exception("API error"))):
            results = await _search_gemini_collection("test query", None, 5)
            assert results == [], "Should return empty list on error"
