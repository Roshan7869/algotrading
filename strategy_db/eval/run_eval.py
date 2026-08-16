#!/usr/bin/env python3
"""Run retrieval evaluation and detect regressions."""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def main():
    parser = argparse.ArgumentParser(description="RAG retrieval evaluation")
    parser.add_argument("--dataset", default=None,
                        help="Path to eval dataset JSON")
    parser.add_argument("--baseline", default=None,
                        help="Path to baseline metrics JSON")
    parser.add_argument("--threshold", type=float, default=0.02,
                        help="Regression threshold (fraction)")
    parser.add_argument("--save-baseline", action="store_true",
                        help="Save current metrics as baseline")
    parser.add_argument("--output", default=None,
                        help="Output path for metrics JSON")
    parser.add_argument("--by-type", action="store_true",
                        help="Show breakdown by setup_type")
    parser.add_argument("--by-difficulty", action="store_true",
                        help="Show breakdown by difficulty")
    parser.add_argument("--top-k", type=int, default=10,
                        help="Top-k cutoff for metrics (default: 10)")
    args = parser.parse_args()

    from strategy_db.eval.evaluator import RetrievalEvaluator

    dataset_path = args.dataset
    if dataset_path is None:
        dataset_path = os.path.join(os.path.dirname(__file__),
                                    "eval_dataset.json")

    evaluator = RetrievalEvaluator(dataset_path)

    from strategy_db.search import search as db_search

    def query_fn(q, top_k=10):
        return db_search(q, top_k=top_k)

    t0 = time.time()
    metrics = evaluator.evaluate(query_fn, top_k=args.top_k)
    elapsed = time.time() - t0

    print(f"Evaluation complete ({elapsed:.1f}s, "
          f"{metrics['n_queries'] - metrics.get('errors', 0)}/{metrics['n_queries']} queries)")
    print(f"  HR@1:  {metrics['HR@1']:.1%}")
    print(f"  HR@5:  {metrics['HR@5']:.1%}")
    print(f"  HR@10: {metrics['HR@10']:.1%}")
    print(f"  MRR@10: {metrics['MRR@10']:.4f}")
    print(f"  P@5:   {metrics['precision@5']:.1%}")
    if metrics.get("errors", 0) > 0:
        print(f"  Errors: {metrics['errors']}")

    if args.by_type:
        print("\n--- By Setup Type ---")
        type_metrics = evaluator.per_setup_type_metrics(query_fn,
                                                        top_k=args.top_k)
        for stype, tm in sorted(type_metrics.items()):
            print(f"  {stype}: HR@10={tm['HR@10']:.1%} "
                  f"MRR@10={tm['MRR@10']:.4f}")

    if args.by_difficulty:
        print("\n--- By Difficulty ---")
        diff_metrics = evaluator.per_difficulty_metrics(query_fn,
                                                         top_k=args.top_k)
        for diff, dm in sorted(diff_metrics.items()):
            print(f"  {diff}: HR@10={dm['HR@10']:.1%} "
                  f"MRR@10={dm['MRR@10']:.4f}")

    if args.save_baseline:
        baseline_path = args.baseline or os.path.join(os.path.dirname(__file__),
                                                      "baseline.json")
        with open(baseline_path, "w") as f:
            json.dump(metrics, f, indent=2)
        print(f"\nBaseline saved to {baseline_path}")

    if args.baseline and os.path.exists(args.baseline):
        with open(args.baseline) as f:
            baseline = json.load(f)
        passed, regressions = evaluator.check_regression(
            metrics, baseline, args.threshold
        )
        if not passed:
            print("\nRegressions detected:")
            for r in regressions:
                print(f"  {r}")
            sys.exit(1)
        else:
            print("\nNo regressions detected.")

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(metrics, f, indent=2)


if __name__ == "__main__":
    main()
