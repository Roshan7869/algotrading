# Graphify Live Execution Plan — 4-Layer Typed DAG

## Structure

Each node in the plan has a **4-level ID**: `L<layer>.<phase>.<task>.<subtask>`

Example: `L1.2.3.4` = Layer 1, Phase 2, Task 3, Subtask 4

| Level | Granularity | Example | Scope |
|-------|-------------|---------|-------|
| Layer | ~10-20 tasks | `L1` | One logical goal |
| Phase | ~3-5 tasks | `L1.2` | One file category |
| Task | ~2-4 subtasks | `L1.2.3` | One file change |
| Subtask | ~5-30 lines | `L1.2.3.4` | One edit in one file |

---

## Layer 0: Graphify Live Tracking Infrastructure

**Goal:** Build the execution tracking system that grounds all subsequent layers. Every action below is logged to this graph.

### Phase 0.1: Live Tracker Core (`graphify-out/live_tracker.py`)

| ID | Task | File | Action | Inputs | Outputs | Guardrails | Tokens |
|----|------|------|--------|--------|---------|------------|--------|
| L0.1.1 | Create live_tracker.py skeleton | `graphify-out/live_tracker.py` | NEW | — | live_tracker.py | Must be single file, <300 lines | 200 |
| L0.1.1.1 | Phase DAG class (nodes = phases/tasks, edges = deps) | `live_tracker.py` | NEW | — | PhaseGraph class | Uses dict not DB, no external deps | 60 |
| L0.1.1.2 | Action logger (log_action, token_count, files_touched) | `live_tracker.py` | NEW | PhaseGraph | ActionLog class | Logs to JSON, auto-rotates at 1000 entries | 50 |
| L0.1.1.3 | Context budget monitor (65% warn, 80% block, 85% force-checkpoint) | `live_tracker.py` | NEW | ActionLog | ContextBudget | Reads token estimate from action log | 40 |
| L0.1.1.4 | Guardrail checker (verify current action matches planned task scope) | `live_tracker.py` | NEW | PhaseGraph | GuardrailGate | Rejects file edits not in planned file list | 50 |

### Phase 0.2: Execution Protocol Wrapper (`graphify-out/execution_protocol.py`)

| ID | Task | File | Action | Inputs | Outputs | Guardrails | Tokens |
|----|------|------|--------|--------|---------|------------|--------|
| L0.2.1 | Create execution_protocol.py | `graphify-out/execution_protocol.py` | NEW | live_tracker.py | execution_protocol.py | <200 lines | 150 |
| L0.2.1.1 | pre_phase() — read state, check deps, budget, guardrails | `execution_protocol.py` | NEW | L0.1 | pre_phase hook | Must NOT modify any file | 40 |
| L0.2.1.2 | post_phase() — verify, write audit, compact | `execution_protocol.py` | NEW | L0.1 | post_phase hook | Must NOT modify project source files | 40 |
| L0.2.1.3 | checkpoint() — snapshot to graphify-out/memory/ | `execution_protocol.py` | NEW | L0.2.1.2 | checkpoint JSON | Writes to memory/, not cwd | 30 |
| L0.2.1.4 | hallucination_gate(planned_scope, actual_action) — OOD check | `execution_protocol.py` | NEW | L0.1.1.4 | pass/reject | Rejects if file not in planned scope | 40 |

### Phase 0.3: Enhanced CLI (`graphify-out/track.py`)

| ID | Task | File | Action | Inputs | Outputs | Guardrails | Tokens |
|----|------|------|--------|--------|---------|------------|--------|
| L0.3.1 | Add `start <phase> <task>` command | `track.py` | MODIFY | L0.1 | CLI | Must NOT break existing `status`/`mark` commands | 30 |
| L0.3.2 | Add `log <phase> <task> <msg>` command | `track.py` | MODIFY | L0.1.1.2 | CLI | Writes to action log | 20 |
| L0.3.3 | Add `checkpoint` command | `track.py` | MODIFY | L0.2.1.3 | CLI | Same as execution_protocol.checkpoint() | 20 |
| L0.3.4 | Add `budget` command — show context budget status | `track.py` | MODIFY | L0.1.1.3 | CLI | Read-only | 15 |

### Phase 0.4: ChromaDB KB Sync (`graphify-out/ingest_graphify_memory.py`)

| ID | Task | File | Action | Inputs | Outputs | Guardrails | Tokens |
|----|------|------|--------|--------|---------|------------|--------|
| L0.4.1 | Create KB sync script | `graphify-out/ingest_graphify_memory.py` | NEW | — | ingest script | <100 lines | 80 |
| L0.4.1.1 | Read memory/ JSON files | `ingest_graphify_memory.py` | NEW | L0.2.1.3 | parsed results | Must handle empty/missing gracefully | 20 |
| L0.4.1.2 | Format as user_knowledge chunks | `ingest_graphify_memory.py` | NEW | L0.4.1.1 | formatted docs | Title = phase_id, content = decisions + results | 25 |
| L0.4.1.3 | Write to ChromaDB user_knowledge collection | `ingest_graphify_memory.py` | NEW | L0.4.1.2 | KB entries | Uses shared chromadb client, no schema change | 35 |

### Phase 0.5: Seed phase_tracker.json with L0 tasks

| ID | Task | File | Action | Inputs | Outputs | Guardrails | Tokens |
|----|------|------|--------|--------|---------|------------|--------|
| L0.5.1 | Update phase_tracker.json with L0 phases/tasks | `phase_tracker.json` | MODIFY | — | updated tracker | Must preserve existing Phases 1-4 data | 20 |
| L0.5.2 | Verify `track.py status` renders L0 correctly | terminal | VERIFY | L0.5.1 | terminal output | Run `python3 track.py status` | 10 |

---

## Layer 1: Foundation — Fix Bridge Bugs (P0–P1)

### Phase 1.1: Bridge — add enabled property + logging

| ID | Task | File | Action | Inputs | Outputs | Guardrails | Tokens |
|----|------|------|--------|--------|---------|------------|--------|
| L1.1.1 | Add `import logging` + `logger` to bridge.py | `nexus/bridge.py` | MODIFY | — | logging setup | Must NOT change any existing logic | 10 |
| L1.1.2 | Add `@property enabled` that checks NEXUS_THOMPSON_ROUTING env | `nexus/bridge.py` | MODIFY | — | enabled prop | Returns bool, no side effects | 15 |
| L1.1.3 | Add logger.warning to ImportError catch in feed_outcome_to_nexus | `nexus/bridge.py` | MODIFY | — | logged errors | Must NOT re-raise exception | 10 |
| L1.1.4 | Add logger.warning to ImportError catch in record_coach_outcome | `nexus/bridge.py` | MODIFY | — | logged errors | Same pattern as L1.1.3 | 10 |
| L1.1.5 | Verify bridge loads + enabled property works | terminal | VERIFY | L1.1.1-4 | `python3 -c` | `python3 -c "from nexus.bridge import get_bridge; b=get_bridge(); print(b.enabled)"` | 10 |

### Phase 1.2: Search — fix _get_user_collection() client reference

| ID | Task | File | Action | Inputs | Outputs | Guardrails | Tokens |
|----|------|------|--------|--------|---------|------------|--------|
| L1.2.1 | Replace `_get_collection()._client` with `chromadb.PersistentClient` | `strategy_db/search.py` | MODIFY | — | new _get_user_collection | Must NOT change _get_collection() | 20 |
| L1.2.1.1 | Import chromadb + Settings at function scope or reuse module-level | `search.py:L543-552` | MODIFY | — | fixed import | Use existing chromadb import, don't add new top-level import | 10 |
| L1.2.1.2 | Instantiate PersistentClient directly with DB_DIR | `search.py:L547` | MODIFY | — | direct client | Use same DB_DIR as _get_collection() | 10 |
| L1.2.2 | Verify query_user_knowledge() works | terminal | VERIFY | L1.2.1 | terminal output | `python3 -c "from strategy_db.search import query_user_knowledge; print(query_user_knowledge('project rules'))"` | 10 |

### Phase 1.3: Add logging to silent catch blocks

| ID | Task | File | Action | Inputs | Outputs | Guardrails | Tokens |
|----|------|------|--------|--------|---------|------------|--------|
| L1.3.1 | Add logging to event_bridge.py try/except blocks | `nexus/event_bridge.py` | MODIFY | — | logged errors | Add import logging + logger.warning to both try blocks | 15 |
| L1.3.2 | Add logging to outcome_sync.py exception handlers | `strategy_db/outcome_sync.py` | MODIFY | — | logged errors | Add import logging + logger.warning where bare except exists | 15 |
| L1.3.3 | Verify logger output | terminal | VERIFY | L1.3.1-2 | terminal output | Set LOGLEVEL=DEBUG, trigger each path | 15 |

### Phase 1.4: Set NEXUS_THOMPSON_ROUTING env var

| ID | Task | File | Action | Inputs | Outputs | Guardrails | Tokens |
|----|------|------|--------|--------|---------|------------|--------|
| L1.4.1 | Add NEXUS_THOMPSON_ROUTING=true to ~/.bashrc | `~/.bashrc` | MODIFY | — | env var set | Must NOT change any other line in bashrc | 10 |
| L1.4.2 | Verify env var is loaded | terminal | VERIFY | L1.4.1 | echo $VAR | Source bashrc, echo the var | 5 |

---

## Layer 2: Hook Injection — Prompt-time ChromaDB + Outcome Logging

### Phase 2.1: UserPromptSubmit handler

| ID | Task | File | Action | Inputs | Outputs | Guardrails | Tokens |
|----|------|------|--------|--------|---------|------------|--------|
| L2.1.1 | Add TRADING_KEYWORDS list + trading prompt detection fn | `hook-handler.cjs` | MODIFY | — | keyword matcher | Must be < 20 keywords, case-insensitive | 15 |
| L2.1.2 | Add `user-prompt` command handler that calls ChromaDB via subprocess | `hook-handler.cjs` | MODIFY | L2.1.1 | handler fn | Must timeout after 3s, must NOT block prompt | 30 |
| L2.1.3 | Format top-3 results as context injection string | `hook-handler.cjs` | MODIFY | L2.1.2 | formatted ctx | Truncate to 1000 chars max | 20 |
| L2.1.4 | Verify handler works standalone | terminal | VERIFY | L2.1.3 | terminal output | `echo '{"prompt":"show me liquidity strategies"}' | node hook-handler.cjs user-prompt` | 10 |

### Phase 2.2: PostToolUse outcome logging

| ID | Task | File | Action | Inputs | Outputs | Guardrails | Tokens |
|----|------|------|--------|--------|---------|------------|--------|
| L2.2.1 | Add `post-tool` handler that detects nexus_*/query_* tool names | `hook-handler.cjs` | MODIFY | — | tool detector | Must match `nexus_*`, `query_*`, `search_*` tool names | 15 |
| L2.2.2 | Wire PostToolUse to call feed_outcome_to_nexus() subprocess | `hook-handler.cjs` | MODIFY | L2.2.1 | outcome call | Timeout 5s, must not block tool response | 25 |
| L2.2.3 | Add outcome_sync.py trigger after each trade outcome | `hook-handler.cjs` | MODIFY | L2.2.2 | sync trigger | Only triggers on "correct"/"wrong" outcomes | 20 |
| L2.2.4 | Register handlers in settings.json hook config | `.claude/settings.json` | READ-VERIFY | L2.2.1-3 | validation | Verify post-tool hooks exist in settings.json, document path | 10 |

---

## Layer 3: Learning Loop Activation

### Phase 3.1: Verify Thompson config

| ID | Task | File | Action | Inputs | Outputs | Guardrails | Tokens |
|----|------|------|--------|--------|---------|------------|--------|
| L3.1.1 | Confirm MIN_SAMPLES_FOR_ROUTING=3 in learner.py | `nexus/core/learner.py` | READ | — | verified value | Must be <= 5 | 5 |
| L3.1.2 | Confirm LEARNING_ENABLED reads env var correctly | `nexus/server/event_bridge.py` | READ | L1.4.1 | verified | Must use `os.environ.get("NEXUS_THOMPSON_ROUTING")` | 5 |
| L3.1.3 | Test Thompson is enabled end-to-end | terminal | VERIFY | L3.1.1-2 | terminal output | `python3 -c "import os; os.environ['NEXUS_THOMPSON_ROUTING']='true'; from nexus.server.event_bridge import EventBridge; eb=EventBridge(); print(eb.outcome_to_event('correct', {'provider':'test','model':'test'}))"` | 15 |

### Phase 3.2: Auto-outcome-sync wiring

| ID | Task | File | Action | Inputs | Outputs | Guardrails | Tokens |
|----|------|------|--------|--------|---------|------------|--------|
| L3.2.1 | Add `PYTHONPATH` to outcome_sync subprocess call hook | `hook-handler.cjs` | MODIFY | L2.2.3 | env setup | Must use same PYTHONPATH as MCP configs | 10 |
| L3.2.2 | Verify outcome_sync.py can run standalone | terminal | VERIFY | L3.2.1 | terminal output | `cd /home/roshan/Downloads/Algotrading && python3 strategy_db/outcome_sync.py` | 10 |

---

## Layer 4: IDE Config Unification

### Phase 4.1: Create single source of truth

| ID | Task | File | Action | Inputs | Outputs | Guardrails | Tokens |
|----|------|------|--------|--------|---------|------------|--------|
| L4.1.1 | Create .opencode/mcp-shared.json with strategy-kb + nexus | `.opencode/mcp-shared.json` | NEW | — | shared config | Must match existing working configs exactly | 15 |
| L4.1.2 | Add `__source` metadata field to shared config | `.opencode/mcp-shared.json` | MODIFY | L4.1.1 | annotated config | `"__source": ".opencode/mcp-shared.json"` | 5 |

### Phase 4.2: Point all 3 IDEs to shared config

| ID | Task | File | Action | Inputs | Outputs | Guardrails | Tokens |
|----|------|------|--------|--------|---------|------------|--------|
| L4.2.1 | Update ~/.config/opencode/opencode.json with reference | `~/.config/opencode/opencode.json` | MODIFY | L4.1 | updated config | Must keep existing model/provider config intact | 10 |
| L4.2.2 | Update .cursor/mcp.json with reference | `.cursor/mcp.json` | MODIFY | L4.1 | updated config | Must keep existing structure | 10 |
| L4.2.3 | Update ~/.continue/config.json with reference | `~/.continue/config.json` | MODIFY | L4.1 | updated config | Must keep models array intact | 10 |
| L4.2.4 | Verify all 3 configs are valid JSON | terminal | VERIFY | L4.2.1-3 | terminal output | `python3 -m json.tool` on each file | 5 |

---

## Layer 5: Full E2E Verification

### Phase 5.1: Unit tests

| ID | Task | File | Action | Inputs | Outputs | Guardrails | Tokens |
|----|------|------|--------|--------|---------|------------|--------|
| L5.1.1 | Run existing test suite | terminal | VERIFY | — | test results | `python3 -m pytest tests/ -x -v --timeout=30` — must not break existing 146 passing | 30 |
| L5.1.2 | Test bridge.enabled property | terminal | VERIFY | L1.1 | test results | `python3 -c "from nexus.bridge import get_bridge; assert hasattr(get_bridge(), 'enabled')"` | 5 |
| L5.1.3 | Test query_user_knowledge() actually returns results | terminal | VERIFY | L1.2 | test results | `python3 -c "from strategy_db.search import query_user_knowledge; r=query_user_knowledge('test'); assert isinstance(r, list)"` | 5 |

### Phase 5.2: Integration chain test

| ID | Task | File | Action | Inputs | Outputs | Guardrails | Tokens |
|----|------|------|--------|--------|---------|------------|--------|
| L5.2.1 | Test: hook → ChromaDB query → formatted output | terminal | VERIFY | L2.1 | terminal | `echo '{"prompt":"liquidity trap"}' | node .claude/helpers/hook-handler.cjs user-prompt` | 15 |
| L5.2.2 | Test: PostToolUse → outcome → NEXUS learning | terminal | VERIFY | L2.2, L3.1 | terminal | Simulate a tool outcome, verify event_bridge logs it | 20 |
| L5.2.3 | Test: outcome_sync → ChromaDB metadata update | terminal | VERIFY | L3.2 | terminal | Run outcome_sync.py, check a chunk has outcome_win_rate | 15 |

### Phase 5.3: Graphify audit

| ID | Task | File | Action | Inputs | Outputs | Guardrails | Tokens |
|----|------|------|--------|--------|---------|------------|--------|
| L5.3.1 | Run `track.py status` for full dashboard | terminal | VERIFY | L0.5 | terminal output | All phases must show correct progress | 10 |
| L5.3.2 | Ingest graphify memory to ChromaDB user_knowledge | terminal | VERIFY | L0.4 | terminal output | `python3 graphify-out/ingest_graphify_memory.py` | 10 |
| L5.3.3 | Query KB for execution history | terminal | VERIFY | L5.3.2 | terminal output | `python3 strategy_db/gcode_bridge.py query "execution phase results"` | 10 |
| L5.3.4 | Generate final audit summary | terminal | VERIFY | L5.3.1-3 | audit text | Count: total tasks, verified, failed, skipped | 20 |

---

## Guardrails (Applied to EVERY Phase)

| Guardrail | Check | Action on Violation |
|-----------|-------|---------------------|
| **OOM: Context budget** | Before each phase, check current token estimate | At 65%: warn. At 80%: block edits. At 85%: force checkpoint+compact |
| **OOD: File scope** | Every file touch must match planned file list for this task | REJECT: "File X is not in planned scope for task Y. Planned: [list]" |
| **OOD: Task boundary** | Only execute tasks listed in current phase | REJECT: "Task X not in phase Y. Planned tasks: [list]" |
| **Regression** | After every file edit, re-run `python3 -c "from <modified_module> import *"` | STOP: ImportError means broken module |
| **Checkpoint** | After every phase, write checkpoint to graphify-out/memory/ | WARN if no checkpoint file found |
| **KB Sync** | After every layer, sync to ChromaDB user_knowledge | WARN if ChromaDB unavailable (non-fatal) |

---

## Dependency Graph (DAG)

```
L0.1 ─→ L0.2 ─→ L0.3 ─→ L0.4 ─→ L0.5
                                      │
                                      ▼
                                 L1.1 ─→ L1.2 ─→ L1.3 ─→ L1.4
                                                          │
                                                          ▼
                                                     L2.1 ─→ L2.2
                                                          │    │
                                                          ▼    ▼
                                                     L3.1    L3.2
                                                          │    │
                                                          ▼    ▼
                                                     L4.1 ─→ L4.2
                                                          │    │
                                                          ▼    ▼
                                                     L5.1 ─→ L5.2 ─→ L5.3
```

**Dependency rule:** A phase can only start when ALL its inputs (phases listed in `Inputs` column) are verified complete.

---

## Estimated Token Budget

| Layer | Tasks | Est Tokens | Checkpoints | Max Context Before Compact |
|-------|-------|------------|-------------|---------------------------|
| L0 | 18 | 4,000 | 5 | 65% warning, 80% block |
| L1 | 13 | 1,500 | 4 | 65% warning, 80% block |
| L2 | 8 | 1,500 | 2 | 65% warning, 80% block |
| L3 | 4 | 500 | 2 | 65% warning, 80% block |
| L4 | 5 | 600 | 2 | 65% warning, 80% block |
| L5 | 8 | 2,000 | 3 | 65% warning, 80% block |
| **Total** | **56** | **10,100** | **18** | — |

---

## Execution Protocol

1. **Pre-phase** → Run `track.py start <phase>`, check deps, check budget, check guardrails
2. **Execute** → One subtask at a time, log each action with `track.py log`, verify after each
3. **Post-phase** → Run `track.py checkpoint`, sync to KB, compact context
4. **Audit** → After each layer, run full `track.py status` + verify no regressions
