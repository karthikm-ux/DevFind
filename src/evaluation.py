"""Retrieval evaluation for DevFind.

Measures Recall@k, Precision@k, Mean Reciprocal Rank, and search latency
across semantic, hybrid, and keyword search modes.

Uses an explicit evaluation dataset with labeled relevant issues.
All results are saved as JSON and CSV for reproducibility.

IMPORTANT: Results are from a synthetic dataset. They indicate relative
performance between search modes but do not establish production accuracy.
"""
from __future__ import annotations

import csv
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

RESULTS_DIR = Path(__file__).parent.parent / "results"


@dataclass
class EvalQuery:
    """A single evaluation query with relevance labels."""
    query_id: str
    query_text: str
    relevant_issue_keys: list[str]           # Ground-truth positives
    category: str = "general"               # 'duplicate', 'related', 'unrelated', 'ambiguous'
    description: str = ""


@dataclass
class EvalResult:
    """Metrics for one query across one search mode."""
    query_id: str
    query_text: str
    search_mode: str
    k: int
    precision_at_k: float
    recall_at_k: float
    reciprocal_rank: float
    retrieved_keys: list[str] = field(default_factory=list)
    relevant_retrieved: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    category: str = "general"


@dataclass
class AggregatedMetrics:
    """Averaged metrics across all queries for a search mode."""
    search_mode: str
    k: int
    mean_precision_at_k: float
    mean_recall_at_k: float
    mean_reciprocal_rank: float
    mean_latency_ms: float
    total_queries: int
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    @property
    def precision(self) -> float:
        total = self.true_positives + self.false_positives
        return self.true_positives / total if total > 0 else 0.0

    @property
    def recall(self) -> float:
        total = self.true_positives + self.false_negatives
        return self.true_positives / total if total > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0


# ---------------------------------------------------------------------------
# Metric calculations
# ---------------------------------------------------------------------------

def precision_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Fraction of top-k retrieved items that are relevant."""
    if k <= 0 or not retrieved:
        return 0.0
    top_k = retrieved[:k]
    hits = sum(1 for key in top_k if key in relevant)
    return hits / k


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Fraction of all relevant items found in top-k results."""
    if not relevant or not retrieved:
        return 0.0
    top_k = retrieved[:k]
    hits = sum(1 for key in top_k if key in relevant)
    return hits / len(relevant)


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    """Reciprocal of rank of first relevant result (0 if none found)."""
    for i, key in enumerate(retrieved, 1):
        if key in relevant:
            return 1.0 / i
    return 0.0


def evaluate_search_mode(
    search_fn: Any,  # callable(query_text) -> list of result objects
    eval_queries: list[EvalQuery],
    *,
    k: int = 5,
    mode_name: str = "search",
) -> tuple[list[EvalResult], AggregatedMetrics]:
    """Evaluate a search function on all eval queries.

    Args:
        search_fn:    Callable that accepts a query string and returns a list
                      of objects with an 'issue_key' attribute or key.
        eval_queries: List of EvalQuery with ground-truth labels.
        k:            Rank cutoff for Precision@k and Recall@k.
        mode_name:    Label for this search mode in results.

    Returns:
        (list of per-query EvalResult, AggregatedMetrics)
    """
    results: list[EvalResult] = []

    for eq in eval_queries:
        t0 = time.perf_counter()
        try:
            search_response = search_fn(eq.query_text)
            # Handle both SearchResponse object and plain list
            if hasattr(search_response, "results"):
                objects = search_response.results
            else:
                objects = search_response or []
        except Exception as exc:
            logger.warning("Search failed for query '%s': %s", eq.query_text, exc)
            objects = []
        latency_ms = (time.perf_counter() - t0) * 1000

        retrieved_keys = []
        for obj in objects:
            if hasattr(obj, "issue_key"):
                retrieved_keys.append(obj.issue_key)
            elif isinstance(obj, dict):
                retrieved_keys.append(obj.get("issue_key", ""))

        relevant_set = set(eq.relevant_issue_keys)
        p = precision_at_k(retrieved_keys, relevant_set, k)
        r = recall_at_k(retrieved_keys, relevant_set, k)
        rr = reciprocal_rank(retrieved_keys, relevant_set)
        relevant_retrieved = [key for key in retrieved_keys[:k] if key in relevant_set]

        results.append(EvalResult(
            query_id=eq.query_id,
            query_text=eq.query_text,
            search_mode=mode_name,
            k=k,
            precision_at_k=round(p, 4),
            recall_at_k=round(r, 4),
            reciprocal_rank=round(rr, 4),
            retrieved_keys=retrieved_keys[:k],
            relevant_retrieved=relevant_retrieved,
            latency_ms=round(latency_ms, 2),
            category=eq.category,
        ))

    # Aggregate
    n = len(results)
    if n == 0:
        agg = AggregatedMetrics(
            search_mode=mode_name, k=k,
            mean_precision_at_k=0.0, mean_recall_at_k=0.0,
            mean_reciprocal_rank=0.0, mean_latency_ms=0.0,
            total_queries=0,
        )
    else:
        tp = sum(len(r.relevant_retrieved) for r in results)
        fp = sum(len(r.retrieved_keys) - len(r.relevant_retrieved) for r in results)
        fn = sum(
            max(0, len(set(eq.relevant_issue_keys)) - len(r.relevant_retrieved))
            for eq, r in zip(eval_queries, results)
        )
        agg = AggregatedMetrics(
            search_mode=mode_name,
            k=k,
            mean_precision_at_k=round(sum(r.precision_at_k for r in results) / n, 4),
            mean_recall_at_k=round(sum(r.recall_at_k for r in results) / n, 4),
            mean_reciprocal_rank=round(sum(r.reciprocal_rank for r in results) / n, 4),
            mean_latency_ms=round(sum(r.latency_ms for r in results) / n, 2),
            total_queries=n,
            true_positives=tp,
            false_positives=fp,
            false_negatives=fn,
        )

    return results, agg


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_results(
    all_results: list[EvalResult],
    aggregated: list[AggregatedMetrics],
    *,
    output_dir: Optional[Path] = None,
) -> dict[str, str]:
    """Save evaluation results as JSON and CSV. Returns file paths."""
    out = output_dir or RESULTS_DIR
    out.mkdir(parents=True, exist_ok=True)

    json_path = out / "eval_results.json"
    csv_path = out / "eval_results.csv"
    summary_path = out / "eval_summary.json"

    # Per-query JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in all_results], f, indent=2)

    # Per-query CSV
    if all_results:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(asdict(all_results[0]).keys()))
            writer.writeheader()
            for r in all_results:
                row = asdict(r)
                row["retrieved_keys"] = "|".join(row["retrieved_keys"])
                row["relevant_retrieved"] = "|".join(row["relevant_retrieved"])
                writer.writerow(row)

    # Aggregated summary JSON
    summary = {
        "methodology": (
            "Evaluation on synthetic dataset. Labels are human-assigned. "
            "Results indicate relative search mode performance. "
            "This dataset is too small to establish production accuracy."
        ),
        "aggregated": [asdict(a) for a in aggregated],
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    logger.info("Saved eval results to %s", out)
    return {
        "per_query_json": str(json_path),
        "per_query_csv": str(csv_path),
        "summary_json": str(summary_path),
    }


def print_summary(aggregated: list[AggregatedMetrics]) -> None:
    """Print a human-readable evaluation summary table."""
    print("\n" + "=" * 70)
    print("DevFind Retrieval Evaluation Summary")
    print("=" * 70)
    print(f"{'Mode':<12} {'P@k':>6} {'R@k':>6} {'MRR':>6} {'Latency(ms)':>12} {'Queries':>8}")
    print("-" * 70)
    for m in aggregated:
        print(
            f"{m.search_mode:<12} "
            f"{m.mean_precision_at_k:>6.3f} "
            f"{m.mean_recall_at_k:>6.3f} "
            f"{m.mean_reciprocal_rank:>6.3f} "
            f"{m.mean_latency_ms:>12.1f} "
            f"{m.total_queries:>8}"
        )
    print("=" * 70)
    print(
        "\nNote: Evaluated on synthetic dataset. "
        "Results do not represent production performance.\n"
    )
