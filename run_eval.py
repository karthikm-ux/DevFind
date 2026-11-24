"""Standalone evaluation script for DevFind retrieval quality.

Usage:
    python run_eval.py

Requires WEAVIATE_URL and WEAVIATE_API_KEY to run live evaluation.
If Weaviate is unavailable, runs the mock-based evaluation only.

Results are saved to results/eval_results.json and results/eval_results.csv.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.WARNING)

from src.evaluation import (
    AggregatedMetrics,
    EvalQuery,
    EvalResult,
    evaluate_search_mode,
    print_summary,
    save_results,
)

RESULTS_DIR = Path(__file__).parent / "results"
DATA_DIR = Path(__file__).parent / "data"


def load_eval_queries() -> list[EvalQuery]:
    """Load evaluation queries from the eval dataset JSON."""
    eval_path = DATA_DIR / "eval_dataset.json"
    if not eval_path.exists():
        print(f"❌ eval_dataset.json not found at {eval_path}")
        return []

    with open(eval_path, encoding="utf-8") as f:
        data = json.load(f)

    queries = []
    for q in data.get("queries", []):
        queries.append(EvalQuery(
            query_id=q["query_id"],
            query_text=q["query_text"],
            relevant_issue_keys=q.get("relevant_issue_keys", []),
            category=q.get("category", "general"),
            description=q.get("description", ""),
        ))
    return queries


def run_live_evaluation(client) -> tuple[list[EvalResult], list[AggregatedMetrics]]:
    """Run evaluation against live Weaviate with all search modes."""
    from src.db.search import hybrid_search, keyword_search, semantic_search

    queries = load_eval_queries()
    if not queries:
        print("No evaluation queries loaded.")
        return [], []

    print(f"\nLoaded {len(queries)} evaluation queries.")
    k = 5

    all_results: list[EvalResult] = []
    aggregated: list[AggregatedMetrics] = []

    for mode_name, search_fn_factory in [
        ("semantic", lambda: lambda q: semantic_search(client, q, limit=k)),
        ("hybrid",   lambda: lambda q: hybrid_search(client, q, limit=k)),
        ("keyword",  lambda: lambda q: keyword_search(client, q, limit=k)),
    ]:
        print(f"\nEvaluating {mode_name} search...")
        search_fn = search_fn_factory()
        results, agg = evaluate_search_mode(search_fn, queries, k=k, mode_name=mode_name)
        all_results.extend(results)
        aggregated.append(agg)
        print(f"  P@{k}={agg.mean_precision_at_k:.3f} "
              f"R@{k}={agg.mean_recall_at_k:.3f} "
              f"MRR={agg.mean_reciprocal_rank:.3f} "
              f"Latency={agg.mean_latency_ms:.1f}ms")

    return all_results, aggregated


def run_mock_evaluation() -> tuple[list[EvalResult], list[AggregatedMetrics]]:
    """Run evaluation with synthetic search results for demonstration."""
    print("\n[WARNING] No live Weaviate connection. Running mock evaluation for demonstration.")
    print("          Results show the evaluation framework only - not real retrieval quality.")

    queries = load_eval_queries()
    if not queries:
        return [], []

    # Mock search: returns first relevant key only (simulates imperfect search)
    def mock_search_fn(query_text: str):
        class FakeResult:
            def __init__(self, k):
                self.issue_key = k
        # Find queries that have relevant keys
        for q in queries:
            if any(word in query_text.lower() for word in q.query_text.lower().split()[:3]):
                return [FakeResult(k) for k in q.relevant_issue_keys[:3]]
        return []

    results, agg = evaluate_search_mode(
        mock_search_fn, queries[:10], k=5, mode_name="mock_demo"
    )
    print(f"  Mock P@5={agg.mean_precision_at_k:.3f} R@5={agg.mean_recall_at_k:.3f} (not real)")
    return results, [agg]


def main() -> None:
    print("=" * 60)
    print("  DevFind Retrieval Evaluation")
    print("=" * 60)
    print("\nNote: Evaluating on synthetic dataset.")
    print("Results indicate relative search mode performance only.")
    print("Not representative of production accuracy.\n")

    # Try live evaluation
    try:
        from src.db.client import get_client
        from src.db.schema import ensure_collections
        client = get_client()
        ensure_collections(client)
        all_results, aggregated = run_live_evaluation(client)
        live = True
    except Exception as exc:
        print(f"Weaviate unavailable ({exc}). Falling back to mock evaluation.")
        all_results, aggregated = run_mock_evaluation()
        live = False

    if not aggregated:
        print("No results to display.")
        return

    print_summary(aggregated)

    paths = save_results(all_results, aggregated, output_dir=RESULTS_DIR)
    print("\nResults saved to:")
    for label, path in paths.items():
        print(f"  {label}: {path}")

    if not live:
        print(
            "\n[BLOCKED] Live evaluation requires Weaviate credentials.\n"
            "Set WEAVIATE_URL and WEAVIATE_API_KEY to run real retrieval evaluation."
        )


if __name__ == "__main__":
    main()
