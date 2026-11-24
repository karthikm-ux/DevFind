"""Weaviate client management for DevFind.

Provides a singleton-style connection factory with environment-based
configuration. Supports both Weaviate Cloud (hosted) and local instances.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import weaviate
from weaviate.classes.init import Auth

logger = logging.getLogger(__name__)

_client: Optional[weaviate.WeaviateClient] = None


def get_client() -> weaviate.WeaviateClient:
    """Return a connected Weaviate client, creating one if necessary.

    Reads WEAVIATE_URL and WEAVIATE_API_KEY from the environment.
    Falls back to a local instance at http://localhost:8080 if no URL is set.

    Raises:
        RuntimeError: When the cluster is not reachable.
        EnvironmentError: When required environment variables are missing.
    """
    global _client
    if _client is not None and _client.is_connected():
        return _client

    url = os.getenv("WEAVIATE_URL")
    api_key = os.getenv("WEAVIATE_API_KEY")

    try:
        if url and api_key:
            logger.info("Connecting to Weaviate Cloud at %s", url)
            _client = weaviate.connect_to_weaviate_cloud(
                cluster_url=url,
                auth_credentials=Auth.api_key(api_key),
            )
        elif url:
            # URL provided without key → assume custom local/server instance
            logger.info("Connecting to Weaviate at %s (no API key)", url)
            _client = weaviate.connect_to_custom(
                http_host=url.rstrip("/"),
                http_port=443,
                http_secure=True,
            )
        else:
            logger.info("Connecting to local Weaviate at localhost:8080")
            _client = weaviate.connect_to_local()

        if not _client.is_ready():
            raise RuntimeError("Weaviate cluster is not ready after connecting.")
        logger.info("Weaviate connection established successfully.")
        return _client

    except Exception as exc:
        raise RuntimeError(f"Failed to connect to Weaviate: {exc}") from exc


def close_client() -> None:
    """Close the global Weaviate client if open."""
    global _client
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
        _client = None


def is_connected() -> bool:
    """Return True if the global client is connected and ready."""
    try:
        return _client is not None and _client.is_connected() and _client.is_ready()
    except Exception:
        return False
