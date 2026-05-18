#!/bin/bash
# Run all HEdge strategies in backtest mode (parallel via tmux)
# Usage:
#   ./run_all_backtests.sh          # Run all 9 backtests sequentially
#   ./run_all_backtests.sh --dry    # Show commands without running
#   ./run_all_backtests.sh --tmux   # Run each in a separate tmux window

DRY_RUN=false
TMUX_MODE=false

for arg in "$@"; do
    case "$arg" in
        --dry) DRY_RUN=true ;;
        --tmux) TMUX_MODE=true ;;
    esac
done

BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONFIGS_DIR="$BASE_DIR/configs"
FREQTRADE_DIR="$BASE_DIR/.."
TIMEFRAME="1h"
TIMERANGE="20250101-"
EXPORT="signals"

# Deploy first
echo ">>> Deploying strategies..."
python3 "$BASE_DIR/deploy.py"

STRATEGIES=(
    "config_hedge_01_fixed_fractional.json"
    "config_hedge_02_risk_to_zero.json"
    "config_hedge_03_half_kelly.json"
    "config_hedge_04_consec_loss_protect.json"
    "config_hedge_05_scale_out.json"
    "config_hedge_06_anti_martingale.json"
    "config_hedge_07_win_rate_adaptive.json"
    "config_hedge_meta_7in1.json"
    "config_hedge_champion_p3f.json"
)

run_backtest() {
    local config="$1"
    local name
    name=$(basename "$config" .json | sed 's/config_hedge_//')
    local strategy_name
    strategy_name=$(python3 -c "
import json
with open('$CONFIGS_DIR/$config') as f:
    print(json.load(f)['strategy'])
    ")

    echo "========================================"
    echo "  $strategy_name ($name)"
    echo "========================================"

    local cmd="cd $FREQTRADE_DIR && freqtrade backtesting \\
        --config $CONFIGS_DIR/$config \\
        --timerange $TIMERANGE \\
        --timeframe $TIMEFRAME \\
        --export $EXPORT \\
        --breakdown month \\
        --cache none"

    if [ "$DRY_RUN" = true ]; then
        echo "[DRY-RUN] $cmd"
        return
    fi

    if [ "$TMUX_MODE" = true ]; then
        tmux new-window -n "hedge-$name" "$cmd; echo 'DONE'; sleep 5"
    else
        eval "$cmd"
    fi
}

echo ""
echo "=== HEdge Backtest Runner ==="
echo "Timeframe: $TIMEFRAME"
echo "Timerange: $TIMERANGE"
echo "Configs: $CONFIGS_DIR"
echo "Strategies: ${#STRATEGIES[@]}"
echo "Mode: $([ "$TMUX_MODE" = true ] && echo 'tmux (parallel)' || echo 'sequential')"
echo ""

for config in "${STRATEGIES[@]}"; do
    run_backtest "$config"
done

echo ""
echo "=== All backtests complete ==="
