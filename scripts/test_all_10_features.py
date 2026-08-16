#!/usr/bin/env python3
"""Structured E2E test for all 10 Nexus features.

F1: outcome_recording   — local_learning_store record_outcome + get_outcomes
F2: thompson_sampling   — thompson_rank, thompson_score, get_thompson_stats
F3: self_reflection     — record_failure, classify_error, find_alternatives, get_failure_stats
F4: cluster_affinity    — get_cluster_affinities, _map_skill_to_cluster
F5: auto_invoke         — auto_invoke with retry + alternative finding
F6: skill_manager       — add/remove/list/get/update skills
F7: session_memory      — save_session, search_sessions, get_session
F8: user_preferences    — get/set/delete/list preferences
F9: strategy_kb         — bridge.query_strategies (ChromaDB)
F10: mcp_tools          — 15 tool definitions + all handlers
"""

import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

PASS = 0
FAIL = 0


def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        print(f"  ✓ {name}")
        PASS += 1
    else:
        print(f"  ✗ {name} — {detail}")
        FAIL += 1


def main():
    global PASS, FAIL
    print("=" * 60)
    print("NEXUS 10-FEATURE E2E TEST")
    print("=" * 60)

    # ── F1: Outcome Recording ──
    print("\n[F1] Outcome Recording (local_learning_store)")
    from nexus.local_learning_store import record_outcome, get_outcomes, get_stats

    # Clean slate
    store_path = Path(__file__).parent.parent / "nexus" / "outcomes.jsonl"
    if store_path.exists():
        store_path.unlink()

    r1 = record_outcome("test_skill_a", "correct", "e2e test task")
    test("record_outcome returns success", r1["success"] is True)
    test("record_outcome via local_store", r1.get("via") == "local_store")
    test("record_outcome has entry", "entry" in r1)

    r2 = record_outcome("test_skill_a", "wrong", "e2e failing task")
    test("record wrong outcome", r2["success"] is True)

    outcomes = get_outcomes(limit=100)
    test("get_outcomes returns list", isinstance(outcomes, list))
    test("get_outcomes has 2 entries", len(outcomes) == 2)

    stats = get_stats()
    test("get_stats total=2", stats["total"] == 2)
    test("get_stats correct=1", stats["correct"] == 1)
    test("get_stats wrong=1", stats["wrong"] == 1)
    test("get_stats win_rate=0.5", stats["win_rate"] == 0.5)

    # ── F2: Thompson Sampling ──
    print("\n[F2] Thompson Sampling")
    from nexus.thompson_local import thompson_score, thompson_rank, get_thompson_stats

    score = thompson_score("test_skill_a")
    test("thompson_score returns float", isinstance(score, float))
    test("thompson_score in (0,1)", 0 < score < 1)

    candidates = [
        {"setup_name": "test_skill_a", "score": 0.8},
        {"setup_name": "test_skill_b", "score": 0.5},
    ]
    ranked = thompson_rank(candidates)
    test("thompson_rank returns list", isinstance(ranked, list))
    test("thompson_rank has 2 results", len(ranked) == 2)

    ts = get_thompson_stats()
    test("thompson_stats enabled", ts.get("enabled") is True)
    test("thompson_stats skills_tracked >= 1", ts.get("skills_tracked", 0) >= 1)
    skill_scores = ts.get("skill_scores", {})
    test("test_skill_a in stats", "test_skill_a" in skill_scores)
    a_stats = skill_scores["test_skill_a"]
    test("skill_a correct=1", a_stats["correct"] == 1)
    test("skill_a wrong=1", a_stats["wrong"] == 1)

    # ── F3: Self-Reflection ──
    print("\n[F3] Self-Reflection")
    from nexus.self_reflection import record_failure, classify_error, find_alternatives, get_failure_stats

    # Clean reflection db
    ref_db = Path(__file__).parent.parent / "nexus" / "reflection.db"
    if ref_db.exists():
        ref_db.unlink()

    ref = record_failure("test_failing_skill", "Null pointer exception in module x")
    test("record_failure returns dict", isinstance(ref, dict))
    test("record_failure status=logged", ref.get("status") == "logged")
    test("record_failure error_type=null_reference",
         ref.get("error_type") == "null_reference")

    ref2 = record_failure("test_failing_skill", "Connection timeout after 30s")
    test("second failure logged", ref2.get("status") == "logged")
    test("second failure error_type=timeout", ref2.get("error_type") == "timeout")

    error_type = classify_error("import error: no module named pandas")
    test("classify_error missing_dependency", error_type == "missing_dependency")

    error_type2 = classify_error("permission denied to access /etc/shadow")
    test("classify_error permission_denied", error_type2 == "permission_denied")

    error_type3 = classify_error("unrecognized error")
    test("classify_error general_failure", error_type3 == "general_failure")

    alternatives = find_alternatives("test_failing_skill")
    test("find_alternatives returns list", isinstance(alternatives, list))

    stats3 = get_failure_stats()
    test("failure_stats total_failures >= 2", stats3.get("total_failures", 0) >= 2)

    # ── F4: Cluster Affinity ──
    print("\n[F4] Cluster Affinity")
    from nexus.cluster_affinity import get_cluster_affinities, _map_skill_to_cluster

    affinities = get_cluster_affinities()
    test("affinities is dict", isinstance(affinities, dict))
    test("affinities has 8 clusters", len(affinities) == 8)
    for cluster in ["analyzer_planner", "architect", "frontend_ui", "backend_api",
                    "devops_infra", "quality_security", "knowledge_wiki", "general"]:
        test(f"  cluster {cluster} has score", cluster in affinities)
        test(f"  cluster {cluster} score in [0,1]", 0 <= affinities[cluster] <= 1)

    mapped = _map_skill_to_cluster("test strategy analyzer")
    test("map analyzer to analyzer_planner", mapped == "analyzer_planner")

    mapped2 = _map_skill_to_cluster("deploy_docker")
    test("map deploy to devops_infra", mapped2 == "devops_infra")

    mapped3 = _map_skill_to_cluster("unknown_xyz")
    test("map unknown to general", mapped3 == "general")

    # ── F5: Auto-Invoke ──
    print("\n[F5] Auto-Invoke")
    from nexus.auto_invoke import auto_invoke

    # We need some outcomes in the store for alternatives. Already have test_skill_a.
    result = auto_invoke("test e2e task", "test_failing_skill", max_retries=3)
    test("auto_invoke returns dict", isinstance(result, dict))
    test("auto_invoke has status", "status" in result)
    test("auto_invoke has attempts list", isinstance(result.get("attempts"), list))

    # ── F6: Skill Manager ──
    print("\n[F6] Skill Manager")
    from nexus.skill_manager import list_skills, get_skill, add_skill, remove_skill, update_skill

    # Clean slate
    skills_path = Path(__file__).parent.parent / "nexus" / "skills_registry.json"
    if skills_path.exists():
        skills_path.unlink()

    skills = list_skills()
    test("list_skills empty initially", skills == [])

    add = add_skill("test_skill", "a test skill", "testing", tags=["e2e", "test"])
    test("add_skill success", add["success"] is True)
    test("add_skill has skill", "skill" in add)

    add_dup = add_skill("test_skill", "duplicate")
    test("add_skill duplicate rejected", add_dup["success"] is False)

    skills = list_skills()
    test("list_skills has 1", len(skills) == 1)

    fetched = get_skill("test_skill")
    test("get_skill found", fetched is not None)
    test("get_skill correct name", fetched["name"] == "test_skill")

    updated = update_skill("test_skill", description="updated description")
    test("update_skill success", updated["success"] is True)

    fetched2 = get_skill("test_skill")
    test("update_skill description changed", fetched2["description"] == "updated description")

    removed = remove_skill("test_skill")
    test("remove_skill success", removed["success"] is True)

    skills = list_skills()
    test("list_skills empty after remove", skills == [])

    # ── F7: Session Memory ──
    print("\n[F7] Session Memory")
    from nexus.session_memory import save_session, search_sessions, get_session

    # Clean slate
    sm_path = Path(__file__).parent.parent / "nexus" / "session_memory.jsonl"
    if sm_path.exists():
        sm_path.unlink()

    s1 = save_session("e2e_session", "e2e_key", "e2e value for testing")
    test("save_session returns success", s1["success"] is True)
    test("save_session has entry", "entry" in s1)

    s2 = save_session("e2e_session", "another_key", "breakout strategy data")
    test("save_session second entry", s2["success"] is True)

    s3 = save_session("other_session", "topic", "risk management rules")
    test("save_session third entry", s3["success"] is True)

    # Fix: search term must be a substring of stored value
    results = search_sessions("e2e value")
    test("search_sessions finds by value", len(results) >= 1)
    if results:
        test("  result value matches", "e2e value" in results[0].get("value", ""))

    results2 = search_sessions("breakout")
    test("search_sessions finds breakout", len(results2) >= 1)
    if results2:
        test("  result key is another_key", results2[0]["key"] == "another_key")

    results3 = search_sessions("risk")
    test("search_sessions finds risk", len(results3) >= 1)

    # Search that matches nothing should return empty
    results4 = search_sessions("xyznonexistent12345")
    test("search_sessions no match returns empty", len(results4) == 0)

    session = get_session("e2e_session")
    test("get_session returns entries", len(session) >= 2)

    # ── F8: User Preferences ──
    print("\n[F8] User Preferences")
    from nexus.user_preferences import get, set as up_set, delete, list_keys, get_all

    # Clean slate
    up_path = Path(__file__).parent.parent / "nexus" / "user_preferences.json"
    if up_path.exists():
        up_path.unlink()

    all_prefs = get_all()
    test("get_all empty initially", all_prefs == {})

    keys = list_keys()
    test("list_keys empty initially", keys == [])

    r = up_set("theme", "dark")
    test("set preference success", r["success"] is True)
    test("set preference correct key", r["key"] == "theme")
    test("set preference correct value", r["value"] == "dark")

    val = get("theme")
    test("get preference returns dark", val == "dark")

    val_default = get("nonexistent", "fallback")
    test("get with default returns fallback", val_default == "fallback")

    keys = list_keys()
    test("list_keys has theme", "theme" in keys)

    all_prefs = get_all()
    test("get_all has theme", all_prefs.get("theme") == "dark")

    d = delete("theme")
    test("delete success", d["success"] is True)

    val = get("theme")
    test("get after delete returns None", val is None)

    d2 = delete("nonexistent")
    test("delete nonexistent fails", d2["success"] is False)

    # ── F9: Strategy Knowledge Base ──
    print("\n[F9] Strategy KB (ChromaDB)")
    from nexus.bridge import get_bridge

    bridge = get_bridge()
    results9 = bridge.query_strategies("breakout entry setup", top_k=3)
    test("query_strategies returns list", isinstance(results9, list))
    if results9:
        test("  has results", len(results9) > 0)
        first = results9[0]
        test("  result has score", "score" in first)

    # ── F10: MCP Tools ──
    print("\n[F10] MCP Tools")
    from nexus.mcp_tools import get_tool_definitions, handle_tool_call

    defs = get_tool_definitions()
    test("mcp has 15 tool definitions", len(defs) == 15)
    names = [d["name"] for d in defs]
    test("  names are unique", len(names) == len(set(names)))
    for d in defs:
        has_name = "name" in d
        has_desc = "description" in d
        has_schema = "inputSchema" in d
        test(f"  {d.get('name', '?')} has all required fields", has_name and has_desc and has_schema)

    # Test specific handlers
    ts_result = handle_tool_call("trade_status", {})
    test("handle_trade_status returns status",
         ts_result.get("status") == "online")

    config_result = handle_tool_call("adjust_config",
                                      {"key": "max_drawdown_pct", "value": "15"})
    test("handle_adjust_config success", config_result.get("success") is True)

    unknown = handle_tool_call("nonexistent_tool", {})
    test("handle_unknown_tool returns error", "error" in unknown)

    cluster_result = handle_tool_call("cluster_affinities", {})
    test("handle_cluster_affinities returns affinities",
         "affinities" in cluster_result)

    thompson_result = handle_tool_call("thompson_stats", {})
    test("handle_thompson_stats enabled", thompson_result.get("enabled") is True)

    reflection_result = handle_tool_call("reflection_stats", {})
    test("handle_reflection_stats has total_failures",
         "total_failures" in reflection_result)

    # ── Summary ──
    print("\n" + "=" * 60)
    total = PASS + FAIL
    print(f"RESULTS: {PASS}/{total} passed, {FAIL} failed")
    if FAIL == 0:
        print("ALL 10 FEATURES PASSED ✓")
    else:
        print(f"FAILURES: {FAIL} ✗")
    print("=" * 60)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
