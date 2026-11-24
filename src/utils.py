"""Utility functions for DevFind.

Covers input validation, stable ID generation, data normalization,
and common helper routines used across modules.
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_SEVERITIES = {"Critical", "High", "Medium", "Low"}
VALID_STATUSES = {"Open", "In Progress", "Resolved", "Closed", "Reopened"}
VALID_SOURCES = {"synthetic", "github", "manual"}
VALID_REVIEW_STATUSES = {"pending", "confirmed_dup", "distinct"}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_issue(data: dict[str, Any]) -> list[str]:
    """Validate issue dict fields. Returns list of error messages (empty = valid)."""
    errors: list[str] = []

    title = data.get("title", "")
    if not title or not isinstance(title, str) or len(title.strip()) < 3:
        errors.append("'title' must be a non-empty string with at least 3 characters.")
    elif len(title) > 500:
        errors.append("'title' must not exceed 500 characters.")

    description = data.get("description", "")
    if description and not isinstance(description, str):
        errors.append("'description' must be a string.")
    elif description and len(description) > 10_000:
        errors.append("'description' must not exceed 10,000 characters.")

    severity = data.get("severity")
    if severity and severity not in VALID_SEVERITIES:
        errors.append(f"'severity' must be one of {sorted(VALID_SEVERITIES)}. Got: {severity!r}")

    status = data.get("status")
    if status and status not in VALID_STATUSES:
        errors.append(f"'status' must be one of {sorted(VALID_STATUSES)}. Got: {status!r}")

    source = data.get("source")
    if source and source not in VALID_SOURCES:
        errors.append(f"'source' must be one of {sorted(VALID_SOURCES)}. Got: {source!r}")

    issue_key = data.get("issue_key", "")
    if issue_key and not re.match(r"^[A-Za-z0-9_\-]+$", str(issue_key)):
        errors.append(f"'issue_key' must contain only alphanumeric characters, hyphens, or underscores. Got: {issue_key!r}")

    return errors


def validate_knowledge_chunk(data: dict[str, Any]) -> list[str]:
    """Validate knowledge chunk dict. Returns error messages."""
    errors: list[str] = []
    if not data.get("content") or not isinstance(data["content"], str):
        errors.append("'content' is required and must be a string.")
    elif len(data["content"].strip()) < 10:
        errors.append("'content' must be at least 10 characters.")
    if not data.get("source_name"):
        errors.append("'source_name' is required.")
    return errors


# ---------------------------------------------------------------------------
# ID generation
# ---------------------------------------------------------------------------

def stable_issue_uuid(issue_key: str, source: str = "") -> uuid.UUID:
    """Generate a deterministic UUID for an issue from its key and source.

    Using UUIDv5 with the DNS namespace ensures the same issue always gets
    the same UUID, enabling idempotent inserts and upserts.
    """
    seed = f"{source}:{issue_key}".lower().strip()
    return uuid.uuid5(uuid.NAMESPACE_DNS, seed)


def stable_github_uuid(repo_full_name: str, issue_number: int) -> uuid.UUID:
    """Generate a deterministic UUID for a GitHub issue."""
    seed = f"github:{repo_full_name}#{issue_number}".lower()
    return uuid.uuid5(uuid.NAMESPACE_DNS, seed)


def stable_knowledge_uuid(doc_id: str, chunk_index: int) -> uuid.UUID:
    """Generate a deterministic UUID for a knowledge chunk."""
    seed = f"knowledge:{doc_id}:chunk:{chunk_index}"
    return uuid.uuid5(uuid.NAMESPACE_DNS, seed)


def content_hash(text: str) -> str:
    """Return a short SHA-256 hex digest of text (first 16 chars)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def normalize_issue(data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of data with defaults filled in and fields sanitized."""
    now = utc_now_iso()
    normalized = {
        "issue_key":     str(data.get("issue_key", "") or "").strip(),
        "title":         str(data.get("title", "") or "").strip(),
        "description":   str(data.get("description", "") or "").strip(),
        "severity":      data.get("severity") or "Medium",
        "status":        data.get("status") or "Open",
        "component":     str(data.get("component", "") or "").strip(),
        "project":       str(data.get("project", "") or "").strip(),
        "resolution":    str(data.get("resolution", "") or "").strip(),
        "created_at":    data.get("created_at") or now,
        "updated_at":    data.get("updated_at") or now,
        "source":        data.get("source") or "manual",
        "source_url":    str(data.get("source_url", "") or "").strip(),
        "duplicate_of":  str(data.get("duplicate_of", "") or "").strip(),
        "review_status": data.get("review_status") or "pending",
        "reviewed_by":   str(data.get("reviewed_by", "") or "").strip(),
        "reviewed_at":   str(data.get("reviewed_at", "") or "").strip(),
        "tags":          list(data.get("tags") or []),
    }
    return normalized


def normalize_github_issue(raw: dict[str, Any], repo_full_name: str) -> dict[str, Any]:
    """Convert a raw GitHub Issues API response to a DevFindIssue dict."""
    number = raw.get("number", 0)
    body = raw.get("body") or ""
    labels = [lbl.get("name", "") for lbl in (raw.get("labels") or [])]
    return {
        "issue_key":    f"GH-{repo_full_name.replace('/', '_')}-{number}",
        "title":        (raw.get("title") or "")[:500],
        "description":  body[:10_000],
        "severity":     _gh_labels_to_severity(labels),
        "status":       "Open" if raw.get("state") == "open" else "Resolved",
        "component":    _gh_labels_to_component(labels),
        "project":      repo_full_name,
        "resolution":   "",
        "created_at":   raw.get("created_at") or utc_now_iso(),
        "updated_at":   raw.get("updated_at") or utc_now_iso(),
        "source":       "github",
        "source_url":   raw.get("html_url") or "",
        "duplicate_of": "",
        "review_status":"pending",
        "reviewed_by":  "",
        "reviewed_at":  "",
        "tags":         labels,
    }


def _gh_labels_to_severity(labels: list[str]) -> str:
    label_lower = [l.lower() for l in labels]
    if any("critical" in l or "blocker" in l for l in label_lower):
        return "Critical"
    if any("high" in l or "major" in l for l in label_lower):
        return "High"
    if any("low" in l or "minor" in l for l in label_lower):
        return "Low"
    return "Medium"


def _gh_labels_to_component(labels: list[str]) -> str:
    """Best-effort component extraction from GitHub labels."""
    component_keywords = [
        "auth", "search", "ui", "api", "database", "payment",
        "notification", "email", "profile", "reporting", "mobile",
    ]
    for label in labels:
        for kw in component_keywords:
            if kw in label.lower():
                return label.title()
    return ""


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def utc_now_iso() -> str:
    """Return current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def parse_iso(ts: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp string to a timezone-aware datetime."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Search result helpers
# ---------------------------------------------------------------------------

def format_search_result(obj: Any, score: Optional[float] = None) -> dict[str, Any]:
    """Convert a Weaviate query result object to a plain dict for display."""
    props = obj.properties if hasattr(obj, "properties") else {}
    result: dict[str, Any] = {
        "uuid":         str(obj.uuid) if hasattr(obj, "uuid") else None,
        "issue_key":    props.get("issue_key", ""),
        "title":        props.get("title", ""),
        "description":  props.get("description", ""),
        "severity":     props.get("severity", ""),
        "status":       props.get("status", ""),
        "component":    props.get("component", ""),
        "project":      props.get("project", ""),
        "source_url":   props.get("source_url", ""),
        "duplicate_of": props.get("duplicate_of", ""),
        "review_status":props.get("review_status", ""),
        "tags":         props.get("tags") or [],
    }
    if score is not None:
        result["score"] = round(float(score), 4)
    # Attach metadata score if available from Weaviate
    if hasattr(obj, "metadata") and obj.metadata:
        meta = obj.metadata
        if hasattr(meta, "score") and meta.score is not None:
            result["score"] = round(float(meta.score), 4)
        if hasattr(meta, "distance") and meta.distance is not None:
            result["distance"] = round(float(meta.distance), 4)
        if hasattr(meta, "certainty") and meta.certainty is not None:
            result["certainty"] = round(float(meta.certainty), 4)
    return result


def truncate(text: str, max_len: int = 200) -> str:
    """Truncate text with ellipsis if longer than max_len."""
    if not text:
        return ""
    return text if len(text) <= max_len else text[:max_len - 3] + "..."
