# 18x vs 3x — 60-day 1h, 100 USDT margin per run

| Field | Value |
|---|---|
| Generated | 2026-11-20T07:51:13.051538+00:00 |
| Git SHA | `e9dbdd4e8c2b75505c92c019322cd17ec21097a0` |
| Data manifest | `D:/nexus-data/pippin/MANIFEST_18x.json` (sha256 `222f92c47b8a703a189a49fddb503fc11198bab9d4b590953668270cc292d849`) |
| Configs | `user_data/config_backtest_{pippin,sol,doge,xrp}_18x.json` — futures/isolated, leverage 18, stake 100, max_open_trades 1, dry_run true |
| Strategies | 5 new copies `user_data/strategies/*18x.py` with `leverage() -> min(18, max_leverage)`; original strategy files untouched; all load OK |
| Verification | Exported trades show **leverage 18.0** and stake ~100 USDT |
| Exchange caps | PIPPIN 25x, SOL 100x, DOGE 75x, XRP 100x — 18x permitted |
| Window | 2026-09-21 → 2026-11-20 UTC, 1h candles, 30-day warmup |
| Cost | `--fee 0.001` = 10 bps/side proxy; slippage not modeled |
| Runs | 20 (4 pairs × 5 strategies), all exit 0, zero errors, full window |

## 3x vs 18x (only combinations that traded)

| Pair | Strategy | 3x trades | 3x P&L | 18x trades | 18x P&L | 18x win% |
|---|---|---:|---:|---:|---:|---:|
| pippin | EmaTrendFollowing | 8 | -8.995 USDT | 21 | -39.713 USDT | 19.0 |
| sol | BollingerMeanReversion | 1 | +2.640 USDT | 0 | +0.000 USDT | 0 |
| xrp | EmaTrendFollowing | 2 | -11.165 USDT | 2 | -17.074 USDT | 0 |

Simple sum of 18x loss-making runs: **-56.787 USDT** (independent 100-USDT runs, not a portfolio).

## Why 18x destroyed the PIPPIN result

- PIPPIN EMA at 18x: 21 trades, **−39.713 USDT (−39.7% of margin)**, 19% win rate. Breakdown: 3 trailing-stop wins +64.774, 1 ROI win +35.142, **17 stop-outs −139.628**.
- Freqtrade divides the strategy stoploss (−5%) by leverage: at 18x that is roughly a −0.28% adverse price move, so almost every trade gets stopped. Higher leverage created *more* trades (8 → 21) and a much larger loss.
- XRP EMA at 18x: 2 trades, both stop-outs, −17.074 USDT (−17.1%). SOL Bollinger made 1 trade at 3x (+2.64) and none at 18x.
- The other 17 combinations produced no trades at either leverage.

## Reading

- **Leverage amplified an already negative expectancy.** No 18x result supports more risk: 2 trading combos lost 56.8 USDT combined and the single 3x winner vanished.
- Samples remain small (1–21 trades); the 35-window walkforward has all strategies on FAIL. No live config was started.
