# Contributing to DevFind

Thank you for your interest in contributing to DevFind! We welcome bug reports, documentation updates, search algorithm enhancements, and new feature ideas.

## Getting Started

1. **Fork the Repository:** Create your own fork on GitHub.
2. **Clone Locally:**
   ```bash
   git clone https://github.com/<your-username>/DevFind.git
   cd DevFind
   ```
3. **Set Up Python Environment (Python 3.10+):**
   ```bash
   python -m venv .venv
   # On Windows:
   .venv\Scripts\activate
   # On macOS/Linux:
   source .venv/bin/activate
   ```
4. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
5. **Configure Environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials or run in mock mode
   ```

## Development Guidelines

### Branching Strategy
- Branch from `main`.
- Use descriptive branch names:
  - `feat/semantic-reranking`
  - `fix/schema-retry-backoff`
  - `docs/architecture-diagram-update`

### Coding Standards
- Follow standard PEP 8 formatting conventions.
- Keep type annotations on public functions and dataclasses.
- Ensure logging uses `logger.info()` / `logger.warning()` rather than naked `print()` statements in library code (`src/`).
- Never hardcode secrets, endpoints, or API keys. Keep all sensitive credentials in `.env` and access them via `os.getenv()`.

### Testing Requirements
Every pull request must pass the test suite before merging:
```bash
# Run unit and mocked integration tests
python -m pytest tests/ -v

# Run with test coverage
python -m pytest --cov=src tests/
```
Note: Live Weaviate integration tests are automatically skipped if `WEAVIATE_URL` and `WEAVIATE_API_KEY` are unset, allowing full test execution in standard CI pipelines.

### Submitting a Pull Request
1. Commit your changes with clear, imperative commit messages (e.g., `feat: add hybrid search score normalizer`).
2. Push your branch to your fork.
3. Open a Pull Request targeting the `main` branch of `aadiur/DevFind`.
4. Fill out the PR template describing the motivation, changes, and verification steps.
5. Ensure all CI checks pass.
