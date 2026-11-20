# Multi-pair 3x / 100 USDT backtest — 2026-11-13 → 11-20

| Field | Value |
|---|---|
| Generated | 2026-11-20T07:34:46.226545+00:00 |
| Git SHA | `484d9f4b6a15c4676f9ce109bc90d95f9f682382` |
| Data manifest | `D:/nexus-data/pippin/MANIFEST_multi3x.json` (sha256 `c716f9d9acba10edd6401ef4d26d5ecc5cca8c6f668ce9aa530d9e3254ef9de9`) |
| Configs | `user_data/config_backtest_{pippin,sol,doge,xrp}_3x.json` — futures/isolated, leverage 3, stake 100 USDT, max_open_trades 1, dry_run true |
| Cost | `--fee 0.001` = 10 bps/side proxy; slippage not modeled |
| Data | Binance futures 1h (720 new bars appended to existing history) + 4h (180), 30-day warmup; BTC/USDT:USDT 1h informative |
| Runs | 20 = 4 pairs × 5 strategies, one freqtrade process each; all exit 0, zero data warnings |

## Results

| Pair | Strategy | Trades | P&L (USDT) | Return % |
|---|---|---:|---:|---:|
| pippin | EmaTrendFollowing | 0 | 0.000 | 0.0 |
| pippin | BollingerMeanReversion | 0 | 0.000 | 0.0 |
| pippin | DmiAdxStrategy | 0 | 0.000 | 0.0 |
| pippin | MacdRsiStrategy | 0 | 0.000 | 0.0 |
| pippin | AroonMomentumEngine_Hybrid | 0 | 0.000 | 0.0 |
| sol | EmaTrendFollowing | 0 | 0.000 | 0.0 |
| sol | BollingerMeanReversion | 0 | 0.000 | 0.0 |
| sol | DmiAdxStrategy | 0 | 0.000 | 0.0 |
| sol | MacdRsiStrategy | 0 | 0.000 | 0.0 |
| sol | AroonMomentumEngine_Hybrid | 0 | 0.000 | 0.0 |
| doge | EmaTrendFollowing | 0 | 0.000 | 0.0 |
| doge | BollingerMeanReversion | 0 | 0.000 | 0.0 |
| doge | DmiAdxStrategy | 0 | 0.000 | 0.0 |
| doge | MacdRsiStrategy | 0 | 0.000 | 0.0 |
| doge | AroonMomentumEngine_Hybrid | 0 | 0.000 | 0.0 |
| xrp | EmaTrendFollowing | 0 | 0.000 | 0.0 |
| xrp | BollingerMeanReversion | 0 | 0.000 | 0.0 |
| xrp | DmiAdxStrategy | 0 | 0.000 | 0.0 |
| xrp | MacdRsiStrategy | 0 | 0.000 | 0.0 |
| xrp | AroonMomentumEngine_Hybrid | 0 | 0.000 | 0.0 |

## Reading

- **All 20 runs: zero trades, zero P&L.** At 3x on 100 USDT margin there is no gain to report — no position was ever opened.
- This is not a leverage or strategy failure per se: none of the five strategies generated an entry signal on any of the four pairs in this 7-day window at the 10 bps/side cost floor.
- 7 days / ~168 bars has no statistical power; the 35-window walkforward still has all strategies on FAIL. No live config was started.
