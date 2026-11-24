# DevFind User Guide & Workflow Manual

This guide covers all capabilities of the DevFind platform across both the interactive Streamlit UI and the command-line developer utilities.

---

## 1. Web Application Overview

Start the application with:
```bash
streamlit run app.py
```
Then navigate to `http://localhost:8501`.

The left sidebar displays:
- **Navigation Menu:** Direct access to all 5 core modules.
- **System Status Card:** Real-time connectivity indicators for Weaviate Cloud, `DevFindIssue` collection, `DevFindKnowledge` collection, and LLM provider.
- **Dataset Seeder:** A one-click button to populate the database with the included 82 synthetic software issues.

---

## 2. Modules & Features

### 2.1 Dashboard
The central operations screen provides:
- **High-Level Metrics:** Total indexed issues, open defects, critical issues, and confirmed duplicate groups.
- **Component Distribution Bars:** Visual breakdown of defects categorized by architectural subsystem (`Authentication`, `Search`, `Database`, `UI`, `API Gateway`).
- **Recent Activity Table:** Fast preview of the latest 10 indexed issues with status and severity badges.

### 2.2 Issue Management (CRUD)
The issue management interface supports complete lifecycle operations:
- **Browse & Filter:** Filter issues dynamically by status (`Open`, `In Progress`, `Resolved`, `Closed`), severity (`Critical`, `High`, `Medium`, `Low`), and component.
- **Create Issue:** Form to submit new bug reports with automatic ISO-8601 timestamping and unique issue keys (`ISSUE-XXX`).
- **Edit Issue:** Update resolution notes, modify status, reassign severity, or adjust tags.
- **Delete Issue:** Safely remove issues with confirmation safeguards.

### 2.3 Duplicate Finder
The core intelligent triage tool:
1. **Search Mode:** Enter a natural language symptom (e.g., *"auth token invalid after page reload"*) or paste an existing issue key.
2. **Threshold Calibration:** Use the distance threshold slider (default: `0.25`).
   - $\text{Distance} \le 0.15$: Very close match (almost identical wording).
   - $\text{Distance} \le 0.25$: High likelihood of shared defect.
   - $\text{Distance} \le 0.40$: Broad conceptual relatedness.
3. **Candidate Highlighting:** Results within the threshold are flagged with a prominent candidate badge.
4. **Side-by-Side Review:** Compare query details against candidate reports.
5. **Review Action:**
   - Click **Confirm Duplicate**: Links the issue to the parent key and sets `review_status = "confirmed_dup"`.
   - Click **Mark Distinct**: Sets `review_status = "distinct"` to prevent false alarms.

### 2.4 GitHub Issues Import
Synchronize bug reports directly from a public or private GitHub repository:
1. Provide the target repository in the format `owner/repo`.
2. Toggle **Dry Run Mode** (Recommended): Simulates the import, fetching issues from GitHub and validating schema normalization without writing to Weaviate.
3. Disable Dry Run and click **Synchronize Issues**: Imports issues with idempotent `uuid5` keys, preventing duplication across repeated runs.

### 2.5 Knowledge Assistant (RAG)
Interactive troubleshooting assistant for software engineers:
1. Enter an issue description, error trace, or architecture question.
2. The RAG pipeline performs dual retrieval:
   - Queries `DevFindIssue` for historical incident solutions.
   - Queries `DevFindKnowledge` for architectural guides and runbook chunks.
3. Renders a grounded technical explanation accompanied by **Source Citations** detailing exact document IDs and similarity distances.
4. If the knowledge collection is temporarily unavailable, a restrained amber status panel informs the developer gracefully without crashing the UI.

---

## 3. Command-Line Tools

### 3.1 Retrieval Evaluation (`run_eval.py`)
Run the information retrieval benchmark suite:
```bash
python run_eval.py
```
This executes all evaluation queries from `data/eval_dataset.json` across Semantic, Hybrid, and Keyword search modes, calculating Precision@5, Recall@5, Mean Reciprocal Rank (MRR), and execution latency. Results are written to `results/eval_results.json` and `results/eval_results.csv`.

### 3.2 Safe Database Reset (`reset_db.py`)
Reset collections when wiping test data:
```bash
# Interactive mode (prompts for confirmation)
python reset_db.py

# Reset only the issues collection
python reset_db.py --collection DevFindIssue

# Scripted execution (bypasses prompt)
python reset_db.py --yes
```

### 3.3 Classroom Demo (`devfind_demo.py`)
Run the original self-contained script demonstrating basic Weaviate operations:
```bash
python devfind_demo.py
```
