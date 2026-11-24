"""Search operations for DevFind.

Provides semantic (near_text), hybrid, and keyword-filtered search
against the DevFindIssue collection, plus knowledge-chunk retrieval
for the RAG workflow.

IMPORTANT: Similarity scores and distances are *indicators* of relatedness,
not proof of shared root cause. All candidate results are labeled as
'candidate' — duplication must be confirmed by a human reviewer.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import weaviate
from weaviate.classes.query import Filter, MetadataQuery

from src.db.schema import ISSUE_COLLECTION, KNOWLEDGE_COLLECTION
from src.utils import format_search_result

logger = logging.getLogger(__name__)

# Default candidate similarity threshold (distance ≤ this value is flagged).
# This value is calibrated against the synthetic evaluation dataset.
# A lower distance means closer (more similar) vectors.
DEFAULT_DISTANCE_THRESHOLD = 0.25
DEFAULT_LIMIT = 10


@dataclass
class SearchResult:
    """A single search result with metadata."""
    uuid: str
    issue_key: str
    title: str
    description: str
    severity: str
    status: str
    component: str
    project: str
    source_url: str
    duplicate_of: str
    review_status: str
    score: Optional[float] = None
    distance: Optional[float] = None
    certainty: Optional[float] = None
    is_candidate: bool = False  # True if within duplicate threshold
    tags: list[str] = field(default_factory=list)


@dataclass
class SearchResponse:
    """Aggregated search response with timing."""
    results: list[SearchResult]
    query: str
    search_mode: str
    latency_ms: float
    total_returned: int
    threshold_used: Optional[float] = None
    candidates_above_threshold: int = 0


def _parse_objects(
    objects: list[Any],
    threshold: Optional[float] = None,
    exclude_issue_key: Optional[str] = None,
) -> list[SearchResult]:
    """Convert Weaviate result objects to SearchResult dataclasses."""
    results: list[SearchResult] = []
    for obj in objects:
        props = obj.properties if hasattr(obj, "properties") else {}
        issue_key = props.get("issue_key", "")

        if exclude_issue_key and issue_key == exclude_issue_key:
            continue

        distance: Optional[float] = None
        certainty: Optional[float] = None
        score: Optional[float] = None

        if hasattr(obj, "metadata") and obj.metadata:
            meta = obj.metadata
            if hasattr(meta, "distance") and meta.distance is not None:
                distance = round(float(meta.distance), 4)
            if hasattr(meta, "certainty") and meta.certainty is not None:
                certainty = round(float(meta.certainty), 4)
            if hasattr(meta, "score") and meta.score is not None:
                score = round(float(meta.score), 4)

        is_candidate = False
        if threshold is not None and distance is not None:
            is_candidate = distance <= threshold

        results.append(SearchResult(
            uuid=str(obj.uuid) if hasattr(obj, "uuid") else "",
            issue_key=issue_key,
            title=props.get("title", ""),
            description=props.get("description", ""),
            severity=props.get("severity", ""),
            status=props.get("status", ""),
            component=props.get("component", ""),
            project=props.get("project", ""),
            source_url=props.get("source_url", ""),
            duplicate_of=props.get("duplicate_of", ""),
            review_status=props.get("review_status", ""),
            score=score,
            distance=distance,
            certainty=certainty,
            is_candidate=is_candidate,
            tags=list(props.get("tags") or []),
        ))
    return results


def _build_filters(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    component: Optional[str] = None,
    project: Optional[str] = None,
) -> Optional[Any]:
    """Build Weaviate filter chain from optional metadata constraints."""
    chain = []
    if status:
        chain.append(Filter.by_property("status").equal(status))
    if severity:
        chain.append(Filter.by_property("severity").equal(severity))
    if component:
        chain.append(Filter.by_property("component").equal(component))
    if project:
        chain.append(Filter.by_property("project").equal(project))

    if not chain:
        return None
    result = chain[0]
    for f in chain[1:]:
        result = result & f
    return result


def semantic_search(
    client: weaviate.WeaviateClient,
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    threshold: float = DEFAULT_DISTANCE_THRESHOLD,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    component: Optional[str] = None,
    project: Optional[str] = None,
    exclude_issue_key: Optional[str] = None,
) -> SearchResponse:
    """Semantic (vector) similarity search over DevFindIssue.

    Args:
        query:             Natural-language query string.
        limit:             Maximum results to return.
        threshold:         Distance threshold for flagging duplicate candidates.
                           Lower distance = more similar. Flagged ≤ threshold.
        exclude_issue_key: Exclude an issue from its own search results.

    Returns:
        SearchResponse with ranked results and timing.
    """
    if not query or not query.strip():
        return SearchResponse(
            results=[], query=query, search_mode="semantic",
            latency_ms=0.0, total_returned=0,
        )

    col = client.collections.use(ISSUE_COLLECTION)
    filters = _build_filters(status, severity, component, project)

    t0 = time.perf_counter()
    response = col.query.near_text(
        query=query.strip(),
        limit=limit + (1 if exclude_issue_key else 0),
        distance=threshold + 0.2,  # Fetch slightly beyond threshold to allow exclusion
        filters=filters,
        return_metadata=MetadataQuery(distance=True, certainty=True),
    )
    latency_ms = (time.perf_counter() - t0) * 1000

    results = _parse_objects(response.objects, threshold=threshold, exclude_issue_key=exclude_issue_key)
    results = results[:limit]
    candidates = sum(1 for r in results if r.is_candidate)

    return SearchResponse(
        results=results,
        query=query,
        search_mode="semantic",
        latency_ms=round(latency_ms, 2),
        total_returned=len(results),
        threshold_used=threshold,
        candidates_above_threshold=candidates,
    )


def hybrid_search(
    client: weaviate.WeaviateClient,
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    alpha: float = 0.7,
    threshold: float = DEFAULT_DISTANCE_THRESHOLD,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    component: Optional[str] = None,
    project: Optional[str] = None,
    exclude_issue_key: Optional[str] = None,
) -> SearchResponse:
    """Hybrid search combining vector similarity and BM25 keyword search.

    Args:
        alpha: Weight between vector (1.0) and keyword (0.0) search.
               0.7 gives vector search 70% weight.
    """
    if not query or not query.strip():
        return SearchResponse(
            results=[], query=query, search_mode="hybrid",
            latency_ms=0.0, total_returned=0,
        )

    col = client.collections.use(ISSUE_COLLECTION)
    filters = _build_filters(status, severity, component, project)

    t0 = time.perf_counter()
    response = col.query.hybrid(
        query=query.strip(),
        alpha=alpha,
        limit=limit + (1 if exclude_issue_key else 0),
        filters=filters,
        return_metadata=MetadataQuery(score=True),
    )
    latency_ms = (time.perf_counter() - t0) * 1000

    results = _parse_objects(response.objects, threshold=None, exclude_issue_key=exclude_issue_key)
    results = results[:limit]

    return SearchResponse(
        results=results,
        query=query,
        search_mode="hybrid",
        latency_ms=round(latency_ms, 2),
        total_returned=len(results),
        threshold_used=None,
        candidates_above_threshold=0,
    )


def keyword_search(
    client: weaviate.WeaviateClient,
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    component: Optional[str] = None,
    project: Optional[str] = None,
) -> SearchResponse:
    """BM25 keyword-only search for comparison against semantic search."""
    if not query or not query.strip():
        return SearchResponse(
            results=[], query=query, search_mode="keyword",
            latency_ms=0.0, total_returned=0,
        )

    col = client.collections.use(ISSUE_COLLECTION)
    filters = _build_filters(status, severity, component, project)

    t0 = time.perf_counter()
    response = col.query.bm25(
        query=query.strip(),
        query_properties=["title", "description"],
        limit=limit,
        filters=filters,
        return_metadata=MetadataQuery(score=True),
    )
    latency_ms = (time.perf_counter() - t0) * 1000

    results = _parse_objects(response.objects, threshold=None)

    return SearchResponse(
        results=results,
        query=query,
        search_mode="keyword",
        latency_ms=round(latency_ms, 2),
        total_returned=len(results),
    )


def search_knowledge(
    client: weaviate.WeaviateClient,
    query: str,
    *,
    limit: int = 5,
    doc_type: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Retrieve relevant knowledge chunks for RAG context.

    Returns:
        List of plain dicts with keys: content, title, source_name, source_url, doc_type.
    """
    if not query or not query.strip():
        return []

    col = client.collections.use(KNOWLEDGE_COLLECTION)
    filters = None
    if doc_type:
        filters = Filter.by_property("doc_type").equal(doc_type)

    try:
        response = col.query.near_text(
            query=query.strip(),
            limit=limit,
            filters=filters,
            return_metadata=MetadataQuery(distance=True),
        )
    except Exception as exc:
        logger.warning("Knowledge search failed: %s", exc)
        return []

    chunks = []
    for obj in response.objects:
        props = obj.properties if hasattr(obj, "properties") else {}
        chunks.append({
            "content":     props.get("content", ""),
            "title":       props.get("title", ""),
            "source_name": props.get("source_name", ""),
            "source_url":  props.get("source_url", ""),
            "doc_type":    props.get("doc_type", ""),
            "distance":    round(float(obj.metadata.distance), 4) if (hasattr(obj, "metadata") and obj.metadata and obj.metadata.distance is not None) else None,
        })
    return chunks
