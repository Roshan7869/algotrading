#!/bin/bash
cd /home/roshan/Downloads/Algotrading

STRATEGIES=(
    "VectorStrategy"
    "VectorStrategy_P3F_KEY_LEVEL_TIGHT_TRAIL"
    "VectorStrategy_P3E_KEY_LEVEL_BOOST"
    "VectorStrategy_P3E_HYPEROPT"
    "VectorStrategy_P3B_TIGHTER_TRAIL"
    "VectorStrategy_P3C_WIDER_TRAIL"
    "VectorStrategy_P3D_KILL_ZONE_FILTER"
    "VectorStrategy_P3A_RSI_DIVERGENCE_EXIT"
    "BollingerMeanReversion"
    "MacdRsiStrategy"
    "AroonMomentumEngine_V2"
    "EmaTrendFollowing"
    "DmiAdxStrategy"
    "RsiDivergenceStrategy"
    "SupertrendEmaStrategy"
    "ensemble_strategy"
    "VectorStrategyV2"
)

PAIRS="BTC/USDT:USDT ETH/USDT:USDT XRP/USDT:USDT BCH/USDT:USDT ADA/USDT:USDT LTC/USDT:USDT"
TIMERANGE="20200101-20260507"

echo "BATCH BACKTEST START: $(date)"
echo "=========================================="

for s in "${STRATEGIES[@]}"; do
    echo ""
    echo ">>> Running: $s"
    RESULT=$(.venv/bin/freqtrade backtesting \
        --strategy "$s" \
        --timerange "$TIMERANGE" \
        -p $PAIRS \
        --stake-amount 50 \
        --max-open-trades 3 \
        2>&1 | tail -5)
    echo "[$s] $RESULT"
done

echo ""
echo "BATCH BACKTEST COMPLETE: $(date)"