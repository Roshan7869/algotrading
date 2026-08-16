# [PLAN_NAME] — Graphify Typed DAG Plan

```yaml
goal: "<one-line description>"
created: "<timestamp>"
execution_tracker:
  total_blocks: <N>
  completed: 0
  in_progress: null
dependency_graph:
  level_0:
    - <ID0>: "<task>"
  level_1:
    - <ID1>: "<task>"
  level_N:
    - <IDN>: "<task>"
```

---

## Phase 0: First Principles Deconstruction

### Root question
<What is the irreducible problem stripped of assumptions?>

### Component atomization
| Component | What | Why | Inputs | Outputs | Failure mode |
|-----------|------|-----|--------|---------|--------------|

---

## Phase 1: State Analysis (verified)
<Verified facts about current state, file counts, architecture>

---

## Phase 2: Typed DAG — Execution Blocks

### Level <N> (after <DEPS>)

#### BLOCK <ID>: <Name>
```yaml
id: "<ID>"
type: implement|fix|test|verify|research
level: <N>
files:
  - path/to/file.rs (NEW)
  - path/to/file.py (modify L30-45)
description: |
  <What this block accomplishes, with line-level detail>
inputs: ["<DEP_BLOCK_ID>"]
outputs: ["<artifact descriptions>"]
guardrails:
  - "<Constraint that must hold>"
resources:
  cluster: "<nexus_cluster>"
  skills: ["<skill_names>"]
  agents: ["<agent_types>"]
estimated_tokens: <N>
checkpoint: true|false
status: "pending"
```

**Tasks:**
| ID | File | Lines | Action | Change | Verification |
|----|------|-------|--------|--------|-------------|
| <ID>-T1 | `file.rs` | L10-30 | new | Create X struct | `cargo check` |

**Subtasks (line-by-line):**
- `<ID>-T1-L1-10`: Imports and module declarations
- `<ID>-T1-L11-25`: Struct definition with fields
- `<ID>-T1-L26-45`: impl block with methods

---

## Live Tracking Protocol

```bash
# Initialize
python3 graphify-out/track.py init-plan --name "<plan_name>"

# Execute
python3 graphify-out/track.py start <PHASE_ID>
# ... make changes ...
python3 graphify-out/track.py mark <PHASE_ID> <TASK_ID> verified
python3 graphify-out/track.py complete <PHASE_ID>

# Monitor
python3 graphify-out/track.py live     # DAG status
python3 graphify-out/track.py status   # Task-level progress
python3 graphify-out/track.py checkpoint <PHASE_ID>  # Save state
```
