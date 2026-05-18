#!/bin/bash
cd /home/roshan/Downloads/Algotrading
PAIRS="BTC/USDT:USDT ETH/USDT:USDT XRP/USDT:USDT BCH/USDT:USDT ADA/USDT:USDT LTC/USDT:USDT"
TIMERANGE="20200101-20260507"
OUTDIR="user_data/backtest_results_6yr"
mkdir -p "$OUTDIR"

echo "$(date): BATCH START" > "$OUTDIR/progress.log"

run_bt() {
    local s="$1"
    local outf="$OUTDIR/${s}.txt"
    echo "$(date +%H:%M:%S): Starting $s" >> "$OUTDIR/progress.log"
    .venv/bin/freqtrade backtesting \
        --strategy "$s" \
        --timerange "$TIMERANGE" \
        -p $PAIRS \
        --stake-amount 50 \
        --max-open-trades 3 \
        > "$outf" 2>&1
    local rc=$?
    echo "$(date +%H:%M:%S): Finished $s (rc=$rc)" >> "$OUTDIR/progress.log"
}

# Run 3 at a time
for s in VectorStrategy VectorStrategy_P3F_KEY_LEVEL_TIGHT_TRAIL VectorStrategy_P3E_KEY_LEVEL_BOOST; do
    run_bt "$s" &
done
wait

for s in VectorStrategy_P3E_HYPEROPT VectorStrategy_P3B_TIGHTER_TRAIL VectorStrategy_P3C_WIDER_TRAIL; do
    run_bt "$s" &
done
wait

for s in VectorStrategy_P3D_KILL_ZONE_FILTER VectorStrategy_P3A_RSI_DIVERGENCE_EXIT BollingerMeanReversion; do
    run_bt "$s" &
done
wait

for s in MacdRsiStrategy AroonMomentumEngine_V2 EmaTrendFollowing; do
    run_bt "$s" &
done
wait

for s in DmiAdxStrategy RsiDivergenceStrategy SupertrendEmaStrategy; do
    run_bt "$s" &
done
wait

for s in ensemble_strategy VectorStrategyV2; do
    run_bt "$s" &
done
wait

echo "$(date): BATCH COMPLETE" >> "$OUTDIR/progress.log"
echo "All done!"