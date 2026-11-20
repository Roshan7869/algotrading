# PIPPIN 7-day backtest (offline, backtest-only)

| Field | Value |
|---|---|
| Generated | 2026-11-20T07:12:46.899232+00:00 |
| Git SHA | `1f308a19ff1666408153d1465a33477238d65469` |
| Data manifest | `D:/nexus-data/pippin/MANIFEST.json` (sha256 `61a2246243e10623fbe5ef13ca99401ca1d9c72db757ffb067d4dc6b754ede30`) |
| Config | `user_data/config_backtest_pippin.json` (sha256 `d39cec3e0b544bbe7ebb5c4fe5f1403048289f54033335a07f0f88083ea613fb`) |
| Fee model | `--fee 0.001` = 10 bps/side all-in proxy; **slippage not modeled** |
| Window | 2026-11-13 00:00 → 2026-11-20 00:00 UTC (7 days), 30-day warmup |
| Data | Gate.io PIPPIN/USDT spot 1h+4h (720/180 rows); BTC/USDT:USDT 1h informative from Binance futures (cross-venue proxy) |
| Command | `freqtrade backtesting --config user_data/config_backtest_pippin.json --strategy <NAME> --timerange 20261113-20261120 --fee 0.001 --cache none` — one process per strategy |
| Warnings | 0 (all informative data resolved) |

## Results — all exit 0, full 7-day window

| Strategy | Trades | Avg profit % | Total profit (USDT) | Total profit % | Win% | Drawdown |
|---|---:|---:|---:|---:|---:|---|
| EmaTrendFollowing | 0 | 0.00 | 0.000 | 0.0 | 0:00 | 0     0     0     0 | 0 USDT  0.00% |
| BollingerMeanReversion | 0 | 0.00 | 0.000 | 0.0 | 0:00 | 0     0     0     0 | 0 USDT  0.00% |
| DmiAdxStrategy | 0 | 0.00 | 0.000 | 0.0 | 0:00 | 0     0     0     0 | 0 USDT  0.00% |
| MacdRsiStrategy | 0 | 0.00 | 0.000 | 0.0 | 0:00 | 0     0     0     0 | 0 USDT  0.00% |
| AroonMomentumEngine_Hybrid | 0 | 0.00 | 0.000 | 0.0 | 0:00 | 0     0     0     0 | 0 USDT  0.00% |

## Honest reading

- **No edge demonstrated.** One strategy produced a handful of trades; the others produced none. Samples this small cannot support expectancy, win-rate, or annualization claims.
- Wallet 10,000 USDT / stake 100 USDT: any profit shown is a tiny fraction of wallet, not a return to extrapolate.
- Prior 35-window walkforward found all surviving strategies FAIL; this short window does not overturn that.
- Thin memecoin spot liquidity, cross-venue BTC informative data, proxied fees and unmodeled slippage are additional caveats.
- Machinery smoke test and governance record only. No live config was started.
