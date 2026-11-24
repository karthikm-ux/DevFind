"""CRUD operations for the DevFindKnowledge collection.

Knowledge chunks are text excerpts from bug resolutions, technical guides,
and incident reports. Used by the optional RAG-assisted debugging workflow.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

import weaviate
from weaviate.classes.query import Filter

from src.db.schema import KNOWLEDGE_COLLECTION
from src.utils import (
    stable_knowledge_uuid,
    utc_now_iso,
    validate_knowledge_chunk,
)

logger = logging.getLogger(__name__)


def _collection(client: weaviate.WeaviateClient):
    return client.collections.use(KNOWLEDGE_COLLECTION)


def insert_knowledge_chunk(
    client: weaviate.WeaviateClient,
    data: dict[str, Any],
) -> uuid.UUID:
    """Insert a knowledge chunk with a stable UUID. Upserts on conflict.

    Args:
        data: Must include 'content', 'source_name', and optionally
              'doc_id', 'title', 'chunk_index', 'source_url', 'doc_type'.

    Returns:
        The UUID of the inserted or updated chunk.
    """
    errors = validate_knowledge_chunk(data)
    if errors:
        raise ValueError(f"Invalid knowledge chunk: {'; '.join(errors)}")

    doc_id = data.get("doc_id") or data.get("source_name", "unknown")
    chunk_index = int(data.get("chunk_index", 0))
    chunk_uuid = stable_knowledge_uuid(doc_id, chunk_index)

    props = {
        "doc_id":       str(doc_id),
        "title":        str(data.get("title", "") or ""),
        "content":      str(data.get("content", "")),
        "source_name":  str(data.get("source_name", "")),
        "source_url":   str(data.get("source_url", "") or ""),
        "chunk_index":  chunk_index,
        "doc_type":     str(data.get("doc_type", "documentation") or "documentation"),
        "created_at":   data.get("created_at") or utc_now_iso(),
    }

    col = _collection(client)
    existing = col.query.fetch_object_by_id(chunk_uuid)
    if existing:
        col.data.update(uuid=chunk_uuid, properties=props)
        logger.debug("Updated knowledge chunk %s chunk %d", doc_id, chunk_index)
    else:
        col.data.insert(properties=props, uuid=chunk_uuid)
        logger.debug("Inserted knowledge chunk %s chunk %d", doc_id, chunk_index)

    return chunk_uuid


def batch_insert_knowledge(
    client: weaviate.WeaviateClient,
    chunks: list[dict[str, Any]],
) -> dict[str, int]:
    """Batch-insert knowledge chunks. Returns counts."""
    counts = {"inserted": 0, "failed": 0}
    for chunk in chunks:
        try:
            insert_knowledge_chunk(client, chunk)
            counts["inserted"] += 1
        except Exception as exc:
            counts["failed"] += 1
            logger.warning("Failed to insert knowledge chunk: %s", exc)
    return counts


def list_knowledge_chunks(
    client: weaviate.WeaviateClient,
    *,
    doc_type: Optional[str] = None,
    source_name: Optional[str] = None,
    limit: int = 50,
) -> list[Any]:
    """List knowledge chunks with optional filters."""
    col = _collection(client)
    filters = None
    if doc_type and source_name:
        filters = (
            Filter.by_property("doc_type").equal(doc_type)
            & Filter.by_property("source_name").equal(source_name)
        )
    elif doc_type:
        filters = Filter.by_property("doc_type").equal(doc_type)
    elif source_name:
        filters = Filter.by_property("source_name").equal(source_name)

    result = col.query.fetch_objects(filters=filters, limit=limit)
    return result.objects


def count_knowledge_chunks(client: weaviate.WeaviateClient) -> int:
    """Return total count of knowledge chunks."""
    col = _collection(client)
    response = col.aggregate.over_all(total_count=True)
    return response.total_count or 0
