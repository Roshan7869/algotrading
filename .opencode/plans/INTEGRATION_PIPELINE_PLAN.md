# Graphify Execution Plan — Integration Pipeline Fix

## Goal
Fix the integration pipeline between ChromaDB, NEXUS, hook-handler, and agent to enable actual learning from outcomes.

## Root Cause (First Principles)
- `settings.json` hook commands call wrong handler names
- `UserPromptSubmit` calls `route` instead of `user-prompt` → ChromaDB injection dead
- `PostToolUse` only fires on `Write|Edit|Bash` → misses `nexus_*` tool outcomes
- `NEXUS_THOMPSON_ROUTING` unset → Thompson sampling never activates
- Outcome sync matches 9/592 due to strict fuzzy matching

## Layers

### L6: Graphify Setup (Tracking Infrastructure)
- L6.1: Update phase_tracker.json + live_tracker.py with new phases
- L6.2: Verify DAG dependencies
- L6.3: Write this plan file

### L7: Fix Hook Wiring (Root Cause)
- L7.1: UserPromptSubmit: `"route"` → `"user-prompt"` (settings.json L52)
- L7.2: PostToolUse: add catch-all entry for `"post-tool"` (settings.json L25-46)
- L7.3: Test both hooks fire correctly

### L8: Enable Thompson Sampling
- L8.1: config.py default `"false"` → `"true"` (L77)
- L8.2: Kill old daemon (pid 1409), restart with `--all --port 8080`
- L8.3: Kill MCP duplicate processes

### L9: Fix Outcome Sync
- L9.1: Audit 13 outcome keys vs 590 ChromaDB names
- L9.2: Fix: `partial_ratio` + threshold 60→50
- L9.3: Add ALIAS_MAP for known mismatches
- L9.4: Run sync, verify >200 matched

### L10: MCP Cleanup
- L10.1: Audit running MCP processes
- L10.2: Kill duplicates, verify

### L11: Full Pipeline Test
- L11.1: Hook→ChromaDB injection
- L11.2: PostToolUse→NEXUS outcome
- L11.3: Thompson routing verification
- L11.4: Outcome→ChromaDB feedback loop
- L11.5: No regressions

## DAG
```
L6.1 → L6.2 → L6.3
               ├── L7.1 → L7.3 ──┐
               ├── L7.2 → L7.3 ──┤
               ├── L8.1 → L8.2 → L8.3 ──┐
               └── L9.1 → L9.2 → L9.3 → L9.4
L7.3 ──→ L11.1 ──┐
L7.3 ──→ L11.2 ──┤
L8.2 ──→ L11.3 ──┼──→ L11.5
L9.4 ──→ L11.4 ──┘
```

## Execution Protocol
Each phase: `track.py start` → make changes → `track.py log` → `track.py mark` → `track.py checkpoint` → `ingest_graphify_memory.py`
