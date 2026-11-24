"""Weaviate collection schema definitions for DevFind.

Collections:
    DevFindIssue    — bug/issue reports, primary collection
    DevFindKnowledge — documentation and resolution knowledge chunks

IMPORTANT: Never call ensure_collections() on regular startup without
           checking existing data. Use reset_collections() only from
           the explicit reset_db.py script.

Startup-safe API
----------------
Use ``ensure_startup_collections()`` in app startup. It:
- Treats DevFindIssue as mandatory: raises on any failure.
- Treats DevFindKnowledge as optional: retries on HTTP 429 (bounded),
  marks the result as ``knowledge_unavailable=True`` on exhaustion
  instead of raising.

Backward-compatible API
-----------------------
``ensure_collections()``, ``reset_collections()``, and
``get_collection_stats()`` are unchanged for use by reset_db.py,
run_eval.py, and existing tests.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import weaviate
from weaviate.classes.config import Configure, DataType, Property, VectorDistances

logger = logging.getLogger(__name__)

ISSUE_COLLECTION = "DevFindIssue"
KNOWLEDGE_COLLECTION = "DevFindKnowledge"

# ---------------------------------------------------------------------------
# Property definitions
# ---------------------------------------------------------------------------

ISSUE_PROPERTIES = [
    Property(name="issue_key",    data_type=DataType.TEXT,   description="Unique issue key, e.g. AUTH-101"),
    Property(name="title",        data_type=DataType.TEXT,   description="Short issue title"),
    Property(name="description",  data_type=DataType.TEXT,   description="Detailed issue description"),
    Property(name="severity",     data_type=DataType.TEXT,   description="Critical | High | Medium | Low"),
    Property(name="status",       data_type=DataType.TEXT,   description="Open | In Progress | Resolved | Closed"),
    Property(name="component",    data_type=DataType.TEXT,   description="Application component affected"),
    Property(name="project",      data_type=DataType.TEXT,   description="Project identifier"),
    Property(name="resolution",   data_type=DataType.TEXT,   description="How the issue was resolved"),
    Property(name="created_at",   data_type=DataType.TEXT,   description="ISO-8601 creation timestamp"),
    Property(name="updated_at",   data_type=DataType.TEXT,   description="ISO-8601 last-update timestamp"),
    Property(name="source",       data_type=DataType.TEXT,   description="Origin: synthetic | github | manual"),
    Property(name="source_url",   data_type=DataType.TEXT,   description="Link to original issue"),
    Property(name="duplicate_of", data_type=DataType.TEXT,   description="issue_key of confirmed parent duplicate"),
    Property(name="review_status",data_type=DataType.TEXT,   description="pending | confirmed_dup | distinct"),
    Property(name="reviewed_by",  data_type=DataType.TEXT,   description="Reviewer identifier"),
    Property(name="reviewed_at",  data_type=DataType.TEXT,   description="ISO-8601 review timestamp"),
    Property(name="tags",         data_type=DataType.TEXT_ARRAY, description="Free-form tags"),
]

KNOWLEDGE_PROPERTIES = [
    Property(name="doc_id",       data_type=DataType.TEXT,   description="Stable document identifier"),
    Property(name="title",        data_type=DataType.TEXT,   description="Document or section title"),
    Property(name="content",      data_type=DataType.TEXT,   description="Chunk text content"),
    Property(name="source_name",  data_type=DataType.TEXT,   description="Document name or filename"),
    Property(name="source_url",   data_type=DataType.TEXT,   description="URL or file path"),
    Property(name="chunk_index",  data_type=DataType.INT,    description="Zero-based chunk position"),
    Property(name="doc_type",     data_type=DataType.TEXT,   description="resolution | documentation | guide | incident"),
    Property(name="created_at",   data_type=DataType.TEXT,   description="ISO-8601 ingestion timestamp"),
]


# ---------------------------------------------------------------------------
# Internal collection builders
# ---------------------------------------------------------------------------

def _build_issue_collection(client: weaviate.WeaviateClient) -> None:
    """Create the DevFindIssue collection using Weaviate-native text2vec_weaviate vectorizer.

    Note: text2vec_weaviate vectorizes all text properties by default.
    Individual property-level skip_vectorization can be set per property.
    """
    client.collections.create(
        name=ISSUE_COLLECTION,
        description="Bug and issue reports for semantic duplicate detection.",
        vectorizer_config=Configure.Vectorizer.text2vec_weaviate(),
        properties=ISSUE_PROPERTIES,
    )
    logger.info("Created collection: %s", ISSUE_COLLECTION)


def _build_knowledge_collection(client: weaviate.WeaviateClient) -> None:
    """Create the DevFindKnowledge collection."""
    client.collections.create(
        name=KNOWLEDGE_COLLECTION,
        description="Knowledge chunks for RAG-assisted debugging.",
        vectorizer_config=Configure.Vectorizer.text2vec_weaviate(),
        properties=KNOWLEDGE_PROPERTIES,
    )
    logger.info("Created collection: %s", KNOWLEDGE_COLLECTION)


# ---------------------------------------------------------------------------
# Rate-limit detection helper
# ---------------------------------------------------------------------------

def _is_rate_limit_error(exc: Exception) -> bool:
    """Return True when *exc* looks like an HTTP 429 / rate-limit error.

    Matches against the string representation of the exception so that it
    works across all Weaviate client exception types and plain RuntimeErrors.
    """
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg or "too many requests" in msg


# ---------------------------------------------------------------------------
# Startup-safe collection setup
# ---------------------------------------------------------------------------

@dataclass
class CollectionSetupResult:
    """Result of ``ensure_startup_collections()``.

    Attributes:
        issue_status:           'created' | 'exists'
        knowledge_status:       'created' | 'exists' | 'rate_limited' | 'error'
        knowledge_unavailable:  True when the knowledge collection could not
                                be set up (rate-limited or other error).
        knowledge_error:        Human-readable reason, or None on success.
    """
    issue_status: str = ""
    knowledge_status: str = ""
    knowledge_unavailable: bool = False
    knowledge_error: Optional[str] = None

    def as_dict(self) -> dict[str, str]:
        """Return a collection-name → status mapping (like ensure_collections)."""
        return {
            ISSUE_COLLECTION: self.issue_status,
            KNOWLEDGE_COLLECTION: self.knowledge_status,
        }


def ensure_issue_collection(
    client: weaviate.WeaviateClient,
    *,
    verbose: bool = False,
) -> str:
    """Ensure the mandatory DevFindIssue collection exists.

    Returns:
        'exists' or 'created'

    Raises:
        Any exception from the Weaviate client — callers must treat this
        as a hard startup failure.
    """
    if client.collections.exists(ISSUE_COLLECTION):
        if verbose:
            logger.info(
                "Collection %s already exists — skipping creation.", ISSUE_COLLECTION
            )
        return "exists"

    _build_issue_collection(client)
    return "created"


def ensure_knowledge_collection(
    client: weaviate.WeaviateClient,
    *,
    verbose: bool = False,
    max_retries: int = 2,
    retry_delay_s: float = 3.0,
) -> str:
    """Ensure the DevFindKnowledge collection exists, with bounded 429 retries.

    Returns:
        'exists' or 'created'

    Raises:
        RuntimeError: After exhausting retries due to 429.
        Any other exception from the Weaviate client (non-429 errors are not
        retried and propagate immediately).
    """
    if client.collections.exists(KNOWLEDGE_COLLECTION):
        if verbose:
            logger.info(
                "Collection %s already exists — skipping creation.", KNOWLEDGE_COLLECTION
            )
        return "exists"

    last_exc: Optional[Exception] = None
    attempts = 0
    max_attempts = max_retries + 1  # initial attempt + retries

    while attempts < max_attempts:
        try:
            _build_knowledge_collection(client)
            return "created"
        except Exception as exc:
            if _is_rate_limit_error(exc):
                last_exc = exc
                attempts += 1
                if attempts < max_attempts:
                    logger.warning(
                        "HTTP 429 creating %s (attempt %d/%d). Retrying in %.1fs…",
                        KNOWLEDGE_COLLECTION,
                        attempts,
                        max_attempts,
                        retry_delay_s,
                    )
                    time.sleep(retry_delay_s)
                # else: exhausted — fall through to raise
            else:
                # Non-429: do not retry, propagate immediately
                raise

    # Exhausted retries due to rate limiting
    raise RuntimeError(
        f"HTTP 429 creating {KNOWLEDGE_COLLECTION} after {max_attempts} attempt(s). "
        f"Original error: {last_exc}"
    ) from last_exc


def ensure_startup_collections(
    client: weaviate.WeaviateClient,
    *,
    verbose: bool = False,
    knowledge_max_retries: int = 2,
    knowledge_retry_delay_s: float = 3.0,
) -> CollectionSetupResult:
    """Set up collections at application startup with fault-tolerance.

    DevFindIssue is **mandatory**: any failure raises immediately.
    DevFindKnowledge is **optional**: 429 / rate-limit errors are caught after
    bounded retries; the result carries ``knowledge_unavailable=True`` and a
    human-readable ``knowledge_error`` message.  Non-429 knowledge errors also
    set ``knowledge_unavailable=True`` so the caller can surface a clear warning
    rather than crashing the whole application.

    Returns:
        CollectionSetupResult with fields describing what happened.

    Raises:
        Any exception from ensuring DevFindIssue (mandatory hard failure).
    """
    result = CollectionSetupResult()

    # --- Mandatory: DevFindIssue ---
    result.issue_status = ensure_issue_collection(client, verbose=verbose)

    # --- Optional: DevFindKnowledge ---
    try:
        result.knowledge_status = ensure_knowledge_collection(
            client,
            verbose=verbose,
            max_retries=knowledge_max_retries,
            retry_delay_s=knowledge_retry_delay_s,
        )
        result.knowledge_unavailable = False
        result.knowledge_error = None
    except RuntimeError as exc:
        # Bounded 429 exhaustion — tolerate
        status = "rate_limited" if _is_rate_limit_error(exc) else "error"
        result.knowledge_status = status
        result.knowledge_unavailable = True
        result.knowledge_error = (
            f"Knowledge Assistant temporarily unavailable: {exc}"
        )
        logger.warning(
            "DevFindKnowledge setup failed (%s): %s — continuing without it.",
            status,
            exc,
        )
    except Exception as exc:
        # Non-429 unexpected error — still tolerate, but log more loudly
        result.knowledge_status = "error"
        result.knowledge_unavailable = True
        result.knowledge_error = (
            f"Knowledge Assistant unavailable due to setup error: {exc}"
        )
        logger.error(
            "Unexpected error setting up DevFindKnowledge: %s — continuing without it.",
            exc,
        )

    return result


# ---------------------------------------------------------------------------
# Backward-compatible public API
# ---------------------------------------------------------------------------

def ensure_collections(client: weaviate.WeaviateClient, *, verbose: bool = False) -> dict[str, str]:
    """Create collections that do not yet exist. Never deletes existing data.

    Returns:
        A dict mapping collection name → 'created' | 'exists'.

    Note: This function raises on any error (including 429).  For startup
    resilience use ``ensure_startup_collections()`` instead.
    """
    result: dict[str, str] = {}

    if client.collections.exists(ISSUE_COLLECTION):
        if verbose:
            logger.info("Collection %s already exists — skipping creation.", ISSUE_COLLECTION)
        result[ISSUE_COLLECTION] = "exists"
    else:
        _build_issue_collection(client)
        result[ISSUE_COLLECTION] = "created"

    if client.collections.exists(KNOWLEDGE_COLLECTION):
        if verbose:
            logger.info("Collection %s already exists — skipping creation.", KNOWLEDGE_COLLECTION)
        result[KNOWLEDGE_COLLECTION] = "exists"
    else:
        _build_knowledge_collection(client)
        result[KNOWLEDGE_COLLECTION] = "created"

    return result


def reset_collections(client: weaviate.WeaviateClient, collections: Optional[list[str]] = None) -> None:
    """Delete and recreate the specified collections.

    This is a DESTRUCTIVE operation. Only call from the explicit reset_db.py
    script after user confirmation. Never call from application startup.

    Args:
        client: Connected Weaviate client.
        collections: List of collection names to reset. Defaults to both
                     DevFindIssue and DevFindKnowledge.
    """
    targets = collections or [ISSUE_COLLECTION, KNOWLEDGE_COLLECTION]
    for name in targets:
        if client.collections.exists(name):
            client.collections.delete(name)
            logger.warning("DELETED collection: %s", name)

    for name in targets:
        if name == ISSUE_COLLECTION:
            _build_issue_collection(client)
        elif name == KNOWLEDGE_COLLECTION:
            _build_knowledge_collection(client)


def get_collection_stats(client: weaviate.WeaviateClient) -> dict[str, dict]:
    """Return basic stats (object count) for each collection."""
    stats: dict[str, dict] = {}
    for name in [ISSUE_COLLECTION, KNOWLEDGE_COLLECTION]:
        if client.collections.exists(name):
            col = client.collections.use(name)
            response = col.aggregate.over_all(total_count=True)
            stats[name] = {"exists": True, "count": response.total_count or 0}
        else:
            stats[name] = {"exists": False, "count": 0}
    return stats
