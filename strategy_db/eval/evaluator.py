"""Retrieval quality evaluator: HR@k, MRR@k, precision@k."""

import json
import os


class RetrievalEvaluator:
    """Compute retrieval metrics (HR@k, MRR@k, precision@k) against ground truth."""

    def __init__(self, dataset_path: str = None):
        if dataset_path is None:
            dataset_path = os.path.join(os.path.dirname(__file__), "eval_dataset.json")
        with open(dataset_path) as f:
            self.dataset = json.load(f)

    def evaluate(self, query_fn, top_k: int = 10) -> dict:
        """Compute all metrics.

        Args:
            query_fn: Function(query, top_k) -> list[dict] with 'id' or
                      'setup_name' keys
            top_k: Top-k cutoff for metrics

        Returns:
            Dict with HR@1, HR@5, HR@10, MRR@10, precision@5, n_queries
        """
        metrics = {
            "HR@1": 0.0, "HR@5": 0.0, "HR@10": 0.0,
            "MRR@10": 0.0, "precision@5": 0.0,
            "n_queries": len(self.dataset),
            "errors": 0,
        }

        for item in self.dataset:
            try:
                results = query_fn(item["query"], top_k=top_k)
            except Exception as e:
                metrics["errors"] += 1
                import traceback
                traceback.print_exc()
                continue

            retrieved_texts = []
            for r in results:
                txt = f"{r.get('setup_name', '')} {r.get('chunk_text', '')} {r.get('id', '')}"
                retrieved_texts.append(txt.lower())

            relevant_ids = [str(rid).lower() for rid in item.get("relevant_chunk_ids", [])]

            def _is_relevant(retrieved_text: str) -> bool:
                return any(rid in retrieved_text for rid in relevant_ids)

            # HR@k: does any relevant doc appear in top-k?
            for k_val in [1, 5, 10]:
                if any(_is_relevant(t) for t in retrieved_texts[:k_val]):
                    metrics[f"HR@{k_val}"] += 1.0

            # MRR@10: reciprocal rank of first relevant doc
            for rank, txt in enumerate(retrieved_texts[:10]):
                if _is_relevant(txt):
                    metrics["MRR@10"] += 1.0 / (rank + 1)
                    break

            # precision@5: fraction of top-5 that are relevant
            relevant_in_top5 = sum(
                1 for t in retrieved_texts[:5] if _is_relevant(t)
            )
            metrics["precision@5"] += relevant_in_top5 / 5.0

        # Normalize over valid queries
        n = max(metrics["n_queries"] - metrics["errors"], 1)
        for key in metrics:
            if key not in ("n_queries", "errors"):
                metrics[key] = round(metrics[key] / n, 4)

        return metrics

    def check_regression(
        self, current: dict, baseline: dict, threshold: float = 0.02
    ) -> tuple[bool, list[str]]:
        """Check if current metrics regressed vs baseline.

        Args:
            current: Current evaluation metrics dict
            baseline: Baseline metrics dict
            threshold: Maximum allowed negative delta as a fraction

        Returns:
            (passed: bool, regressions: list of descriptions)
        """
        regressions = []
        for metric in ["HR@1", "HR@5", "HR@10", "MRR@10", "precision@5"]:
            if metric in current and metric in baseline:
                delta = current[metric] - baseline[metric]
                if delta < -threshold:
                    regressions.append(
                        f"REGRESSION: {metric} dropped {abs(delta):.1%} "
                        f"(from {baseline[metric]:.1%} to {current[metric]:.1%})"
                    )

        return len(regressions) == 0, regressions

    def per_setup_type_metrics(self, query_fn, top_k: int = 10) -> dict:
        """Compute metrics broken down by setup_type."""
        by_type = {}
        for item in self.dataset:
            stype = item.get("setup_type", "unknown")
            if stype not in by_type:
                by_type[stype] = []
            by_type[stype].append(item)

        results = {}
        for stype, items in by_type.items():
            temp_eval = RetrievalEvaluator.__new__(RetrievalEvaluator)
            temp_eval.dataset = items
            results[stype] = temp_eval.evaluate(query_fn, top_k=top_k)

        return results

    def per_difficulty_metrics(self, query_fn, top_k: int = 10) -> dict:
        """Compute metrics broken down by difficulty."""
        by_diff = {}
        for item in self.dataset:
            diff = item.get("difficulty", "unknown")
            if diff not in by_diff:
                by_diff[diff] = []
            by_diff[diff].append(item)

        results = {}
        for diff, items in by_diff.items():
            temp_eval = RetrievalEvaluator.__new__(RetrievalEvaluator)
            temp_eval.dataset = items
            results[diff] = temp_eval.evaluate(query_fn, top_k=top_k)

        return results
