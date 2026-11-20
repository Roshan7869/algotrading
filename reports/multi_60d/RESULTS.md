# 60-day 1h backtest — 3x leverage, 100 USDT per run

| Field | Value |
|---|---|
| Generated | 2026-11-20T07:40:43.532536+00:00 |
| Git SHA | `050816dbc5bce9ef3ae2c22e8252b82237bec9e4` |
| Data manifest | `D:/nexus-data/pippin/MANIFEST_60d.json` (sha256 `1fbcea23b1fbe830cff8edfdb4dd0979087ecc8499176cb64f00d0afefd65580`) |
| Configs | `user_data/config_backtest_{pippin,sol,doge,xrp}_3x.json` — futures/isolated, leverage 3, stake 100 USDT, max_open_trades 1, dry_run true |
| Window | 2026-09-21 00:00 → 2026-11-20 00:00 UTC (60 days, 1h candles), 30-day warmup |
| Cost | `--fee 0.001` = 10 bps/side proxy; slippage not modeled |
| Runs | 20 = 4 pairs × 5 strategies; all exit 0, zero data warnings, full window confirmed |

## Results

| Pair | Strategy | Trades | P&L (USDT) | Return on 100 USDT margin | Win% |
|---|---|---:|---:|---:|---:|
| pippin | EmaTrendFollowing | 8 | -8.995 | -8.99% | 37.5 |
| pippin | BollingerMeanReversion | 0 | +0.000 | +0.00% | 0 |
| pippin | DmiAdxStrategy | 0 | +0.000 | +0.00% | 0 |
| pippin | MacdRsiStrategy | 0 | +0.000 | +0.00% | 0 |
| pippin | AroonMomentumEngine_Hybrid | 0 | +0.000 | +0.00% | 0 |
| sol | EmaTrendFollowing | 0 | +0.000 | +0.00% | 0 |
| sol | BollingerMeanReversion | 1 | +2.640 | +2.64% | 100 |
| sol | DmiAdxStrategy | 0 | +0.000 | +0.00% | 0 |
| sol | MacdRsiStrategy | 0 | +0.000 | +0.00% | 0 |
| sol | AroonMomentumEngine_Hybrid | 0 | +0.000 | +0.00% | 0 |
| doge | EmaTrendFollowing | 0 | +0.000 | +0.00% | 0 |
| doge | BollingerMeanReversion | 0 | +0.000 | +0.00% | 0 |
| doge | DmiAdxStrategy | 0 | +0.000 | +0.00% | 0 |
| doge | MacdRsiStrategy | 0 | +0.000 | +0.00% | 0 |
| doge | AroonMomentumEngine_Hybrid | 0 | +0.000 | +0.00% | 0 |
| xrp | EmaTrendFollowing | 2 | -11.165 | -11.16% | 0 |
| xrp | BollingerMeanReversion | 0 | +0.000 | +0.00% | 0 |
| xrp | DmiAdxStrategy | 0 | +0.000 | +0.00% | 0 |
| xrp | MacdRsiStrategy | 0 | +0.000 | +0.00% | 0 |
| xrp | AroonMomentumEngine_Hybrid | 0 | +0.000 | +0.00% | 0 |

Simple sum across the three trades-producing runs: **-17.520 USDT** (independent 100-USDT runs, not a portfolio backtest).

## Trade detail

- PIPPIN / EmaTrendFollowing: 8 trades — 3 trailing-stop wins (+18.297 USDT), 5 stop-loss losses (−27.292 USDT), net −8.995 USDT, 37.5% win rate. At 3x the −5% strategy stop becomes a ~1.7% adverse price move, so losses still hit ~5% of margin each.
- SOL / BollingerMeanReversion: 1 short trade, bb_reversion_exit_short, +2.640 USDT (+2.64% on margin).
- XRP / EmaTrendFollowing: 2 trades, both stop-loss, −11.165 USDT (−11.17% on margin), 0% win rate.
- The other 17 pair/strategy combinations produced no trades.

## Reading

- **No positive expectancy.** Three small samples (1–8 trades) cannot support a strategy claim; the 35-window walkforward still has all strategies on FAIL.
- PIPPIN and XRP EMA lost mainly to stop-outs; SOL Bollinger's single win is noise, not evidence.
- Leverage magnified both sides; no live config was started.
