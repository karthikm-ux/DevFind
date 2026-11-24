"""GitHub Issues integration for DevFind.

Imports and incrementally synchronizes issues from a GitHub repository.
Uses idempotent UUIDs (stable_github_uuid) so repeated imports are safe.

Requirements:
    - GITHUB_TOKEN env var with repo read permissions
    - GITHUB_REPO_OWNER and GITHUB_REPO_NAME env vars

Always set credentials as environment variables; never hardcode them.
Use dry_run=True to preview what would be imported without writing to Weaviate.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

import requests

from src.db.issues import upsert_issue
from src.utils import normalize_github_issue, stable_github_uuid, utc_now_iso

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
DEFAULT_PER_PAGE = 100
DEFAULT_REQUEST_TIMEOUT = 30  # seconds


class GitHubRateLimitError(Exception):
    """Raised when the GitHub API rate limit is exceeded."""


class GitHubAuthError(Exception):
    """Raised when GitHub authentication fails."""


class GitHubIntegration:
    """Safe, idempotent GitHub Issues importer.

    Example usage:
        gh = GitHubIntegration.from_env()
        result = gh.import_issues(client, dry_run=True)
        print(result)
    """

    def __init__(
        self,
        token: str,
        repo_owner: str,
        repo_name: str,
        *,
        per_page: int = DEFAULT_PER_PAGE,
        max_pages: Optional[int] = None,
    ) -> None:
        if not token:
            raise GitHubAuthError("GitHub token is required. Set GITHUB_TOKEN environment variable.")
        self.token = token
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.repo_full_name = f"{repo_owner}/{repo_name}"
        self.per_page = min(per_page, 100)
        self.max_pages = max_pages
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    @classmethod
    def from_env(cls) -> "GitHubIntegration":
        """Create from environment variables.

        Raises:
            EnvironmentError: If required variables are missing.
            GitHubAuthError: If GITHUB_TOKEN is absent.
        """
        token = os.getenv("GITHUB_TOKEN", "")
        owner = os.getenv("GITHUB_REPO_OWNER", "")
        repo = os.getenv("GITHUB_REPO_NAME", "")

        if not token:
            raise GitHubAuthError(
                "GITHUB_TOKEN environment variable is not set. "
                "Create a Personal Access Token with 'repo' read permissions."
            )
        if not owner or not repo:
            raise EnvironmentError(
                "GITHUB_REPO_OWNER and GITHUB_REPO_NAME environment variables are required."
            )
        return cls(token=token, repo_owner=owner, repo_name=repo)

    def _get(self, path: str, params: Optional[dict] = None) -> requests.Response:
        """Make a GET request, raising on auth/rate-limit errors."""
        url = f"{GITHUB_API_BASE}{path}"
        try:
            resp = self._session.get(url, params=params, timeout=DEFAULT_REQUEST_TIMEOUT)
        except requests.exceptions.ConnectionError as exc:
            raise ConnectionError(f"Network failure connecting to GitHub API: {exc}") from exc
        except requests.exceptions.Timeout:
            raise TimeoutError(f"GitHub API request timed out: {url}")

        if resp.status_code == 401:
            raise GitHubAuthError("GitHub authentication failed. Check your GITHUB_TOKEN.")
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            reset_ts = resp.headers.get("X-RateLimit-Reset", "unknown")
            raise GitHubRateLimitError(
                f"GitHub API rate limit exceeded. Resets at UNIX timestamp {reset_ts}."
            )
        if resp.status_code == 404:
            raise FileNotFoundError(
                f"Repository {self.repo_full_name} not found or not accessible."
            )
        resp.raise_for_status()
        return resp

    def fetch_issues_page(self, page: int = 1, state: str = "all") -> list[dict]:
        """Fetch one page of issues (excludes pull requests)."""
        resp = self._get(
            f"/repos/{self.repo_owner}/{self.repo_name}/issues",
            params={
                "state": state,
                "per_page": self.per_page,
                "page": page,
                "sort": "created",
                "direction": "desc",
            },
        )
        raw_items = resp.json()
        # Filter out pull requests (they have a 'pull_request' key)
        return [item for item in raw_items if "pull_request" not in item]

    def fetch_all_issues(
        self,
        *,
        state: str = "all",
        since: Optional[str] = None,
    ) -> list[dict]:
        """Fetch all issues from the repository, paginating automatically.

        Args:
            state:  'open' | 'closed' | 'all'
            since:  ISO-8601 timestamp for incremental sync (only issues
                    updated after this timestamp).

        Returns:
            List of raw GitHub issue dicts.
        """
        all_issues: list[dict] = []
        page = 1
        while True:
            if self.max_pages and page > self.max_pages:
                logger.info("Reached max_pages limit (%d). Stopping.", self.max_pages)
                break

            logger.info("Fetching issues page %d from %s...", page, self.repo_full_name)
            try:
                items = self.fetch_issues_page(page=page, state=state)
            except GitHubRateLimitError:
                logger.warning("Rate limited. Waiting 60 seconds before retrying...")
                time.sleep(60)
                items = self.fetch_issues_page(page=page, state=state)

            if not items:
                break

            # Apply since filter if provided
            if since:
                filtered = []
                for item in items:
                    updated = item.get("updated_at") or ""
                    if updated >= since:
                        filtered.append(item)
                    else:
                        # Issues are sorted by created desc; once we pass the
                        # since point we can stop (for recent sync)
                        break
                all_issues.extend(filtered)
                if len(filtered) < len(items):
                    break
            else:
                all_issues.extend(items)

            if len(items) < self.per_page:
                break
            page += 1

        logger.info("Fetched %d issues from %s.", len(all_issues), self.repo_full_name)
        return all_issues

    def normalize_issues(self, raw_issues: list[dict]) -> list[dict]:
        """Convert raw GitHub API responses to DevFindIssue-compatible dicts."""
        return [normalize_github_issue(raw, self.repo_full_name) for raw in raw_issues]

    def import_issues(
        self,
        client: Any,  # weaviate.WeaviateClient
        *,
        state: str = "all",
        since: Optional[str] = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Import issues from GitHub into Weaviate.

        Args:
            client:   Connected Weaviate client.
            state:    Issue state filter ('open'|'closed'|'all').
            since:    ISO timestamp for incremental sync.
            dry_run:  If True, only preview without writing to Weaviate.

        Returns:
            Summary dict with counts and any errors.
        """
        summary: dict[str, Any] = {
            "repo": self.repo_full_name,
            "dry_run": dry_run,
            "fetched": 0,
            "inserted": 0,
            "updated": 0,
            "failed": 0,
            "errors": [],
            "started_at": utc_now_iso(),
            "completed_at": None,
        }

        try:
            raw_issues = self.fetch_all_issues(state=state, since=since)
            normalized = self.normalize_issues(raw_issues)
            summary["fetched"] = len(normalized)

            if dry_run:
                logger.info(
                    "[DRY RUN] Would import %d issues from %s.",
                    len(normalized), self.repo_full_name,
                )
                summary["completed_at"] = utc_now_iso()
                summary["dry_run_preview"] = [
                    {"issue_key": i["issue_key"], "title": i["title"], "status": i["status"]}
                    for i in normalized[:20]  # Show first 20 in preview
                ]
                return summary

            for issue_data in normalized:
                try:
                    _, action = upsert_issue(client, issue_data)
                    if action == "inserted":
                        summary["inserted"] += 1
                    else:
                        summary["updated"] += 1
                except Exception as exc:
                    summary["failed"] += 1
                    summary["errors"].append({
                        "issue_key": issue_data.get("issue_key"),
                        "error": str(exc),
                    })
                    logger.warning("Failed to import issue %s: %s", issue_data.get("issue_key"), exc)

        except (GitHubAuthError, GitHubRateLimitError, ConnectionError, TimeoutError) as exc:
            summary["errors"].append({"fatal": str(exc)})
            logger.error("GitHub import failed: %s", exc)
        except Exception as exc:
            summary["errors"].append({"unexpected": str(exc)})
            logger.exception("Unexpected error during GitHub import: %s", exc)

        summary["completed_at"] = utc_now_iso()
        logger.info(
            "Import complete: %d inserted, %d updated, %d failed.",
            summary["inserted"], summary["updated"], summary["failed"],
        )
        return summary


# ---------------------------------------------------------------------------
# Synthetic fallback for testing without live GitHub access
# ---------------------------------------------------------------------------

SYNTHETIC_GITHUB_ISSUES = [
    {
        "number": 1001,
        "title": "Login button unresponsive on mobile Safari",
        "body": "Tapping the login button on iPhone/Safari does nothing. Reproduced on iOS 17.",
        "state": "open",
        "html_url": "https://github.com/example/repo/issues/1001",
        "labels": [{"name": "bug"}, {"name": "mobile"}, {"name": "high"}],
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-20T12:00:00Z",
    },
    {
        "number": 1002,
        "title": "Password reset link expires too quickly",
        "body": "The password reset link in the email expires in 5 minutes. Should be 24 hours.",
        "state": "closed",
        "html_url": "https://github.com/example/repo/issues/1002",
        "labels": [{"name": "bug"}, {"name": "auth"}, {"name": "medium"}],
        "created_at": "2024-01-16T09:00:00Z",
        "updated_at": "2024-02-01T08:00:00Z",
    },
    {
        "number": 1003,
        "title": "Search returns no results for valid queries",
        "body": "Using quotes in search terms causes 0 results. e.g. searching 'null pointer' returns nothing.",
        "state": "open",
        "html_url": "https://github.com/example/repo/issues/1003",
        "labels": [{"name": "bug"}, {"name": "search"}, {"name": "high"}],
        "created_at": "2024-01-18T14:00:00Z",
        "updated_at": "2024-01-22T16:00:00Z",
    },
    {
        "number": 1004,
        "title": "CSV export missing last page of records",
        "body": "When downloading data as CSV, the last page of results is always missing from the file.",
        "state": "open",
        "html_url": "https://github.com/example/repo/issues/1004",
        "labels": [{"name": "bug"}, {"name": "reporting"}, {"name": "medium"}],
        "created_at": "2024-01-20T11:00:00Z",
        "updated_at": "2024-01-25T10:00:00Z",
    },
    {
        "number": 1005,
        "title": "Avatar upload fails silently on large files",
        "body": "Uploading an avatar image larger than 2MB appears to succeed but shows broken image.",
        "state": "closed",
        "html_url": "https://github.com/example/repo/issues/1005",
        "labels": [{"name": "bug"}, {"name": "ui"}, {"name": "low"}],
        "created_at": "2024-01-22T13:00:00Z",
        "updated_at": "2024-02-05T09:00:00Z",
    },
]


def load_synthetic_github_issues(
    client: Any,
    repo_full_name: str = "example/devfind-demo",
) -> dict[str, Any]:
    """Load synthetic GitHub issues for testing when credentials are unavailable."""
    from src.utils import normalize_github_issue
    summary = {"inserted": 0, "updated": 0, "failed": 0, "errors": []}
    for raw in SYNTHETIC_GITHUB_ISSUES:
        try:
            normalized = normalize_github_issue(raw, repo_full_name)
            _, action = upsert_issue(client, normalized)
            if action == "inserted":
                summary["inserted"] += 1
            else:
                summary["updated"] += 1
        except Exception as exc:
            summary["failed"] += 1
            summary["errors"].append(str(exc))
    return summary
