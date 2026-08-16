# Phase 5: Monitoring & Evaluation

## First Principles Root Cause Analysis

### Core Question
*How can you improve a system whose performance you cannot measure?*

### Decomposition to First Principles

**Principle 1: Unmeasured systems cannot be optimized**
- Every optimization in Phases 1-4 makes a claim: "this change improves retrieval quality"
- Without measurement, these claims are unverifiable opinions, not facts
- You cannot know if hybrid search helps or hurts without precision/recall numbers
- You cannot know if cross-encoder is worth its latency cost without comparing before/after
- You cannot know if embedding fine-tuning degrades general queries while helping trading queries
- **Root cause**: The system has no quantitative performance baseline, making every optimization a blind gamble

**Principle 2: RAG failures have two independent root causes (and you must distinguish them)**
- Retrieval failure: relevant documents not in top-k → LLM gets wrong context → bad answer
- Generation failure: relevant documents retrieved but LLM ignores them → hallucination
- If retrieval fails, improving the LLM won't help. If generation fails, improving retrieval won't help.
- Without separate metrics for retrieval vs generation, you can't know which to fix
- **Root cause**: Current system conflates retrieval quality and generation quality into one unmeasured "does it work?" assessment

**Principle 3: You cannot fix what you don't find**
- A query returning 0 results is a silent failure (user sees empty results, doesn't know why)
- A query returning low-similarity results is a gradual degradation (user loses trust over time)
- A query where retrieved chunks don't match intent is a hidden failure (LLM produces plausible-sounding wrong answer)
- Each of these has different root causes and different fixes
- Without monitoring, ALL of these failures are invisible
- **Root cause**: No monitoring means all retrieval failures are silent — they degrade user trust without any diagnostic signal

### Root Cause Statement

> **The RAG pipeline operates without any quantitative feedback loop — retrieval quality, generation faithfulness, and system performance are entirely unmeasured. This makes every optimization a blind guess, every regression a silent failure, and every deployment a leap of faith. Without evaluation metrics (precision, recall, faithfulness, answer relevancy, latency), the system cannot distinguish between improvements and degradations, and cannot accumulate knowledge about what works.**

### Measured Evidence
- Zero monitoring infrastructure: no logging of queries, results, or latency
- No evaluation dataset: no ground-truth Q/A pairs
- No test/CI for retrieval quality
- User feedback is anecdotal ("it worked" / "it didn't work")
- Existing health dashboard (10_system_health.py) shows system metrics but NOT retrieval quality

---

## Current State Analysis

| Component | Status | Limitation |
|-----------|--------|------------|
| Evaluation dataset (Q/A pairs) | ❌ Missing | No ground truth |
| Retrieval metrics (HR@k, MRR@k) | ❌ Missing | No precision/recall tracking |
| Generation metrics (faithfulness, relevancy) | ❌ Missing | No answer quality tracking |
| Query logging | ❌ Missing | No query history |
| Latency tracking | ❌ Missing | No performance monitoring |
| Zero-result monitoring | ❌ Missing | No alert on empty results |
| CI integration | ❌ Missing | No automated eval on changes |
| Health dashboard extension | ⚠️ Partial | Existing page but no RAG metrics |
| Outcome tracking | ⚠️ Partial | Trade outcomes exist but not linked to retrieval |

---

## Typed Execution Plan

### DAG

```
Phase 5.1 ──[Build 100+ Q/A evaluation dataset]────────────────► Checkpoint 5.1
    │                                                              │ 100+ pairs from real chunks
    ▼                                                              │ balanced across setup_types
Phase 5.2 ──[Implement retrieval evaluator (HR@k, MRR@k, precision@k)]► Checkpoint 5.2
    │                                                              │ runs against eval set
    ▼                                                              │ outputs JSON metrics
Phase 5.3 ──[Implement logging pipeline (query + results + latency)]► Checkpoint 5.3
    │                                                              │ SQLite log file
    ▼                                                              │ append-only, auto-rotate
Phase 5.4 ──[Add zero-result + low-similarity alerts]────────────► Checkpoint 5.4
    │                                                              │ alerts on < 1 result or avg similarity < 0.6
    ▼                                                              │ logged to monitoring/alerts
Phase 5.5 ──[Extend health dashboard with RAG metrics]───────────► Checkpoint 5.5
    │                                                              │ Streamlit page with charts
    ▼                                                              │ trend lines over time
Phase 5.6 ──[CI integration: eval-runs on every pipeline change]► Done
    │                                                              │ GitHub Action or hook
    ▼                                                              │ blocks if HR@10 drops > 2%
Phase 5.7 ──[Benchmark: establish baseline + auto-regression detection]
                                                                   │ All metrics tracked
```

### Phase 5.1 — Evaluation Dataset

**Schema**:
```json
{
  "query_id": "eval_001",
  "query": "How do I place a stop loss after a FVG entry?",
  "relevant_chunk_ids": ["chunk_042", "chunk_087"],
  "setup_type": "entry",
  "market_condition": "any",
  "difficulty": "medium",
  "source": "synthetic"  // or "human"
}
```

**Strategy**:
- 50 queries from synthetic generation (Phase 4.1) — diverse, covers all setup_types
- 50 queries handwritten — edge cases, acronym queries, ambiguous queries
- 10 queries per setup_type (entry, exit, risk_management, market_structure, psychology)
- Ground truth: 1-3 relevant chunk IDs per query (verified by looking at chunk_text)

**Storage**: `strategy_db/eval/eval_dataset_v1.json`

### Phase 5.2 — Retrieval Evaluator

```python
class RetrievalEvaluator:
    def __init__(self, dataset_path: str):
        with open(dataset_path) as f:
            self.dataset = json.load(f)

    def evaluate(self, query_fn, top_k: int = 5) -> dict:
        """Compute retrieval metrics using a query function."""
        metrics = {
            "HR@1": 0, "HR@5": 0, "HR@10": 0,
            "MRR@1": 0, "MRR@5": 0, "MRR@10": 0,
            "precision@5": 0,
            "total_queries": len(self.dataset),
        }

        for item in self.dataset:
            results = query_fn(item["query"], top_k=top_k)
            retrieved_ids = [r["id"] for r in results]
            relevant_ids = item["relevant_chunk_ids"]

            # HR@k
            for k, label in [(1, "HR@1"), (5, "HR@5"), (10, "HR@10")]:
                if any(rid in retrieved_ids[:k] for rid in relevant_ids):
                    metrics[label] += 1 / len(self.dataset)

            # MRR@k
            for k, label in [(1, "MRR@1"), (5, "MRR@5"), (10, "MRR@10")]:
                for rank, rid in enumerate(retrieved_ids[:k]):
                    if rid in relevant_ids:
                        metrics[label] += 1.0 / (rank + 1) / len(self.dataset)
                        break

            # Precision@5
            relevant_in_top5 = sum(1 for rid in retrieved_ids[:5] if rid in relevant_ids)
            metrics["precision@5"] += relevant_in_top5 / 5 / len(self.dataset)

        return metrics
```

### Phase 5.3 — Logging Pipeline

```python
import sqlite3
import json
import time
from datetime import datetime

class QueryLogger:
    def __init__(self, db_path: str = "strategy_db/logs/query_log.db"):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS query_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                query TEXT,
                query_hash TEXT,
                top_k INTEGER,
                where_filters TEXT,
                cache_layer TEXT,
                num_results INTEGER,
                avg_similarity REAL,
                min_similarity REAL,
                latency_ms REAL,
                reranker_used INTEGER,
                finetuned_used INTEGER,
                hybrid_used INTEGER,
                errors TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                total_queries INTEGER,
                zero_result_queries INTEGER,
                avg_latency_ms REAL,
                p95_latency_ms REAL,
                avg_similarity REAL,
                cache_hit_rate REAL,
                avg_results_per_query REAL
            )
        """)
        self.conn.commit()

    def log(self, query: str, top_k: int, results: list, latency_ms: float,
            cache_layer: str = "none", errors: str = None):
        sims = [r.get("rerank_score", r.get("score", 0.0)) for r in results]
        avg_sim = sum(sims) / len(sims) if sims else 0.0
        self.conn.execute(
            """INSERT INTO query_log (...) VALUES (...)""",
            (...)
        )
        self.conn.commit()

    def daily_rollup(self):
        """Compute daily aggregate stats."""
        pass  # Runs via cron or on import
```

### Phase 5.4 — Alerts

```python
class RetrievalAlert:
    def check_query(self, results: list, query: str, latency_ms: float):
        alerts = []
        if len(results) == 0:
            alerts.append(("CRITICAL", f"Zero results for query: {query}"))
        elif len(results) < 3:
            alerts.append(("WARNING", f"Few results ({len(results)}) for: {query}"))
        avg_sim = sum(r.get("rerank_score", 0.5) for r in results) / max(len(results), 1)
        if avg_sim < 0.5:
            alerts.append(("WARNING", f"Low average similarity ({avg_sim:.2f}) for: {query}"))
        if latency_ms > 1000:
            alerts.append(("WARNING", f"High latency ({latency_ms:.0f}ms) for: {query}"))

        # Log alerts
        for level, msg in alerts:
            print(f"[{level}] {msg}")
            # In production: push to monitoring/alerts channel
```

### Phase 5.5 — Dashboard Extension

Extend `ui/pages/10_system_health.py` with:

```python
# RAG Performance Metrics Section
st.subheader("Retrieval Quality")
col1, col2, col3 = st.columns(3)
col1.metric("HR@10 (24h)", f"{rag_metrics['HR@10']:.1%}")
col2.metric("Avg Latency", f"{rag_metrics['avg_latency_ms']:.0f}ms")
col3.metric("Cache Hit Rate", f"{rag_metrics['cache_hit_rate']:.1%}")

# Trend chart
st.line_chart(query_log_daily[["date", "avg_latency_ms", "cache_hit_rate"]])

# Zero-result queries (last 24h)
st.dataframe(query_log_daily[query_log_daily["zero_result_queries"] > 0])
```

### Phase 5.6 — CI Integration

```bash
# .github/workflows/rag-eval.yml (or pre-commit hook)
python3 strategy_db/eval/run_eval.py \
    --dataset strategy_db/eval/eval_dataset_v1.json \
    --baseline strategy_db/eval/baseline_v1.json \
    --threshold 0.02
```

```python
# run_eval.py
def check_regression(current: dict, baseline: dict, threshold: float = 0.02):
    for metric in ["HR@10", "MRR@10", "precision@5"]:
        delta = current[metric] - baseline[metric]
        if delta < -threshold:
            print(f"REGRESSION: {metric} dropped by {abs(delta):.1%} "
                  f"(from {baseline[metric]:.1%} to {current[metric]:.1%})")
            return False
    print("No regressions detected.")
    return True
```

---

## Audit Benchmarks

### Pre-Phase Baseline

| Metric | Current Value | Target |
|--------|---------------|--------|
| Eval dataset size | 0 pairs | >= 100 pairs |
| HR@10 | Unknown | >= 85% (measure first run) |
| Daily query volume | Unknown | Tracked |
| Avg latency per query | Unknown | Tracked |
| Zero-result queries/day | Unknown | Tracked, < 5% |
| Cache hit rate | Unknown | Tracked |
| Alert coverage | 0 alerts | All critical cases covered |

### Post-Phase Verification Matrix

| Check | Tool | Pass Criteria |
|-------|------|---------------|
| Eval dataset has 100+ pairs | `len(dataset) >= 100` | >= 100 |
| Eval dataset covers all setup_types | `set(item['setup_type'] for item in dataset)` | All 5 types present |
| Retrieval evaluator runs without error | `evaluate(query_fn)` | Returns metrics dict |
| Query logger writes to SQLite | `logger.log(...)` | DB row created |
| Daily rollup computes correctly | `daily_rollup()` | Aggregate values match raw data |
| Alerts fire for zero results | `check_query([], "test", 100)` | CRITICAL alert emitted |
| Dashboard renders without error | Streamlit page | No exceptions |
| CI eval runs and blocks on regression | Regression check | Blocks on >2% drop |
| All baseline metrics captured | Run eval once | Output written to baseline JSON |

---

## Verification Protocol (Block-Level)

### Block 1: Eval Dataset Quality

```python
dataset = json.load(open("strategy_db/eval/eval_dataset_v1.json"))
setup_types = set(item["setup_type"] for item in dataset)
assert len(dataset) >= 100, f"Only {len(dataset)} queries"
assert setup_types == {"entry", "exit", "risk_management", "market_structure", "psychology"}, \
    f"Missing types: {setup_types}"
# Each query has at least 1 relevant chunk
for item in dataset:
    assert len(item["relevant_chunk_ids"]) >= 1, f"Query {item['query_id']} has no relevant chunks"
```

### Block 2: Evaluator Correctness

```python
evaluator = RetrievalEvaluator("strategy_db/eval/eval_dataset_v1.json")

# Mock query function that returns ground truth for first N, empty for rest
def mock_query_fn(query, top_k=5):
    ...  # returns correct chunks for known queries

metrics = evaluator.evaluate(mock_query_fn)
assert metrics["HR@5"] == 1.0  # Should be perfect for mock
assert metrics["MRR@5"] == 1.0
```

### Block 3: Logger

```python
logger = QueryLogger(":memory:")  # In-memory SQLite
logger.log("test query", 5, [{"rerank_score": 0.9, "id": "1"}], 50.0)
row = logger.conn.execute("SELECT COUNT(*) FROM query_log").fetchone()
assert row[0] == 1
```

### Block 4: Alert

```python
alerter = RetrievalAlert()
alerts = alerter.check_query([], "test", 100)
assert any("CRITICAL" in a[0] for a in alerts)
assert any("Zero results" in a[1] for a in alerts)
```

### Block 5: CI Regression Detection

```bash
python3 strategy_db/eval/run_eval.py \
    --dataset strategy_db/eval/eval_dataset_v1.json \
    --baseline strategy_db/eval/baseline_v1.json \
    --threshold 0.02
echo "Exit code: $?"
# Should exit 0 if no regression, 1 if regression detected
```

---

## Rollback Plan

| Failure | Action |
|---------|--------|
| Eval dataset too expensive to build | Start with 50 pairs, grow over time |
| Dashboard degrades Streamlit performance | Cache metrics, update on interval |
| CI eval takes too long | Reduce eval dataset to 50 queries for CI, full set for nightly |
| Logger slows down queries | Use async logging (fire-and-forget) |

## Estimated Effort

| Task | Time | Dependencies |
|------|------|-------------|
| Phase 5.1 — Eval dataset | 1h 30min | Existing chunks |
| Phase 5.2 — Retrieval evaluator | 30 min | Phase 5.1 |
| Phase 5.3 — Logging | 30 min | — |
| Phase 5.4 — Alerts | 20 min | Phase 5.3 |
| Phase 5.5 — Dashboard | 1h | Phase 5.3, existing Streamlit |
| Phase 5.6 — CI integration | 30 min | Phase 5.2 |
| Phase 5.7 — Benchmark | 20 min | All above |
| **Total** | **~4h 40min** | |

---

## Success Criteria

- [ ] 100+ query-doc evaluation dataset with all 5 setup_types
- [ ] Retrieval evaluator computes HR@k, MRR@k, precision@k correctly
- [ ] Query logger persists every query with latency, results, and similarity
- [ ] Alerts fire for: zero results, low similarity, high latency
- [ ] Streamlit dashboard shows RAG metrics with trend charts
- [ ] CI pipeline runs eval and blocks on >2% regression in HR@10
- [ ] All metrics have baselines captured for future comparison
- [ ] Silent failures become visible (zero-result, low-similarity)
