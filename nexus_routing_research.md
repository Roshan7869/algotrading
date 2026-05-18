# NEXUS Routing Architecture Research
## Comparative Analysis: AnyTool, ScaleMCP, ToolkenGPT, LLM Wiki

Generated: 2026-05-15

---

## NEXUS CURRENT STATE SNAPSHOT

| Metric | Value |
|--------|-------|
| Total resources | 1686 |
| In "general" cluster | 683 (42%) |
| Unassigned (cluster=NULL) | 65 |
| Low cluster confidence | 819 (49%) |
| Cluster centroids computed | 0 / 8 (all has_centroid=false) |
| FAISS index | EMPTY (semantic search returns nothing) |
| Thompson Sampling | DISABLED |
| Self-Reflection | DISABLED |
| Cluster Affinity | DISABLED |
| Outcome close rate | 21% (79% of routes never evaluated) |
| Routing accuracy | 20.6% (37/180 correct) |
| Routing method | Keyword trigger matching (primary) |

**Critical Diagnosis:** NEXUS has 5 layers of learning infrastructure implemented but all disabled. The primary routing relies on keyword overlap which produces 20.6% accuracy. The FAISS index is empty, meaning semantic search is completely non-functional.

---

## 1. AnyTool (arxiv:2402.04207)
### Hierarchical 3-Layer Tool Retrieval with Self-Reflection

**Core Pattern: Semantic Funnel + Reflective Retry**

AnyTool decomposes tool retrieval into 3 hierarchical layers:

- **Layer 1 (Category):** Match query embedding to category meta-descriptions. Reduces 1000+ candidates to ~10-30.
- **Layer 2 (Tool):** Fine-grained embedding search within activated categories. Reduces to top-K (K=10-20).
- **Layer 3 (Reflect):** If LLM verifies a tool is wrong, REFORMULATE the query and retry up to MAX_RETRY times.

#### Key Architectural Decisions

**1. Discovery: SEMANTIC HIERARCHICAL (not keyword flat)**
- Layer 1 uses category-level meta-descriptions as a "table of contents" for the tool universe.
- The model never sees all tools at once. It navigates a hierarchy.
- This is fundamentally different from NEXUS's keyword trigger lists (["analyze","plan","review"...]).
- Keywords are brittle: they miss synonyms, misspellings, and novel queries that don't contain the trigger words.

**2. Cold-Start: LAZY EMBEDDING ON ACTIVATION**
- New tools get category-level embeddings immediately (cheap, coarse).
- Full tool embeddings are computed on-demand when their category is first activated, then cached.
- This means the system never blocks on computing 1686 embeddings upfront. It computes them progressively.

**3. Ghost Resource Prevention: CATEGORY MEMBERSHIP IS MANDATORY**
- If a tool has no category assignment, it is invisible to Layer 1 and never surfaces.
- Category assignment happens at registration via embedding similarity to category centroids — not manual tagging.
- This is the opposite of NEXUS's "general" catch-all cluster with 683 resources.

**4. Re-Indexing: ON-DEMAND + CACHED**
- Category centroids recomputed when tools are added/removed.
- Individual tool embeddings computed lazily and cached.

**5. Thresholds**
- Layer 1: cosine_similarity >= 0.3 to activate category
- Layer 2: top-K within activated categories
- Layer 3: MAX_RETRY = 3 for self-reflection

#### NEXUS Applicability

| NEXUS Problem | AnyTool Solution |
|---------------|-----------------|
| 683 resources in "general" dump | Mandatory category assignment via embedding similarity |
| Keyword triggers miss queries | Replace with semantic centroids for Layer 1 |
| No self-reflection on failure | Enable NEXUS_REFLECTION with query reformulation |
| FAISS index empty | Build embeddings progressively (lazy compute + cache) |

---

## 2. ScaleMCP
### CRUD Pipeline for MCP Tool Management with Dynamic Embeddings

**Core Pattern: Registration-Time Embedding + Delta Re-Index + Usage Boost**

ScaleMCP treats MCP tool definitions as versioned documents in a CRUD database, with embeddings computed and stored alongside each tool record.

#### Key Architectural Decisions

**1. Discovery: EMBEDDING-FIRST with keyword fallback**
- Primary signal: cosine similarity between query embedding and tool embedding (computed from description + parameters).
- Secondary signal: keyword match on tool name and description (fallback only).
- The embedding is computed at CREATE time, never lazy. New tools are immediately searchable.

**2. Cold-Start: RICH DESCRIPTIONS + EXPLORATION BONUS**
- No usage history needed for initial routing — the tool's description IS the primary signal.
- New tools (0 outcomes) get a small random exploration bonus (epsilon=0.1) to ensure they occasionally surface and accumulate history.
- This is critical: it prevents the "rich get richer" problem where only well-established tools get selected.

**3. Ghost Resource Prevention: CRUD LIFECYCLE**
- Every tool has: embedding (computed at CREATE), content_hash, last_synced, status (active/deprecated/removed).
- Tools not synced in N days auto-deprecated (excluded from search, not deleted).
- Sync polling detects tools that disappeared from the MCP server.

**4. Re-Indexing: DELTA HASH-BASED**
- Each tool definition has a content_hash. On sync, if hash unchanged, skip re-embedding. If changed, recompute.
- This is O(changed_tools) per sync, not O(all_tools).
- Embedding model version is tracked. If model upgraded, trigger full re-embedding.

**5. Scoring: SIMILARITY * USAGE_BOOST**
- final_score = similarity * (1 + log(1 + times_correct))
- Cold-start boost: +0.1 random exploration for tools with 0 outcomes
- Diversity: deduplicate results by category — don't return 5 variants of same tool

#### NEXUS Applicability

| NEXUS Problem | ScaleMCP Solution |
|---------------|-------------------|
| FAISS empty (no embeddings) | Compute embeddings at resource CREATE/UPDATE time, store in DB |
| 819 low-confidence resources | content_hash for delta re-embedding when body changes |
| 21% outcome close rate | Auto-close outcomes after timeout; exploration bonus for no-history resources |
| Thompson Sampling disabled | Enable as BOOST on top of similarity, not as primary signal |
| No re-indexing pipeline | Build content_hash + embedding column; delta re-embed on hash change |

---

## 3. ToolkenGPT (arxiv:2305.05452)
### Tool Embeddings as Tokens in LLM Vocabulary

**Core Pattern: Vocabulary Membership + Softmax Selection + Fallback Retrieval**

ToolkenGPT adds each tool as a special token ("toolken") to the LLM vocabulary. The model generates tool tokens as part of its output sequence, conditioned on the input.

#### Key Architectural Decisions

**1. Discovery: VOCABULARY MEMBERSHIP (closed set)**
- Tool = token in vocabulary. If it's in the vocab, it's reachable. If not, it's not.
- Eliminates the retrieval problem entirely for the closed tool set.
- BUT: Cannot handle dynamic tool sets without fine-tuning.

**2. Cold-Start: IMPOSSIBLE WITHOUT FINE-TUNING**
- New tools require vocabulary expansion + fine-tuning on examples.
- Not practical for NEXUS's 1686 dynamic resources.
- Key insight: ToolkenGPT is only useful for a SMALL, STABLE set of frequently-used tools.

**3. Ghost Resource Prevention: VOCABULARY = MEMBERSHIP**
- A tool that's in the vocabulary but never generated is a "ghost token."
- Low-frequency tokens get "forgotten" by the model (less likely to be sampled).
- Mitigation: Temperature scaling on tool token logits increases probability of rare tools.

**4. Scoring: SOFTMAX OVER TOOL TOKENS**
- The LLM's soft-max over tool tokens IS the scoring mechanism.
- Confidence threshold: if max probability < 0.1, fall back to retrieval.
- N-gram penalty: prevent repeated calls to the same tool.

#### NEXUS Applicability (Hybrid Pattern)

| NEXUS Problem | ToolkenGPT-Inspired Solution |
|---------------|------------------------------|
| Every query goes through full retrieval | "Hot cache" of top-50 resources by usage — direct lookup, no retrieval |
| Same resource selected repeatedly | Frequency penalty on recently-selected resources (-0.1 per recent selection) |
| All 1686 resources searched equally | Two-tier: hot resources (direct lookup) + cold resources (full funnel) |

The hybrid pattern: Use ToolkenGPT-style direct access for the 50 most-proven resources, and AnyTool-style semantic funnel for the remaining 1636. This is the architectural recommendation.

---

## 4. Karpathy's LLM Wiki
### Build/Query Interlinked Markdown Knowledge Bases

**Core Pattern: Index-First + Mandatory Cross-References + Graduation Thresholds + Drift Detection**

(This is implemented as the `hermes-skill-research-llm-wiki` skill in NEXUS itself.)

#### Key Architectural Decisions

**1. Discovery: INDEX-FIRST + SEARCH-SECOND**
- The `index.md` (structured catalog) is the PRIMARY discovery mechanism.
- Full-text search is the BACKUP for wikis with 100+ pages.
- The index provides one-line summaries — enough to decide relevance without reading the full page.
- This mirrors AnyTool's Layer 1: a compact, navigable overview that reduces search space.

**2. Cold-Start / Creation Thresholds**
- "Create a page when entity appears in 2+ sources OR is central to one source."
- This prevents creating pages for every trivial mention.
- For NEXUS: Resources should need to prove relevance before graduating from an incubator.

**3. Ghost Resource Prevention: MANDATORY CROSS-REFERENCES**
- "Every page must link to at least 2 other pages" — ensures no orphans.
- Lint specifically checks for orphan pages (zero inbound links).
- For NEXUS: Every resource should have `related_resource_ids` linking to at least 2 others, ensuring multi-path discoverability.

**4. Re-Indexing / Drift Detection**
- Raw sources get a `sha256` hash at ingest time.
- On re-ingest: recompute hash, compare to stored value. Skip if identical, flag drift and update if different.
- This is exactly what ScaleMCP does with content_hash, applied to knowledge content.
- For NEXUS: Every resource's embedding should be tied to a hash of its body content. When body changes, re-embed.

**5. Quality Signals**
- `confidence: high | medium | low` based on number of corroborating sources.
- `contested: true` for pages with unresolved contradictions.
- Lint surfaces low-confidence pages for review.

#### NEXUS Applicability

| NEXUS Problem | LLM Wiki Solution |
|---------------|--------------------|
| 683 resources in "general" clutter | Resources need graduation criteria to leave incubator |
| Resources isolated (no cross-links) | Mandatory `related_resources` (min 2) for discoverability |
| No content drift detection | content_hash on body text; re-embed on hash change |
| No quality rating on resources | confidence scoring based on usage outcomes (similar to wiki's source corroboration) |

---

## 5. Supplementary Approaches

### Gorilla (API Bloom Filter Pre-Filter)
- Treats tool selection as a RETRIEVAL problem, not a generation problem.
- Uses an "API bloom filter" to reduce the active tool set before LLM invocation.
- Applicable to NEXUS: The 1686 resources should be pre-filtered to a relevant subset (~20-50) before the LLM even sees them.

### ToolFormer (Perplexity-Based Tool Selection)
- Decides whether to call an API by measuring if the API output improves generation quality (perplexity reduction).
- This validates NEXUS's outcome tracking approach, but only if the feedback loop is closed (currently 21% close rate).

### APIBank (Hierarchical Tool Need)
- Not every query needs a tool. Adds a "no tool needed" option.
- NEXUS currently routes EVERY query to some resource, even when none is needed.

---

## CONCRETE ARCHITECTURAL PATTERNS FOR NEXUS

### PATTERN 1: Three-Layer Semantic Funnel (from AnyTool)

**Current:** Keyword trigger matching over 1686 resources
**Proposed:**
- Layer 1: Semantic similarity between query embedding and cluster CENTROIDS (not trigger keywords). Reduces 1686 -> ~200.
- Layer 2: FAISS search within activated clusters. Reduces ~200 -> 20 candidates.
- Layer 3: Self-reflection with query reformulation (max 3 retries).

**Required changes:** Build embeddings, compute centroids, enable FAISS, enable NEXUS_REFLECTION.

### PATTERN 2: Registration-Time Embedding (from ScaleMCP)

**Current:** Resources added with no embedding computation. FAISS returns nothing.
**Proposed:** Embed every resource at CREATE time from body content. Store embedding + content_hash. Delta re-embed on hash change.

**Required changes:** Add embedding vector column, add content_hash column, build FAISS index.

### PATTERN 3: Hot Cache + Retrieval Tail (from ToolkenGPT)

**Current:** All resources searched equally (poorly).
**Proposed:** Track "hot" resources (times_correct >= 10, success_rate >= 0.7). Direct lookup for hot resources. Full funnel for the rest. Frequency penalty for recently-selected resources.

**Required changes:** Add last_selected timestamp, implement two-tier routing.

### PATTERN 4: Graduation-Based Clustering (from LLM Wiki)

**Current:** 683 resources in "general" dumping ground.
**Proposed:** New resources go to "incubator" (not "general"). Must be triggered 2+ times AND have clear semantic cluster match (cosine >= 0.4) to graduate. Mandatory related_resources (min 2).

**Required changes:** Replace "general" with "incubator", add graduation logic, add related_resources field.

### PATTERN 5: Outcome-Weighted Boosting (from ScaleMCP + ToolFormer)

**Current:** Thompson Sampling disabled. 79% of routes never evaluated.
**Proposed:** 
- Primary: semantic similarity (Pattern 1)
- Boost: usage_score = log(1 + times_correct) * success_rate
- Cold-start: epsilon=0.1 exploration bonus for 0-outcome resources
- Auto-close: 5-minute timeout, mark as "routed"

**Required changes:** Enable Thompson Sampling as boost (not primary), add auto-close timer.

### PATTERN 6: Semantic Cluster Assignment (from AnyTool + ScaleMCP)

**Current:** Clusters assigned via trigger keywords. All centroids are false.
**Proposed:** Compute centroids from member embeddings. Assign new resources via embedding similarity. Weekly centroid recomputation. "General" gets a centroid too, and sub-200-similarity resources stay in incubator.

**Required changes:** Build all 1686 embeddings, compute centroids, semantic assignment.

---

## PRIORITY ACTION ITEMS

1. **Build FAISS index** — Currently empty. Compute embeddings for all 1686 resources from body content. Without this, semantic search is broken.

2. **Compute cluster centroids** — All 8 clusters have has_centroid=false. Compute from member embeddings. Use for Layer 1 routing.

3. **Enable NEXUS_REFLECTION** — Implemented but disabled. Turn on with MAX_RETRY=3. Key differentiator.

4. **Add content_hash** — For delta re-embedding when body content changes. Prevents stale embeddings.

5. **Graduate/archive "general" cluster** — 683 in general is 42% of total. Run semantic assignment against centroids. Archive 0-trigger resources with no cluster match.

6. **Fix outcome close rate** — 21% means 79% never evaluated. Add 5-minute auto-close with "routed" status.

7. **Enable Thompson Sampling as boost** — Not as primary routing (it requires history), but as a scoring multiplier on top of semantic similarity. Add epsilon exploration for cold-start resources.

8. **Add mandatory related_resources** — Every resource links to at least 2 others. Enables traversal-based discovery as fallback.

9. **Frequency penalty** — Prevent the same resource from being selected repeatedly. -0.1 per selection in the last N queries.

10. **Add "no tool needed" path** — Not every query requires a resource. Add a confidence threshold below which the system returns nothing.

---

## COMPARATIVE SUMMARY

| Aspect | AnyTool | ScaleMCP | ToolkenGPT | LLM Wiki | NEXUS Now | NEXUS Proposed |
|--------|---------|----------|-------------|-----------|-----------|----------------|
| Discovery | 3-layer semantic funnel | Embed at CREATE + search | Vocab membership | Index + search | Keyword matching | 3-layer semantic funnel |
| Cold-start | Lazy embed on activate | Embed at CREATE + boost | Fine-tune required | Page thresholds | No handling | Embed at CREATE + epsilon exploration |
| Ghost prevent | Category required | CRUD + sync | In vocab = findable | 2+ cross-refs | 683 in general | Incubator + graduation + related_resources |
| Re-index | On-demand + cached | Delta hash + re-embed | Fine-tune cycle | Hash drift detect | None | Content hash + delta re-embed |
| Scoring | Cosine + retry | Similarity * usage boost | Softmax tokens | Confidence levels | Keyword overlap | Similarity * usage_boost + cold_bonus - frequency_penalty |
| Reflection | Reformulate 3x | N/A | N/A | Lint contradictions | Disabled | Enable with max_retry=3 |
