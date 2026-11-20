# PIPPIN 7-day backtest — 3x leverage, 100 USDT margin

| Field | Value |
|---|---|
| Generated | 2026-11-20T07:29:40.944941+00:00 |
| Git SHA | `9873a04a18c91dc73f5652cf1e1239effbcc271b` |
| Data manifest | `D:/nexus-data/pippin/MANIFEST_3x.json` (sha256 `69d440e28d71d524ec718d87418b83ace2815579158c4fcb56ec70f21f109f1a`) |
| Config | `user_data/config_backtest_pippin_3x.json` (futures/isolated, leverage 3, stake 100, dry_run true) |
| Cost | `--fee 0.001` = 10 bps/side proxy; slippage not modeled |
| Data | Binance futures PIPPIN/USDT:USDT 1h+4h (720/180 bars), BTC/USDT:USDT 1h informative; 30-day warmup |
| Window | 2026-11-13 00:00 → 11-20 00:00 UTC (7 days) |
| Command | `freqtrade backtesting -c user_data/config_backtest_pippin_3x.json --strategy <NAME> --timerange 20261113-20261120 --fee 0.001 --cache none` — one process each |

| Warnings | 0 |

## Results (all exit 0)

| Strategy | Trades | P&L (USDT) | Return % | Drawdown |
|---|---:|---:|---:|---|
| EmaTrendFollowing | 0 | 0.00 | 0.000 | 0.0 | 0 |
| BollingerMeanReversion | 0 | 0.00 | 0.000 | 0.0 | 0 |
| DmiAdxStrategy | 0 | 0.00 | 0.000 | 0.0 | 0 |
| MacdRsiStrategy | 0 | 0.00 | 0.000 | 0.0 | 0 |
| AroonMomentumEngine_Hybrid | 0 | 0.00 | 0.000 | 0.0 | 0 |

## Answer to "3x, 100 USDT — how much gain?"

- **Measured gain: 0.00 USDT.** Every strategy opened **zero positions** in the 7-day window; there is no P&L to leverage.
- 100 USDT margin at 3x = 300 USDT notional. Hypothetically a 1% adverse move would cost 3 USDT (3% of margin) before fees; fee proxy on 300 notional round-trip ≈ 0.60 USDT. This is arithmetic, not a forecast.
- No trade was taken, no edge demonstrated, and the 35-window walkforward still has every strategy on FAIL. No live config was started.
