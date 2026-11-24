"""Unit tests for GitHub Issues integration — mocked HTTP, no live GitHub needed."""
from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from unittest.mock import MagicMock, patch
import pytest
import responses as responses_lib

from src.github_integration import (
    SYNTHETIC_GITHUB_ISSUES,
    GitHubAuthError,
    GitHubIntegration,
    GitHubRateLimitError,
    load_synthetic_github_issues,
)
from src.utils import normalize_github_issue


# ---------------------------------------------------------------------------
# GitHubIntegration.from_env
# ---------------------------------------------------------------------------

class TestFromEnv:
    def test_raises_without_token(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setenv("GITHUB_REPO_OWNER", "owner")
        monkeypatch.setenv("GITHUB_REPO_NAME", "repo")
        with pytest.raises(GitHubAuthError):
            GitHubIntegration.from_env()

    def test_raises_without_owner(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "tok")
        monkeypatch.delenv("GITHUB_REPO_OWNER", raising=False)
        monkeypatch.setenv("GITHUB_REPO_NAME", "repo")
        with pytest.raises(EnvironmentError):
            GitHubIntegration.from_env()

    def test_raises_without_repo(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "tok")
        monkeypatch.setenv("GITHUB_REPO_OWNER", "owner")
        monkeypatch.delenv("GITHUB_REPO_NAME", raising=False)
        with pytest.raises(EnvironmentError):
            GitHubIntegration.from_env()

    def test_success_with_all_vars(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("GITHUB_REPO_OWNER", "owner")
        monkeypatch.setenv("GITHUB_REPO_NAME", "repo")
        gh = GitHubIntegration.from_env()
        assert gh.repo_full_name == "owner/repo"


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------

class TestConstructor:
    def test_empty_token_raises(self):
        with pytest.raises(GitHubAuthError):
            GitHubIntegration("", "owner", "repo")

    def test_per_page_capped_at_100(self):
        gh = GitHubIntegration("token", "owner", "repo", per_page=200)
        assert gh.per_page == 100

    def test_repo_full_name(self):
        gh = GitHubIntegration("token", "myorg", "myrepo")
        assert gh.repo_full_name == "myorg/myrepo"


# ---------------------------------------------------------------------------
# HTTP error handling (mocked)
# ---------------------------------------------------------------------------

class TestHTTPErrors:
    def _make_gh(self):
        return GitHubIntegration("token", "owner", "repo")

    @responses_lib.activate
    def test_401_raises_auth_error(self):
        responses_lib.add(
            responses_lib.GET,
            "https://api.github.com/repos/owner/repo/issues",
            status=401,
            json={"message": "Bad credentials"},
        )
        gh = self._make_gh()
        with pytest.raises(GitHubAuthError):
            gh.fetch_issues_page(page=1)

    @responses_lib.activate
    def test_403_rate_limit_raises(self):
        responses_lib.add(
            responses_lib.GET,
            "https://api.github.com/repos/owner/repo/issues",
            status=403,
            json={"message": "rate limit exceeded"},
            headers={"X-RateLimit-Reset": "1700000000"},
        )
        gh = self._make_gh()
        with pytest.raises(GitHubRateLimitError):
            gh.fetch_issues_page(page=1)

    @responses_lib.activate
    def test_404_raises_file_not_found(self):
        responses_lib.add(
            responses_lib.GET,
            "https://api.github.com/repos/owner/repo/issues",
            status=404,
            json={"message": "Not Found"},
        )
        gh = self._make_gh()
        with pytest.raises(FileNotFoundError):
            gh.fetch_issues_page(page=1)


# ---------------------------------------------------------------------------
# Pull request exclusion
# ---------------------------------------------------------------------------

class TestPRExclusion:
    @responses_lib.activate
    def test_pull_requests_excluded(self):
        raw_data = [
            {
                "number": 1, "title": "Normal issue", "body": "desc",
                "state": "open", "html_url": "", "labels": [],
                "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-01T00:00:00Z",
            },
            {
                "number": 2, "title": "A pull request", "body": "pr desc",
                "state": "open", "html_url": "", "labels": [],
                "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-01T00:00:00Z",
                "pull_request": {"url": "https://..."},  # This should be excluded
            },
        ]
        responses_lib.add(
            responses_lib.GET,
            "https://api.github.com/repos/owner/repo/issues",
            json=raw_data,
        )
        gh = GitHubIntegration("token", "owner", "repo")
        result = gh.fetch_issues_page()
        assert len(result) == 1
        assert result[0]["title"] == "Normal issue"


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class TestPagination:
    @responses_lib.activate
    def test_pagination_stops_on_empty_page(self):
        page1 = [
            {"number": i, "title": f"Issue {i}", "body": "", "state": "open",
             "html_url": "", "labels": [], "created_at": "2024-01-01T00:00:00Z",
             "updated_at": "2024-01-01T00:00:00Z"}
            for i in range(1, 4)
        ]
        # Register page 1 and page 2 (empty)
        responses_lib.add(
            responses_lib.GET,
            "https://api.github.com/repos/owner/repo/issues",
            json=page1,
        )
        responses_lib.add(
            responses_lib.GET,
            "https://api.github.com/repos/owner/repo/issues",
            json=[],
        )
        gh = GitHubIntegration("token", "owner", "repo", per_page=100)
        result = gh.fetch_all_issues()
        assert len(result) == 3

    def test_max_pages_respected(self):
        gh = GitHubIntegration("token", "owner", "repo", max_pages=2)
        assert gh.max_pages == 2


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------

class TestDryRun:
    @responses_lib.activate
    def test_dry_run_does_not_write_to_weaviate(self):
        raw_data = [
            {"number": 1, "title": "Issue 1", "body": "body", "state": "open",
             "html_url": "", "labels": [], "created_at": "2024-01-01T00:00:00Z",
             "updated_at": "2024-01-01T00:00:00Z"},
        ]
        responses_lib.add(
            responses_lib.GET,
            "https://api.github.com/repos/owner/repo/issues",
            json=raw_data,
        )
        responses_lib.add(
            responses_lib.GET,
            "https://api.github.com/repos/owner/repo/issues",
            json=[],
        )
        mock_client = MagicMock()
        gh = GitHubIntegration("token", "owner", "repo")
        summary = gh.import_issues(mock_client, dry_run=True)
        assert summary["dry_run"] is True
        assert summary["inserted"] == 0
        assert summary["updated"] == 0
        # Client should NOT have been used for writes
        mock_client.collections.use.assert_not_called()


# ---------------------------------------------------------------------------
# normalize_github_issue
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_normalize_preserves_issue_key_structure(self):
        raw = {
            "number": 101,
            "title": "Bug",
            "body": "description",
            "state": "open",
            "html_url": "https://github.com/org/repo/issues/101",
            "labels": [],
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        result = normalize_github_issue(raw, "org/repo")
        assert "GH-" in result["issue_key"]
        assert "101" in result["issue_key"]

    def test_normalize_multiple_labels(self):
        raw = {
            "number": 5, "title": "T", "body": "", "state": "open",
            "html_url": "", "labels": [{"name": "bug"}, {"name": "high"}, {"name": "auth"}],
            "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-01T00:00:00Z",
        }
        result = normalize_github_issue(raw, "org/repo")
        assert result["severity"] == "High"
        assert len(result["tags"]) == 3


# ---------------------------------------------------------------------------
# Synthetic fallback
# ---------------------------------------------------------------------------

class TestSyntheticFallback:
    def test_synthetic_data_count(self):
        assert len(SYNTHETIC_GITHUB_ISSUES) >= 5

    def test_synthetic_data_no_pull_requests(self):
        for issue in SYNTHETIC_GITHUB_ISSUES:
            assert "pull_request" not in issue

    def test_load_synthetic_uses_upsert(self):
        mock_client = MagicMock()
        # Mock the upsert_issue to return a fake result
        with patch("src.github_integration.upsert_issue") as mock_upsert:
            mock_upsert.return_value = ("fake-uuid", "inserted")
            result = load_synthetic_github_issues(mock_client)
        assert result["inserted"] + result["updated"] == len(SYNTHETIC_GITHUB_ISSUES)
        assert result["failed"] == 0

    def test_load_synthetic_handles_upsert_failure(self):
        mock_client = MagicMock()
        with patch("src.github_integration.upsert_issue") as mock_upsert:
            mock_upsert.side_effect = RuntimeError("DB error")
            result = load_synthetic_github_issues(mock_client)
        assert result["failed"] == len(SYNTHETIC_GITHUB_ISSUES)
