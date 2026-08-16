# FinceptTerminal → Algotrading Integration DAG

**Date:** 2026-05-22
**Purpose:** Architectural feature map + DAG showing which FinceptTerminal components plug into the Algotrading project, via which integration points, and in what dependency order.

---

## 1. FEATURE CATALOG — FinceptTerminal Extractable Components

### Group A: DERIVATIVES & OPTIONS (you have ZERO of this)

| ID | Component | Source | Lines | New Capability |
|----|-----------|--------|-------|----------------|
| F1 | Black-Scholes + Greeks + IV | `scripts/derivatives_pricing.py` | 499 | Options pricing, all 5 Greeks, implied vol |
| F2 | FX Options (Garman-Kohlhagen) | `scripts/derivatives_pricing.py` | same | Currency options pricing |
| F3 | Bond Pricing + YTM | `scripts/derivatives_pricing.py` | same | Duration, convexity, clean/dirty price |
| F4 | IRS + CDS valuation | `scripts/derivatives_pricing.py` | same | Interest rate swap + credit default swap |
| F5 | Forward pricing | `scripts/derivatives_pricing.py` | same | Forward price from spot+rate+time |
| F6 | Greeks batch daemon | `scripts/option_greeks_daemon.py` | 281 | Persistent batch IV+Greeks via py_vollib |

### Group B: PORTFOLIO OPTIMIZATION (you have none — single-strategy only)

| ID | Component | Source | Lines | New Capability |
|----|-----------|--------|-------|----------------|
| F7 | 8-strategy optimizer | `scripts/optimize_portfolio_weights.py` | 386 | max_sharpe, min_vol, risk_parity, HRP, Black-Litterman, equal_weight, target_return, efficient frontier |
| F8 | Skfolio wrapper | `scripts/analytics/python_skfolio_lib/` (8 files) | ~4000 | HRP, mean-risk, copula, factor models, walk-forward backtest |
| F9 | Skfolio service | `scripts/analytics/skfolio_wrapper.py` | 1364 | Plotly interactive visualizations of portfolios |

### Group C: ECONOMETRICS & STATS (you have basic indicators only)

| ID | Component | Source | Lines | New Capability |
|----|-----------|--------|-------|----------------|
| F10 | Statsmodels wrapper | `scripts/analytics/statsmodels_wrapper/` (9 files) | ~3500 | ARIMA, ADF, KPSS, Granger causality, GLM, GAM, survival, multivariate |
| F11 | Quant analytics CLI | `scripts/analytics/quant_analytics_cli.py` | 580 | Unified CLI: trend, stationarity, ARIMA, forecasting, ML |
| F12 | QuantStats tearsheets | `scripts/analytics/quantstats_analytics.py` | 796 | 50+ metrics, HTML tearsheet, drawdown analysis |
| F13 | TSmoothie | `scripts/analytics/tsmoothie_wrapper/` | ~200 | Time series smoothing |

### Group D: STREAMING / INCREMENTAL INDICATORS (you compute batch only)

| ID | Component | Source | Lines | New Capability |
|----|-----------|--------|-------|----------------|
| F14 | Talipp incremental indicators | `scripts/analytics/talipp_wrapper/` (5 files) | ~600 | Streaming RSI/MACD/BB/ATR without full recomputation |
| F15 | Technical analysis suite | `scripts/technicals/` (3 files) | ~890 | 10 momentum + 4 volatility indicators (ta lib) |

### Group E: ML-BASED PATTERN RECOGNITION (you have HMM only)

| ID | Component | Source | Lines | New Capability |
|----|-----------|--------|-------|----------------|
| F16 | Triple Barrier labeling | `scripts/vision_quant/models/triple_barrier.py` | 207 | Lopez de Prado method — industry standard label generation |
| F17 | CNN Autoencoder | `scripts/vision_quant/models/attention_cae.py` | 241 | Chart images → 1024-dim FAISS searchable latent |
| F18 | Vision scorer | `scripts/vision_quant/scorer.py` | 332 | Multi-factor: Vision(0-3) + Fundamental(0-4) + Technical(0-3) |
| F19 | DTW pattern engine | `scripts/vision_quant/engine.py` | 563 | Dynamic Time Warping similarity search via FAISS |
| F20 | Vision backtester | `scripts/vision_quant/backtester.py` | 264 | Adaptive MA+RSI+MACD with vision overlay |

### Group F: FUNDAMENTAL DATA (you are purely technical)

| ID | Component | Source | Lines | New Capability |
|----|-----------|--------|-------|----------------|
| F21 | SEC EDGAR | `scripts/mcp/edgar/` (9 files) | ~2500 | 10-K, 10-Q, 8-K, 13F institutional, insider, XBRL financials |
| F22 | FRED economic data | `scripts/fred_data.py` | ~500 | Federal Reserve economic time series |
| F23 | World Bank data | `scripts/worldbank_data.py` | ~400 | International economic indicators |
| F24 | SEC XBRL data | `scripts/sec_data.py` | 1130 | Direct SEC EDGAR financial data |
| F25 | BEA data | `scripts/bea_data.py` | 911 | US Bureau of Economic Analysis |
| F26 | OECD data | `scripts/oecd_data.py` | 1246 | OECD international statistics |

### Group G: MULTI-EXCHANGE (you are Binance-only)

| ID | Component | Source | Lines | New Capability |
|----|-----------|--------|-------|----------------|
| F27 | CCXT exchange daemon | `scripts/exchange/exchange_daemon.py` | 545 | Persistent JSON-RPC daemon — eliminates cold start |
| F28 | CCXT WebSocket stream | `scripts/exchange/ws_stream.py` | 611 | Real-time streaming with tick dedup |
| F29 | 20 exchange ops scripts | `scripts/exchange/` (20 files) | ~1500 | Order, balance, ticker, OHLCV, OI, funding rate, fees |

### Group H: RISK & EXECUTION (you have circuit breaker but missing pieces)

| ID | Component | Source | Lines | New Capability |
|----|-----------|--------|-------|----------------|
| F30 | Dynamic TP/SL | `scripts/agno_trading/utils/tp_sl_calculator.py` | 221 | ATR-based TP/SL, R:R ratios, trailing stops |
| F31 | Risk-validated executor | `scripts/agno_trading/core/trade_executor.py` | 303 | Safety limits, pre-trade risk validation |
| F32 | Condition evaluator | `scripts/algo_trading/condition_evaluator.py` | ~150 | Generic buy/sell condition engine |

### Group I: MICROSTRUCTURE (your backtests assume perfect fills)

| ID | Component | Source | Lines | New Capability |
|----|-----------|--------|-------|----------------|
| F33 | Order book simulator | `scripts/ai_quant_lab/qlib_advanced_backtest.py` | 880 | 5-level bid/ask, TWAP/VWAP/Limit, slippage, costs |

---

## 2. ALGOTRADING INTEGRATION POINTS

| ID | Integration Point | Interface | Location |
|----|-------------------|-----------|----------|
| A1 | IStrategy (new strategies) | Subclass `IStrategy`, override populate_* methods | `freqtrade/strategy/interface.py` |
| A2 | Signal Generator | Write to `shared_config/{name}_signal.json`, publish to Redis `signals` channel | `engine/signal_bus.py` |
| A3 | MCP Tool Server | Create stdio MCP server with `@app.list_tools()` / `@app.call_tool()`, register in `start_local.sh` | `strategy_db/mcp_server.py` |
| A4 | ChromaDB ingest | Add chunks to `trading_strategies` or new collection | `strategy_db/ingest.py` |
| A5 | Risk gate | Extend `HEdgeCoordinator`, add to `shared_config/circuit_breaker.json` | `knowledge/learning_loop.py` |
| A6 | Streamlit page | Add .py to `ui/pages/`, add entry to `pages` dict in `ui/app.py` | `ui/app.py` |
| A7 | Docker service | Add to `docker-compose.yml` under profile | `docker-compose.yml` |
| A8 | Exchange backend | Subclass `Exchange`, add to `SUPPORTED_EXCHANGES` | `freqtrade/exchange/` |
| A9 | Config slot | Add JSON key to freqtrade config | `user_data/config*.json` |
| A10 | NEXUS tool | Register in NEXUS FAISS + YAML manifest | `nexus/bridge.py` |

---

## 3. INTEGRATION DAG

Dependency order: edges mean "must be integrated BEFORE the target".

```
                    PHASE 1: FOUNDATION
                    (zero internal deps)
                    ┌─────────────────────────────────────────┐
                    │                                         │
                ┌───▼───┐    ┌──────┐    ┌──────┐    ┌──────┐
                │  F1   │    │  F7  │    │ F10  │    │ F14  │
                │Black  │    │8-opt │    │Stats- │    │Talipp│
                │Scholes│    │Portf.│    │models │    │Incr. │
                └───┬───┘    └──┬───┘    └──┬───┘    └──────┘
                    │           │           │
                    │    ┌──────▼──────┐    │
                    │    │     F8      │    │
                    │    │  Skfolio    │    │
                    │    │  Portfolio  │    │
                    │    └──────┬──────┘    │
                    │           │           │
        ┌───────────▼───────────▼───────────▼──────────┐
        │              PHASE 2: ANALYTICS               │
        │     (depends on foundation modules)          │
        │                                              │
        │   ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐     │
        │   │  F3  │  │  F9  │  │ F11  │  │ F12  │     │
        │   │Bond  │  │Skfol.│  │Quant │  │QStats│     │
        │   │YTM   │  │Viz   │  │CLI   │  │Tearsh│     │
        │   └──────┘  └──────┘  └──────┘  └──────┘     │
        │                                              │
        │   ┌──────┐  ┌──────┐                          │
        │   │  F4  │  │  F5  │                          │
        │   │IRS   │  │Fwd   │                          │
        │   │CDS   │  │Price │                          │
        │   └──────┘  └──────┘                          │
        └──────────────────┬───────────────────────────┘
                           │
               ┌───────────▼───────────────────────────┐
               │         PHASE 3: DATA PIPELINES        │
               │  (foundation + analytics ready)      │
               │                                       │
               │  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐   │
               │  │ F21 │  │ F22 │  │ F23 │  │ F24 │   │
               │  │EDGAR│  │FRED │  │WB   │  │SEC  │   │
               │  └──┬──┘  └─────┘  └─────┘  └─────┘   │
               │     │                                │
               │  ┌─────┐  ┌─────┐                    │
               │  │ F25 │  │ F26 │   ┌─────┐          │
               │  │BEA  │  │OECD │   │ F6  │          │
               │  └─────┘  └─────┘   │Greeks│          │
               │                       │Daemn│          │
               │                       └─────┘          │
               └───────────────┬───────────────────────┘
                               │
               ┌───────────────▼───────────────────────┐
               │      PHASE 4: ML PATTERN LAYER        │
               │  (data pipelines feeding features)    │
               │                                       │
               │        ┌──────┐                        │
               │        │ F16  │  Triple Barrier       │
               │        └──┬───┘  Labeling              │
               │           │                            │
               │     ┌─────▼──────┐                     │
               │     │    F17     │  CNN Autoencoder   │
               │     └─────┬──────┘                     │
               │           │                            │
               │     ┌─────▼──────┐                     │
               │     │    F19     │  DTW Pattern        │
               │     │    Engine  │  Search (FAISS)     │
               │     └─────┬──────┘                     │
               │           │                            │
               │     ┌─────▼──────┐                     │
               │     │    F18     │  Vision Scorer     │
               │     │  Multi-Factor│                   │
               │     └─────┬──────┘                     │
               │           │                            │
               │     ┌─────▼──────┐                     │
               │     │    F20     │  Vision Backtester  │
               │     └────────────┘                     │
               └───────────────┬───────────────────────┘
                               │
               ┌───────────────▼───────────────────────┐
               │     PHASE 5: EXECUTION LAYER          │
               │  (ML signals → risk-gated execution)  │
               │                                       │
               │  ┌─────┐  ┌─────┐  ┌─────┐           │
               │  │ F27 │  │ F28 │  │ F29 │           │
               │  │CCXT │  │ WS  │  │ 20  │           │
               │  │Demon│  │Strm │  │Exch │           │
               │  └──┬──┘  └──┬──┘  └──┬──┘           │
               │     │        │        │                │
               │  ┌──▼────────▼────────▼──┐            │
               │  │  Multi-Exchange Bus   │            │
               │  └──────────┬───────────┘            │
               │             │                         │
               │  ┌──────▼───────┐  ┌──────┐           │
               │  │    F30       │  │  F31 │           │
               │  │  Dynamic     │  │ Risk │           │
               │  │  TP/SL       │  │Valid.│           │
               │  └──────┬───────┘  └──┬───┘           │
               │         │             │               │
               │  ┌──────▼───────┐     │               │
               │  │    F32       │◄────┘               │
               │  │  Condition   │                     │
               │  │  Evaluator   │                     │
               │  └──────┬───────┘                     │
               │         │                              │
               │  ┌──────▼───────┐                      │
               │  │    F33       │                      │
               │  │  Microstruct │                      │
               │  │  Backtester  │                      │
               │  └──────────────┘                      │
               └────────────────────────────────────────┘
```

---

## 4. INTEGRATION MAPPING — Component → Algotrading Plug Point

### PHASE 1: FOUNDATION (weekend job, ~2 days)

```
Fincept Component    →  Algotrading Plug Point    →  Where it lands
─────────────────────────────────────────────────────────────────────
F1 Black-Scholes     →  A3 MCP Tool Server        →  New MCP server: derivatives_mcp_server.py
                       A4 ChromaDB ingest          →  New collection: derivatives_strategies
                       A10 NEXUS tool              →  Register in NEXUS FAISS

F7 8-Opt Portfolio   →  A3 MCP Tool Server        →  Extend finance_mcp_server.py with optimize_portfolio tool
                       A2 Signal Generator         →  New: shared_config/portfolio_signal.json
                       A6 Streamlit page          →  New page: Portfolio Optimization

F10 Statsmodels      →  A3 MCP Tool Server        →  New MCP server: econometrics_mcp_server.py
                       A10 NEXUS tool              →  Register in NEXUS

F14 Talipp           →  A1 IStrategy              →  Replace batch ta() calls in strategies with incremental talipp
                       A9 Config slot             →  Add use_incremental_indicators flag
```

### PHASE 2: ANALYTICS (~3 days, depends on Phase 1)

```
Fincept Component    →  Algotrading Plug Point    →  Where it lands
─────────────────────────────────────────────────────────────────────
F3 Bond/YTM          →  A3 MCP Tool               →  Add to derivatives_mcp_server.py
F4 IRS/CDS           →  A3 MCP Tool               →  Add to derivatives_mcp_server.py
F5 Forward pricing   →  A3 MCP Tool               →  Add to derivatives_mcp_server.py
F6 Greeks daemon     →  A2 Signal Gen             →  Run as background service, publish to shared_config/greeks_signal.json
F8 Skfolio           →  A3 MCP Tool               →  Extend portfolio MCP tool
F9 Skfolio Viz       →  A6 Streamlit              →  Portfolio page gets interactive plotly charts
F11 Quant CLI        →  A3 MCP Tool               →  Wrap as MCP tools
F12 QuantStats       →  A6 Streamlit              →  Backtest page gets HTML tearsheet tab
```

### PHASE 3: DATA PIPELINES (~4 days, depends on Phase 1)

```
Fincept Component    →  Algotrading Plug Point    →  Where it lands
─────────────────────────────────────────────────────────────────────
F21 SEC EDGAR        →  A3 MCP Tool Server         →  New: edgar_mcp_server.py (9 tools)
                       A4 ChromaDB ingest          →  New collection: sec_filings
                       A2 Signal Gen               →  shared_config/fundamental_signal.json

F22 FRED             →  A3 MCP Tool                →  Extend finance_mcp_server.py
F23 World Bank       →  A3 MCP Tool                →  Extend finance_mcp_server.py
F24 SEC direct       →  A3 MCP Tool                →  Merge with EDGAR server
F25 BEA              →  A3 MCP Tool                →  Extend finance_mcp_server.py
F26 OECD             →  A3 MCP Tool                →  Extend finance_mcp_server.py
```

### PHASE 4: ML PATTERN LAYER (~5 days, depends on Phase 1+3)

```
Fincept Component    →  Algotrading Plug Point    →  Where it lands
─────────────────────────────────────────────────────────────────────
F16 Triple Barrier   →  A4 ChromaDB                →  New collection: pattern_labels
                       A1 IStrategy               →  New strategy: TripleBarrierStrategy using labels

F17 CNN Autoencoder  →  A7 Docker service         →  New: vision-encoder service
                       A2 Signal Gen              →  shared_config/vision_pattern_signal.json

F19 DTW Engine       →  A7 Docker service          →  New: pattern-search service
                       A10 NEXUS tool             →  Register as searchable resource

F18 Vision Scorer   →  A2 Signal Gen              →  shared_config/vision_score_signal.json
                       A5 Risk gate               →  MiroShark Brain adds Vision score as input

F20 Vision Backtest  →  A1 IStrategy              →  New: VisionEnhancedStrategy
```

### PHASE 5: EXECUTION LAYER (~5 days, depends on Phase 1+2+4)

```
Fincept Component    →  Algotrading Plug Point    →  Where it lands
─────────────────────────────────────────────────────────────────────
F27 CCXT Daemon      →  A8 Exchange backend       →  Replace cold-start CCXT calls in Freqtrade exchange layer
                       A7 Docker service           →  New: exchange-daemon service on Docker

F28 WS Stream        →  A8 Exchange backend        →  Replace polling with WS where exchanges support it
                       A2 Signal Gen              →  Real-time tick → shared_config/tick_stream.json

F29 20 Exchange ops  →  A3 MCP Tool               →  New: exchange_mcp_server.py (20 tools)
                       A8 Exchange backend        →  Add to SUPPORTED_EXCHANGES

F30 Dynamic TP/SL    →  A1 IStrategy              →  Override custom_stoploss in existing strategies
                       A5 Risk gate               →  Integrate into HEdgeCoordinator

F31 Risk Validator   →  A5 Risk gate              →  Pre-trade risk check before Freqtrade execute

F32 Condition Eval   →  A2 Signal Gen             →  Generic signal conditions → shared_config/condition_signal.json

F33 Microstructure   →  A1 IStrategy              →  New: MicrostructureBacktestStrategy
                       A6 Streamlit              →  Backtest page: slippage analysis tab
```

---

## 5. NEW SERVICES IN Docker Compose

```yaml
services:
  # EXISTING (keep)
  freqtrade:    ...
  redis:        ...
  postgres:     ...
  streamlit:    ...
  mirofish:     ...
  tradingagents:...

  # NEW — Phase 1
  derivatives-mcp:
    build: ./mcp_layer
    command: python derivatives_mcp_server.py
    profiles: [full]

  # NEW — Phase 3
  edgar-mcp:
    build: ./mcp_layer
    command: python edgar_mcp_server.py
    profiles: [full]

  exchange-daemon:
    build: ./mcp_layer
    command: python -m exchange.exchange_daemon
    profiles: [full]

  # NEW — Phase 4
  vision-encoder:
    build: ./mcp_layer
    command: python -m vision_quant.attention_cae_serve
    profiles: [full]

  pattern-search:
    build: ./mcp_layer
    command: python -m vision_quant.engine_serve
    profiles: [full]
```

---

## 6. NEW MCP TOOL SERVERS

### derivatives_mcp_server.py (Phase 1)

| Tool | Maps to | Input | Output |
|------|---------|-------|--------|
| `option_price` | F1 black_scholes_price | S, K, T, r, sigma, type | price |
| `option_greeks` | F1 black_scholes_greeks | S, K, T, r, sigma, type | {delta, gamma, theta, vega, rho} |
| `implied_vol` | F1 implied_volatility | S, K, T, r, market_price | IV float |
| `fx_option_price` | F2 garman_kohlhagen | S, K, T, r_d, r_f, sigma, type | price |
| `bond_price` | F3 bond_price_from_ytm | dates, coupon, ytm, freq | {clean, dirty, accrued, duration, convexity} |
| `bond_ytm` | F3 bond_ytm_from_price | dates, coupon, clean_price | ytm |
| `swap_value` | F4 swap_value | dates, fixed_rate, notional | NPV |
| `cds_value` | F4 cds_value | dates, recovery, notional, spread | NPV |
| `forward_price` | F5 forward_price | spot, rate, time | forward |

### econometrics_mcp_server.py (Phase 1)

| Tool | Maps to | Input | Output |
|------|---------|-------|--------|
| `arima_forecast` | F10 ARIMA | series, order, steps | forecast + CI |
| `stationarity_test` | F10 ADF/KPSS | series | {statistic, p_value, is_stationary} |
| `granger_causality` | F10 Granger | x, y, maxlag | {f_stat, p_value, causes} |
| `regression` | F10 OLS/GLM | y, X, family | coefficients + stats |
| `survival_analysis` | F10 Survival | durations, events | survival curve |

### edgar_mcp_server.py (Phase 3)

| Tool | Maps to | Input | Output |
|------|---------|-------|--------|
| `search_company` | F21 | company_name | CIK, tickers, filings |
| `get_10k` | F21 | CIK, year | financial statements |
| `get_10q` | F21 | CIK, quarter | quarterly financials |
| `get_8k` | F21 | CIK, date range | current events |
| `get_13f` | F21 | CIK, quarter | institutional holdings |
| `get_insider` | F21 | CIK | insider transactions |
| `get_financials` | F21 | CIK | XBRL financial data |

### exchange_mcp_server.py (Phase 5)

| Tool | Maps to | Input | Output |
|------|---------|-------|--------|
| `place_order` | F29 | exchange, pair, side, amount, price | order_id |
| `cancel_order` | F29 | exchange, order_id | status |
| `fetch_balance` | F29 | exchange | balances |
| `fetch_ticker` | F29 | exchange, pair | ticker |
| `fetch_ohlcv` | F29 | exchange, pair, tf, limit | candles |
| `fetch_orderbook` | F29 | exchange, pair | bids/asks |
| `fetch_positions` | F29 | exchange | open positions |
| `fetch_funding_rate` | F29 | exchange, pair | rate |
| `fetch_open_interest` | F29 | exchange, pair | OI |
| `set_leverage` | F29 | exchange, pair, leverage | status |

---

## 7. NEW ChromaDB COLLECTIONS

| Collection | Phase | Source | Vectors | Purpose |
|------------|-------|--------|---------|---------|
| `derivatives_strategies` | 1 | F1-F5 | ~50 | Options strategies mapped to market conditions |
| `pattern_labels` | 4 | F16-F18 | ~200 | Triple Barrier + Vision-labeled patterns |
| `sec_filings` | 3 | F21-F26 | ~500 | EDGAR filing summaries for semantic search |
| `econometrics_models` | 1 | F10-F11 | ~30 | ARIMA/regression model configs |

---

## 8. NEW STREAMLIT PAGES

| Page | Phase | Components | Data Source |
|------|-------|-----------|------------|
| Portfolio Optimization | 1 | F7+F8+F9 | shared_config/portfolio_signal.json |
| Derivatives | 1 | F1-F6 | derivatives_mcp_server |
| Econometrics | 1 | F10-F11 | econometrics_mcp_server |
| Fundamentals | 3 | F21-F26 | edgar_mcp_server |
| Vision Patterns | 4 | F16-F20 | vision services |
| Slippage Analysis | 5 | F33 | backtest results + microstructure sim |

---

## 9. NEW SIGNALS IN shared_config/

```
shared_config/
├── derivatives_signal.json     # Phase 1: Greeks, IV, pricing signals
├── portfolio_signal.json       # Phase 1: Allocation weights from optimizer
├── econometrics_signal.json    # Phase 1: ARIMA forecasts, stationarity
├── fundamental_signal.json     # Phase 3: EDGAR/SEC data summaries
├── greeks_signal.json          # Phase 2: Batch Greeks from daemon
├── vision_pattern_signal.json  # Phase 4: CNN pattern matches
├── vision_score_signal.json    # Phase 4: Multi-factor vision score
├── tick_stream.json            # Phase 5: Real-time WS ticks
├── condition_signal.json       # Phase 5: Condition evaluator output
└── microstructure_signal.json  # Phase 5: Slippage/cost estimates
```

---

## 10. EXECUTION TIMELINE

| Phase | Duration | Components | New Capabilities | Docker Services |
|-------|----------|-----------|-----------------|-----------------|
| 1 Foundation | 2 days | F1, F7, F10, F14 | Options pricing, portfolio opt, econometrics, streaming indicators | derivatives-mcp |
| 2 Analytics | 3 days | F3-F6, F8-F9, F11-F12 | Bond/FX/IRS/CDS, tearsheets, interactive portfolio viz | (none new) |
| 3 Data | 4 days | F21-F26 | SEC EDGAR, FRED, World Bank, BEA, OECD fundamental data | edgar-mcp |
| 4 ML Patterns | 5 days | F16-F20 | Triple Barrier, CNN patterns, DTW search, vision scoring | vision-encoder, pattern-search |
| 5 Execution | 5 days | F27-F33 | Multi-exchange daemon, WS streaming, dynamic TP/SL, microstructure backtest | exchange-daemon |

**Total: ~19 days of focused integration work**

Post-integration, your Algotrading stack gains:
- 5 new MCP tool servers (45+ tools)
- 4 new ChromaDB collections (~780 vectors)
- 6 new Streamlit pages
- 9 new shared_config signal files
- 5 new Docker services
- Options/derivatives capability from zero
- Portfolio optimization from zero
- Fundamental data pipeline from zero
- ML pattern recognition layer (complement to HMM)
- Multi-exchange support (from Binance-only)
- Microstructure-aware backtesting