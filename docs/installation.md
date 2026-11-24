# DevFind Installation & Environment Setup Guide

This guide provides complete instructions for setting up DevFind on Windows, macOS, or Linux.

---

## 1. Prerequisites

- **Python:** 3.10, 3.11, or 3.12 (check with `python --version`)
- **Git:** Installed and configured
- **Package Manager:** `pip` (bundled with Python)

---

## 2. Step-by-Step Installation

### Step 2.1: Clone the Repository
```bash
git clone https://github.com/aadiur/DevFind.git
cd DevFind
```

### Step 2.2: Create a Virtual Environment
It is strongly recommended to use an isolated virtual environment:

**On macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**On Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**On Windows (Command Prompt):**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

### Step 2.3: Upgrade pip and Install Dependencies
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## 3. Weaviate Database Configuration

DevFind requires access to a Weaviate instance. You can use **Weaviate Cloud (Recommended)** or a **Local Docker instance**.

### Option A: Weaviate Cloud (Fastest & Recommended)
1. Sign up for a free account at [Weaviate Cloud Console](https://console.weaviate.cloud).
2. Click **Create Cluster** and select the free **Sandbox** tier.
3. In the cluster configuration settings, ensure **Weaviate Embeddings** (`text2vec-weaviate`) is enabled.
4. Copy your **REST Endpoint URL** (e.g., `your-cluster-id.c0.eu-central-1.aws.weaviate.cloud`).
5. Click **API Keys** and generate a standard API key.

### Option B: Local Weaviate via Docker Compose
If you prefer running Weaviate entirely on your local machine:
```yaml
# docker-compose.yml
version: '3.4'
services:
  weaviate:
    image: cr.weaviate.io/semitechnologies/weaviate:1.27.0
    ports:
      - "8080:8080"
      - "50051:50051"
    environment:
      QUERY_DEFAULTS_LIMIT: 25
      AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED: 'true'
      PERSISTENCE_DATA_PATH: '/var/lib/weaviate'
      DEFAULT_VECTORIZER_MODULE: 'text2vec-transformers'
      ENABLE_MODULES: 'text2vec-transformers'
      TRANSFORMERS_INFERENCE_API: 'http://t2v-transformers:8080'
  t2v-transformers:
    image: cr.weaviate.io/semitechnologies/transformers-inference:sentence-transformers-all-MiniLM-L6-v2
    environment:
      ENABLE_CUDA: '0'
```

---

## 4. Environment Configuration (`.env`)

Copy the template configuration file:
```bash
# On Linux/macOS
cp .env.example .env

# On Windows PowerShell
Copy-Item .env.example .env
```

Open `.env` in your text editor and supply your credentials:

```ini
# Weaviate Cloud
WEAVIATE_URL=your-cluster-id.c0.region.aws.weaviate.cloud
WEAVIATE_API_KEY=your-weaviate-api-key

# GitHub Integration (Optional: for importing live repo issues)
GITHUB_TOKEN=ghp_your_personal_access_token
GITHUB_REPO_OWNER=your-github-username-or-org
GITHUB_REPO_NAME=your-repo-name

# LLM / RAG Assistant (Optional: defaults to local Ollama)
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
# OPENAI_API_KEY=sk-your-openai-api-key
# OPENAI_MODEL=gpt-4o-mini

# Application Settings
DEVFIND_ENV=development
LOG_LEVEL=INFO
```

> **Security Note:** Never commit `.env` to Git. The `.gitignore` file automatically excludes it.

---

## 5. Optional Integrations

### 5.1 Local LLM with Ollama (Free, Offline)
1. Download Ollama from [ollama.com](https://ollama.com).
2. Pull the recommended lightweight model:
   ```bash
   ollama pull llama3.2
   ```
3. Ollama runs as a background service on `http://localhost:11434`.

### 5.2 GitHub Personal Access Token
To import issues from a private or public GitHub repository:
1. Go to **GitHub Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens**.
2. Generate a token with **Repository permissions: Issues (Read-only)**.
3. Paste the token in `GITHUB_TOKEN`.

---

## 6. Verification Checklist

Run the following commands to verify that your installation is healthy:

```bash
# 1. Run unit test suite
python -m pytest tests/ -v

# 2. Run mock evaluation pipeline
python run_eval.py

# 3. Launch Streamlit UI
streamlit run app.py
```

Open your browser at `http://localhost:8501`.
