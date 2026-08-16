# Algotrading Project — Integration Surface Map

**Purpose:** Exact plugin/extension points, interfaces, registrations, and configuration slots for adding new components (e.g., Fincept).

---

## 1. Strategy Plugin (IStrategy Interface)

**File:** `freqtrade/strategy/interface.py` (1886 lines)

**Base class:** `IStrategy` — all strategies must subclass this.

### Required overrides:
```python
class MyStrategy(IStrategy):
    # Class-level config attributes (REQUIRED):
    minimal_roi = {}           # e.g. {"0": 0.10}
    stoploss = -0.10           # Stop loss ratio
    timeframe = "1h"           # Candle timeframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Add indicators to dataframe. Called once per pair."""
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Set 'enter_long'/'enter_short' columns to 1 to signal entries."""
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Set 'exit_long'/'exit_short' columns to 1 to signal exits."""
        return dataframe
```

### Optional hooks (override as needed):
```python
    def custom_stoploss(self, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float,
                        after_fill: bool, **kwargs) -> float | None:
        """Dynamic stoploss. Return None to use static stoploss."""

    def custom_exit(self, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float,
                    **kwargs) -> str | bool | None:
        """Custom exit logic. Return string reason or True to exit."""

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float,
                 entry_tag: str | None, side: str, **kwargs) -> float:
        """Customize leverage per trade. Futures mode only."""

    def adjust_trade_position(self, trade: Trade, current_time: datetime,
                               current_rate: float, current_profit: float,
                               min_stake: float | None, max_stake: float,
                               current_entry_rate: float, current_exit_rate: float,
                               current_entry_profit: float, current_exit_profit: float,
                               **kwargs) -> tuple[float | None, str]:
        """DCA / partial exit. Return (stake_amount, direction)."""

    def adjust_entry_price(self, trade: Trade, order: Order, pair: str,
                            current_time: datetime, proposed_rate: float,
                            current_order_rate: float, entry_tag: str | None,
                            side: str, **kwargs) -> float | None:
        """Adjust entry price after order placed."""

    def adjust_exit_price(self, trade: Trade, order: Order, pair: str,
                           current_time: datetime, proposed_rate: float,
                           current_order_rate: float, entry_tag: str | None,
                           side: str, **kwargs) -> float | None:
        """Adjust exit price after order placed."""

    def informative_pairs(self) -> ListPairsWithTimeframes:
        """Declare informative pair/timeframe combinations to cache."""
        return [("ETH/USDT", "5m"), ("BTC/USDT", "15m")]

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float,
                            rate: float, time_in_force: str, current_time: datetime,
                            entry_tag: str | None, side: str, **kwargs) -> bool:
        """Filter entries. Return False to reject."""

    def confirm_trade_exit(self, pair: str, trade: Trade, order_type: str,
                           amount: float, rate: float, time_in_force: str,
                           current_time: datetime, exit_reason: str, **kwargs) -> bool:
        """Filter exits. Return False to reject."""

    # FreqAI feature engineering hooks (only if FreqAI enabled):
    def feature_engineering_expand_all(self, dataframe, period, metadata, **kwargs) -> DataFrame: ...
    def feature_engineering_expand_basic(self, dataframe, metadata, **kwargs) -> DataFrame: ...
    def feature_engineering_standard(self, dataframe, metadata, **kwargs) -> DataFrame: ...
    def set_freqai_targets(self, dataframe, metadata, **kwargs) -> DataFrame: ...

    def plot_annotations(self, pair, start_date, end_date, dataframe, **kwargs) -> list[AnnotationType]: ...
    def version(self) -> str | None: ...
```

### Registration pattern:
1. Place strategy file in `user_data/strategies/` directory
2. Set class name matching filename (e.g., `MyStrategy` in `MyStrategy.py`)
3. Reference via CLI `--strategy MyStrategy` or JSON config `"strategy": "MyStrategy"`
4. **Resolver:** `freqtrade/resolvers/strategy_resolver.py` — `StrategyResolver.load_strategy()` scans `user_data/strategies/` for the class

---

## 2. Data Sources (DataProvider)

**File:** `freqtrade/data/dataprovider.py` (648 lines)

### Interface exposed to strategies:
```python
class DataProvider:
    def __init__(self, config: Config, exchange: Exchange | None,
                 pairlists=None, rpc: RPCManager | None = None)

    # Access in strategies via self.dp (injected by Freqtrade engine)
    # Key methods available to strategies:
    def current_whitelist(self) -> list[str]               # Active pair whitelist
    def ohlcv(self, pair: str, timeframe: str, candle_type: CandleType) -> DataFrame
    def ticker(self, pair: str) -> Ticker                   # Current ticker
    def orderbook(self, pair: str, maximum: int) -> OrderBook
    def funding_rate(self, pair: str) -> float | None       # Current funding rate
    def runmode(self) -> RunMode                            # backtest/dry-run/live
```

### Adding new data sources:
- **Exchange-provided data:** Exchange subclass provides `fetchOHLCV`, `fetchTicker`, `fetchOrderBook` via ccxt
- **External message consumer** (data from other bots/agents):
  ```json
  // In Freqtrade JSON config:
  "external_message_consumer": {
    "producers": [
      { "name": "signal_producer", "host": "127.0.0.1", "port": 8080 }
    ]
  }
  ```
- **Files in `shared_config/`:** Signal files like `tradingagents_signal.json`, `miroshark_brain.json`, `sentiment_signal.json` — read by strategies or engine components

### Registration pattern:
Data sources are NOT dynamically registered. They come from:
1. Exchange (via ccxt adapters)
2. `shared_config/` JSON files (read directly by components)
3. External message consumer (WebSocket producers in config)

---

## 3. Exchange Adapters

**File:** `freqtrade/exchange/exchange.py` (4149 lines), `freqtrade/exchange/common.py`

### Adding a new exchange:
```python
# 1. Create freqtrade/exchange/<exchange_name>.py
from freqtrade.exchange import Exchange

class MyExchange(Exchange):
    _ft_has: FtHas = {
        "stoploss_on_exchange": False,
        "order_time_in_force": ["GTC", "FOK"],
        # ... exchange-specific capability flags
    }
    _ft_has_futures: FtHas = { ... }  # Futures-specific overrides
    _supported_trading_mode_margin_pairs = [
        (TradingMode.SPOT, MarginMode.NONE),
    ]
```

### Required ccxt capabilities (from `common.py`):
```python
EXCHANGE_HAS_REQUIRED = {
    "fetchOrder": ["fetchOpenOrder", "fetchClosedOrder"],
    "fetchL2OrderBook": ["fetchTicker"],
    "cancelOrder": [],
    "createOrder": [],
    "fetchBalance": [],
    "fetchOHLCV": [],
}
```

### Registration pattern:
1. Create `freqtrade/exchange/<name>.py` with class inheriting `Exchange`
2. Add exchange name to `SUPPORTED_EXCHANGES` in `common.py`:
   ```python
   SUPPORTED_EXCHANGES = ["binance", "bybit", "okx", ...]
   ```
3. Add alias mapping if needed: `MAP_EXCHANGE_CHILDCLASS = {"gateio": "gate"}`
4. **Resolver:** `freqtrade/resolvers/exchange_resolver.py` — `ExchangeResolver.load_exchange()` resolves by `exchange.name` config key
5. Reference in JSON config: `"exchange": {"name": "my_exchange", "key": "...", "secret": "..."}`

Current supported exchanges: binance, binanceus, binanceusdm, bingx, bitmart, bitget, bybit, gate, htx, hyperliquid, kraken, krakenfutures, okx, myokx

---

## 4. Signal Bus

**File:** `engine/signal_bus.py` (132 lines)

### Interface: `RedisSignalBus`
```python
class RedisSignalBus:
    CHANNELS = {"signals", "risk", "pnl", "commands"}

    def __init__(self, host: str = "127.0.0.1", port: int = 6379, db: int = 0)

    # Core pub/sub:
    def publish(self, channel: str, message: dict) -> bool
    def subscribe(self, channel: str)
    def subscribe_all(self)
    def listen(self, timeout: Optional[float] = None) -> Generator[dict]
    def unsubscribe(self, channel: str)
    def unsubscribe_all(self)

    # Convenience methods:
    def publish_signal(self, pair: str, side: str, price: float,
                       amount: float, strategy: str = "", signal_id: str = "") -> bool
    def publish_risk_event(self, event_type: str, message: str, details: dict = None) -> bool
    def publish_pnl(self, pair: str, pnl: float, trade_id: str = "") -> bool
```

### Channel schema:
| Channel   | Message shape                              | JSON backup file                        |
|-----------|-------------------------------------------|-----------------------------------------|
| `signals` | `{pair, side, price, amount, strategy, signal_id}` | `shared_config/signal_bus_signals.json` |
| `risk`    | `{event, message, details}`               | `shared_config/signal_bus_risk.json`    |
| `pnl`     | `{pair, pnl, trade_id}`                   | `shared_config/signal_bus_pnl.json`     |
| `commands`| (user-defined)                            | `shared_config/signal_bus_commands.json` |

### Registration pattern:
- Channel names are hardcoded in `CHANNELS` dict — to add a new channel, edit `engine/signal_bus.py` and add the key
- The bus also writes every message to a JSON file backup in `shared_config/` (auto-appends, max 1000 entries, trims to 500)
- Message format always includes `type` and `timestamp` (auto-injected)

---

## 5. MCP Tool Registration

### 5a. Strategy-KB MCP Server (`strategy_db/mcp_server.py`, 618 lines)

**Framework:** `mcp` Python SDK (`from mcp.server import Server`, `from mcp.server.stdio import stdio_server`)

**Registration pattern:**
```python
app = Server("strategy-kb")  # Server name

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="tool_name",              # Unique tool name
            description="...",
            inputSchema={                   # JSON Schema
                "type": "object",
                "properties": { ... },
                "required": [...],
            },
        ),
        # ... more tools
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "tool_name":
        result = ...
        return [TextContent(type="text", text=json.dumps(result))]

# Entry point:
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())
```

**Registered tools (10):**
| Tool name              | Required params    | Optional params                    |
|------------------------|--------------------|-------------------------------------|
| `query_strategies`     | `query`            | `setup_type`, `market_condition`, `keyword`, `top_k` |
| `query_user_knowledge` | `query`            | `top_k`                             |
| `get_strategy`         | `name`             | `top_k`                             |
| `list_setup_types`     | —                  | —                                   |
| `list_market_conditions`| —                 | —                                   |
| `strategy_stats`       | —                  | —                                   |
| `regime_detect`        | `pair`             | `timeframe`                         |
| `strategy_context`     | `regime`           | `top_k`, `outcome_weight`           |
| `outcome_sync`         | —                  | —                                   |
| `regime_aware_search`  | `query`            | `pair`, `timeframe`, `top_k`, `outcome_weight` |
| `sentiment_query`      | `query`            | `top_k`                             |

### 5b. Finance MCP Server (`mcp_layer/finance_mcp_server.py`, 442 lines)

**Framework:** Custom JSON-RPC 2.0 over stdio (NOT using mcp SDK)

**Registration pattern:**
```python
class FinanceMcpServer:
    def __init__(self):
        self.tools = {
            "tool_name": self._handle_tool_name,   # Map name -> handler
        }

    def handle_request(self, request: dict) -> dict:
        """JSON-RPC 2.0 dispatch: tools/list -> list, tools/call -> handler"""

    def run(self):
        """Read stdin line-by-line, process JSON-RPC, write stdout"""
```

**Registered tools (~10):**
| Tool name               | Description                       |
|-------------------------|-----------------------------------|
| `get_stock_price`       | Current price via yfinance        |
| `get_stock_history`     | Historical OHLCV                 |
| `get_stock_info`        | Company info/metrics              |
| `get_market_indices`    | Major indices (S&P, DOW, NASDAQ)  |
| `get_crypto_price`      | Crypto current price              |
| `get_crypto_history`    | Crypto historical data            |
| `get_forex_rate`        | Forex exchange rate               |
| `get_earnings_calendar` | Upcoming earnings                 |
| `get_market_news`       | Market news headlines             |
| `get_treasury_yields`   | US Treasury yield curve           |

### 5c. MCP Server in Hermes/NEXUS config
Registered in `start_local.sh`:
```bash
start_service "strategy-kb" "$PYTHON" "$ALGOTRADING_DIR/strategy_db/mcp_server.py"
start_service "finance-mcp" "$PYTHON" "$ALGOTRADING_DIR/mcp_layer/finance_mcp_server.py"
```

And in `.mcp.json`:
```json
{
  "mcpServers": {
    "claude-flow": { "command": "npx", "args": ["ruflo@latest"] },
    "hierarchical-mesh": { "command": "npx", "args": ["hierarchical-mesh@latest"] }
  }
}
```

### To add a new MCP server:
1. Create server file (use `mcp` SDK pattern from strategy_db, or custom JSON-RPC)
2. Add handler to `tools` dict or use `@app.list_tools()` / `@app.call_tool()` decorators
3. Add `start_service` line in `start_local.sh`
4. Add entry in `.mcp.json` if used by Claude Code / Hermes

---

## 6. Streamlit UI Pages

**File:** `ui/app.py` (99 lines)

### Registration pattern:
Pages are registered as a **hardcoded sidebar dict** in `ui/app.py`:
```python
pages = {
    "Dashboard": "📊",
    "Portfolio": "💰",
    "Signals": "📡",
    "Risk Monitor": "⚠️",
    "PnL Analytics": "📈",
    "Market Data": "🔍",
    "Strategies": "⚙️",
    "Backtest": "🧪",
    "System Health": "🏥",
    "Settings": "🔧",
}
```

Page files live in `ui/pages/` — 12 files found. Navigation uses `st.page_link()`:
```python
st.page_link("pages/2_portfolio.py", label="View Portfolio")
st.page_link("pages/3_signals.py", label="Check Signals")
```

### To add a new page:
1. Create file `ui/pages/<N>_<name>.py` (N = page number for ordering)
2. Add entry to `pages` dict in `ui/app.py`
3. Optionally add `st.page_link()` in the Quick Actions section

### Data layer for pages:
```python
# ui/data_layer.py — functions available to all pages:
from ui.data_layer import (
    get_circuit_breaker,       # Reads shared_config/circuit_breaker.json
    classify_ui_tier,          # Risk tier classification
    get_tier_label,            # Human-readable tier label
    get_strategy_performance,  # Reads strategy_performance_db.json
    get_hedge_state,           # Reads shared_config/hedge_state.json
)
```

---

## 7. Monitoring & Alerts

**File:** `monitoring/alerter.py` (260 lines)

### Configuration:
```json
// shared_config/alerter_config.json
{
    "slack_webhook_url": "https://hooks.slack.com/...",
    "generic_webhook_url": "https://...",
    "min_pnl_alert": 50.0,            // Minimum |PnL| to alert on
    "max_signal_age": 300,            // Seconds before "stale signals" alert
    "alert_on_critical_breaker": true, // HALT/LIQUIDATE breaker states
    "alert_on_warning_breaker": true,  // CAUTION/RESTRICTED states
    "alert_on_large_pnl": true,       // Large PnL events
    "alert_on_stale_signals": true    // Signal freshness checks
}
```

### Monitored files:
| File                               | Purpose                              |
|------------------------------------|--------------------------------------|
| `shared_config/circuit_breaker.json` | Breaker state (NORMAL/CAUTION/RESTRICTED/HALT/LIQUIDATE) |
| `shared_config/signal_bus_pnl.json` | PnL events from signal bus           |
| `shared_config/signal_bus_signals.json` | Trade signals from signal bus    |
| `shared_config/agent_health.json`  | Agent health status                   |

### Alert dispatch:
```python
class Alerter:
    def __init__(self, config: Optional[dict] = None)
    def check_breaker(self) -> list[dict]     # Circuit breaker state changes
    def check_pnl(self) -> list[dict]         # Large PnL events
    def check_signal_freshness(self) -> list[dict]  # Stale signal detection
    def check_all(self) -> list[dict]         # Run all checks
    def get_stats(self) -> dict               # Total alerts, last breaker state

# Webhook dispatch functions:
def send_slack(cfg: dict, message: str, color: str = "#ff4444")
def send_generic(cfg: dict, event: str, severity: str, message: str)
```

### CLI usage:
```bash
python3 monitoring/alerter.py --watch    # Continuous (60s interval)
python3 monitoring/alerter.py --once     # Single check
python3 monitoring/alerter.py --config /path/to/config.json  # Custom config
```

### To add new alert checks:
1. Add new `check_<name>()` method to `Alerter` class
2. Add new file to monitor (follow pattern of existing `read_json_safe` / `read_json_list`)
3. Add call in `check_all()`
4. Add config toggle to `DEFAULT_CONFIG` dict and `alerter_config.json`

---

## 8. ChromaDB Collections

**File:** `strategy_db/config.py`, `strategy_db/search.py`, `strategy_db/schema.py`, `strategy_db/ingest.py`

### Collection configuration:
```python
# strategy_db/config.py
DB_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")  # ChromaDB storage
COLLECTION_NAME = "trading_strategies"        # Primary collection
EMBEDDING_MODEL = "all-MiniLM-L6-v2"         # SentenceTransformer model
TOP_K_DEFAULT = 5
ENABLE_HYBRID_SEARCH = True                   # BM25 + dense hybrid
```

### Schema (StrategyChunk):
```python
@dataclass
class StrategyChunk:
    chunk_id: str
    source_type: str           # "youtube", "book", "article"
    youtube_url: str
    video_title: str
    channel_name: str
    setup_name: str            # Strategy name
    setup_type: str            # "entry", "exit", "confirmation", "risk_management", ...
    timeframe: str
    market_condition: str      # "trending", "ranging", "ranging_to_trending", "any"
    strategy_style: str
    assets_applicable: list[str]
    chunk_text: str             # Full text for embedding
    entry_condition: str
    confirmation_signal: str
    stop_loss_rule: str
    target_exit_rule: str
    invalidation_condition: str
    risk_reward: str
    position_sizing: str
    psychology_note: str
    edge_description: str
    confluence_factors: list[str]
    keywords: list[str]
    transcript_evidence: str
    start_timestamp: str
    end_timestamp: str
    source_section: str
    author_concept: bool
    confidence: Optional[float] = None
```

### Ingestion pipeline (`strategy_db/ingest.py`):
```python
def ingest_from_json(json_path: str, ...)  # Batch ingest from JSON
def ingest_single_chunk(chunk: StrategyChunk)  # Single chunk ingest
```

### To create a NEW ChromaDB collection:
1. Define `COLLECTION_NAME` in `strategy_db/config.py` (or add new constant)
2. Use `chromadb.PersistentClient(path=DB_DIR)` to get client
3. `client.get_or_create_collection(name, embedding_function=...)`
4. Add document + metadata via `collection.add(ids=[], documents=[], metadatas=[])`
5. Query via `collection.query(query_texts=[], n_results=top_k, where={...})`

### Known collections:
- `trading_strategies` — Primary strategy knowledge base
- `news_sentiment` — FinBERT-powered news sentiment (used by `sentiment_query` tool)

### Hybrid search:
- Uses BM25 sparse matching + ChromaDB dense similarity
- Abbreviation expansion for ICT/SMC terms (FVG→Fair Value Gap, CVD→Cumulative Volume Delta, etc.)
- Abbreviations defined in `strategy_db/config.py` `ABBREVIATIONS` dict

---

## 9. Configuration System

### 9a. Freqtrade JSON configs (`user_data/*.json`)
Primary config format for Freqtrade engine. Key config file: `user_data/config_market_ready.json`

**Structure:**
```json
{
    "max_open_trades": 1,
    "stake_currency": "USDT",
    "stake_amount": "unlimited",
    "tradable_balance_ratio": 0.5,
    "timeframe": "1h",
    "dry_run": true,
    "dry_run_wallet": 1000,
    "trading_mode": "futures",
    "margin_mode": "isolated",
    "strategy": "AroonMomentumEngine_Hybrid",
    "leverage": 3,
    "exchange": {
        "name": "binance",
        "key": "${FREQTRADE__EXCHANGE__KEY}",       // Env var substitution
        "secret": "${FREQTRADE__EXCHANGE__SECRET}",
        "pair_whitelist": ["BTC/USDT:USDT", ...],
        "pair_blacklist": ["BNB/.*"]
    },
    "pairlists": [{"method": "StaticPairList"}],
    "telegram": {
        "enabled": true,
        "token": "${TELEGRAM_TOKEN}",
        "chat_id": "${TELEGRAM_CHAT_ID}"
    },
    "api_server": {
        "enabled": true,
        "listen_ip_address": "127.0.0.1",
        "listen_port": 8080,
        "username": "${FREQTRADE_API_USER}",
        "password": "${FREQTRADE_API_PASSWORD}",
        "jwt_secret_key": "${FREQTRADE_API_JWT_SECRET}"
    }
}
```

Env var substitution: `${VAR_NAME}` syntax resolved by Freqtrade's `environment_vars_to_dict()`.

### 9b. Environment variables (`.env` / `.env.example`)

| Variable                  | Purpose                         | Default         |
|---------------------------|---------------------------------|-----------------|
| `DRY_RUN`                 | Paper trading toggle            | `true`          |
| `DRY_RUN_WALLET`          | Initial paper balance (USDT)    | `1000`          |
| `MAX_OPEN_TRADES`         | Maximum concurrent trades       | `5`             |
| `LEVERAGE`                | Default leverage                | `6`             |
| `BINANCE_API_KEY`         | Exchange API key               | —               |
| `BINANCE_API_SECRET`      | Exchange API secret            | —               |
| `TELEGRAM_TOKEN`          | Telegram bot token             | —               |
| `TELEGRAM_CHAT_ID`        | Telegram chat ID              | —               |
| `POSTGRES_USER`           | PostgreSQL username            | `freqtrade`     |
| `POSTGRES_PASSWORD`       | PostgreSQL password            | `freqtrade`     |
| `POSTGRES_DB`             | PostgreSQL database            | `freqtrade`     |
| `FREQTRADE__EXCHANGE__KEY`| Freqtrade env-override for key | —               |
| `FREQTRADE__EXCHANGE__SECRET`| Freqtrade env-override     | —               |
| `SHARED_CONFIG_DIR`       | Path to shared_config/         | `./shared_config` |
| `OLLAMA_BASE_URL`         | Ollama LLM endpoint            | `http://host.docker.internal:11434/v1` |

### 9c. Configuration class (`freqtrade/configuration/configuration.py`)
```python
class Configuration:
    def __init__(self, args: dict, runmode: RunMode | None = None)
    def get_config(self) -> Config
    @staticmethod
    def from_files(files: list[str]) -> dict    # Merge multiple JSON configs
    # Internal: load_from_files() -> environment_vars_to_dict() -> deep_merge_dicts()
```

### 9d. `shared_config/` JSON files (inter-component state)
| File                             | Producer          | Consumer               |
|----------------------------------|-------------------|------------------------|
| `circuit_breaker.json`           | Risk engine       | Alerter, UI            |
| `signal_bus_signals.json`        | RedisSignalBus     | Strategies, UI         |
| `signal_bus_pnl.json`           | RedisSignalBus     | Alerter, UI            |
| `signal_bus_risk.json`          | RedisSignalBus     | Alerter                |
| `signal_bus_commands.json`      | RedisSignalBus     | Engine                 |
| `agent_health.json`             | TradingAgents      | Alerter, UI            |
| `tradingagents_signal.json`     | TradingAgents      | Freqtrade              |
| `miroshark_brain.json`          | MiroFish           | Freqtrade              |
| `sentiment_signal.json`         | News pipeline     | Freqtrade              |
| `market_regime.json`            | HMM detector       | Strategies             |
| `hedge_state.json`              | Hedge logic        | UI                     |
| `leverage_signal.json`          | Leverage manager   | Freqtrade              |
| `alerter_config.json`           | Manual             | Alerter                |
| `alerter_state.json`            | Alerter            | Alerter (persistence)  |
| `orchestrator_signal.json`      | Orchestrator       | Engine                 |
| `orchestrator_result.json`      | Orchestrator       | UI                     |
| `llm_cache.json`                | LLM agent          | TradingAgents          |
| `outcome_feedback.json`         | Trade outcomes     | StrategyDB (outcome_sync) |

### 9e. Streamlit config (`.streamlit/config.toml`)
Standard Streamlit server config (theme, port, etc.)

---

## 10. Docker Service Registration

**Files:** `docker-compose.yml`, `docker-compose.unified.yml`, `start_local.sh`

### docker-compose.yml Profiles:
| Profile   | Services                                    |
|-----------|----------------------------------------------|
| `core`    | freqtrade, redis                             |
| `full`    | freqtrade, redis, postgres, mirofish, tradingagents |
| `dev`     | freqtrade, redis, postgres, streamlit, jupyter |

### Services and ports:
| Service          | Image/Build              | Ports                | Profiles    |
|------------------|--------------------------|----------------------|-------------|
| `freqtrade`      | freqtradeorg/freqtrade:stable | 127.0.0.1:8080  | core, full, dev |
| `redis`          | redis:7-alpine           | 127.0.0.1:6379      | core, full, dev |
| `postgres`       | postgres:16-alpine       | 127.0.0.1:5432      | full, dev   |
| `streamlit`      | python:3.12-slim         | 127.0.0.1:8501      | dev         |
| `mirofish`       | ../MiroFish (build)      | 127.0.0.1:3000, 5001 | full       |
| `tradingagents`  | ./TradingAgents (build)  | —                    | full        |
| `jupyter`        | jupyter/scipy-notebook   | 127.0.0.1:8888      | dev         |

### Volumes:
| Volume           | Mount Point                          |
|------------------|--------------------------------------|
| `./user_data`    | `/freqtrade/user_data` (freqtrade)   |
| `./shared_config`| `/freqtrade/shared_config:ro` (freqtrade) and `/freqtrade/shared_config` (tradingagents) |
| `./ui`           | `/app/ui` (streamlit)               |
| `redis_data`     | `/data` (redis)                     |
| `postgres_data`  | `/var/lib/postgresql/data` (postgres) |

### Network:
- `trading_net` — bridge network shared by all services

### start_local.sh services (non-Docker):
```bash
nexus-http      # NEXUS HTTP daemon (port 8080)
nexus-mcp       # NEXUS MCP enhanced server
strategy-kb     # Strategy-KB MCP server (ChromaDB)
finance-mcp     # Finance MCP server (yfinance)
streamlit       # Streamlit UI (port 8501)
```

### To add a new Docker service:
1. Add service definition to `docker-compose.yml` under appropriate profile
2. Mount `./shared_config:/app/shared_config` for inter-process communication
3. Connect to `trading_net` network
4. Add redis/postgres dependencies if needed
5. Add `start_service` entry in `start_local.sh` for local dev

### To add a new local process service:
```bash
# In start_local.sh:
start_service "my-service" "$PYTHON" "/path/to/my_service.py"
```

---

## Quick Reference: Fincept Component Integration Points

| Fincept Component       | Integration Point                   | How to Plug In                              |
|--------------------------|-------------------------------------|---------------------------------------------|
| New trading strategy     | `user_data/strategies/`             | Subclass `IStrategy`, override required methods |
| New exchange             | `freqtrade/exchange/<name>.py`     | Subclass `Exchange`, add to `SUPPORTED_EXCHANGES` |
| New data source          | `shared_config/<name>.json`        | Write JSON to shared_config, read in strategy |
| New MCP tool             | `strategy_db/mcp_server.py` or new server | Add `Tool()` + handler, register in `start_local.sh` |
| New signal channel       | `engine/signal_bus.py`              | Add to `CHANNELS` dict, add `publish_*` method |
| New UI page              | `ui/pages/<N>_<name>.py`          | Add to `pages` dict in `ui/app.py`          |
| New alert check          | `monitoring/alerter.py`            | Add `check_*()` method, toggle in `alerter_config.json` |
| New ChromaDB collection  | `strategy_db/config.py`            | Add `COLLECTION_NAME`, create in search.py  |
| New env variable         | `.env`                              | Add var, reference via `${VAR}` in JSON config |
| New Docker service       | `docker-compose.yml`               | Add service def, add profile, mount shared_config |