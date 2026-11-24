# Security Policy

## Supported Versions

Security updates and patches are applied to the active `main` branch.

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Security Vulnerability

If you discover a security issue or credential exposure, please **do not open a public GitHub issue**.

Instead, report security concerns responsibly via:
- **Email:** `aadiur710@gmail.com`
- **GitHub Security Advisories:** Through the repository's "Security" tab → "Report a vulnerability"

Please include:
1. Description of the vulnerability.
2. Steps to reproduce or proof-of-concept.
3. Affected components (`src/db/`, `app.py`, `src/github_integration.py`, etc.).
4. Any potential remediation recommendations.

You will receive an initial response within 48 hours, followed by updates on progress toward a fix and release.

## Credential Safety Guidelines

DevFind connects to external cloud services including Weaviate Cloud, GitHub API, and LLM endpoints:
- Never commit `.env` or files containing live tokens (`WEAVIATE_API_KEY`, `GITHUB_TOKEN`, `OPENAI_API_KEY`) to version control.
- Keep `.env` strictly in `.gitignore`.
- If an API key is inadvertently pushed to a remote repository, immediately revoke and rotate the key through the service provider's management console.
- In CI workflows, use GitHub Secrets rather than plain environment variables.
