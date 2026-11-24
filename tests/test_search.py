"""Unit tests for search result transformation and evaluation metrics.

All tests run without Weaviate — uses mock objects and plain data.
"""
from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import pytest
from src.evaluation import (
    EvalQuery,
    EvalResult,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    evaluate_search_mode,
    AggregatedMetrics,
)
from src.db.search import SearchResult, SearchResponse, DEFAULT_DISTANCE_THRESHOLD


# ---------------------------------------------------------------------------
# Metric unit tests
# ---------------------------------------------------------------------------

class TestPrecisionAtK:
    def test_all_relevant(self):
        assert precision_at_k(["A", "B", "C"], {"A", "B", "C"}, 3) == 1.0

    def test_none_relevant(self):
        assert precision_at_k(["X", "Y", "Z"], {"A", "B"}, 3) == 0.0

    def test_half_relevant(self):
        assert precision_at_k(["A", "X", "B"], {"A", "B"}, 3) == pytest.approx(2/3, rel=1e-3)

    def test_k_greater_than_retrieved(self):
        # Only 2 results but k=5
        assert precision_at_k(["A", "B"], {"A", "B"}, 5) == pytest.approx(2/5, rel=1e-3)

    def test_empty_retrieved(self):
        assert precision_at_k([], {"A"}, 5) == 0.0

    def test_k_zero(self):
        assert precision_at_k(["A"], {"A"}, 0) == 0.0

    def test_first_result_relevant(self):
        assert precision_at_k(["A", "X", "X", "X", "X"], {"A"}, 5) == pytest.approx(1/5, rel=1e-3)


class TestRecallAtK:
    def test_all_found(self):
        assert recall_at_k(["A", "B", "C"], {"A", "B"}, 5) == 1.0

    def test_none_found(self):
        assert recall_at_k(["X", "Y"], {"A", "B"}, 5) == 0.0

    def test_half_found(self):
        assert recall_at_k(["A", "X"], {"A", "B"}, 5) == 0.5

    def test_empty_relevant(self):
        assert recall_at_k(["A", "B"], set(), 5) == 0.0

    def test_empty_retrieved(self):
        assert recall_at_k([], {"A"}, 5) == 0.0

    def test_k_limits_retrieved(self):
        # 3 relevant, A in top 1, B in position 2, C in position 4 (outside k=3)
        assert recall_at_k(["A", "B", "X", "C"], {"A", "B", "C"}, 3) == pytest.approx(2/3, rel=1e-3)


class TestReciprocalRank:
    def test_first_result_relevant(self):
        assert reciprocal_rank(["A", "B", "C"], {"A"}) == 1.0

    def test_second_result_relevant(self):
        assert reciprocal_rank(["X", "A", "C"], {"A"}) == 0.5

    def test_third_result_relevant(self):
        assert reciprocal_rank(["X", "Y", "A"], {"A"}) == pytest.approx(1/3, rel=1e-3)

    def test_none_relevant(self):
        assert reciprocal_rank(["X", "Y"], {"A"}) == 0.0

    def test_empty_retrieved(self):
        assert reciprocal_rank([], {"A"}) == 0.0

    def test_multiple_relevant_uses_first(self):
        assert reciprocal_rank(["X", "A", "B"], {"A", "B"}) == 0.5


# ---------------------------------------------------------------------------
# evaluate_search_mode
# ---------------------------------------------------------------------------

class TestEvaluateSearchMode:
    def _make_search_fn(self, result_keys: list[str]):
        """Return a search function that always returns fixed results."""
        class MockResult:
            def __init__(self, key):
                self.issue_key = key
        class MockResponse:
            def __init__(self, keys):
                self.results = [MockResult(k) for k in keys]
        def search_fn(query):
            return MockResponse(result_keys)
        return search_fn

    def test_perfect_retrieval(self):
        queries = [
            EvalQuery("Q1", "test query", ["AUTH-101", "AUTH-104"], category="duplicate"),
        ]
        fn = self._make_search_fn(["AUTH-101", "AUTH-104", "SRCH-201"])
        results, agg = evaluate_search_mode(fn, queries, k=5)
        assert len(results) == 1
        assert results[0].precision_at_k == pytest.approx(2/5, rel=1e-3)
        assert results[0].recall_at_k == 1.0
        assert results[0].reciprocal_rank == 1.0

    def test_no_relevant_found(self):
        queries = [
            EvalQuery("Q1", "test query", ["AUTH-101"], category="unrelated"),
        ]
        fn = self._make_search_fn(["X", "Y", "Z"])
        results, agg = evaluate_search_mode(fn, queries, k=3)
        assert results[0].precision_at_k == 0.0
        assert results[0].recall_at_k == 0.0
        assert results[0].reciprocal_rank == 0.0

    def test_empty_search_result(self):
        queries = [EvalQuery("Q1", "query", ["AUTH-101"])]
        fn = self._make_search_fn([])
        results, agg = evaluate_search_mode(fn, queries, k=5)
        assert results[0].recall_at_k == 0.0

    def test_aggregation_fields(self):
        queries = [
            EvalQuery("Q1", "q1", ["A"], category="duplicate"),
            EvalQuery("Q2", "q2", ["B"], category="related"),
        ]
        fn = self._make_search_fn(["A", "B"])
        _, agg = evaluate_search_mode(fn, queries, k=5, mode_name="test_mode")
        assert agg.search_mode == "test_mode"
        assert agg.total_queries == 2
        assert 0.0 <= agg.mean_precision_at_k <= 1.0
        assert 0.0 <= agg.mean_recall_at_k <= 1.0
        assert 0.0 <= agg.mean_reciprocal_rank <= 1.0

    def test_search_fn_exception_handled(self):
        """Evaluation should not crash if search raises an exception."""
        queries = [EvalQuery("Q1", "query", ["AUTH-101"])]
        def failing_fn(q):
            raise RuntimeError("simulated failure")
        results, agg = evaluate_search_mode(failing_fn, queries, k=5)
        assert len(results) == 1
        assert results[0].precision_at_k == 0.0


# ---------------------------------------------------------------------------
# SearchResult and SearchResponse dataclasses
# ---------------------------------------------------------------------------

class TestSearchDataclasses:
    def _make_result(self, distance=0.1, threshold=0.25):
        return SearchResult(
            uuid="abc",
            issue_key="AUTH-101",
            title="Login fails",
            description="desc",
            severity="High",
            status="Open",
            component="Auth",
            project="ProjectAlpha",
            source_url="",
            duplicate_of="",
            review_status="pending",
            distance=distance,
            is_candidate=distance <= threshold,
        )

    def test_candidate_flagged_below_threshold(self):
        r = self._make_result(distance=0.15, threshold=0.25)
        assert r.is_candidate is True

    def test_not_candidate_above_threshold(self):
        r = self._make_result(distance=0.35, threshold=0.25)
        assert r.is_candidate is False

    def test_search_response_fields(self):
        resp = SearchResponse(
            results=[],
            query="test",
            search_mode="semantic",
            latency_ms=42.5,
            total_returned=0,
        )
        assert resp.search_mode == "semantic"
        assert resp.latency_ms == 42.5


# ---------------------------------------------------------------------------
# Filter construction (via helper — no Weaviate needed)
# ---------------------------------------------------------------------------

class TestFilterConstruction:
    def test_no_filters_returns_none(self):
        from src.db.search import _build_filters
        result = _build_filters()
        assert result is None

    def test_single_filter(self):
        from src.db.search import _build_filters
        result = _build_filters(status="Open")
        assert result is not None

    def test_multiple_filters(self):
        from src.db.search import _build_filters
        result = _build_filters(status="Open", severity="High", component="Auth")
        assert result is not None

    def test_empty_query_returns_empty_response(self):
        """semantic_search with empty query should not hit Weaviate."""
        from unittest.mock import MagicMock
        from src.db.search import semantic_search
        mock_client = MagicMock()
        response = semantic_search(mock_client, "")
        # Should return empty response without calling Weaviate
        assert response.total_returned == 0
        assert response.results == []
        mock_client.collections.use.assert_not_called()

    def test_empty_query_hybrid_no_call(self):
        from unittest.mock import MagicMock
        from src.db.search import hybrid_search
        mock_client = MagicMock()
        response = hybrid_search(mock_client, "   ")
        assert response.total_returned == 0
        mock_client.collections.use.assert_not_called()

    def test_empty_query_keyword_no_call(self):
        from unittest.mock import MagicMock
        from src.db.search import keyword_search
        mock_client = MagicMock()
        response = keyword_search(mock_client, "")
        assert response.total_returned == 0
        mock_client.collections.use.assert_not_called()
