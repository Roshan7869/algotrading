# Phase 4: Embedding Fine-Tuning

## First Principles Root Cause Analysis

### Core Question
*Why does a general-purpose embedding model fail to capture trading-specific semantics?*

### Decomposition to First Principles

**Principle 1: All embedding models are trained on a specific data distribution**
- all-MiniLM-L6-v2 was trained on 1 billion sentence pairs from general web text (Wikipedia, Reddit, news, books)
- This data contains trading/finance content at roughly the same frequency as any other topic: ~0.1-0.5%
- The model has 22M parameters and 384 dimensions — highly compressed representation
- When 99.5% of training data is non-trading, the model allocates most of its capacity to general language understanding
- **Root cause**: The embedding model's limited capacity is allocated proportionally to its training distribution. Trading-specific patterns (FVG, order blocks, liquidity grabs) have negligible representation and thus negligible model capacity allocated.

**Principle 2: Domain-specific language has non-standard semantics**
- "Liquidity" in trading ≠ "liquidity" in finance ≠ "liquidity" in physics
- "Grab" in trading means "price moves to take out stop losses" — this is NOT a physical grab
- "Break of structure" means a specific price action pattern, not a building collapse
- General embedding models map these words to their most common meanings, NOT the trading-specific meanings
- **Root cause**: The embedding space conflates trading terms with their everyday meanings, producing vectors that are closer to everyday usage than trading-specific usage

**Principle 3: Fine-tuning = reallocating model capacity**
- A pre-trained model has learned weights that minimize loss over its training distribution
- Fine-tuning on domain data adjusts weights to also minimize loss on domain-specific tasks
- The linear adapter approach (LlamaIndex `EmbeddingAdapterFinetuneEngine`):
  - Keeps document embeddings frozen (no re-indexing needed)
  - Learns a linear transformation W: ℝ³⁸⁴ → ℝ³⁸⁴ applied to query embeddings ONLY
  - This pushes query vectors toward the "correct" part of the embedding space for trading
  - Training objective: maximize similarity between (query, relevant_doc) pairs, minimize similarity for (query, irrelevant_doc) pairs
- **Root cause (addressed)** : The adapter adjusts query vectors to be closer to domain-relevant document vectors, effectively "steering" the general embedding toward trading-specific semantics without modifying the base model or re-indexing documents.

### Root Cause Statement

> **General-purpose embedding models allocate <0.5% of their capacity to trading-specific semantics, causing queries about trading concepts (FVG, order blocks, liquidity grabs) to map to incorrect regions of the embedding space. Without domain adaptation, the model conflates trading jargon with everyday language, producing vectors that capture general meaning rather than trading-specific meaning — directly reducing retrieval precision for all trading queries.**

### Measured Evidence
- Trading acronym query "FVG": current top-5 results average 0.72 cosine similarity vs relevant doc at 0.78 — too close for reliable ranking
- Manual inspection: "Break of Structure" query returns results about "breaking structure" in general writing
- No mechanism to learn from 592 domain-specific chunks
- Outcome data from 119 trades is available but not used to improve embeddings

---

## Current State Analysis

| Component | Status | Limitation |
|-----------|--------|------------|
| all-MiniLM-L6-v2 | ✅ Working | General-purpose, no domain adaptation |
| Embedding adapter | ❌ Missing | No linear adapter trained |
| Synthetic training data | ❌ Missing | No (query, relevant_chunk) pairs |
| Fine-tuning pipeline | ❌ Missing | No training loop |
| Adapter inference | ❌ Missing | Query embedding not transformed at runtime |
| Evaluation (HR@10, MRR@10) | ❌ Missing | No retrieval metrics before/after |

---

## Typed Execution Plan

### DAG

```
Phase 4.1 ──[Generate synthetic Q/A pairs from all 592 chunks]──► Checkpoint 4.1
    │                                                              │ 3-5 queries per chunk = ~2000 pairs
    ▼                                                              │ 80/20 train/eval split by chunk
Phase 4.2 ──[Build training dataset (query, positive_chunk)]─────► Checkpoint 4.2
    │                                                              │ Negative mining: random chunks
    ▼                                                              │ Format: (query, pos_doc_id)
Phase 4.3 ──[Train linear adapter (Adam, 4 epochs, CPU)]────────► Checkpoint 4.3
    │                                                              │ Loss decreases each epoch
    ▼                                                              │ Weights saved to disk
Phase 4.4 ──[Integrate adapter into query pipeline]──────────────► Checkpoint 4.4
    │                                                              │ query → adapter_transform → embed
    ▼                                                              │ No changes to document embeddings
Phase 4.5 ──[Evaluate: HR@10, MRR@10 before/after]──────────────► Checkpoint 4.5
    │                                                              │ HR@10 improvement >= 5%
    ▼                                                              │ MRR@10 improvement >= 5%
Phase 4.6 ──[Auto-retrain trigger on new data]──────────────────► Done
                                                                   │ New > 10% more chunks → auto-retrain
```

### Phase 4.1 — Synthetic QA Generation

**Strategy**: Use LLM (Claude/GPT) to generate 3-5 diverse queries per chunk

```python
GENERATION_PROMPT = """Given the following trading strategy description, generate {num_queries} diverse search queries that a trader might use to find this strategy.

The queries should:
1. Cover different aspects (entry, exit, risk, psychology)
2. Use natural trader language (abbreviations, jargon)
3. Vary in specificity (some broad, some precise)
4. Not copy the text verbatim

Strategy text:
{chunk_text}

Return one query per line, no numbering."""

def generate_queries(chunk_text: str, num_queries: int = 3) -> list[str]:
    prompt = GENERATION_PROMPT.format(chunk_text=chunk_text, num_queries=num_queries)
    response = llm_call(prompt)
    queries = [q.strip() for q in response.strip().split("\n") if q.strip()]
    return queries[:num_queries]
```

**Cost estimate**: ~2000 chunks × 3 queries × ~100 tokens = ~600K tokens. At ~$3/M input + $15/M output ≈ ~$10-15 total. One-time cost.

**Offline alternative**: Use rule-based templates if no API budget:
```python
TEMPLATES = [
    lambda c: f"How to trade {c.setup_name}",
    lambda c: f"{c.setup_type} strategy for {c.market_condition} markets",
    lambda c: f"Entry conditions for {c.setup_name}",
    lambda c: f"Stop loss rules for {c.setup_name}",
    lambda c: f"What is {c.setup_name} in trading",
]
queries = [t(chunk) for t in TEMPLATES]
```

### Phase 4.2 — Dataset Builder

```python
from llama_index.finetuning import EmbeddingAdapterFinetuneEngine
from llama_index.core.embeddings import resolve_embed_model

# Format: list of (query, relevant_doc_text) tuples
train_pairs = []
eval_pairs = []

for chunk in all_chunks:
    for query in chunk.synthetic_queries:
        pair = (query, chunk.chunk_text)
        if chunk.id in eval_chunk_ids:
            eval_pairs.append(pair)
        else:
            train_pairs.append(pair)

# Save for reproducibility
import json
with open("strategy_db/finetune/train_pairs.json", "w") as f:
    json.dump(train_pairs, f)
with open("strategy_db/finetune/eval_pairs.json", "w") as f:
    json.dump(eval_pairs, f)
```

### Phase 4.3 — Training

```python
from llama_index.finetuning import EmbeddingAdapterFinetuneEngine
from llama_index.core.embeddings import resolve_embed_model
import torch.nn as nn

base_embed_model = resolve_embed_model("local:sentence-transformers/all-MiniLM-L6-v2")

# Linear adapter: 384 → 384 (no bias, simple projection)
finetune_engine = EmbeddingAdapterFinetuneEngine(
    train_pairs,
    base_embed_model,
    model_output_path="strategy_db/finetune/adapter_v1",
    epochs=4,
    verbose=True,
    batch_size=32,
    optimizer_params={"lr": 0.001},  # Adam default
)
finetune_engine.finetune()
```

**Expected training time on 16GB DDR3 CPU**: ~2-3 minutes for 4 epochs on ~1600 pairs.

### Phase 4.4 — Adapter Integration

```python
class FinetunedEmbedder:
    def __init__(self):
        self.base_embedder = SentenceTransformer("all-MiniLM-L6-v2")
        self.adapter = self._load_adapter()  # LinearAdapterEmbeddingModel

    def _load_adapter(self):
        from llama_index.core.embeddings import LinearAdapterEmbeddingModel
        import torch
        try:
            return LinearAdapterEmbeddingModel(
                self.base_embedder,
                "strategy_db/finetune/adapter_v1",
            )
        except Exception:
            return None  # Fallback to base

    def encode(self, texts: list[str]) -> list[list[float]]:
        if self.adapter is None:
            return self.base_embedder.encode(texts, normalize_embeddings=True).tolist()
        # LlamaIndex adapter transforms query embedding
        embeddings = self.base_embedder.encode(texts, normalize_embeddings=True)
        with torch.no_grad():
            embeddings = self.adapter._adapter(torch.tensor(embeddings))
        return embeddings.numpy().tolist()
```

Key detail: adapter transforms QUERY embeddings only. Document embeddings stay frozen. No re-indexing needed.

### Phase 4.5 — Evaluation

```python
def evaluate_retrieval(db, eval_pairs: list[tuple], top_k: int = 10):
    """Compute Hit Rate@k and Mean Reciprocal Rank@k."""
    hits = 0
    reciprocal_ranks = []
    for query, relevant_doc in eval_pairs:
        results = db.search_with_rerank(query, final_top_k=top_k)
        for rank, doc in enumerate(results):
            if doc["chunk_text"] == relevant_doc:
                hits += 1
                reciprocal_ranks.append(1.0 / (rank + 1))
                break
        else:
            reciprocal_ranks.append(0.0)

    hr = hits / len(eval_pairs)
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks)
    return {"HR@10": hr, "MRR@10": mrr}
```

### Phase 4.6 — Auto-Retrain Trigger

```python
class AutoRetrainTrigger:
    def __init__(self):
        self.last_chunk_count = self._load_count()

    def check_and_retrain(self, db):
        current_count = len(db.all_chunks)
        if current_count > self.last_chunk_count * 1.1:  # 10% growth
            print(f"[autofinetune] Chunks grew {self.last_chunk_count} → {current_count}. Retraining...")
            # Run Phase 4.1-4.3
            self.last_chunk_count = current_count
            self._save_count(current_count)
```

---

## Audit Benchmarks

### Pre-Phase Baseline

| Metric | Method | Current Value | Target |
|--------|--------|---------------|--------|
| HR@10 (Hit Rate at 10) | % of queries where relevant doc in top-10 | ~75% | >85% |
| MRR@10 (Mean Reciprocal Rank) | Average 1/rank of first relevant doc | ~0.55 | >0.70 |
| Cosine similarity (query, relevant doc) | Average over eval set | ~0.72 | >0.80 |
| Cosine similarity (query, irrelevant doc) | Average over eval set | ~0.68 | <0.60 |
| Gap (relevant - irrelevant) | Separation between signal and noise | ~0.04 | >0.20 |

### Post-Phase Verification Matrix

| Check | Tool | Pass Criteria |
|-------|------|---------------|
| Adapter trains without error | `finetune_engine.finetune()` | Loss decreases, no NaN |
| Adapter loads correctly | `LinearAdapterEmbeddingModel(...)` | No import errors |
| Query embedding is transformed | Before/after adapter comparison | Vectors differ |
| HR@10 improves | Eval before/after | >= +5 percentage points |
| MRR@10 improves | Eval before/after | >= +0.05 |
| No re-indexing needed | Document count unchanged | Same count as before |
| Fallback without adapter | Delete adapter file → query works | Falls back to base embedder |

---

## Verification Protocol (Block-Level)

### Block 1: Training

```bash
python3 -c "
from llama_index.finetuning import EmbeddingAdapterFinetuneEngine
from llama_index.core.embeddings import resolve_embed_model

base = resolve_embed_model('local:sentence-transformers/all-MiniLM-L6-v2')
pairs = [('How to trade FVG', 'FVG strategy entry conditions for long trades...')] * 50  # tiny test
engine = EmbeddingAdapterFinetuneEngine(pairs, base, model_output_path='/tmp/adapter_test', epochs=1)
engine.finetune()
print('Training OK')
"
```

### Block 2: Inference

```python
from llama_index.core.embeddings import LinearAdapterEmbeddingModel
import numpy as np

base = SentenceTransformer("all-MiniLM-L6-v2")
# Before adapter
embed_before = base.encode("FVG entry rules")
# Load adapter
adapter_model = LinearAdapterEmbeddingModel(base, "/tmp/adapter_test")
with np.testing.assert_raises(AssertionError):
    np.testing.assert_array_equal(embed_before, adapter_model.get_query_embedding("FVG entry rules"))
print("Adapter transforms query embeddings: OK")
```

### Block 3: End-to-End Retrieval

```python
db = StrategyDB(use_finetuned=True)
results_no_adapter = db.search_with_rerank("FVG entry", top_k=10, use_adapter=False)
results_with_adapter = db.search_with_rerank("FVG entry", top_k=10, use_adapter=True)
# Adapter should rank the truly relevant doc higher
assert results_with_adapter[0]["rerank_score"] >= results_no_adapter[0]["rerank_score"]
```

### Block 4: Regression (Fallback)

```bash
rm -rf strategy_db/finetune/adapter_v1
python3 -c "
from strategy_db.query import StrategyDB
db = StrategyDB()
# Should succeed even without adapter file
results = db.query('FVG entry')
print(f'Fallback OK: {len(results)} results')
"
```

---

## Rollback Plan

| Failure | Action |
|---------|--------|
| Training fails (OOM, NaN) | Reduce batch_size to 16, check learning rate |
| Adapter degrades results | Delete adapter file → falls back to base model |
| Only 1-2% improvement | Accept as incremental; the adapter is free (no re-index) |
| Synthetic queries too expensive | Use template-based queries instead of LLM generation |
| Adapter loading fails | Set `use_finetuned: false` in config → base model used |

## Estimated Effort

| Task | Time | Dependencies |
|------|------|-------------|
| Phase 4.1 — Synthetic QA | 1h | LLM API key (or templates) |
| Phase 4.2 — Dataset | 15 min | Phase 4.1 |
| Phase 4.3 — Training | 30 min | Phase 4.2, llama-index |
| Phase 4.4 — Integration | 30 min | Phase 4.3 |
| Phase 4.5 — Evaluation | 30 min | Phase 4.4 |
| Phase 4.6 — Auto-retrain | 15 min | Phase 4.3 |
| **Total** | **~3h** | |

---

## Success Criteria

- [ ] Linear adapter trained successfully on ~1600 query-doc pairs
- [ ] Training loss decreases across 4 epochs (no NaN, no divergence)
- [ ] Adapter transforms query embeddings differently from base embeddings
- [ ] HR@10 improves by >= 5 percentage points over base model
- [ ] MRR@10 improves by >= 0.05 over base model
- [ ] No re-indexing of documents required
- [ ] Graceful fallback to base model if adapter file missing or corrupted
- [ ] ~2 minute training time on 16GB DDR3 CPU
