# Algotrading + Strategy Knowledge Base

## Project Documentation Index

| Document | Purpose | Last Updated |
|----------|---------|-------------|
| [OPTIMIZATION_ROADMAP.md](./OPTIMIZATION_ROADMAP.md) | **Primary:** Gap analysis + 5-phase action plan (Kronos, QuantDinger, AI-Trader, neural-trader, Kelly, walk-forward) | 2026-05-15 |
| [CROSS_PROJECT_INTELLIGENCE.md](./CROSS_PROJECT_INTELLIGENCE.md) | **Reference:** Detailed analysis of all 6 projects (Kronos, QuantDinger, AI-Trader, neural-trader, MoondevRED, Strategy DB) with extracted patterns and code | 2026-05-15 |
| [OPTIMIZATION_MASTERPLAN.md](./OPTIMIZATION_MASTERPLAN.md) | First-principles quantitative diagnosis + external research synthesis (Kronos, NostalgiaForInfinity, GeneTrader, bolsa-ai-trading, MoondevRED) | 2026-05-15 |
| [TYPED_EXECUTION_PLAN.md](./TYPED_EXECUTION_PLAN.md) | 8-phase typed DAG with 7 checkpoints, code appendices, rollback triggers, graduated capital plan | 2026-05-15 |
| [Trading_RESEARCH_PREVIEW_SYSTEM.md](./Trading_RESEARCH_PREVIEW_SYSTEM.md) | TRAP system design (preview, estimate, backtest_query, walk_forward, dashboard) + gap analysis | 2026-05-15 |
| [MoondevRED_Engine_DeepDive.md](./MoondevRED_Engine_DeepDive.md) | Audit of MoondevRED RBI engine (14 strategies, execution logs, PnL schema) | 2026-05-15 |
| [ARCHITECTURE_DAG.md](./ARCHITECTURE_DAG.md) | Current 9-layer system architecture (freqtrade → agents → swarm → signals → risk) | 2026-05-10 |
| [ALGOTRADING_STATE_ANALYSIS.md](./ALGOTRADING_STATE_ANALYSIS.md) | Security audit, strategy analysis, leverage/risk config, AI layer issues | 2026-05-07 |
| [STRATEGIC_PIPELINE_SUMMARY.md](./STRATEGIC_PIPELINE_SUMMARY.md) | Strategic pipeline for eliminating duplicate configs (Run-Trading.ps1) | 2026-05-07 |
| [VERIFICATION_REPORT.md](./VERIFICATION_REPORT.md) | Post-change verification checklist | 2026-05-07 |

---

## Strategy Vector DB (ChromaDB)

A local vector database of 443 trading strategy chunks scraped from YouTube, indexed with all-MiniLM-L6-v2 embeddings.

### Available Commands

**Query strategies semantically:**
```bash
cd /home/roshan/Downloads/Algotrading
python3 strategy_db/gcode_bridge.py query "liquidity trap with 1:3 R:R"
python3 strategy_db/gcode_bridge.py query --setup-type entry --keyword breakout
python3 strategy_db/gcode_bridge.py get "First Red Day"
```

**Explore the knowledge base:**
```bash
python3 strategy_db/gcode_bridge.py list-types
python3 strategy_db/gcode_bridge.py list-conditions
```

### Filters
- `--setup-type` — market_structure, entry, exit, risk_management, psychology, etc.
- `--market-condition` — trending, ranging, volatile, reversal, any
- `--keyword` — liquidity_trap, breakout, momentum, reversal, etc.

### Re-ingestion
To re-index after adding new strategy files:
```bash
cd /home/roshan/Downloads/Algotrading
python3 strategy_db/ingest.py
```

### MCP Server (planned)
A proper MCP server exposing `query_strategies` tool is planned for deeper Gcode integration.
