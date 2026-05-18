# Algotrading Intelligence System — Typed Execution Plan v2

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Transform ChromaDB from a static 474-vector knowledge base into a live adaptive intelligence layer that detects market regimes, retrieves strategy context, records trade outcomes, and improves future decisions through closed-loop feedback — all integrated with the existing VectorStrategy.

**Architecture:** 5-layer stack: (1) Regime Detection (HMM → rule fallback), (2) Regime-Conditioned Retrieval (ChromaDB queries weighted by outcome history), (3) Signal Fusion (technical + KB + sentiment), (4) Outcome Feedback (every trade updates chunk win rates), (5) Live Execution (Freqtrade with regime-adaptive parameters).

**Tech Stack:** Python 3.12, ChromaDB (all-MiniLM-L6-v2, cosine), Freqtrade 2026.5-dev, hmmlearn, numpy/pandas/talib, CryptoPanic API (free RSS), FinBERT (optional, rule-based fallback included).

**Baseline:** VectorStrategy +53.47% return, 1.55 Sharpe, 6.2% max DD, 74 trades, 74.3% WR (365d backtest).

---

## Current State

| Component | Status | Lines | Location |
|-----------|--------|-------|----------|
| VectorStrategy.py | Working, backtested | 381 | `user_data/strategies/VectorStrategy.py` |
| ChromaDB (474 vectors) | Working, 10 types | — | `strategy_db/chroma_db/` |
| ingest.py | Working, full rebuild | 79 | `strategy_db/ingest.py` |
| regime_query.py | Working, tested | 482 | `strategy_db/regime_query.py` |
| news_pipeline.py | Working, tested | 399 | `strategy_db/news_pipeline.py` |
| intelligence_layer.py | Working, tested | 373 | `strategy_db/intelligence_layer.py` |
| outcome_history.json | 5 sample trades | — | `strategy_db/outcome_history.json` |
| mcp_server.py | Working (5 tools) | 254 | `strategy_db/mcp_server.py` |

**Critical Gaps:**
- ~~Exit chunks: **8** (need 50+)~~ → **DONE: 63 exit chunks**
- ~~Position sizing chunks: **3** (need 30+)~~ → **DONE: 36 position_sizing chunks**
- HMM regime model: **Not built** (rule-based only)
- Outcome feedback loop: **Not connected** to Freqtrade trades
- Strategy agents: **Not wired** to VectorStrategy
- News data: **0 articles** (pipeline built but no data)

---

## Phase 1: Knowledge Base Expansion (Days 1-2)

**Objective:** Fill the exit and position sizing gaps in ChromaDB from 11 chunks to 80+.

### Task 1.1: Create exit strategy JSON chunks

**Objective:** Generate 50+ exit strategy chunks from existing source material and research.

**Files:**
- Create: `strategy_db/source_data/exit_strategies_chunks.json`
- Modify: `strategy_db/ingest.py` (add exit_strategies_chunks.json to ingestion)

**Step 1: Analyze current exit chunks in ChromaDB**

```bash
cd /home/roshan/Downloads/Algotrading
python3 strategy_db/chromadb_deep_analysis.py 2>&1 | grep "exit" | head -20
```

**Step 2: Write exit strategy chunks JSON**

Create a JSON file with 50+ exit strategy chunks. Each chunk has the same schema as existing chunks:
```json
{
  "setup_name": "Trailing Stop — ATR Multiple Exit",
  "setup_type": "exit",
  "market_condition": "trending",
  "strategy_style": "swing",
  "keywords": "trailing stop, ATR, dynamic exit, trend following",
  "description": "Exit using a trailing stop set at 2-3x ATR from the current price. In trending markets, this allows the trade to breathe while protecting profits. For longs, trail below the low; for shorts, trail above the high. Tighten by 0.5x ATR when volume drops below 50% of average, signaling the move is exhausting."
}
```

Categories to cover (minimum 5 each):
- Trailing stops (ATR-based, %, Chandelier, volatility-adjusted)
- Time-based exits (session close, day-of-week, N-bar exit)
- Target-based exits (opposing liquidity, round numbers, Fibonacci extensions)
- Signal-based exits (divergence, overbought/oversold, candlestick patterns)
- Risk management exits (breakeven move, risk-to-zero, daily max loss)
- Mean reversion exits (Bollinger %b extremes, RSI reversal, VWAP reversion)

**Step 3: Verify JSON validity**

```bash
python3 -c "import json; data=json.load(open('strategy_db/source_data/exit_strategies_chunks.json')); print(f'Chunks: {len(data)}'); types=set(c['setup_type'] for c in data); print(f'Types: {types}')"
```

**Step 4: Add to ingest.py**

Modify `strategy_db/ingest.py` to also load and ingest `exit_strategies_chunks.json`.

**Step 5: Run ingestion**

```bash
cd /home/roshan/Downloads/Algotrading
python3 strategy_db/ingest.py
```

**Step 6: Verify exit chunk count increased**

```bash
python3 -c "from strategy_db.regime_query import _get_collection; c=_get_collection(); r=c.get(include=['metadatas']); from collections import Counter; t=Counter(m.get('setup_type','?') for m in r['metadatas']); print(dict(t)); assert t.get('exit',0) >= 50, f'Only {t.get(\"exit\",0)} exit chunks'"
```

**Step 7: Commit**

```bash
git add strategy_db/source_data/exit_strategies_chunks.json strategy_db/ingest.py
git commit -m "feat: add 50+ exit strategy chunks to ChromaDB"
```

### Task 1.2: Create position sizing chunks

**Objective:** Generate 30+ position sizing and risk management chunks.

**Files:**
- Create: `strategy_db/source_data/position_sizing_chunks.json`
- Modify: `strategy_db/ingest.py`

Same process as Task 1.1. Categories:
- Fixed fractional sizing (1-2% risk per trade)
- Kelly criterion (optimal f, half-Kelly, fractional Kelly)
- Volatility-adjusted sizing (ATR-based, inverse volatility)
- Drawdown-adjusted (reduce size after losses, circuit breaker)
- Regime-based sizing (trending=larger, volatile=smaller)
- Account-level risk (daily max, weekly max, correlation limits)

**Verification:** `position_sizing` count >= 30 after ingestion.

### Task 1.3: Create session/time filter chunks

**Objective:** Generate 20+ kill zone / session filter chunks.

**Files:**
- Create: `strategy_db/source_data/session_filter_chunks.json`
- Modify: `strategy_db/ingest.py`

Categories: London session, NY session, Asian session, kill zones, overlap windows, low-volume avoid filters, day-of-week effects, FOMC/news filters, weekend gaps.

**Verification:** `filter` count >= 100 after ingestion (currently 83, adding 20+).

---

## Phase 2: HMM Regime Detection (Days 2-3)

**Objective:** Replace rule-based regime detection with Gaussian HMM that detects trend/range/volatile from OHLCV features.

### Task 2.1: Install hmmlearn and build regime model

**Objective:** Train a 4-state Gaussian HMM on BTC 1h features (returns, volatility, ADX).

**Files:**
- Create: `strategy_db/regime_detector_hmm.py`

**Step 1: Install hmmlearn**

```bash
cd /home/roshan/Downloads/Algotrading
.venv/bin/pip install hmmlearn
```

**Step 2: Write HMM regime detector**

File: `strategy_db/regime_detector_hmm.py`

```python
"""
Gaussian HMM Regime Detector.
4 states: trending_up, trending_down, ranging, volatile.
Trained on BTC 1h features (returns, realized vol, ADX).
"""
import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from pathlib import Path
import joblib
import json

REGIME_LABELS = {0: "ranging", 1: "trending_up", 2: "trending_down", 3: "volatile"}

class HMMRegimeDetector:
    def __init__(self, n_states=4, model_path=None):
        self.n_states = n_states
        self.model_path = model_path or str(Path(__file__).parent / "regime_hmm.pkl")
        self.model = None
        self.feature_means = None
        self.feature_stds = None

    def _compute_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute OHLCV features for HMM input."""
        df = df.copy()
        df["returns"] = df["close"].pct_change()
        df["realized_vol"] = df["returns"].rolling(20).std()
        df["high_low_range"] = (df["high"] - df["low"]) / df["close"]
        df["volume_change"] = df["volume"].pct_change()
        # EMA slope (trend direction proxy)
        df["ema_21"] = df["close"].ewm(span=21).mean()
        df["ema_slope"] = df["ema_21"].pct_change()
        df = df.dropna()
        return df

    def train(self, df: pd.DataFrame, save=True):
        """Train HMM on OHLCV data."""
        feat_df = self._compute_features(df)
        features = ["returns", "realized_vol", "high_low_range", "ema_slope"]
        X = feat_df[features].values

        # Standardize
        self.feature_means = X.mean(axis=0)
        self.feature_stds = X.std(axis=0)
        X_scaled = (X - self.feature_means) / self.feature_stds

        # Train
        self.model = GaussianHMM(
            n_components=self.n_states,
            covariance_type="full",
            n_iter=200,
            random_state=42
        )
        self.model.fit(X_scaled)

        # Map states to labels by examining means
        self._map_states(X_scaled, feat_df)

        if save:
            self.save()

        return self

    def _map_states(self, X_scaled, feat_df):
        """Map HMM states to regime labels by examining emission means."""
        means = self.model.means_
        # Column 0=returns, 1=vol, 2=range, 3=slope
        # Sort by (slope, -vol):
        #   trending_up: high slope, low vol
        #   trending_down: low slope, low vol
        #   volatile: high vol
        #   ranging: near-zero slope, low vol

        # Use returns mean as proxy for direction
        for i in range(self.n_states):
            ret_mean = means[i][0]  # returns
            vol_mean = means[i][1]  # volatility
            slope_mean = means[i][3]  # slope

            if vol_mean > 0.5:  # high volatility state
                REGIME_LABELS[i] = "volatile"
            elif slope_mean > 0.1:  # positive trend
                REGIME_LABELS[i] = "trending_up"
            elif slope_mean < -0.1:  # negative trend
                REGIME_LABELS[i] = "trending_down"
            else:
                REGIME_LABELS[i] = "ranging"

    def predict(self, df: pd.DataFrame) -> tuple:
        """Predict regime for each candle. Returns (regimes, metrics)."""
        if self.model is None:
            self.load()

        feat_df = self._compute_features(df)
        features = ["returns", "realized_vol", "high_low_range", "ema_slope"]
        X = feat_df[features].values
        X_scaled = (X - self.feature_means) / self.feature_stds

        states = self.model.predict(X_scaled)
        regime_labels = [REGIME_LABELS[s] for s in states]
        probabilities = self.model.predict_proba(X_scaled)

        current_regime = regime_labels[-1]
        current_probs = {REGIME_LABELS[i]: round(prob, 3)
                        for i, prob in enumerate(probabilities[-1])}

        metrics = {
            "regime": current_regime,
            "regime_probs": current_probs,
            "returns_20": round(float(feat_df["returns"].iloc[-20:].mean()), 6) if len(feat_df) >= 20 else 0,
            "volatility_20": round(float(feat_df["realized_vol"].iloc[-1]), 6),
            "atr_pct": round(float(feat_df["high_low_range"].iloc[-1]), 6),
            "ema_slope": round(float(feat_df["ema_slope"].iloc[-1]), 6)
        }

        return current_regime, metrics

    def save(self):
        """Save model and preprocessing params."""
        joblib.dump({
            "model": self.model,
            "means": self.feature_means,
            "stds": self.feature_stds,
            "labels": REGIME_LABELS
        }, self.model_path)

    def load(self):
        """Load saved model."""
        data = joblib.load(self.model_path)
        self.model = data["model"]
        self.feature_means = data["means"]
        self.feature_stds = data["stds"]
        REGIME_LABELS.update(data["labels"])
```

**Step 3: Train on BTC data**

```bash
cd /home/roshan/Downloads/Algotrading
.venv/bin/python3 -c "
import pandas as pd
from strategy_db.regime_detector_hmm import HMMRegimeDetector

# Load BTC 1h data
df = pd.read_feather('user_data/data/binance/futures/BTC_USDT_USDT-1h-futures.feather')
detector = HMMRegimeDetector()
detector.train(df)
regime, metrics = detector.predict(df)
print(f'Current regime: {regime}')
print(f'Metrics: {metrics}')
print(f'Model saved to: {detector.model_path}')
"
```

**Step 4: Verify model file exists**

```bash
ls -la strategy_db/regime_hmm.pkl
```

**Step 5: Commit**

```bash
git add strategy_db/regime_detector_hmm.py strategy_db/regime_hmm.pkl
git commit -m "feat: add HMM regime detector trained on BTC 1h data"
```

### Task 2.2: Integrate HMM detector into intelligence_layer.py

**Objective:** Replace RegimeDetector (rule-based) with HMMRegimeDetector.

**Files:**
- Modify: `strategy_db/intelligence_layer.py` (swap RegimeDetector import)

**Step 1:** In `intelligence_layer.py`, change import from:
```python
from regime_query import RegimeAwareQueryEngine, RegimeDetector, OutcomeTracker
```
to:
```python
from regime_query import RegimeAwareQueryEngine, OutcomeTracker
from regime_detector_hmm import HMMRegimeDetector
```

**Step 2:** In `IntelligenceLayer.__init__`, replace:
```python
self.regime_detector = RegimeDetector()
```
with:
```python
self.regime_detector = HMMRegimeDetector(model_path=str(Path(__file__).parent / "regime_hmm.pkl"))
try:
    self.regime_detector.load()
except FileNotFoundError:
    self.regime_detector = RegimeDetector()  # Fallback to rule-based
```

**Step 3:** Test:

```bash
cd /home/roshan/Downloads/Algotrading
.venv/bin/python3 strategy_db/intelligence_layer.py --regime ranging --pair BTC/USDT 2>&1 | head -20
```

**Step 4: Commit**

```bash
git add strategy_db/intelligence_layer.py
git commit -m "feat: integrate HMM regime detector into intelligence layer"
```

---

## Phase 3: Outcome Feedback Loop (Days 3-4)

**Objective:** Wire every VectorStrategy trade to automatically update outcome_history.json, creating a closed feedback loop.

### Task 3.1: Add VDBMixin to VectorStrategy for outcome recording

**Objective:** After each trade closes, record which KB chunks informed it and whether it was profitable.

**Files:**
- Modify: `user_data/strategies/VectorStrategy.py`

**Step 1:** Add imports and outcome recorder init at the top of VectorStrategy class:

```python
import json
from pathlib import Path
from datetime import datetime

# Outcome feedback — records which KB chunks informed each trade
VDB_OUTCOME_PATH = Path(__file__).parent.parent.parent / "strategy_db" / "outcome_history.json"
```

**Step 2:** Add `custom_exit` outcome recording. Modify `custom_exit` to record trade outcome before returning:

```python
def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
    # ... existing logic ...

    # Record outcome for feedback loop
    try:
        self._record_outcome(pair, trade, current_profit, current_rate)
    except Exception:
        pass  # Never let outcome recording crash the strategy

    return None  # or existing return value
```

**Step 3:** Add `_record_outcome` method:

```python
def _record_outcome(self, pair, trade, profit_pct, current_rate):
    """Record trade outcome to feedback loop."""
    # Determine regime at trade time (use cached value or default)
    regime = getattr(self, '_current_regime', 'ranging')

    # Which signals triggered this trade
    entry_tag = trade.enter_tag or "unknown"
    setup_names = self._get_setup_names(entry_tag)
    is_win = profit_pct > 0
    r_multiple = profit_pct / abs(trade.stop_loss_pct) if trade.stop_loss_pct else profit_pct

    outcome = {
        "trade_id": f"{pair}_{trade.open_date.strftime('%Y%m%d_%H%M')}",
        "pair": pair,
        "timestamp": datetime.utcnow().isoformat(),
        "regime": regime,
        "setup_names": setup_names,
        "pnl_pct": round(profit_pct * 100, 2),
        "r_multiple": round(r_multiple, 2),
        "is_win": is_win,
        "strategy_type": "VectorStrategy",
        "dominant_signal": entry_tag,
        "open_rate": trade.open_rate,
        "close_rate": current_rate,
        "trade_duration_hours": (datetime.utcnow() - trade.open_date).total_seconds() / 3600
    }

    # Append to outcome history
    path = VDB_OUTCOME_PATH
    if path.exists():
        with open(path) as f:
            history = json.load(f)
    else:
        history = {"trades": [], "chunk_stats": {}}

    history["trades"].append(outcome)

    with open(path, 'w') as f:
        json.dump(history, f, indent=2, default=str)

def _get_setup_names(self, entry_tag):
    """Map freqtrade entry tags to ChromaDB setup names."""
    tag_to_setups = {
        "vector_long": ["BB Squeeze Breakout", "Mean Reversion %b Long", "EMA Alignment Trend Following", "3SD Expansion Long", "Key Level Support Rejection"],
        "vector_short": ["BB Squeeze Breakdown", "Mean Reversion %b Short", "EMA Alignment Short Following", "3SD Expansion Short", "Key Level Resistance Rejection"],
    }
    return tag_to_setups.get(entry_tag, [entry_tag])
```

**Step 4:** In `populate_indicators`, add regime detection caching:

```python
def populate_indicators(self, dataframe, metadata):
    # ... existing indicators ...

    # Cache current regime for outcome recording
    try:
        from strategy_db.regime_detector_hmm import HMMRegimeDetector
        detector = HMMRegimeDetector(model_path=str(Path(__file__).parent.parent.parent / "strategy_db" / "regime_hmm.pkl"))
        detector.load()
        regime, metrics = detector.predict(dataframe)
        self._current_regime = regime
    except Exception:
        self._current_regime = "ranging"

    return dataframe
```

**Step 5: Test with existing backtest**

```bash
cd /home/roshan/Downloads/Algotrading
.venv/bin/freqtrade backtesting \
  --config user_data/config_vector_backtest.json \
  --strategy VectorStrategy \
  --timerange 20250516-20260507 \
  --timeframe 1h \
  --datadir user_data/data/binance \
  --export trades 2>&1 | tail -30
```

**Step 6: Verify outcome_history.json was updated**

```bash
python3 -c "import json; h=json.load(open('strategy_db/outcome_history.json')); print(f'Trades: {len(h[\"trades\"])}')"
```

**Step 7: Commit**

```bash
git add user_data/strategies/VectorStrategy.py
git commit -m "feat: add outcome feedback loop to VectorStrategy"
```

### Task 3.2: Wire outcome tracker to regime query engine

**Objective:** When `IntelligenceLayer.analyze()` is called, use outcome_history.json to weight chunk recommendations.

**Files:**
- Modify: `strategy_db/regime_query.py` (already has OutcomeTracker)
- Verify: outcome_tracker reads from same file VectorStrategy writes to

**Step 1:** Verify the path alignment:

```bash
# OutcomeTracker default path should match VectorStrategy's VDB_OUTCOME_PATH
python3 -c "
from strategy_db.regime_query import OutcomeTracker
ot = OutcomeTracker()
print(f'OutcomeTracker path: {ot.db_path}')
print(f'File exists: {ot.db_path.exists()}')
print(f'Trades: {len(ot.history[\"trades\"])}')
"
```

**Step 2:** Run regime query with outcome-weighted scoring:

```bash
cd /home/roshan/Downloads/Algotrading
python3 strategy_db/intelligence_layer.py --regime trending_up --pair BTC/USDT 2>&1 | head -30
```

**Step 3: Verify outcome scores appear** (should show `outcome=N/A` for chunks with no history, or `outcome=XX%` for chunks with recorded trades).

**Step 4: Commit**

```bash
git add strategy_db/regime_query.py
git commit -m "feat: outcome-weighted chunk scoring in regime queries"
```

---

## Phase 4: News Sentiment Pipeline (Days 4-5)

**Objective:** Stream crypto news from CryptoPanic, embed with FinBERT/rule-based sentiment, store in ChromaDB, query alongside strategy context.

### Task 4.1: Schedule news fetching cron job

**Objective:** Run news fetch every 30 minutes via Hermes cronjob.

**Step 1: Test CryptoPanic fetch manually**

```bash
cd /home/roshan/Downloads/Algotrading
python3 strategy_db/news_pipeline.py --fetch 2>&1 | head -20
```

**Step 2: Create a fetch script (lightweight, no model dependency)**

Create: `strategy_db/fetch_news.sh`

```bash
#!/bin/bash
cd /home/roshan/Downloads/Algotrading
.venv/bin/python3 strategy_db/news_pipeline.py --fetch 2>&1 | logger -t news_fetch
```

```bash
chmod +x strategy_db/fetch_news.sh
```

**Step 3: Schedule with Hermes cronjob** (30-minute interval)

```bash
# This creates a cron job that calls the fetch script every 30 minutes
```

**Step 4: Verify news collection after 1 hour**

```bash
python3 strategy_db/news_pipeline.py --summary 2>&1
```

**Step 5: Commit**

```bash
git add strategy_db/fetch_news.sh
git commit -m "feat: add news fetching script for scheduled runs"
```

### Task 4.2: Wire news sentiment into intelligence layer

**Objective:** The IntelligenceLayer already has news integration. Verify it works end-to-end.

**Step 1: Test full intelligence layer with news**

```bash
cd /home/roshan/Downloads/Algotrading
python3 strategy_db/intelligence_layer.py --regime volatile --pair BTC/USDT 2>&1 | head -40
```

**Step 2: Verify sentiment section appears** (even with 0 articles, should show empty metrics, not crash).

**Step 3: Commit** (if changes were needed).

---

## Phase 5: Regime-Adaptive VectorStrategyV2 (Days 5-7)

**Objective:** Build VectorStrategyV2 that uses intelligence layer for regime-adaptive parameters.

### Task 5.1: Create VectorStrategyV2 with regime-adaptive parameters

**Objective:** VectorStrategyV2 uses IntelligenceLayer to detect regime and adjust parameters per-trade.

**Files:**
- Create: `user_data/strategies/VectorStrategyV2.py`

**Step 1:** Create the new strategy file. Key changes from V1:

```python
"""
VectorStrategyV2 — Regime-Adaptive ChromaDB Intelligence Strategy
=================================================================
Differences from V1:
1. HMM regime detection (4 states) instead of static parameters
2. Regime-adaptive parameter adjustment (from IntelligenceLayer._compute_regime_parameters)
3. Outcome feedback recording after each trade
4. Session filter (kill zones from ChromaDB knowledge)
5. CVD divergence confirmation (from ChromaDB knowledge)
"""
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
# ... imports ...
from strategy_db.intelligence_layer import IntelligenceLayer
from strategy_db.regime_detector_hmm import HMMRegimeDetector

class VectorStrategyV2(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    startup_candle_count = 200

    # Base parameters (will be overridden by regime)
    stoploss = -0.06
    trailing_stop = True
    trailing_stop_positive = 0.025
    trailing_stop_positive_offset = 0.04
    trailing_only_offset_is_reached = True

    # Same ROI structure as V1
    minimal_roi = {"0": 0.15, "60": 0.08, "240": 0.04, "720": 0.02}

    # Regime-adaptive parameters (tuned per regime)
    # These are populated by IntelligenceLayer in populate_indicators
    _regime_params = {}

    def __init__(self, config=None):
        super().__init__(config)
        self.intel = IntelligenceLayer()
        self.hmm = HMMRegimeDetector(model_path=str(Path(__file__).parent.parent.parent / "strategy_db" / "regime_hmm.pkl"))
        try:
            self.hmm.load()
        except FileNotFoundError:
            self.hmm = None

    def populate_indicators(self, dataframe, metadata):
        # Detect regime from last 200 candles
        if self.hmm:
            regime, metrics = self.hmm.predict(dataframe)
        else:
            regime = "ranging"
            metrics = {}

        self._current_regime = regime

        # Get regime-adaptive parameters from IntelligenceLayer
        params = self.intel._compute_regime_parameters(
            regime, metrics, [], {}
        )
        self._regime_params = params

        # Compute all V1 indicators
        # ... (same as V1: BB, EMA, RSI, volume, ATR, VWAP, pivots)

        # ADD: CVD divergence concept from ChromaDB
        # CVD = cumulative volume delta (proxy using close vs open)
        dataframe["cvd"] = (
            (dataframe["close"] - dataframe["open"]) * dataframe["volume"]
        ).cumsum()
        dataframe["cvd_sma"] = dataframe["cvd"].rolling(20).mean()

        # ADD: Session filter (UTC hours → kill zones)
        dataframe["hour"] = pd.to_datetime(dataframe["date"]).dt.hour
        # London kill zone: 7-9 UTC, NY kill zone: 13-16 UTC
        dataframe["kill_zone"] = (
            (dataframe["hour"] >= 7) & (dataframe["hour"] <= 9) |
            (dataframe["hour"] >= 13) & (dataframe["hour"] <= 16)
        ).astype(int)

        # Store regime per candle for outcome tracking
        dataframe["regime"] = regime

        return dataframe

    def populate_entry_trend(self, dataframe, metadata):
        p = self._regime_params  # Regime-adaptive parameters

        # Same 5 signals as V1, but with regime-adjusted thresholds
        # Signal 1: BBands squeeze with regime-adjusted threshold
        squeeze_long = (
            (dataframe["bb_width"] < p.get("bb_squeeze_threshold", 0.06)) &
            (dataframe["bb_width"].shift(1) < dataframe["bb_width"]) &
            (dataframe["close"] > dataframe["bb_middleband"]) &
            (dataframe["volume_ratio"] > p.get("volume_multiplier", 1.5)) &
            (dataframe["kill_zone"] == 1)  # Only trade in kill zones
        )

        # Signal 2: Mean reversion
        mean_rev_long = (
            (dataframe["bb_pctb"] < p.get("bb_pct_lower", 0.4)) &
            (dataframe["close"] > dataframe["bb3_lower"]) &
            (dataframe["rsi"] < p.get("rsi_lower", 35)) &
            (dataframe["close"] > dataframe["vwap"])
        )

        # Signal 3: EMA alignment
        ema_long = (
            (dataframe["ema_fast"] > dataframe["ema_medium"]) &
            (dataframe["close"] > dataframe["ema_fast"]) &
            (dataframe["ema_medium"] > dataframe["ema_200"]) &
            (dataframe["rsi"] > 35) &
            (dataframe["rsi"] < p.get("rsi_lower", 35) + 30)
        )

        # Signal 4: CVD divergence (NEW — ChromaDB knowledge)
        cvd_long = (
            (dataframe["cvd"] > dataframe["cvd_sma"]) &  # CVD trending up
            (dataframe["close"] > dataframe["open"])  # Bullish candle
        ).astype(int)

        # Signal 5: Key level rejection
        key_level_long = (
            (dataframe["dist_to_support"] < 1.0) &
            (dataframe["close"] > dataframe["open"]) &
            (dataframe["volume_ratio"] > 1.2) &
            (dataframe["rsi"] > 35) &
            (dataframe["rsi"] < 65)
        )

        long_signals = [
            squeeze_long.astype(int),
            mean_rev_long.astype(int),
            ema_long.astype(int),
            cvd_long,
            key_level_long.astype(int),
        ]
        long_score = sum(long_signals)

        dataframe.loc[
            (long_score >= p.get("confluence_min", 2)) & (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"]
        ] = (1, f"v2_long_{self._current_regime}")

        # Mirror for shorts (similar adjustments)
        # ... (same pattern as V1 with regime params)

        return dataframe

    # custom_stoploss uses regime-adaptive ATR multiplier
    def custom_stoploss(self, pair, trade, current_time, current_rate, profit_after_fee, after_fill, **kwargs):
        p = self._regime_params
        base_sl = p.get("stoploss", -0.06)
        # ... (ATR-based dynamic stop with regime adjustment)
        return base_sl

    # custom_exit with outcome recording
    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        # ... (same beacon target logic as V1)
        # PLUS: Record outcome
        self._record_outcome(pair, trade, current_profit, current_rate)
        return None
```

**Step 2: Backtest V2**

```bash
cd /home/roshan/Downloads/Algotrading
# Create config for V2 (same as V1 but with strategy name)
cp user_data/config_vector_backtest.json user_data/config_v2_backtest.json
# Edit strategy name to VectorStrategyV2

.venv/bin/freqtrade backtesting \
  --config user_data/config_v2_backtest.json \
  --strategy VectorStrategyV2 \
  --timerange 20250516-20260507 \
  --timeframe 1h \
  --datadir user_data/data/binance \
  --export trades 2>&1 | tail -40
```

**Step 3: Compare V1 vs V2 results**

```bash
echo "=== V1 Baseline ==="
echo "Return: +53.47%, Sharpe: 1.55, Max DD: 6.2%, Trades: 74, WR: 74.3%"
echo ""
echo "=== V2 Results ==="
# Extract from backtest output
```

**Step 4: Commit**

```bash
git add user_data/strategies/VectorStrategyV2.py user_data/config_v2_backtest.json
git commit -m "feat: VectorStrategyV2 with regime-adaptive parameters"
```

### Task 5.2: Hyperopt V2 for regime-specific parameters

**Objective:** Optimize regime-specific parameter ranges.

**Step 1: Run quick hyperopt (60 epochs, 1h trades)**

```bash
cd /home/roshan/Downloads/Algotrading
.venv/bin/freqtrade hyperopt \
  --config user_data/config_v2_backtest.json \
  --strategy VectorStrategyV2 \
  --hyperopt-loss SharpeHyperOptLoss \
  --epochs 60 \
  --spaces buy sell roi stoploss \
  --timerange 20251101-20260507 \
  --timeframe 1h \
  --datadir user_data/data/binance 2>&1 | tail -40
```

**Step 2: Review best parameters and update V2 defaults**

**Step 3: Commit optimized parameters**

---

## Phase 6: MCP Server Upgrade (Day 7)

**Objective:** Upgrade strategy-kb MCP server to expose all new capabilities (regime detection, outcome feedback, news sentiment).

### Task 6.1: Add new MCP tools

**Objective:** Add 4 new tools to strategy-kb MCP server.

**Files:**
- Modify: `strategy_db/mcp_server.py`

New tools to add:

1. `detect_regime` — Takes OHLCV data, returns current regime + probabilities
2. `get_regime_context` — Takes regime name, returns top strategy chunks + params
3. `record_trade_outcome` — Records a trade outcome
4. `get_sentiment_summary` — Returns aggregated sentiment for a pair

**Step 1:** Read current MCP server:

```bash
head -50 strategy_db/mcp_server.py
```

**Step 2:** Add new tool handlers. Each tool follows the existing pattern:

```python
@server.call_tool()
async def detect_regime(arguments: dict) -> list[types.TextContent]:
    """Detect current market regime from OHLCV data."""
    # Load HMM model, predict, return regime + metrics
    ...

@server.call_tool()
async def get_regime_context(arguments: dict) -> list[types.TextContent]:
    """Get strategy context for a market regime."""
    regime = arguments.get("regime", "ranging")
    pair = arguments.get("pair", "BTC/USDT")
    engine = RegimeAwareQueryEngine()
    context = engine.get_regime_strategy_context(regime, top_k=10)
    return [types.TextContent(type="text", text=context)]

@server.call_tool()
async def record_trade_outcome(arguments: dict) -> list[types.TextContent]:
    """Record a trade outcome for the feedback loop."""
    tracker = OutcomeTracker()
    result = tracker.record_trade(
        trade_id=arguments["trade_id"],
        pair=arguments["pair"],
        regime=arguments["regime"],
        setup_names=arguments.get("setup_names", []),
        pnl_pct=arguments["pnl_pct"],
        r_multiple=arguments["r_multiple"],
        is_win=arguments["is_win"],
        strategy_type=arguments.get("strategy_type", "VectorStrategy"),
        dominant_signal=arguments.get("dominant_signal", "")
    )
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

@server.call_tool()
async def get_sentiment_summary(arguments: dict) -> list[types.TextContent]:
    """Get aggregated sentiment for a pair."""
    embedder = FinBERTNewsEmbedder()
    summary = embedder.get_sentiment_summary(
        pair=arguments.get("pair", "BTC"),
        hours=arguments.get("hours", 24)
    )
    return [types.TextContent(type="text", text=json.dumps(summary, indent=2))]
```

**Step 3:** Register tool list:

```python
@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ... existing 5 tools ...
        types.Tool(name="detect_regime", description="Detect market regime from OHLCV data", inputSchema={...}),
        types.Tool(name="get_regime_context", description="Get strategy context for a regime", inputSchema={...}),
        types.Tool(name="record_trade_outcome", description="Record trade outcome for feedback", inputSchema={...}),
        types.Tool(name="get_sentiment_summary", description="Get aggregated sentiment", inputSchema={...}),
    ]
```

**Step 4:** Test MCP server:

```bash
cd /home/roshan/Downloads/Algotrading
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 strategy_db/mcp_server.py 2>&1 | python3 -m json.tool | head -30
```

**Step 5: Commit**

```bash
git add strategy_db/mcp_server.py
git commit -m "feat: add 4 new MCP tools (regime, outcome, sentiment)"
```

---

## Phase 7: Verification & Testing (Day 7)

**Objective:** Run comprehensive tests to verify all components work end-to-end.

### Task 7.1: Integration test — full pipeline

**Objective:** Verify: data → regime → KB query → sentiment → outcome recording all works.

```bash
cd /home/roshan/Downloads/Algotrading
.venv/bin/python3 -c "
from strategy_db.intelligence_layer import IntelligenceLayer
import pandas as pd

# Load BTC data
df = pd.read_feather('user_data/data/binance/futures/BTC_USDT_USDT-1h-futures.feather')

# Run full analysis
intel = IntelligenceLayer()
report = intel.analyze(df.tail(200), pair='BTC/USDT', timeframe='1h')

print('=== FULL INTEGRATION TEST ===')
print(f'Regime: {report[\"regime\"][\"label\"]}')
print(f'Confidence: {report[\"signal_confidence\"]}')
print(f'KB chunks returned: {len(report[\"knowledge_base\"][\"top_chunks\"])}')
print(f'Recommended stoploss: {report[\"recommended_params\"][\"stoploss\"]}')
print(f'Recommended confluence_min: {report[\"recommended_params\"][\"confluence_min\"]}')
print(f'Outcome feedback: {len(report[\"outcome_feedback\"][\"best_chunks\"])} chunks with history')
print('PASS: Full pipeline works')
"
```

### Task 7.2: Backtest comparison — V1 vs V2

```bash
cd /home/roshan/Downloads/Algotrading

echo "=== V1 BACKTEST ==="
.venv/bin/freqtrade backtesting \
  --config user_data/config_vector_backtest.json \
  --strategy VectorStrategy \
  --timerange 20250516-20260507 \
  --timeframe 1h \
  --datadir user_data/data/binance 2>&1 | grep -E "TOTAL|profit|Sharpe|Drawdown|trades"

echo "=== V2 BACKTEST ==="
.venv/bin/freqtrade backtesting \
  --config user_data/config_v2_backtest.json \
  --strategy VectorStrategyV2 \
  --timerange 20250516-20260507 \
  --timeframe 1h \
  --datadir user_data/data/binance 2>&1 | grep -E "TOTAL|profit|Sharpe|Drawdown|trades"
```

### Task 7.3: Outcome feedback loop test

```bash
cd /home/roshan/Downloads/Algotrading
.venv/bin/python3 -c "
from strategy_db.regime_query import OutcomeTracker
ot = OutcomeTracker()
summary = ot.get_regime_summary()
print('=== OUTCOME FEEDBACK LOOP ===')
for regime, data in summary.items():
    print(f'  {regime}: WR={data[\"win_rate\"]:.1%}, pnl={data[\"avg_pnl\"]:+.2f}%, trades={data[\"total_trades\"]}')

# Verify chunk stats exist
for name, stats in list(ot.history['chunk_stats'].items())[:3]:
    wr = stats['wins'] / stats['total_trades'] if stats['total_trades'] > 0 else 0
    print(f'  Chunk \"{name}\": WR={wr:.1%}, trades={stats[\"total_trades\"]}')
print('PASS: Outcome feedback loop working')
"
```

---

## Rollback Triggers

| Metric | V1 Baseline | V2 Minimum | Rollback If |
|--------|-------------|-------------|-------------|
| Total Return | +53.47% | > +45% | Below +35% |
| Sharpe Ratio | 1.55 | > 1.3 | Below 1.0 |
| Max Drawdown | 6.2% | < 10% | Above 15% |
| Win Rate | 74.3% | > 65% | Below 55% |
| Trade Count | 74 | > 50 | Below 30 |
| Avg Trade Duration | — | < 48h | Too stale |

---

## Implementation Priority (if time-constrained)

| Priority | Phase | Impact | Effort |
|----------|-------|--------|--------|
| P0 | Phase 3: Outcome Feedback | HIGH — closes the loop | LOW — 1 file change |
| P0 | Phase 5: VectorStrategyV2 | HIGH — regime adaptation | MEDIUM — 200 lines |
| P1 | Phase 2: HMM Regime Detection | HIGH — replaces rules | MEDIUM — 150 lines + training |
| P1 | Phase 1: KB Expansion | MEDIUM — more exit chunks | MEDIUM — data entry |
| P2 | Phase 4: News Pipeline | LOW — nice to have | LOW — already built |
| P2 | Phase 6: MCP Upgrade | LOW — for external tools | LOW — 4 tool functions |

---

## File Tree After Completion

```
strategy_db/
├── chroma_db/                          # 474+ vectors (550+ after expansion)
├── source_data/
│   ├── exit_strategies_chunks.json     # NEW: 50+ exit chunks
│   ├── position_sizing_chunks.json     # NEW: 30+ position sizing chunks
│   └── session_filter_chunks.json      # NEW: 20+ session filter chunks
├── ingest.py                           # MODIFIED: includes new data
├── schema.py                           # Existing schema
├── config.py                           # Existing config
├── query.py                            # Existing query
├── search.py                           # Existing search
├── deep_dive.py                        # Existing analysis
├── source_analysis.py                  # Existing
├── chromadb_deep_analysis.py           # Existing
├── chromadb_content_sample.py          # Existing
├── gcode_bridge.py                     # Existing CLI
├── regime_query.py                     # Working: regime-conditioned queries
├── regime_detector_hmm.py              # NEW: HMM regime detector
├── regime_hmm.pkl                      # NEW: trained HMM model
├── news_pipeline.py                    # Working: FinBERT news pipeline
├── intelligence_layer.py               # Working: unified 5-layer orchestrator
├── outcome_history.json                # Growing: trade outcome feedback
├── mcp_server.py                       # MODIFIED: 9 tools (was 5)
├── fetch_news.sh                       # NEW: cron news fetcher
├── to_config.py                        # Existing
├── runtime_bridge.py                   # Existing
└── strategy_agents.py                  # Existing: multi-agent debate

user_data/strategies/
├── VectorStrategy.py                   # Existing V1 (unchanged)
└── VectorStrategyV2.py                 # NEW: regime-adaptive with feedback loop

user_data/
├── config_vector_backtest.json         # V1 config
└── config_v2_backtest.json             # NEW: V2 config
```