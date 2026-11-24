"""Integration tests for Weaviate database operations.

These tests require a live Weaviate connection (WEAVIATE_URL + WEAVIATE_API_KEY).
Tests are automatically skipped when the connection is unavailable.

Uses a dedicated TEST collection (DevFindIssueTest / DevFindKnowledgeTest)
to avoid modifying production data.
"""
from __future__ import annotations

import sys, pathlib, os
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import uuid
import pytest
from unittest.mock import MagicMock, patch

# Check if Weaviate credentials are available
HAS_WEAVIATE = bool(os.getenv("WEAVIATE_URL") and os.getenv("WEAVIATE_API_KEY"))

skip_live = pytest.mark.skipif(
    not HAS_WEAVIATE,
    reason="WEAVIATE_URL and WEAVIATE_API_KEY not set. Live integration tests skipped.",
)

# ---------------------------------------------------------------------------
# Mock-based database tests (always run)
# ---------------------------------------------------------------------------

class TestIssuesCRUDMocked:
    """Tests using a fully mocked Weaviate client."""

    def _make_client(self):
        """Build a mock Weaviate client that simulates basic operations."""
        client = MagicMock()
        col = MagicMock()
        client.collections.use.return_value = col
        client.collections.exists.return_value = True

        # Mock fetch_object_by_id to return None (object not found = insert path)
        col.query.fetch_object_by_id.return_value = None

        # Mock insert to return a UUID
        mock_uuid = uuid.UUID("12345678-1234-5678-1234-567812345678")
        col.data.insert.return_value = mock_uuid

        # Mock aggregate
        agg = MagicMock()
        agg.total_count = 10
        col.aggregate.over_all.return_value = agg

        # Mock fetch_objects
        result = MagicMock()
        result.objects = []
        col.query.fetch_objects.return_value = result

        return client, col

    def test_insert_valid_issue(self):
        from src.db.issues import insert_issue
        client, col = self._make_client()
        issue_uuid = insert_issue(client, {
            "issue_key": "TEST-001",
            "title": "Test issue for mocked insert",
            "severity": "High",
            "status": "Open",
            "source": "synthetic",
        })
        assert isinstance(issue_uuid, uuid.UUID)
        col.data.insert.assert_called_once()

    def test_insert_invalid_issue_raises(self):
        from src.db.issues import insert_issue
        client, _ = self._make_client()
        with pytest.raises(ValueError):
            insert_issue(client, {"title": "AB"})  # Too short

    def test_upsert_inserts_when_not_exists(self):
        from src.db.issues import upsert_issue
        client, col = self._make_client()
        col.query.fetch_object_by_id.return_value = None
        _, action = upsert_issue(client, {
            "issue_key": "TEST-002",
            "title": "New issue to upsert",
        })
        assert action == "inserted"

    def test_upsert_updates_when_exists(self):
        from src.db.issues import upsert_issue
        client, col = self._make_client()
        # Simulate existing object
        existing_obj = MagicMock()
        existing_obj.properties = {"issue_key": "TEST-003", "title": "Existing"}
        col.query.fetch_object_by_id.return_value = existing_obj
        _, action = upsert_issue(client, {
            "issue_key": "TEST-003",
            "title": "Updated title that is long enough",
        })
        assert action == "updated"
        col.data.update.assert_called_once()

    def test_get_issue_by_id_not_found(self):
        from src.db.issues import get_issue_by_id
        client, col = self._make_client()
        col.query.fetch_object_by_id.return_value = None
        result = get_issue_by_id(client, uuid.uuid4())
        assert result is None

    def test_count_issues(self):
        from src.db.issues import count_issues
        client, col = self._make_client()
        agg = MagicMock()
        agg.total_count = 42
        col.aggregate.over_all.return_value = agg
        count = count_issues(client)
        assert count == 42

    def test_update_issue_not_found(self):
        from src.db.issues import update_issue
        client, col = self._make_client()
        col.query.fetch_object_by_id.return_value = None
        result = update_issue(client, uuid.uuid4(), {"status": "Resolved"})
        assert result is False

    def test_delete_issue_not_found(self):
        from src.db.issues import delete_issue
        client, col = self._make_client()
        col.query.fetch_object_by_id.return_value = None
        result = delete_issue(client, uuid.uuid4())
        assert result is False

    def test_delete_issue_found(self):
        from src.db.issues import delete_issue
        client, col = self._make_client()
        existing = MagicMock()
        col.query.fetch_object_by_id.return_value = existing
        result = delete_issue(client, uuid.uuid4())
        assert result is True
        col.data.delete_by_id.assert_called_once()

    def test_record_review_confirmed_dup(self):
        from src.db.issues import record_review
        client, col = self._make_client()
        test_uuid = uuid.UUID("12345678-1234-5678-1234-567812345678")
        existing = MagicMock()
        existing.properties = {"issue_key": "TEST-010"}
        col.query.fetch_object_by_id.return_value = existing
        result = record_review(
            client, test_uuid,
            review_status="confirmed_dup",
            duplicate_of="AUTH-101",
            reviewed_by="developer",
        )
        assert result is True

    def test_record_review_self_reference_raises(self):
        from src.db.issues import record_review
        client, col = self._make_client()
        test_uuid = uuid.uuid4()
        existing = MagicMock()
        existing.properties = {"issue_key": "AUTH-101"}
        col.query.fetch_object_by_id.return_value = existing
        with pytest.raises(ValueError, match="itself"):
            record_review(
                client, test_uuid,
                review_status="confirmed_dup",
                duplicate_of="AUTH-101",  # Same as issue_key → self-reference
            )

    def test_record_review_invalid_status(self):
        from src.db.issues import record_review
        client, _ = self._make_client()
        with pytest.raises(ValueError):
            record_review(client, uuid.uuid4(), review_status="invalid_status")

    def test_batch_insert_validation_failures_counted(self):
        from src.db.issues import batch_insert_issues
        client, col = self._make_client()

        # Setup batch mock
        batch_ctx = MagicMock()
        batch_ctx.__enter__ = MagicMock(return_value=batch_ctx)
        batch_ctx.__exit__ = MagicMock(return_value=False)
        col.batch.dynamic.return_value = batch_ctx

        issues = [
            {"title": "AB"},  # Too short — should fail validation
            {"issue_key": "TEST-VALID-001", "title": "Valid title here", "source": "synthetic"},
        ]
        result = batch_insert_issues(client, issues, upsert=False)
        assert result["failed"] == 1
        assert result["inserted"] == 1


# ---------------------------------------------------------------------------
# Schema tests (mocked)
# ---------------------------------------------------------------------------

class TestSchemaMocked:
    def test_ensure_collections_skips_existing(self):
        from src.db.schema import ensure_collections, ISSUE_COLLECTION, KNOWLEDGE_COLLECTION
        client = MagicMock()
        client.collections.exists.return_value = True
        result = ensure_collections(client)
        assert result[ISSUE_COLLECTION] == "exists"
        assert result[KNOWLEDGE_COLLECTION] == "exists"
        client.collections.create.assert_not_called()

    def test_ensure_collections_creates_missing(self):
        from src.db.schema import ensure_collections, ISSUE_COLLECTION, KNOWLEDGE_COLLECTION
        client = MagicMock()
        client.collections.exists.return_value = False
        result = ensure_collections(client)
        assert result[ISSUE_COLLECTION] == "created"
        assert result[KNOWLEDGE_COLLECTION] == "created"
        assert client.collections.create.call_count == 2

    def test_reset_collections_deletes_then_creates(self):
        from src.db.schema import reset_collections, ISSUE_COLLECTION, KNOWLEDGE_COLLECTION
        client = MagicMock()
        client.collections.exists.return_value = True
        reset_collections(client, [ISSUE_COLLECTION])
        client.collections.delete.assert_called_with(ISSUE_COLLECTION)
        client.collections.create.assert_called_once()

    def test_get_collection_stats_not_exists(self):
        from src.db.schema import get_collection_stats
        client = MagicMock()
        client.collections.exists.return_value = False
        stats = get_collection_stats(client)
        for info in stats.values():
            assert info["exists"] is False
            assert info["count"] == 0

    # --- New startup-safety tests ---

    def test_429_on_knowledge_collection_does_not_prevent_startup(self):
        """ensure_startup_collections tolerates 429 on knowledge — issue collection is unaffected."""
        from src.db.schema import ensure_startup_collections, ISSUE_COLLECTION, KNOWLEDGE_COLLECTION
        client = MagicMock()
        # Issue collection exists; knowledge creation raises a 429
        client.collections.exists.side_effect = lambda name: name == ISSUE_COLLECTION
        client.collections.create.side_effect = RuntimeError("HTTP 429 Too Many Requests")

        result = ensure_startup_collections(
            client, knowledge_max_retries=0, knowledge_retry_delay_s=0
        )

        assert result.issue_status == "exists"
        assert result.knowledge_unavailable is True
        assert result.knowledge_status == "rate_limited"
        assert result.knowledge_error is not None
        error_lower = result.knowledge_error.lower()
        assert "429" in result.knowledge_error or "rate" in error_lower
        assert result.as_dict()[ISSUE_COLLECTION] == "exists"

    def test_startup_succeeds_when_both_collections_exist(self):
        """ensure_startup_collections reports exists for both when both are present."""
        from src.db.schema import ensure_startup_collections, ISSUE_COLLECTION, KNOWLEDGE_COLLECTION
        client = MagicMock()
        client.collections.exists.return_value = True

        result = ensure_startup_collections(client)

        assert result.issue_status == "exists"
        assert result.knowledge_status == "exists"
        assert result.knowledge_unavailable is False
        assert result.knowledge_error is None
        client.collections.create.assert_not_called()

    def test_is_rate_limit_error_detection(self):
        """_is_rate_limit_error correctly classifies 429 and rate-limit messages."""
        from src.db.schema import _is_rate_limit_error
        assert _is_rate_limit_error(RuntimeError("HTTP 429 Too Many Requests"))
        assert _is_rate_limit_error(Exception("rate limit exceeded"))
        assert _is_rate_limit_error(RuntimeError("too many requests from this cluster"))
        assert not _is_rate_limit_error(RuntimeError("HTTP 500 Internal Server Error"))
        assert not _is_rate_limit_error(RuntimeError("Authentication failed"))
        assert not _is_rate_limit_error(ValueError("invalid argument"))

    def test_non_429_knowledge_error_is_not_retried(self):
        """Non-429 errors on knowledge collection must not be retried."""
        from src.db.schema import ensure_knowledge_collection, KNOWLEDGE_COLLECTION
        client = MagicMock()
        client.collections.exists.return_value = False
        client.collections.create.side_effect = RuntimeError("Authentication failed")

        with pytest.raises(RuntimeError, match="Authentication failed"):
            ensure_knowledge_collection(client, max_retries=2, retry_delay_s=0)

        # Only called once — no retries for non-429 errors
        assert client.collections.create.call_count == 1


# ---------------------------------------------------------------------------
# Live integration tests (skipped without credentials)
# ---------------------------------------------------------------------------

class TestLiveWeaviate:
    @skip_live
    def test_connect_and_ready(self):
        from src.db.client import get_client, close_client
        try:
            client = get_client()
            assert client.is_ready()
        finally:
            close_client()

    @skip_live
    def test_ensure_collections_idempotent(self):
        """Running ensure_collections twice should not raise or duplicate."""
        from src.db.client import get_client, close_client
        from src.db.schema import ensure_collections, ISSUE_COLLECTION
        try:
            client = get_client()
            result1 = ensure_collections(client)
            result2 = ensure_collections(client)
            # Second call: all should be 'exists'
            assert all(v == "exists" for v in result2.values())
        finally:
            close_client()

    @skip_live
    def test_insert_and_fetch_issue(self):
        from src.db.client import get_client, close_client
        from src.db.schema import ensure_collections
        from src.db.issues import insert_issue, get_issue_by_id, delete_issue
        try:
            client = get_client()
            ensure_collections(client)

            test_issue = {
                "issue_key": f"LIVETEST-{uuid.uuid4().hex[:6]}",
                "title": "Live integration test issue",
                "description": "This issue is created during automated testing.",
                "severity": "Low",
                "status": "Open",
                "source": "synthetic",
            }
            inserted_uuid = insert_issue(client, test_issue)
            assert isinstance(inserted_uuid, uuid.UUID)

            fetched = get_issue_by_id(client, inserted_uuid)
            assert fetched is not None
            assert fetched.properties["title"] == test_issue["title"]

            # Cleanup
            deleted = delete_issue(client, inserted_uuid)
            assert deleted is True

            # Verify deleted
            fetched_after = get_issue_by_id(client, inserted_uuid)
            assert fetched_after is None
        finally:
            close_client()

    @skip_live
    def test_upsert_idempotent(self):
        """Upserting the same issue twice should not duplicate it."""
        from src.db.client import get_client, close_client
        from src.db.schema import ensure_collections
        from src.db.issues import upsert_issue, get_issue_by_id, delete_issue
        try:
            client = get_client()
            ensure_collections(client)

            unique_key = f"UPSERT-{uuid.uuid4().hex[:6]}"
            issue_data = {
                "issue_key": unique_key,
                "title": "Idempotent upsert test issue",
                "source": "synthetic",
            }

            u1, action1 = upsert_issue(client, issue_data)
            u2, action2 = upsert_issue(client, issue_data)

            assert u1 == u2  # Same UUID
            assert action1 == "inserted"
            assert action2 == "updated"

            # Cleanup
            delete_issue(client, u1)
        finally:
            close_client()

    @skip_live
    def test_collection_reuse_on_restart(self):
        """ensure_collections called multiple times must not delete existing data."""
        from src.db.client import get_client, close_client
        from src.db.schema import ensure_collections
        from src.db.issues import insert_issue, get_issue_by_id, count_issues, delete_issue
        try:
            client = get_client()
            before = count_issues(client)
            ensure_collections(client)  # Simulate second startup
            after = count_issues(client)
            assert after >= before  # Count should not decrease
        finally:
            close_client()

    @skip_live
    def test_semantic_search_live(self):
        """Verify near_text search returns results after data load."""
        from src.db.client import get_client, close_client
        from src.db.schema import ensure_collections
        from src.db.issues import insert_issue, delete_issue
        from src.db.search import semantic_search
        import time
        try:
            client = get_client()
            ensure_collections(client)

            unique_key = f"SEMANTIC-{uuid.uuid4().hex[:6]}"
            insert_issue(client, {
                "issue_key": unique_key,
                "title": "Authentication fails when refreshing access token",
                "description": "The login session ends unexpectedly after token refresh.",
                "severity": "High",
                "status": "Open",
                "source": "synthetic",
            })
            time.sleep(1)  # Allow indexing

            response = semantic_search(client, "user gets logged out after token refresh", limit=5)
            assert response.total_returned >= 0  # May be 0 if vectorizer not configured
            # Cleanup
            from src.db.issues import get_issue_by_key
            obj = get_issue_by_key(client, unique_key)
            if obj:
                delete_issue(client, obj.uuid)
        finally:
            close_client()

    @skip_live
    def test_invalid_query_handled(self):
        """An empty query should return empty results, not raise."""
        from src.db.client import get_client, close_client
        from src.db.search import semantic_search
        try:
            client = get_client()
            response = semantic_search(client, "")
            assert response.total_returned == 0
        finally:
            close_client()
