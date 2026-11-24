"""Unit tests for src/utils.py — all tests run without Weaviate."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from src.utils import (
    VALID_REVIEW_STATUSES,
    VALID_SEVERITIES,
    VALID_STATUSES,
    content_hash,
    format_search_result,
    normalize_github_issue,
    normalize_issue,
    parse_iso,
    stable_github_uuid,
    stable_issue_uuid,
    stable_knowledge_uuid,
    truncate,
    utc_now_iso,
    validate_issue,
    validate_knowledge_chunk,
)


# ---------------------------------------------------------------------------
# validate_issue
# ---------------------------------------------------------------------------

class TestValidateIssue:
    def test_valid_minimal(self):
        assert validate_issue({"title": "Valid title"}) == []

    def test_valid_full(self):
        data = {
            "title": "Login fails",
            "description": "Detailed description here",
            "severity": "High",
            "status": "Open",
            "source": "synthetic",
            "issue_key": "AUTH-101",
        }
        assert validate_issue(data) == []

    def test_missing_title_error(self):
        errors = validate_issue({})
        assert any("title" in e for e in errors)

    def test_empty_title_error(self):
        errors = validate_issue({"title": "  "})
        assert any("title" in e for e in errors)

    def test_short_title_error(self):
        errors = validate_issue({"title": "AB"})
        assert any("title" in e for e in errors)

    def test_long_title_error(self):
        errors = validate_issue({"title": "A" * 501})
        assert any("title" in e for e in errors)

    def test_invalid_severity(self):
        errors = validate_issue({"title": "Valid title", "severity": "Catastrophic"})
        assert any("severity" in e for e in errors)

    def test_invalid_status(self):
        errors = validate_issue({"title": "Valid title", "status": "Broken"})
        assert any("status" in e for e in errors)

    def test_invalid_source(self):
        errors = validate_issue({"title": "Valid title", "source": "jira"})
        assert any("source" in e for e in errors)

    def test_invalid_issue_key_chars(self):
        errors = validate_issue({"title": "Valid", "issue_key": "AUTH 101!"})
        assert any("issue_key" in e for e in errors)

    def test_valid_issue_key_formats(self):
        for key in ["AUTH-101", "PROJ_002", "BUG123"]:
            assert validate_issue({"title": "Valid title", "issue_key": key}) == [], f"Key {key!r} should be valid"

    def test_description_too_long(self):
        errors = validate_issue({"title": "Valid", "description": "X" * 10_001})
        assert any("description" in e for e in errors)

    def test_all_valid_severities(self):
        for sev in VALID_SEVERITIES:
            assert validate_issue({"title": "Valid title", "severity": sev}) == []

    def test_all_valid_statuses(self):
        for st in VALID_STATUSES:
            assert validate_issue({"title": "Valid title", "status": st}) == []


# ---------------------------------------------------------------------------
# validate_knowledge_chunk
# ---------------------------------------------------------------------------

class TestValidateKnowledgeChunk:
    def test_valid_chunk(self):
        errors = validate_knowledge_chunk({"content": "X" * 50, "source_name": "doc.md"})
        assert errors == []

    def test_missing_content(self):
        errors = validate_knowledge_chunk({"source_name": "doc.md"})
        assert any("content" in e for e in errors)

    def test_too_short_content(self):
        errors = validate_knowledge_chunk({"content": "short", "source_name": "doc.md"})
        assert any("content" in e for e in errors)

    def test_missing_source_name(self):
        errors = validate_knowledge_chunk({"content": "X" * 50})
        assert any("source_name" in e for e in errors)


# ---------------------------------------------------------------------------
# Stable UUID generation
# ---------------------------------------------------------------------------

class TestStableUUIDs:
    def test_same_input_same_uuid(self):
        u1 = stable_issue_uuid("AUTH-101", "synthetic")
        u2 = stable_issue_uuid("AUTH-101", "synthetic")
        assert u1 == u2

    def test_different_key_different_uuid(self):
        u1 = stable_issue_uuid("AUTH-101", "synthetic")
        u2 = stable_issue_uuid("AUTH-102", "synthetic")
        assert u1 != u2

    def test_different_source_different_uuid(self):
        u1 = stable_issue_uuid("AUTH-101", "synthetic")
        u2 = stable_issue_uuid("AUTH-101", "github")
        assert u1 != u2

    def test_returns_uuid_type(self):
        assert isinstance(stable_issue_uuid("X", "y"), uuid.UUID)

    def test_github_uuid_stable(self):
        u1 = stable_github_uuid("owner/repo", 123)
        u2 = stable_github_uuid("owner/repo", 123)
        assert u1 == u2

    def test_github_uuid_different_number(self):
        u1 = stable_github_uuid("owner/repo", 1)
        u2 = stable_github_uuid("owner/repo", 2)
        assert u1 != u2

    def test_knowledge_uuid_stable(self):
        u1 = stable_knowledge_uuid("doc-001", 0)
        u2 = stable_knowledge_uuid("doc-001", 0)
        assert u1 == u2

    def test_knowledge_uuid_different_chunk(self):
        u1 = stable_knowledge_uuid("doc-001", 0)
        u2 = stable_knowledge_uuid("doc-001", 1)
        assert u1 != u2


# ---------------------------------------------------------------------------
# normalize_issue
# ---------------------------------------------------------------------------

class TestNormalizeIssue:
    def test_defaults_applied(self):
        result = normalize_issue({"title": "Test issue"})
        assert result["severity"] == "Medium"
        assert result["status"] == "Open"
        assert result["source"] == "manual"
        assert result["review_status"] == "pending"
        assert isinstance(result["tags"], list)

    def test_existing_values_preserved(self):
        data = {
            "title": "Test",
            "severity": "Critical",
            "status": "Resolved",
            "source": "github",
        }
        result = normalize_issue(data)
        assert result["severity"] == "Critical"
        assert result["status"] == "Resolved"
        assert result["source"] == "github"

    def test_whitespace_stripped(self):
        result = normalize_issue({"title": "  Spaced Title  ", "component": "  Auth  "})
        assert result["title"] == "Spaced Title"
        assert result["component"] == "Auth"

    def test_none_fields_default_to_empty(self):
        result = normalize_issue({"title": "Test", "resolution": None, "source_url": None})
        assert result["resolution"] == ""
        assert result["source_url"] == ""


# ---------------------------------------------------------------------------
# normalize_github_issue
# ---------------------------------------------------------------------------

class TestNormalizeGithubIssue:
    def _raw(self, **kwargs):
        defaults = {
            "number": 42,
            "title": "Bug title",
            "body": "Bug description",
            "state": "open",
            "html_url": "https://github.com/org/repo/issues/42",
            "labels": [],
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-02T00:00:00Z",
        }
        defaults.update(kwargs)
        return defaults

    def test_basic_mapping(self):
        result = normalize_github_issue(self._raw(), "org/repo")
        assert result["issue_key"] == "GH-org_repo-42"
        assert result["source"] == "github"
        assert result["source_url"] == "https://github.com/org/repo/issues/42"
        assert result["status"] == "Open"

    def test_closed_state(self):
        result = normalize_github_issue(self._raw(state="closed"), "org/repo")
        assert result["status"] == "Resolved"

    def test_labels_to_severity_critical(self):
        raw = self._raw(labels=[{"name": "critical"}])
        result = normalize_github_issue(raw, "org/repo")
        assert result["severity"] == "Critical"

    def test_labels_to_severity_low(self):
        raw = self._raw(labels=[{"name": "low-priority"}])
        result = normalize_github_issue(raw, "org/repo")
        assert result["severity"] == "Low"

    def test_missing_body_defaults_to_empty(self):
        raw = self._raw(body=None)
        result = normalize_github_issue(raw, "org/repo")
        assert result["description"] == ""

    def test_title_truncated_to_500(self):
        raw = self._raw(title="T" * 600)
        result = normalize_github_issue(raw, "org/repo")
        assert len(result["title"]) == 500

    def test_pr_exclusion_marker(self):
        """Normalized GitHub issues should not have pull_request in them."""
        raw = self._raw()
        raw["pull_request"] = {"url": "..."}  # PR marker
        # normalize_github_issue itself doesn't filter PRS (that's done in fetch)
        # but let's verify the normalized output still processes correctly
        result = normalize_github_issue(raw, "org/repo")
        assert "pull_request" not in result


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_utc_now_iso_format(self):
        ts = utc_now_iso()
        dt = datetime.fromisoformat(ts)
        assert dt.tzinfo is not None

    def test_parse_iso_valid(self):
        dt = parse_iso("2024-01-15T10:00:00+00:00")
        assert isinstance(dt, datetime)

    def test_parse_iso_z_suffix(self):
        dt = parse_iso("2024-01-15T10:00:00Z")
        assert isinstance(dt, datetime)

    def test_parse_iso_none(self):
        assert parse_iso(None) is None

    def test_parse_iso_empty(self):
        assert parse_iso("") is None

    def test_truncate_short(self):
        assert truncate("hello", 100) == "hello"

    def test_truncate_long(self):
        result = truncate("A" * 300, 200)
        assert len(result) == 200
        assert result.endswith("...")

    def test_truncate_empty(self):
        assert truncate("") == ""

    def test_content_hash_consistent(self):
        h1 = content_hash("test text")
        h2 = content_hash("test text")
        assert h1 == h2

    def test_content_hash_different_inputs(self):
        h1 = content_hash("text A")
        h2 = content_hash("text B")
        assert h1 != h2

    def test_content_hash_length(self):
        h = content_hash("anything")
        assert len(h) == 16


# ---------------------------------------------------------------------------
# format_search_result
# ---------------------------------------------------------------------------

class TestFormatSearchResult:
    def _mock_obj(self, issue_key="AUTH-101", title="Test", distance=None):
        class Meta:
            pass
        class Obj:
            properties = {"issue_key": issue_key, "title": title, "severity": "High",
                          "status": "Open", "component": "Auth", "project": "P",
                          "source_url": "", "duplicate_of": "", "review_status": "pending",
                          "description": "desc", "tags": []}
            uuid = uuid.UUID("12345678-1234-5678-1234-567812345678")
            metadata = Meta()
        if distance is not None:
            Obj.metadata.distance = distance
            Obj.metadata.certainty = None
            Obj.metadata.score = None
        else:
            Obj.metadata.distance = None
            Obj.metadata.certainty = None
            Obj.metadata.score = None
        return Obj()

    def test_returns_dict(self):
        result = format_search_result(self._mock_obj())
        assert isinstance(result, dict)

    def test_contains_key_fields(self):
        result = format_search_result(self._mock_obj())
        for field in ["uuid", "issue_key", "title", "severity", "status"]:
            assert field in result

    def test_distance_included(self):
        result = format_search_result(self._mock_obj(distance=0.123))
        assert "distance" in result
        assert result["distance"] == 0.123
