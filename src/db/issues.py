"""CRUD operations for DevFindIssue collection.

All writes use deterministic UUIDs (UUIDv5) derived from issue_key + source,
so repeated inserts of the same issue are idempotent (upsert behavior).
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

import weaviate
from weaviate.classes.query import Filter

from src.db.schema import ISSUE_COLLECTION
from src.utils import (
    normalize_issue,
    stable_issue_uuid,
    utc_now_iso,
    validate_issue,
)

logger = logging.getLogger(__name__)


def _collection(client: weaviate.WeaviateClient):
    return client.collections.use(ISSUE_COLLECTION)


# ---------------------------------------------------------------------------
# CREATE / UPSERT
# ---------------------------------------------------------------------------

def insert_issue(client: weaviate.WeaviateClient, data: dict[str, Any]) -> uuid.UUID:
    """Insert a new issue. Raises ValueError on validation failure.

    Uses a stable UUID derived from issue_key + source so the same issue
    can be inserted multiple times without duplication (upsert on conflict).
    """
    errors = validate_issue(data)
    if errors:
        raise ValueError(f"Invalid issue data: {'; '.join(errors)}")

    normalized = normalize_issue(data)
    issue_uuid = stable_issue_uuid(
        normalized["issue_key"] or str(uuid.uuid4()),
        normalized["source"],
    )

    col = _collection(client)
    try:
        col.data.insert(properties=normalized, uuid=issue_uuid)
        logger.debug("Inserted issue %s with UUID %s", normalized["issue_key"], issue_uuid)
    except Exception as exc:
        # If object already exists (409-like), attempt update instead
        if "already exists" in str(exc).lower() or "conflict" in str(exc).lower():
            normalized["updated_at"] = utc_now_iso()
            col.data.update(uuid=issue_uuid, properties=normalized)
            logger.debug("Upserted (updated) issue %s", normalized["issue_key"])
        else:
            raise

    return issue_uuid


def upsert_issue(client: weaviate.WeaviateClient, data: dict[str, Any]) -> tuple[uuid.UUID, str]:
    """Insert or update an issue. Returns (uuid, 'inserted'|'updated')."""
    errors = validate_issue(data)
    if errors:
        raise ValueError(f"Invalid issue data: {'; '.join(errors)}")

    normalized = normalize_issue(data)
    issue_uuid = stable_issue_uuid(
        normalized["issue_key"] or str(uuid.uuid4()),
        normalized["source"],
    )

    col = _collection(client)
    existing = col.query.fetch_object_by_id(issue_uuid)
    if existing is not None:
        normalized["updated_at"] = utc_now_iso()
        col.data.update(uuid=issue_uuid, properties=normalized)
        return issue_uuid, "updated"
    else:
        col.data.insert(properties=normalized, uuid=issue_uuid)
        return issue_uuid, "inserted"


def batch_insert_issues(
    client: weaviate.WeaviateClient,
    issues: list[dict[str, Any]],
    *,
    upsert: bool = True,
) -> dict[str, Any]:
    """Insert or upsert a list of issues using Weaviate batch insert.

    Returns a summary dict with counts of inserted, updated, skipped, failed.
    """
    counts = {"inserted": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}

    valid_issues: list[tuple[uuid.UUID, dict]] = []
    for raw in issues:
        errors = validate_issue(raw)
        if errors:
            counts["failed"] += 1
            counts["errors"].append({"issue_key": raw.get("issue_key"), "errors": errors})
            continue
        normalized = normalize_issue(raw)
        issue_uuid = stable_issue_uuid(
            normalized["issue_key"] or str(uuid.uuid4()),
            normalized["source"],
        )
        valid_issues.append((issue_uuid, normalized))

    if not valid_issues:
        return counts

    col = _collection(client)

    if upsert:
        # Check which already exist
        existing_uuids: set[str] = set()
        for batch_start in range(0, len(valid_issues), 50):
            batch = valid_issues[batch_start : batch_start + 50]
            for iuuid, _ in batch:
                obj = col.query.fetch_object_by_id(iuuid)
                if obj is not None:
                    existing_uuids.add(str(iuuid))

        with col.batch.dynamic() as batch:
            for iuuid, props in valid_issues:
                if str(iuuid) in existing_uuids:
                    props["updated_at"] = utc_now_iso()
                    try:
                        col.data.update(uuid=iuuid, properties=props)
                        counts["updated"] += 1
                    except Exception as exc:
                        counts["failed"] += 1
                        counts["errors"].append({"uuid": str(iuuid), "error": str(exc)})
                else:
                    batch.add_object(properties=props, uuid=iuuid)
                    counts["inserted"] += 1
    else:
        with col.batch.dynamic() as batch:
            for iuuid, props in valid_issues:
                batch.add_object(properties=props, uuid=iuuid)
                counts["inserted"] += 1

    return counts


# ---------------------------------------------------------------------------
# READ
# ---------------------------------------------------------------------------

def get_issue_by_id(client: weaviate.WeaviateClient, issue_uuid: uuid.UUID) -> Optional[Any]:
    """Fetch a single issue by Weaviate UUID. Returns None if not found."""
    col = _collection(client)
    return col.query.fetch_object_by_id(issue_uuid)


def get_issue_by_key(client: weaviate.WeaviateClient, issue_key: str) -> Optional[Any]:
    """Fetch the first issue matching issue_key. Returns None if not found."""
    col = _collection(client)
    result = col.query.fetch_objects(
        filters=Filter.by_property("issue_key").equal(issue_key),
        limit=1,
    )
    return result.objects[0] if result.objects else None


def list_issues(
    client: weaviate.WeaviateClient,
    *,
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    component: Optional[str] = None,
    project: Optional[str] = None,
    source: Optional[str] = None,
) -> list[Any]:
    """List issues with optional metadata filters."""
    col = _collection(client)

    filters = None
    filter_chain: list = []
    if status:
        filter_chain.append(Filter.by_property("status").equal(status))
    if severity:
        filter_chain.append(Filter.by_property("severity").equal(severity))
    if component:
        filter_chain.append(Filter.by_property("component").equal(component))
    if project:
        filter_chain.append(Filter.by_property("project").equal(project))
    if source:
        filter_chain.append(Filter.by_property("source").equal(source))

    if len(filter_chain) == 1:
        filters = filter_chain[0]
    elif len(filter_chain) > 1:
        filters = filter_chain[0]
        for f in filter_chain[1:]:
            filters = filters & f

    result = col.query.fetch_objects(filters=filters, limit=limit, offset=offset)
    return result.objects


def count_issues(
    client: weaviate.WeaviateClient,
    *,
    status: Optional[str] = None,
    severity: Optional[str] = None,
) -> int:
    """Return total issue count with optional status/severity filter."""
    col = _collection(client)
    filters = None
    if status and severity:
        filters = (
            Filter.by_property("status").equal(status)
            & Filter.by_property("severity").equal(severity)
        )
    elif status:
        filters = Filter.by_property("status").equal(status)
    elif severity:
        filters = Filter.by_property("severity").equal(severity)

    response = col.aggregate.over_all(total_count=True, filters=filters)
    return response.total_count or 0


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------

def update_issue(
    client: weaviate.WeaviateClient,
    issue_uuid: uuid.UUID,
    updates: dict[str, Any],
) -> bool:
    """Update specific fields of an issue. Returns True on success."""
    col = _collection(client)
    existing = col.query.fetch_object_by_id(issue_uuid)
    if existing is None:
        logger.warning("Update failed: no issue with UUID %s", issue_uuid)
        return False

    updates["updated_at"] = utc_now_iso()
    col.data.update(uuid=issue_uuid, properties=updates)
    logger.debug("Updated issue UUID %s with fields: %s", issue_uuid, list(updates.keys()))
    return True


def record_review(
    client: weaviate.WeaviateClient,
    issue_uuid: uuid.UUID,
    *,
    review_status: str,
    duplicate_of: str = "",
    reviewed_by: str = "developer",
) -> bool:
    """Record a human review decision on a duplicate candidate.

    Args:
        issue_uuid:     UUID of the issue being reviewed.
        review_status:  'confirmed_dup' | 'distinct' | 'pending'
        duplicate_of:   issue_key of the parent if confirmed_dup.
        reviewed_by:    Reviewer identifier.

    Returns:
        True if the update succeeded.
    """
    from src.utils import VALID_REVIEW_STATUSES
    if review_status not in VALID_REVIEW_STATUSES:
        raise ValueError(f"review_status must be one of {VALID_REVIEW_STATUSES}")

    updates: dict[str, Any] = {
        "review_status": review_status,
        "reviewed_by":   reviewed_by,
        "reviewed_at":   utc_now_iso(),
    }
    if review_status == "confirmed_dup":
        if not duplicate_of:
            raise ValueError("duplicate_of must be set when confirming a duplicate.")
        # Prevent self-reference
        existing = get_issue_by_id(client, issue_uuid)
        if existing and existing.properties.get("issue_key") == duplicate_of:
            raise ValueError("An issue cannot be marked as a duplicate of itself.")
        updates["duplicate_of"] = duplicate_of

    return update_issue(client, issue_uuid, updates)


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

def delete_issue(client: weaviate.WeaviateClient, issue_uuid: uuid.UUID) -> bool:
    """Delete an issue by UUID. Returns True if deleted, False if not found."""
    col = _collection(client)
    existing = col.query.fetch_object_by_id(issue_uuid)
    if existing is None:
        logger.warning("Delete skipped: no issue with UUID %s", issue_uuid)
        return False
    col.data.delete_by_id(issue_uuid)
    logger.info("Deleted issue UUID %s", issue_uuid)
    return True


# ---------------------------------------------------------------------------
# STATS
# ---------------------------------------------------------------------------

def get_dashboard_stats(client: weaviate.WeaviateClient) -> dict[str, Any]:
    """Compute dashboard statistics from the DevFindIssue collection."""
    total = count_issues(client)
    open_count = count_issues(client, status="Open")
    in_progress = count_issues(client, status="In Progress")
    resolved = count_issues(client, status="Resolved")
    closed = count_issues(client, status="Closed")

    severity_counts: dict[str, int] = {}
    for sev in ["Critical", "High", "Medium", "Low"]:
        severity_counts[sev] = count_issues(client, severity=sev)

    # Count confirmed duplicates
    col = _collection(client)
    dup_result = col.query.fetch_objects(
        filters=Filter.by_property("review_status").equal("confirmed_dup"),
        limit=1000,
    )
    confirmed_dups = len(dup_result.objects)

    return {
        "total": total,
        "open": open_count,
        "in_progress": in_progress,
        "resolved": resolved,
        "closed": closed,
        "severity_distribution": severity_counts,
        "confirmed_duplicates": confirmed_dups,
    }
