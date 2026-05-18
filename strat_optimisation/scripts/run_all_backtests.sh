#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# BOS+LVN+VWAP Strategy Optimisation — Batch Backtest Runner
# ═══════════════════════════════════════════════════════════════════
# Runs all 5 variants + 3 SL variants and collects results
#
# Usage: bash strat_optimisation/scripts/run_all_backtests.sh
# ═══════════════════════════════════════════════════════════════════

set -e
cd /home/roshan/Downloads/Algotrading
source .venv/bin/activate

BASE="strat_optimisation/configs"
TIMEFRAME_1H="20260501-20260518"
TIMEFRAME_4H="20260401-20260518"
RESULTS_DIR="strat_optimisation/results"
mkdir -p "$RESULTS_DIR"

echo "═══════════════════════════════════════════════════════════"
echo "  BOS+LVN+VWAP Strategy Optimisation — Backtest Suite"
echo "═══════════════════════════════════════════════════════════"
echo ""

# ─── V1: SHORT-only Top 9 ────────────────────────────────────
echo ">>> V1: BOS SHORT-only Top 9 pairs (drop SOL)"
freqtrade backtesting \
    --config "$BASE/config_v1_short_top9.json" \
    --strategy BOS_V1_ShortTop9 \
    --timerange "$TIMEFRAME_1H" \
    --timeframe 1h \
    --cache none 2>&1 | tee "$RESULTS_DIR/v1_short_top9.txt"
echo ""

# ─── V2: SL Optimizer — 4%, 6%, 8% ──────────────────────────
for SL in 4 6 8; do
    echo ">>> V2: BOS SHORT SL=${SL}%"
    freqtrade backtesting \
        --config "$BASE/config_v2_sl_optimizer.json" \
        --strategy "BOS_V2_Short_SL${SL}" \
        --timerange "$TIMEFRAME_1H" \
        --timeframe 1h \
        --cache none 2>&1 | tee "$RESULTS_DIR/v2_sl${SL}.txt"
    echo ""
done

# ─── V3: V6 Late Trail Merge ─────────────────────────────────
echo ">>> V3: BOS entry + V6 Late Trail exit"
freqtrade backtesting \
    --config "$BASE/config_v3_late_trail.json" \
    --strategy BOS_V3_LateTrailMerge \
    --timerange "$TIMEFRAME_1H" \
    --timeframe 1h \
    --cache none 2>&1 | tee "$RESULTS_DIR/v3_late_trail.txt"
echo ""

# ─── V4: 4H Validation ───────────────────────────────────────
echo ">>> V4: BOS 4H timeframe validation"
freqtrade backtesting \
    --config "$BASE/config_v4_4h.json" \
    --strategy BOS_V4_4H_Validation \
    --timerange "$TIMEFRAME_4H" \
    --timeframe 4h \
    --cache none 2>&1 | tee "$RESULTS_DIR/v4_4h.txt"
echo ""

# ─── V5: Hyperopt (dry run — just validate it loads) ─────────
echo ">>> V5: Hyperopt-ready strategy validation"
freqtrade backtesting \
    --config "$BASE/config_v5_hyperopt.json" \
    --strategy BOS_V5_Hyperopt \
    --timerange "$TIMEFRAME_1H" \
    --timeframe 1h \
    --cache none 2>&1 | tee "$RESULTS_DIR/v5_hyperopt_baseline.txt"
echo ""

echo "═══════════════════════════════════════════════════════════"
echo "  ALL BACKTESTS COMPLETE"
echo "  Results saved to: $RESULTS_DIR/"
echo "═══════════════════════════════════════════════════════════"