# Bloomberg-Inspired Terminal Projects — Research Compendium

> Research date: 2026-05-18
> Purpose: Reference for developing our algotrading terminal stack (freqtrade + Strategy KB + NEXUS + multi-agent architecture)

---

## TIER 1: Major Projects (1,000+ Stars)

### 1. OpenBB — 67,741 stars
- **URL**: https://github.com/OpenBB-finance/OpenBB
- **Language**: Python
- **Description**: Financial data platform for analysts, quants and AI agents
- **Key Features**:
  - Full SDK, CLI, and web GUI
  - Supports stocks, crypto, forex, macro data
  - AI agent framework (`experimental-openbb-platform-agent`, 1,337 stars)
  - Backend templates (`backends-for-openbb`, 181 stars) for custom data
  - Custom agents (`agents-for-openbb`, 323 stars)
  - Active ecosystem with extensions
- **Relevance**: THE open-source Bloomberg Terminal alternative. SDK alone worth integrating. AI agent experiments map directly to our multi-agent architecture. Should be our data backbone.
- **Ecosystem**:
  - FinanceToolkit (4,786 stars) — comprehensive financial analysis library
  - FinanceDatabase (7,620 stars) — 300K+ symbol database
  - Both by JerBouma, OpenBB-compatible

### 2. Bloomberg Terminal Clone (feremabraz) — 1,263 stars
- **URL**: https://github.com/feremabraz/bloomberg-terminal
- **Language**: TypeScript
- **Description**: Bloomberg-like terminal with AI. Uses Redis + AlphaVantage data with local simulations to avoid API rate limits.
- **Key Features**:
  - Closest visual clone of Bloomberg Terminal UI
  - AI-integrated (natural language queries)
  - Redis caching layer for API rate limit avoidance
  - Real-time market data via AlphaVantage
- **Relevance**: Best UI/UX reference for Bloomberg-style design patterns. Caching strategy (Redis) is a good pattern for our data pipeline.

### 3. Maestro — 1,151 stars
- **URL**: https://github.com/its-maestro-baby/maestro
- **Language**: TypeScript
- **Description**: "The Bloomberg Terminal for CLI Agents"
- **Key Features**:
  - Purpose-built for AI agent orchestration
  - Agents can navigate, query, and execute financial operations
  - CLI-first design
- **Relevance**: Directly relevant — this is a Bloomberg Terminal that AI agents drive. Architecture patterns (agent tool interfaces, command routing) should inform our NEXUS + strategy-KB agent design. STUDY THIS.

---

## TIER 2: Mid-Range Projects (50–500 Stars)

### 4. Rust-Finance — 341 stars
- **URL**: https://github.com/Ashutosh0x/rust-finance
- **Language**: Rust
- **Description**: High-performance, ultra low-latency trading terminal and AI-infused daemon built completely in Rust.
- **Key Features**:
  - Ultra-low latency execution
  - AI daemon for strategy decisions
  - Built entirely in Rust for performance
- **Relevance**: If we need HFT-grade latency, this architecture is the reference. Rust + AI daemon pattern could inform a future high-performance execution layer for our freqtrade stack.

### 5. Equables — 107 stars
- **URL**: https://github.com/daniel3303/Equables
- **Language**: C#
- **Description**: Self-hosted mini Bloomberg Terminal for AI agents — SEC filings, institutional holdings, insider trading, congressional trades, short data.
- **Key Features**:
  - Self-hosted (no external API dependency)
  - Alternative data focus: SEC filings, congressional trades, insider trading, short interest
  - Agent-oriented API design
- **Relevance**: Self-hosted alternative data pipeline. Congressional trades + insider data = alpha signals. Architecture (data plumbing, self-hosted stack) directly applicable to our strategy KB enrichment.

### 6. Bloomberg Terminal Free / Fincept Terminal — 108 stars
- **URL**: https://github.com/bloomberg-terminal/bloomberg-terminal-free
- **Language**: Python
- **Description**: Institutional-grade financial analysis, real-time market data (Stocks, Crypto, Macro), local AI (Llama 3). Claims "$24k value for free."
- **Key Features**:
  - Python CLI (aligns with our stack)
  - Local LLM integration (Llama 3)
  - Stocks + Crypto + Macro data
  - Institutional-grade analysis tools
- **Relevance**: Most directly comparable to our freqtrade + strategy-KB + NEXUS stack. Local AI pattern is exactly what we're doing.

---

## TIER 3: Niche / Emerging Projects (< 50 Stars but Notable)

### 7. Momentum MCP — 19 stars
- **URL**: https://github.com/mphinance/momentum-mcp
- **Language**: Python
- **Description**: MCP server for stock screening, OHLCV data, technical analysis, chart generation, financial news. "Give your AI agent a Bloomberg terminal."
- **Key Features**:
  - MCP protocol (plugs into Hermes/NEXUS directly)
  - Stock screening as a tool
  - OHLCV + TA indicators
  - Chart generation
  - Financial news integration
- **Relevance**: HIGHEST IMMEDIATE INTEGRATION VALUE. Drop-in MCP server for our Hermes agent. We already have MCP infrastructure. This adds stock screening + TA + charts as tools.

### 8. Bloomberg MCP — 8 stars
- **URL**: https://github.com/QmQsun/Bloomberg-MCP
- **Language**: Python
- **Description**: Enhanced MCP server for actual Bloomberg Terminal (BDP/BDH/BDS/BQL/TA) with 18 tools, caching, dynamic screening.
- **Key Features**:
  - 18 Bloomberg API tools via MCP
  - Caching layer
  - Dynamic screening
  - BDP/BDH/BDS/BQL function coverage
- **Relevance**: If we ever get Bloomberg API access, this is production-ready. 18 tools covering the full Bloomberg data API via MCP.

### 9. Gloom — 8 stars
- **URL**: https://github.com/akayy-dev/gloom
- **Language**: Go
- **Description**: Highly customizable and extensible financial terminal for CLI
- **Key Features**:
  - Go-based TUI (similar to our Hermes TUI)
  - Extensible plugin architecture
  - CLI-first design
- **Relevance**: Plugin architecture pattern useful for our modular terminal design. Go performance for real-time data rendering.

### 10. Terminal-Trade — 11 stars
- **URL**: https://github.com/letrinhandn/Terminal-Trade
- **Language**: Python
- **Description**: Open-source trading platform inspired by Bloomberg Terminal. Real-time data, backtesting, options analysis.
- **Key Features**:
  - Backtesting integrated in terminal
  - Options analysis
  - Real-time data feeds
- **Relevance**: Backtesting + terminal integration pattern useful for our freqtrade backtest display.

### 11. MacroDashboard — 10 stars
- **URL**: https://github.com/SunFish98/MacroDashboard
- **Language**: Python/Flask
- **Description**: Self-hosted, real-time macro dashboard. Tracks US economic indicators, Fed policy expectations, presidential social media. Bloomberg-inspired dark UI.
- **Key Features**:
  - US economic indicators tracking
  - Fed policy expectations (FOMC)
  - Presidential social media sentiment
  - Dark Bloomberg-style UI
- **Relevance**: Macro data pipeline (Fed, economic indicators) for regime detection. Could feed into our HMM regime detector.

### 12. QuantumTerminal — 24 stars
- **URL**: https://github.com/RAYDENFLY/quantumterminal
- **Language**: TypeScript/Next.js
- **Description**: Crypto trading dashboard (Bloomberg-inspired). Real-time market data, news aggregation, on-chain analytics, educational resources.
- **Key Features**:
  - Crypto-focused (aligned with our Binance futures stack)
  - On-chain analytics
  - News aggregation
  - Next.js (React) for web UI
- **Relevance**: Crypto focus + on-chain analytics + news sentiment. Directly applicable to our crypto strategy pipeline.

### 13. Ticker-Tape — 1 star
- **URL**: https://github.com/jeffbai996/ticker-tape
- **Language**: Python
- **Description**: TUI-based financial terminal with interactive commands, built-in AI trading assistant, IBKR API integration, multi-language support.
- **Key Features**:
  - TUI (terminal UI) design
  - Built-in AI assistant
  - IBKR API integration
  - Interactive commands
- **Relevance**: TUI pattern + AI assistant is exactly what Hermes + our terminal could become.

### 14. TerminalQ — 2 stars
- **URL**: https://github.com/fakoli/terminalq
- **Language**: Python
- **Description**: Bloomberg-style financial terminal — Claude Code MCP plugin with 30 tools.
- **Key Features**:
  - 30 financial tools via MCP
  - Live quotes
  - AI analysis
  - Earnings calendar, options flow
- **Relevance**: Another MCP reference. 30-tool pattern for financial data extraction.

### 15. claude-code-trading-terminal — 19 stars
- **URL**: https://github.com/degentic-tools/claude-code-trading-terminal
- **Language**: JavaScript
- **Description**: Agent-native trading terminal built on Claude Code. Sub-agents execute trades, monitor positions, manage risk in parallel across unlimited wallets.
- **Key Features**:
  - Agent-native architecture
  - Sub-agent parallelization
  - Multi-wallet support
  - Risk management agents
- **Relevance**: Agent-native pattern directly relevant to our multi-agent architecture. Sub-agent parallelization and multi-wallet management are patterns we need.

### 16. Vibe-Sensei — 18 stars
- **URL**: https://github.com/VictorVVedtion/vibe-sensei
- **Language**: TypeScript
- **Description**: AI Trading Terminal — 68 historical masters watch your trades. Buffett warns on risk, Soros spots reflexivity. Paper trading sandbox, terminal-native.
- **Key Features**:
  - AI personality personas (Buffett, Soros, etc.)
  - Paper trading sandbox
  - Terminal-native design
- **Relevance**: Fun concept but "68 historical masters" persona pattern could inform our strategy KB advisor personas.

### 17. Sentinel-Lite — 28 stars
- **URL**: https://github.com/pattty847/Sentinel-Lite
- **Language**: Python
- **Description**: Crypto Trading Terminal & Monitoring — SEC filing viewer, market scanners, market monitoring.
- **Key Features**:
  - Crypto focus
  - SEC filing viewer
  - Market scanners
  - Monitoring dashboards
- **Relevance**: Crypto + scanning patterns applicable to our Binance futures monitoring.

### 18. diy-bloomberg-terminal — 9 stars
- **URL**: https://github.com/christian-spooner/diy-bloomberg-terminal
- **Language**: Python
- **Description**: Command-line application for retrieving financial data, a la Bloomberg
- **Key Features**:
  - Pure CLI (no GUI)
  - Simple data retrieval pattern
- **Relevance**: Minimal reference for CLI-only financial data access. Good starting point pattern.

### 19. Brodberg — 2 stars
- **URL**: https://github.com/JackBroderick/brodberg
- **Language**: Python
- **Description**: Bloomberg-style financial terminal for the command line.
- **Key Features**:
  - CLI-first
  - Python (aligned with our stack)
- **Relevance**: Simple CLI architecture reference.

### 20. saifberg-terminal — 2 stars
- **URL**: https://github.com/saifkhan7865/saifberg-terminal
- **Language**: TypeScript
- **Description**: Bloomberg-style financial terminal — live quotes, AI analysis, earnings calendar, options flow.
- **Key Features**:
  - Live quotes
  - AI analysis
  - Earnings calendar
  - Options flow
- **Relevance**: Options flow + earnings calendar patterns useful for sentiment/strategy signals.

---

## Ecosystem Reference Projects

| Project | Stars | Language | Key Feature |
|---------|-------|----------|-------------|
| FinanceToolkit (JerBouma) | 4,786 | Python | Comprehensive financial analysis library |
| FinanceDatabase (JerBouma) | 7,620 | Python | 300K+ symbols database |
| Astras Trading UI (Alor Broker) | 84 | TypeScript | Professional broker terminal (Angular) |
| OpenBB Agents | 323 | Python | Custom agents for OpenBB Workspace |
| OpenBB Backends | 181 | Python | BYO data into OpenBB |
| financial-chat (wshobson) | 231 | Python | LangChain + OpenBB + Claude financial chat |
| Polyterminal (kapilcdave) | 13 | Python | Bloomberg Terminal for prediction markets |
| Polyterminal (txbabaxyz) | 77 | Python | Polymarket 15-min crypto prediction terminal |

---

## MCP Integration Priority

These projects plug into our existing Hermes/NEXUS MCP infrastructure:

| Priority | Project | Stars | Integration Effort | Value |
|----------|---------|-------|--------------------|-------|
| P0 | Momentum MCP | 19 | Low — drop-in MCP server | Stock screening, TA, charts as tools |
| P0 | Bloomberg MCP | 8 | Low — drop-in MCP server | 18 Bloomberg API tools (with terminal access) |
| P1 | TerminalQ | 2 | Low — MCP plugin | 30 financial tools |
| P1 | Maestro | 1,151 | Medium — study architecture | Agent-driven terminal patterns |
| P2 | OpenBB SDK | 67,741 | Medium — SDK integration | Data backbone for all instruments |
| P2 | Equables | 107 | Medium — self-hosted stack | Alternative data pipeline |

---

## Architecture Patterns to Study

### 1. Redis Caching Layer (feremabraz/bloomberg-terminal)
- Cache AlphaVantage/yfinance data in Redis
- Serve from cache first, refresh on TTL expiry
- Pattern applicable to our Strategy KB data pipeline

### 2. Agent-Driven Terminal (Maestro)
- CLI agents navigate data
- Tool interface per agent capability
- Maps to our NEXUS routing + strategy-KB agents

### 3. MCP as Universal Data Interface (Momentum MCP, Bloomberg MCP, TerminalQ)
- Financial data = MCP tools
- Terminal queries = tool calls
- Our Hermes agent already speaks MCP — immediate compatibility

### 4. Sub-Agent Parallelization (claude-code-trading-terminal)
- Multiple agents trade simultaneously
- Per-wallet isolation
- Risk agent as overseer
- Pattern directly applicable to our multi-pair freqtrade setup

### 5. Self-Hosted Alternative Data (Equables)
- SEC filings, congressional trades, insider data
- No external API dependency
- Pattern for enriching our strategy KB with alpha signals

### 6. Local LLM Integration (bloomberg-terminal-free)
- Llama 3 runs locally
- No cloud API dependency for analysis
- Pattern: embed local models via Ollama (we already have this)

### 7. Macro Dashboard Pipeline (MacroDashboard)
- Fed policy tracking
- Economic indicator alerts
- Pattern applicable to our HMM regime detector's macro input layer

---

## Recommended Action Plan

1. **Install Momentum MCP** as an MCP server in our Hermes config — immediate financial data tools
2. **Study Maestro** architecture for agent-driven terminal patterns
3. **Clone Equables** for self-hosted alternative data pipeline patterns
4. **Evaluate OpenBB SDK** as data backbone (replaces yfinance/alpha-vantage calls)
5. **Reference Bloomberg MCP** if Bloomberg API access becomes available
6. **Study Rust-Finance** daemon pattern for potential high-speed execution layer
7. **Integrate MacroDashboard** macro pipeline into our regime detector

---

*Research saved for project development reference. Revisit when building the terminal UI layer or expanding data sources.*