#!/usr/bin/env python3
"""End-to-end integration test for MiroShark pipeline.

Verifies:
1. Signal Bus read/write
2. HMM regime detection
3. News sentiment query
4. Outcome stats
5. Brain decision
6. All cron scripts
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "strategy_db"))

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
    print("MIROSHARK E2E INTEGRATION TEST")
    print("=" * 60)

    # ── 1. Signal Bus ──
    print("\n[1] Signal Bus")
    from shared_config.signal_bus import get_bus
    bus = get_bus()
    signals = bus.list_signals()
    test("Signal Bus lists files", len(signals) >= 5, f"only {len(signals)} signals")

    expected = ["market_regime.json", "sentiment_signal.json",
                "outcome_feedback.json", "miroshark_brain.json"]
    for s in expected:
        test(f"  {s} present", s in signals, "missing")

    # Test write
    ok = bus.write("__test_signal.json", {"test": True})
    test("Atomic write", ok, "write failed")
    data = bus.read("__test_signal.json")
    test("Atomic read", data is not None and data.get("test") is True, "read failed")
    bus.delete("__test_signal.json")

    # ── 2. Regime Detection ──
    print("\n[2] Regime Detection (HMM)")
    import joblib
    hmm_path = PROJECT_ROOT / "strategy_db" / "regime_hmm.pkl"
    test("HMM model exists", hmm_path.exists(), "not found")
    if hmm_path.exists():
        m = joblib.load(hmm_path)
        test("  Model has 4 components", m["model"].n_components == 4, f"got {m['model'].n_components}")
        test("  Regime labels present", len(m["regime_labels"]) == 4, f"got {len(m['regime_labels'])}")
        labels = set(m["regime_labels"].values())
        test("  All regimes present", labels >= {"trending_up", "trending_down", "volatile"}, f"got {labels}")

    regime_data = bus.read("market_regime.json")
    test("Regime signal not stale", regime_data is not None, "stale or missing")
    if regime_data:
        regime = regime_data.get("regime", "unknown")
        test("  Regime is valid", regime in ["trending_up", "trending_down", "ranging", "volatile"],
             f"got '{regime}'")

    # ── 3. Sentiment ──
    print("\n[3] News Sentiment")
    sent_data = bus.read("sentiment_signal.json")
    test("Sentiment signal present", sent_data is not None, "missing")
    if sent_data:
        score = sent_data.get("sentiment_score", 0)
        test("  Score in [0,1]", 0 <= score <= 1, f"got {score}")
        dom = sent_data.get("dominant", "")
        test("  Dominant sentiment valid", dom in ["bullish", "bearish", "neutral"], f"got '{dom}'")

    # ChromaDB query test
    try:
        from strategy_db.gcode_bridge import cmd_query
        results = cmd_query("breakout entry", top_k=2, setup_type=None, market_condition=None, keyword=None)
        test("ChromaDB strategy query", len(results) > 0, "no results")
    except Exception as e:
        try:
            from strategy_db.gcode_bridge import search
            results = search("breakout entry")
            test("ChromaDB strategy query (fallback)", len(results) > 0, "no results")
        except Exception as e2:
            test("ChromaDB strategy query", False, str(e))

    # ── 4. Outcomes ──
    print("\n[4] Outcome Feedback")
    out_data = bus.read("outcome_feedback.json")
    test("Outcome signal present", out_data is not None, "missing")
    if out_data:
        wr = out_data.get("win_rate", 0)
        test("  Win rate valid", 0 <= wr <= 1, f"got {wr}")
        trades = out_data.get("total_trades", 0)
        test("  Trades > 0", trades > 0, f"got {trades}")

    # ── 5. Brain Decision ──
    print("\n[5] Brain Decision")
    from miroshark.brain import MiroSharkBrain
    brain = MiroSharkBrain()
    signal = brain.decide()
    test("Brain produces decision", signal.action is not None, "no action")
    test("  Confidence in [0,1]", 0 <= signal.confidence <= 1, f"got {signal.confidence}")
    test("  Direction valid", signal.direction in ["long", "short", "none"], f"got '{signal.direction}'")
    test("  Leverage in [3,10]", 3 <= signal.suggested_leverage <= 10,
         f"got {signal.suggested_leverage}")
    test("  Valid action", signal.action in ["STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL", "PAUSE"],
         f"got '{signal.action}'")
    for key in ["regime", "sentiment", "outcome", "agents", "circuit_breaker", "composite"]:
        test(f"  Score: {key}", key in signal.scores, "missing")

    # ── 6. Cron Scripts ──
    print("\n[6] Cron Scripts")
    scripts_dir = PROJECT_ROOT / "scripts"
    for name in ["refresh_regime.py", "refresh_sentiment.py", "refresh_outcomes.py", "refresh_agents.py"]:
        test(f"  {name} exists", (scripts_dir / name).exists(), "not found")

    crontab = PROJECT_ROOT / "scripts" / "crontab.conf"
    test("crontab.conf exists", crontab.exists(), "not found")

    # ── Summary ──
    print("\n" + "=" * 60)
    total = PASS + FAIL
    print(f"RESULTS: {PASS}/{total} passed, {FAIL} failed")
    if FAIL == 0:
        print("ALL TESTS PASSED ✓")
    else:
        print(f"FAILURES: {FAIL} ✗")
    print("=" * 60)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())