# Changelog

All notable changes to DevFind are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-11-13

### Added
- **Weaviate Cloud Integration:** Primary vector database integration utilizing Weaviate v4 Python client with `text2vec_weaviate` vectorizer.
- **Multi-Modal Retrieval Pipeline:**
  - Semantic vector search with cosine distance filtering.
  - Hybrid retrieval combining dense embeddings and BM25 sparse keyword scoring with configurable `alpha` weight (0.0 - 1.0).
  - Exact BM25 keyword search baseline.
- **Duplicate Issue Detection:** Semantic duplicate discovery engine with real-time distance threshold calibration and duplicate review workflow (`confirmed_dup`, `distinct`).
- **Streamlit Web Dashboard:** Dark graphite-and-teal developer UI featuring 5 dedicated views:
  - System Dashboard with live health checks and component distribution metrics.
  - Issue Management with full CRUD, filtering, pagination, and manual triage.
  - Duplicate Finder with threshold slider and side-by-side comparison.
  - GitHub Issues Import with live sync, dry-run mode, and pagination.
  - Knowledge Assistant RAG interface with contextual grounding and source citations.
- **RAG Debugging Workflow:** Retrieval-Augmented Generation pipeline pulling context from `DevFindKnowledge` chunks with Ollama (local) and OpenAI support.
- **GitHub REST Integration:** Idempotent issue synchronization with UUID determinism (`uuid5`) based on repository and issue number.
- **Quantitative Evaluation Suite:** Precision@K, Recall@K, Mean Reciprocal Rank (MRR), and search latency benchmark suite with JSON/CSV reporting.
- **Automated CI/CD:** GitHub Actions test automation running across Python versions without live database dependencies.
- **Comprehensive Documentation:** In-depth architectural specifications, schema diagrams, setup guides, and user manuals.

### Security
- Sanitized `.env.example` to remove sensitive development credentials.
- Updated `.gitignore` to enforce exclusion of environment secrets, caches, and build artifacts.
