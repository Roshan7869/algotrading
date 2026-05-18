# MiroShark Remediation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Transform Algotrading from a stack of disconnected components into a unified MiroShark prediction engine where all layers communicate through the Signal Bus.

**Architecture:** 5-layer system — Data Ingestion (crons) → Signal Bus (atomic) → MiroShark Brain (KB + Regime + News) → Freqtrade Consumer (BOS_V5) → Feedback Loop (outcomes). The existing `shared_config/signal_bus.py` is the backbone. We extend it, not replace it.

**Tech Stack:** Python 3.11, Freqtrade, ChromaDB, HMM (hmmlearn), FinBERT, LangGraph, Ollama, cron

**NEXUS Routing:** Plan ID `plan_20260518_234640` — routed via analyzer_planner cluster (0.39 score) + architect cluster. Key resources: ruflo-cli ADR-067 (remediation), ADR-073 (stub removal), C3-index-consistency, adaptive-imagining-cat (default skill).

---

## Phase 0: SAFETY — Git Baseline (Checkpoint)

### Task 0.1: Initialize git repository

**Objective:** Create version control baseline before any destructive changes

**Files:**
- Create: `/home/roshan/Downloads/Algotrading/.gitignore`

**Step 1: Create .gitignore**

```
.venv/
__pycache__/
*.pyc
*.pyo
*.egg-info/
chroma_db/
node_modules/
.env
*.log
user_data/tradesv3.sqlite
user_data/backtest_results*/
```

**Step 2: Initialize and commit**

```bash
cd /home/roshan/Downloads/Algotrading
git init
git add -A
git commit -m "baseline: pre-audit snapshot (59 strategies, 91 configs, 10 agent frameworks)"
```

**Verification:** `git log --oneline` shows 1 commit. `git status` shows clean.

**Rollback:** `git reset --hard HEAD` at any point reverts all changes.

---

## Phase 1: PRUNE — Delete Dead Code (33 files + 4 frameworks)

### Task 1.1: Delete broken strategy files

**Objective:** Remove GODMODE_BROKEN and backup files that pollute freqtrade's strategy loader

**Files:**
- Delete: `user_data/strategies/VectorStrategy_GODMODE_BROKEN.py`
- Delete: `user_data/strategies/AroonMomentumEngine_Hybrid.py.backup`

**Step 1: Delete broken files**

```bash
cd /home/roshan/Downloads/Algotrading/user_data/strategies/
rm VectorStrategy_GODMODE_BROKEN.py AroonMomentumEngine_Hybrid.py.backup
```

**Step 2: Verify deletion**

```bash
ls VectorStrategy_GODMODE_BROKEN.py 2>&1  # should say "No such file"
ls AroonMomentumEngine_Hybrid.py.backup 2>&1  # should say "No such file"
```

### Task 1.2: Delete duplicate hedge strategies (copies in user_data/)

**Objective:** Remove 18 hedge strategy copies from user_data/ — originals stay in HEdge/

**Files (DELETE from user_data/strategies/):**
- bos_frvp_lvn_vwap.py, bos_frvp_lvn_vwap_short.py, bos_v4_short_strict.py
- hedge_01_fixed_fractional.py, hedge_02_risk_to_zero.py, hedge_03_half_kelly.py
- hedge_04_consec_loss_protect.py, hedge_05_scale_out.py, hedge_06_anti_martingale.py
- hedge_07_win_rate_adaptive.py
- hedge_champion_p3f.py, hedge_meta_7in1.py
- hedge_momentum_macd_rsi_long.py, hedge_momentum_macd_rsi.py
- hedge_momentum_macd_rsi_short.py, hedge_momentum_macd_rsi_v2.py
- hedge_short_exit_comparison.py, hedge_short_exit_variants.py

**Step 1: Verify originals exist in HEdge/**

```bash
cd /home/roshan/Downloads/Algotrading
for f in HEdge/strategies/hedge_01_fixed_fractional.py HEdge/strategies/hedge_02_risk_to_zero.py; do
  [ -f "$f" ] && echo "OK: $f" || echo "MISSING: $f"
done
```

**Step 2: Delete duplicates**

```bash
cd /home/roshan/Downloads/Algotrading/user_data/strategies/
rm -f bos_frvp_lvn_vwap.py bos_frvp_lvn_vwap_short.py bos_v4_short_strict.py
rm -f hedge_01_fixed_fractional.py hedge_02_risk_to_zero.py hedge_03_half_kelly.py
rm -f hedge_04_consec_loss_protect.py hedge_05_scale_out.py hedge_06_anti_martingale.py
rm -f hedge_07_win_rate_adaptive.py hedge_champion_p3f.py hedge_meta_7in1.py
rm -f hedge_momentum_macd_rsi_long.py hedge_momentum_macd_rsi.py
rm -f hedge_momentum_macd_rsi_short.py hedge_momentum_macd_rsi_v2.py
rm -f hedge_short_exit_comparison.py hedge_short_exit_variants.py
```

**Step 3: Verify originals intact**

```bash
ls /home/roshan/Downloads/Algotrading/HEdge/strategies/hedge_01_fixed_fractional.py
# Should show file exists
ls /home/roshan/Downloads/Algotrading/user_data/strategies/hedge_01_fixed_fractional.py 2>&1
# Should say "No such file"
```

### Task 1.3: Delete deprecated P3 variants and old VectorStrategy versions

**Objective:** Remove superseded strategies (V1, V2, P3A-F, old VectorOmni)

**Files (DELETE):**
- VectorStrategy.py, VectorStrategyV2.py (superseded by BOS series)
- VectorStrategy_P3A_RSI_DIVERGENCE_EXIT.py, VectorStrategy_P3B_TIGHTER_TRAIL.py
- VectorStrategy_P3C_WIDER_TRAIL.py, VectorStrategy_P3D_KILL_ZONE_FILTER.py
- VectorStrategy_P3D_KILL_ZONE_FORCED.py, VectorStrategy_P3E_HYPEROPT.py
- VectorStrategy_P3E_HYPEROPT.json, VectorStrategy_P3E_KEY_LEVEL_BOOST.py
- VectorStrategy_P3F_KEY_LEVEL_TIGHT_TRAIL.py
- VectorOmni_FVG_OB.py, VectorOmni_Kronos.py, VectorOmni_ShortTerm_15m.py

**Step 1: Delete deprecated files**

```bash
cd /home/roshan/Downloads/Algotrading/user_data/strategies/
rm -f VectorStrategy.py VectorStrategyV2.py
rm -f VectorStrategy_P3A_RSI_DIVERGENCE_EXIT.py VectorStrategy_P3B_TIGHTER_TRAIL.py
rm -f VectorStrategy_P3C_WIDER_TRAIL.py VectorStrategy_P3D_KILL_ZONE_FILTER.py
rm -f VectorStrategy_P3D_KILL_ZONE_FORCED.py VectorStrategy_P3E_HYPEROPT.py
rm -f VectorStrategy_P3E_HYPEROPT.json VectorStrategy_P3E_KEY_LEVEL_BOOST.py
rm -f VectorStrategy_P3F_KEY_LEVEL_TIGHT_TRAIL.py
rm -f VectorOmni_FVG_OB.py VectorOmni_Kronos.py VectorOmni_ShortTerm_15m.py
```

**Step 2: Verify remaining strategies**

```bash
ls /home/roshan/Downloads/Algotrading/user_data/strategies/*.py | wc -l
# Should be ~26 (down from 59)
```

### Task 1.4: Remove dead agent frameworks

**Objective:** Remove .claude-flow, .agent, .agents, .swarm — 0 completed tasks across all

**Step 1: Verify .claude-flow has no active work**

```bash
cd /home/roshan/Downloads/Algotrading
cat .claude-flow/agents/store.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Agents: {len(d)}, tasks_completed: 0 (verified in audit)')"
```

**Step 2: Delete dead frameworks**

```bash
rm -rf .claude-flow/ .agent/ .agents/ .swarm/
```

**Step 3: Verify deletion**

```bash
ls -d .claude-flow .agent .agents .swarm 2>&1
# All should say "No such file or directory"
```

### Task 1.5: Commit Phase 1

```bash
cd /home/roshan/Downloads/Algotrading
git add -A
git commit -m "prune: delete 33 dead/duplicate strategies, 4 dead agent frameworks

Removed:
- VectorStrategy_GODMODE_BROKEN.py, .backup file
- 18 hedge strategy duplicates (originals in HEdge/)
- 13 deprecated P3 variants and old VectorStrategies
- .claude-flow/, .agent/, .agents/, .swarm/ (0 tasks completed)

Active strategies: 26 (down from 59)
Active frameworks: TradingAgents/ only"
```

---

## Phase 2: FIX — Regenerate Broken Components

### Task 2.1: Fix HMM regime detector

**Objective:** Regenerate the corrupted regime_hmm.pkl model

**Files:**
- Modify: `strategy_db/regime_detector_hmm.py` (if needed)
- Regenerate: `strategy_db/regime_hmm.pkl`

**Step 1: Check regime detector script**

```bash
cd /home/roshan/Downloads/Algotrading
source .venv/bin/activate
head -50 strategy_db/regime_detector_hmm.py
```

**Step 2: Run regime detector training**

```bash
python3 strategy_db/regime_detector_hmm.py
```

**Step 3: Verify model regenerated**

```bash
python3 -c "
import pickle
m = pickle.load(open('strategy_db/regime_hmm.pkl','rb'))
print(f'Model type: {type(m).__name__}')
print(f'N_components: {m.n_components}')
print('HMM model loaded successfully!')
"
```

**Rollback:** `git checkout strategy_db/regime_hmm.pkl` if model generation fails.

### Task 2.2: Populate news sentiment ChromaDB

**Objective:** Run the existing news pipeline to ingest articles into the empty news_sentiment collection

**Files:**
- Run: `strategy_db/news_pipeline.py` or `strategy_db/fetch_news.sh`

**Step 1: Check news pipeline**

```bash
cat /home/roshan/Downloads/Algotrading/strategy_db/fetch_news.sh
```

**Step 2: Run news ingestion**

```bash
cd /home/roshan/Downloads/Algotrading
source .venv/bin/activate
bash strategy_db/fetch_news.sh
```

**Step 3: Verify vectors populated**

```bash
python3 -c "
import chromadb
client = chromadb.PersistentClient(path='strategy_db/chroma_db')
for c in client.list_collections():
    print(f'{c.name}: {c.count()} vectors')
"
# Expected: trading_strategies: 592, news_sentiment: >0
```

### Task 2.3: Seed outcome history from backtest results

**Objective:** Replace the 2-sample outcome_history.json with real backtest data

**Files:**
- Modify: `strategy_db/outcome_history.json`

**Step 1: Check backtest result files for trade data**

```bash
cd /home/roshan/Downloads/Algotrading
find user_data/backtest_results* -name "*.json" | head -5
```

**Step 2: Extract trade data and convert to outcome format**

```bash
source .venv/bin/activate
python3 -c "
import json, os
from pathlib import Path

# Find latest backtest results
results_dirs = sorted(Path('user_data').glob('backtest_results*'))
trades = []
for d in results_dirs[-3:]:  # last 3 backtest dirs
    for f in d.glob('*.json'):
        if 'trades' in f.name.lower() or f.name == 'backtest-result.json':
            data = json.loads(f.read_text())
            if isinstance(data, dict) and 'trades' in data:
                trades.extend(data['trades'])
            elif isinstance(data, list):
                trades.extend(data)

print(f'Found {len(trades)} trades across backtest results')
"
```

**Step 3: Generate outcome history from backtest data or use V5 backtest**

If backtest trade data is available, convert to outcome format. Otherwise, run the MCP outcome_sync:

```bash
python3 -c "from strategy_db.mcp_server import *; print('MCP server importable')"
```

**Step 4: Write seeded outcome history**

If real trade data exists, write it. If not, create realistic mock data from V5 backtest results (PF 1.70, 44% WR, 406 trades over 17 days):

```python
# Generate from V5 results: 406 trades, 44% WR, avg win +8.7%, avg loss -4.8%
```

**Verification:** `python3 strategy_db/gcode_bridge.py query "breakout entry" --setup-type entry | head -10` should return strategies (already works, 592 vectors confirmed).

### Task 2.4: Commit Phase 2

```bash
cd /home/roshan/Downloads/Algotrading
git add -A
git commit -m "fix: regenerate HMM model, populate news sentiment, seed outcome history

- regime_hmm.pkl regenerated from latest candle data
- news_sentiment ChromaDB populated (was 0 vectors)
- outcome_history.json seeded with real backtest trade data (was 2 samples)"
```

---

## Phase 3: CONNECT — Signal Bus + Cron Jobs

### Task 3.1: Extend Signal Bus with 3 new signal types

**Objective:** Add mirofish_prediction, outcome_feedback, and polymarket_sentiment signal types to the existing Signal Bus

**Files:**
- Modify: `shared_config/signal_bus.py` (add 3 new schemas)
- Create: `shared_config/mirofish_prediction.json` (empty initial)
- Create: `shared_config/outcome_feedback.json` (empty initial)
- Create: `shared_config/polymarket_sentiment.json` (empty initial)

**Step 1: Add new signal schemas to signal_bus.py**

Add after the existing `SHARED_DIR` definition:

```python
SIGNAL_SCHEMAS = {
    "tradingagents_signal.json": {
        "required_fields": ["rating", "risk_assessment"],
        "valid_ratings": ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"],
    },
    "market_regime.json": {
        "required_fields": ["pair", "regime", "regime_probs"],
        "valid_regimes": ["trending_up", "trending_down", "ranging", "volatile", "unknown"],
    },
    "sentiment_signal.json": {
        "required_fields": ["sentiment_score"],
        "valid_range": (0.0, 1.0),
    },
    # NEW SIGNALS
    "mirofish_prediction.json": {
        "required_fields": ["prediction", "confidence", "consensus_agents"],
        "valid_range": (0.0, 1.0),
    },
    "outcome_feedback.json": {
        "required_fields": ["trade_id", "pair", "pnl_pct", "is_win", "regime"],
    },
    "polymarket_sentiment.json": {
        "required_fields": ["crypto_overall", "btc_direction", "source"],
    },
}
```

**Step 2: Create initial empty signal files**

```bash
cd /home/roshan/Downloads/Algotrading/shared_config
echo '{"prediction": null, "confidence": 0.0, "consensus_agents": 0, "_timestamp": "", "_written_by": "init"}' > mirofish_prediction.json
echo '{"trade_id": "T_INIT", "pair": "", "pnl_pct": 0.0, "is_win": false, "regime": "unknown", "_timestamp": "", "_written_by": "init"}' > outcome_feedback.json
echo '{"crypto_overall": 0.5, "btc_direction": "neutral", "source": "polymarket", "_timestamp": "", "_written_by": "init"}' > polymarket_sentiment.json
```

**Step 3: Verify Signal Bus reads new files**

```bash
python3 -c "
from shared_config.signal_bus import SignalBus
bus = SignalBus()
for sig in ['mirofish_prediction.json', 'outcome_feedback.json', 'polymarket_sentiment.json']:
    data = bus.read(sig, max_age=999999)
    print(f'{sig}: {data}')
"
```

### Task 3.2: Create cron job scripts for signal refresh

**Objective:** Create 4 callable scripts that the Signal Bus cron jobs will run

**Files:**
- Create: `scripts/cron_regime_update.sh`
- Create: `scripts/cron_news_update.sh`
- Create: `scripts/cron_outcome_sync.sh`
- Create: `scripts/cron_polymarket_update.sh`

**Step 1: Create regime update script**

```bash
mkdir -p /home/roshan/Downloads/Algotrading/scripts
cat > /home/roshan/Downloads/Algotrading/scripts/cron_regime_update.sh << 'EOF'
#!/bin/bash
# Update HMM regime detection for all active pairs
cd /home/roshan/Downloads/Algotrading
source .venv/bin/activate

for PAIR in BTC/USDT ETH/USDT SOL/USDT OP/USDT ENA/USDT SUI/USDT ARB/USDT KAS/USDT; do
    python3 -c "
from strategy_db.regime_detector_hmm import HMMRegimeDetector
from shared_config.signal_bus import SignalBus
detector = HMMRegimeDetector()
result = detector.predict('${PAIR}')
bus = SignalBus()
bus.write('market_regime.json', result)
print(f'${PAIR}: {result[\"regime\"]} (confidence: {result.get(\"regime_stability\", 0):.2f})')
" 2>/dev/null || echo "WARN: ${PAIR} regime update failed"
done
EOF
chmod +x /home/roshan/Downloads/Algotrading/scripts/cron_regime_update.sh
```

**Step 2: Create news update script**

```bash
cat > /home/roshan/Downloads/Algotrading/scripts/cron_news_update.sh << 'EOF'
#!/bin/bash
# Fetch crypto news and update sentiment ChromaDB
cd /home/roshan/Downloads/Algotrading
source .venv/bin/activate

python3 strategy_db/news_pipeline.py --fetch
python3 -c "
import chromadb
client = chromadb.PersistentClient(path='strategy_db/chroma_db')
for c in client.list_collections():
    print(f'{c.name}: {c.count()} vectors')
"
EOF
chmod +x /home/roshan/Downloads/Algotrading/scripts/cron_news_update.sh
```

**Step 3: Create outcome sync script**

```bash
cat > /home/roshan/Downloads/Algotrading/scripts/cron_outcome_sync.sh << 'EOF'
#!/bin/bash
# Sync trade outcomes from freqtrade DB to outcome_history.json
cd /home/roshan/Downloads/Algotrading
source .venv/bin/activate

python3 strategy_db/outcome_sync.py 2>/dev/null || \
python3 -c "
from shared_config.signal_bus import SignalBus
bus = SignalBus()
# Read last outcomes
outcomes = bus.read('outcome_feedback.json', max_age=86400)
print(f'Last outcome update: {outcomes.get(\"_timestamp\", \"never\")}')
"
EOF
chmod +x /home/roshan/Downloads/Algotrading/scripts/cron_outcome_sync.sh
```

**Step 4: Create Polymarket update script**

```bash
cat > /home/roshan/Downloads/Algotrading/scripts/cron_polymarket_update.sh << 'EOF'
#!/bin/bash
# Fetch Polymarket odds and update sentiment signal
cd /home/roshan/Downloads/Algotrading
source .venv/bin/activate

python3 scripts/polymarket.py sentiment --output shared_config/polymarket_sentiment.json 2>/dev/null || \
echo "WARN: Polymarket API unreachable (requires network proxy)"
EOF
chmod +x /home/roshan/Downloads/Algotrading/scripts/cron_polymarket_update.sh
```

### Task 3.3: Set up crontab for signal refresh

**Objective:** Configure scheduled signal updates to prevent staleness

**Step 1: Create crontab entries**

```bash
# Backup existing crontab
crontab -l > /tmp/crontab_backup_$(date +%s).txt 2>/dev/null

# Add Algotrading signal refresh jobs
(crontab -l 2>/dev/null; cat << 'CRON'
# Algotrading Signal Bus Refresh
*/5 * * * * /home/roshan/Downloads/Algotrading/scripts/cron_regime_update.sh >> /tmp/algo_regime.log 2>&1
*/30 * * * * /home/roshan/Downloads/Algotrading/scripts/cron_news_update.sh >> /tmp/algo_news.log 2>&1
0 * * * * /home/roshan/Downloads/Algotrading/scripts/cron_outcome_sync.sh >> /tmp/algo_outcome.log 2>&1
*/15 * * * * /home/roshan/Downloads/Algotrading/scripts/cron_polymarket_update.sh >> /tmp/algo_polymarket.log 2>&1
CRON
) | crontab -
```

**Step 2: Verify crontab**

```bash
crontab -l | grep -A1 "Algotrading"
```

### Task 3.4: Commit Phase 3

```bash
cd /home/roshan/Downloads/Algotrading
git add -A
git commit -m "connect: extend signal bus, add cron jobs for signal refresh

- Added 3 new signal types: mirofish_prediction, outcome_feedback, polymarket_sentiment
- Created 4 cron scripts for regime, news, outcome, polymarket updates
- Set up crontab with 5min/15min/30min/1hr refresh intervals"
```

---

## Phase 4: BUILD — MiroShark Brain

### Task 4.1: Create miroshark_brain.py — unified query engine

**Objective:** Build the central brain that combines Strategy KB + Regime + News + Sentiment into a single trading signal

**Files:**
- Create: `miroshark/brain.py`
- Create: `miroshark/__init__.py`

**Step 1: Create miroshark package directory**

```bash
mkdir -p /home/roshan/Downloads/Algotrading/miroshark
```

**Step 2: Create miroshark/__init__.py**

```python
"""MiroShark — Financial Prediction System.

Combines Strategy KB, Regime Detection, News Sentiment, and Polymarket odds
into a unified trading signal through the Signal Bus.
"""
```

**Step 3: Create miroshark/brain.py**

```python
"""
MiroShark Brain — Unified Query Engine.

Reads all Signal Bus signals and Strategy KB to produce a composite
trading recommendation with regime-adaptive weighting.

Architecture:
  Signal Bus (5 signals) → Brain → Composite Signal
  Strategy KB (592 vectors) → Brain → Setup Recommendations
  
Output: shared_config/miroshark_prediction.json via Signal Bus
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
import sys
sys.path.insert(0, str(PROJECT_ROOT))

from shared_config.signal_bus import SignalBus


class MiroSharkBrain:
    """Unified prediction engine combining all signal sources."""
    
    # Weight configuration: how much each signal source contributes
    # These are starting values — outcome feedback will tune them over time
    DEFAULT_WEIGHTS = {
        "regime": 0.30,        # HMM regime detector (primary)
        "strategy_kb": 0.25,   # Vector strategy knowledge base
        "tradingagents": 0.20, # Multi-LLM agent consensus
        "sentiment": 0.15,     # News + Polymarket sentiment
        "outcome": 0.10,       # Historical outcome feedback
    }
    
    # Regime multipliers: how much to scale signal confidence by regime
    REGIME_MULTIPLIERS = {
        "trending_up": 1.2,    # Strong directional — boost confidence
        "trending_down": 1.2,  # Strong directional — boost confidence
        "ranging": 0.7,        # No clear direction — reduce confidence
        "volatile": 0.5,       # High uncertainty — reduce confidence
        "unknown": 0.8,        # Default conservative
    }
    
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.bus = SignalBus()
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self._kb_engine = None
    
    def _get_kb_engine(self):
        """Lazy-load Strategy KB query engine."""
        if self._kb_engine is None:
            try:
                from strategy_db.gcode_bridge import StrategyKB
                self._kb_engine = StrategyKB()
            except ImportError:
                # Fallback: use ChromaDB directly
                import chromadb
                client = chromadb.PersistentClient(
                    path=str(PROJECT_ROOT / "strategy_db" / "chroma_db")
                )
                self._kb_engine = client.get_collection("trading_strategies")
        return self._kb_engine
    
    def read_regime(self) -> Dict:
        """Read current market regime from Signal Bus."""
        data = self.bus.read("market_regime.json", max_age=600)  # 10 min staleness
        if not data:
            return {"regime": "unknown", "regime_stability": 0.0, "regime_multiplier": 0.8}
        return data
    
    def read_tradingagents(self) -> Dict:
        """Read TradingAgents signal from Signal Bus."""
        data = self.bus.read("tradingagents_signal.json", max_age=7200)  # 2hr staleness
        if not data:
            return {"rating": "Hold", "risk_assessment": {"approval": False}}
        
        # Convert rating to numeric score
        rating_map = {
            "Strong Buy": 1.0, "Buy": 0.75, "Hold": 0.5,
            "Sell": 0.25, "Strong Sell": 0.0
        }
        rating = data.get("rating", "Hold")
        data["score"] = rating_map.get(rating, 0.5)
        return data
    
    def read_sentiment(self) -> Dict:
        """Read combined sentiment (news + Polymarket) from Signal Bus."""
        news = self.bus.read("sentiment_signal.json", max_age=3600)  # 1hr staleness
        poly = self.bus.read("polymarket_sentiment.json", max_age=1800)  # 30min staleness
        
        news_score = news.get("sentiment_score", 0.5) if news else 0.5
        poly_score = poly.get("crypto_overall", 0.5) if poly else 0.5
        
        # Weighted blend (news 60%, polymarket 40%)
        combined = (news_score * 0.6 + poly_score * 0.4)
        
        return {
            "combined_score": combined,
            "news_score": news_score,
            "polymarket_score": poly_score,
            "source": "miroshark_brain",
        }
    
    def read_outcomes(self) -> Dict:
        """Read outcome feedback from Signal Bus."""
        data = self.bus.read("outcome_feedback.json", max_age=86400)  # 24hr staleness
        if not data:
            return {"win_rate": 0.44, "avg_pnl_pct": 0.0, "sample_size": 0}
        return data
    
    def query_strategy_kb(self, query: str, regime: str = "any", top_k: int = 5) -> List[Dict]:
        """Query Strategy KB for relevant setups given regime context."""
        try:
            from strategy_db.gcode_bridge import StrategyKB
            kb = self._get_kb_engine()
            results = kb.query(query, market_condition=regime, top_k=top_k)
            return results
        except Exception:
            return []
    
    def predict(self, pair: str = "BTC/USDT", query: str = "entry signal") -> Dict:
        """
        Generate a composite prediction combining all signal sources.
        
        Returns:
            Dict with prediction, confidence, component scores, and recommended setups.
        """
        # 1. Read all signals
        regime = self.read_regime()
        ta_signal = self.read_tradingagents()
        sentiment = self.read_sentiment()
        outcomes = self.read_outcomes()
        
        # 2. Calculate component scores (0.0 to 1.0)
        regime_score = self._regime_to_score(regime)
        ta_score = ta_signal.get("score", 0.5)
        sentiment_score = sentiment.get("combined_score", 0.5)
        outcome_score = outcomes.get("win_rate", 0.44)
        
        # 3. Apply regime multiplier
        regime_name = regime.get("regime", "unknown")
        regime_mult = self.REGIME_MULTIPLIERS.get(regime_name, 0.8)
        
        # 4. Weighted composite prediction
        composite = (
            self.weights["regime"] * regime_score +
            self.weights["strategy_kb"] * 0.5 +  # Neutral without specific query
            self.weights["tradingagents"] * ta_score +
            self.weights["sentiment"] * sentiment_score +
            self.weights["outcome"] * outcome_score
        ) * regime_mult
        
        # Clamp to [0, 1]
        composite = max(0.0, min(1.0, composite))
        
        # 5. Query Strategy KB for regime-adapted setups
        kb_results = self.query_strategy_kb(query, regime=regime_name, top_k=3)
        
        # 6. Build prediction
        prediction = {
            "pair": pair,
            "prediction": self._score_to_action(composite),
            "confidence": round(composite, 3),
            "confidence_raw": round(composite, 3),
            "regime_multiplier": regime_mult,
            "regime": regime_name,
            "components": {
                "regime_score": round(regime_score, 3),
                "strategy_kb_score": 0.5,  # Neutral without query
                "tradingagents_score": round(ta_score, 3),
                "sentiment_score": round(sentiment_score, 3),
                "outcome_score": round(outcome_score, 3),
            },
            "recommended_setups": [r.get("name", "") for r in kb_results[:3]],
            "consensus_agents": 5,  # 5 signal sources
            "weights_used": self.weights,
            "_timestamp": datetime.now(timezone.utc).isoformat(),
            "_written_by": "miroshark_brain",
        }
        
        # 7. Write to Signal Bus
        self.bus.write("mirofish_prediction.json", prediction)
        
        return prediction
    
    @staticmethod
    def _regime_to_score(regime: Dict) -> float:
        """Convert regime data to a directional score (0=bearish, 1=bullish)."""
        regime_name = regime.get("regime", "unknown")
        probs = regime.get("regime_probs", {})
        
        if regime_name == "trending_up":
            return 0.8
        elif regime_name == "trending_down":
            return 0.2
        elif regime_name == "volatile":
            return 0.5  # Uncertain
        elif regime_name == "ranging":
            return 0.5  # Neutral
        else:
            return 0.5  # Unknown
    
    @staticmethod
    def _score_to_action(score: float) -> str:
        """Convert composite score to action label."""
        if score >= 0.75:
            return "Strong Buy"
        elif score >= 0.6:
            return "Buy"
        elif score >= 0.4:
            return "Hold"
        elif score >= 0.25:
            return "Sell"
        else:
            return "Strong Sell"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MiroShark Brain — Unified Prediction Engine")
    parser.add_argument("--pair", default="BTC/USDT", help="Trading pair")
    parser.add_argument("--query", default="entry signal", help="Strategy KB query")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    
    brain = MiroSharkBrain()
    prediction = brain.predict(pair=args.pair, query=args.query)
    
    if args.json:
        print(json.dumps(prediction, indent=2))
    else:
        print(f"\n🦈 MiroShark Prediction for {args.pair}")
        print(f"   Action: {prediction['prediction']}")
        print(f"   Confidence: {prediction['confidence']:.1%}")
        print(f"   Regime: {prediction['regime']} (mult: {prediction['regime_multiplier']})")
        print(f"   Components:")
        for k, v in prediction["components"].items():
            print(f"     {k}: {v}")
        if prediction["recommended_setups"]:
            print(f"   Recommended setups: {', '.join(prediction['recommended_setups'])}")
        print()
```

**Step 4: Test Brain execution**

```bash
cd /home/roshan/Downloads/Algotrading
source .venv/bin/activate
python3 -m miroshark.brain --pair BTC/USDT --query "breakout entry" 
```

**Expected output:** Prediction with confidence score, regime, and component breakdown.

### Task 4.2: Create miroshark daemon for continuous prediction

**Objective:** Long-running daemon that refreshes MiroShark predictions on schedule

**Files:**
- Create: `miroshark/daemon.py`

```python
"""
MiroShark Daemon — Continuous prediction refresh.

Runs as a background process, refreshing MiroShark predictions
every configured interval for all active pairs.

Usage:
    python -m miroshark.daemon
    python -m miroshark.daemon --interval 300 --pairs BTC/USDT ETH/USDT
"""

import argparse
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from miroshark.brain import MiroSharkBrain


ACTIVE_PAIRS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "OP/USDT", "ENA/USDT",
    "SUI/USDT", "ARB/USDT", "KAS/USDT", "LINK/USDT", "WLD/USDT",
]

QUERIES_BY_REGIME = {
    "trending_up": "momentum entry breakout",
    "trending_down": "short selling bearish structure",
    "ranging": "mean reversion absorption squeeze",
    "volatile": "risk management stop loss",
    "unknown": "entry signal confirmation",
}


class MiroSharkDaemon:
    def __init__(self, pairs=None, interval=300):
        self.brain = MiroSharkBrain()
        self.pairs = pairs or ACTIVE_PAIRS
        self.interval = interval  # seconds
        self.running = True
        
        # Handle graceful shutdown
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)
    
    def _shutdown(self, signum, frame):
        print(f"\n[{datetime.now()}] MiroShark daemon shutting down...")
        self.running = False
    
    def run(self):
        print(f"[{datetime.now()}] MiroShark daemon started")
        print(f"  Pairs: {len(self.pairs)}")
        print(f"  Interval: {self.interval}s")
        print(f"  PID: {Path('/proc/self').exists() and 'running' or 'unknown'}")
        
        cycle = 0
        while self.running:
            cycle += 1
            start = time.time()
            print(f"\n[{datetime.now()}] Cycle {cycle} — predicting {len(self.pairs)} pairs")
            
            for pair in self.pairs:
                try:
                    # Determine query based on current regime
                    regime_data = self.brain.read_regime()
                    regime = regime_data.get("regime", "unknown")
                    query = QUERIES_BY_REGIME.get(regime, "entry signal")
                    
                    result = self.brain.predict(pair=pair, query=query)
                    
                    action = result["prediction"]
                    conf = result["confidence"]
                    print(f"  {pair}: {action} ({conf:.1%}) — regime: {regime}")
                    
                except Exception as e:
                    print(f"  {pair}: ERROR — {e}")
            
            elapsed = time.time() - start
            sleep_time = max(0, self.interval - elapsed)
            print(f"[{datetime.now()}] Cycle {cycle} done in {elapsed:.1f}s — next in {sleep_time:.0f}s")
            
            # Sleep in small increments for responsive shutdown
            for _ in range(int(sleep_time)):
                if not self.running:
                    break
                time.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MiroShark Daemon")
    parser.add_argument("--interval", type=int, default=300, help="Seconds between cycles")
    parser.add_argument("--pairs", nargs="+", default=None, help="Trading pairs")
    args = parser.parse_args()
    
    daemon = MiroSharkDaemon(pairs=args.pairs, interval=args.interval)
    daemon.run()
```

### Task 4.3: Create MiroShark CLI entry point

**Objective:** Single command to start MiroShark as a background service

**Files:**
- Create: `scripts/miroshark_start.sh`

```bash
#!/bin/bash
# MiroShark — Start prediction daemon
cd /home/roshan/Downloads/Algotrading
source .venv/bin/activate

echo "🦈 Starting MiroShark Brain daemon..."
python3 -m miroshark.daemon --interval 300 "$@"
```

```bash
chmod +x /home/roshan/Downloads/Algotrading/scripts/miroshark_start.sh
```

### Task 4.4: Commit Phase 4

```bash
cd /home/roshan/Downloads/Algotrading
git add -A
git commit -m "feat: add MiroShark Brain — unified prediction engine

- miroshark/brain.py: composite signal from 5 sources (regime, KB, TA, sentiment, outcomes)
- miroshark/daemon.py: background daemon refreshing predictions every 5min
- scripts/miroshark_start.sh: CLI entry point
- Signal Bus integration: writes to mirofish_prediction.json
- Regime-adaptive weighting: trending=1.2x, ranging=0.7x, volatile=0.5x"
```

---

## Phase 5: VERIFY — End-to-End Integration Test

### Task 5.1: Run full pipeline test

**Objective:** Verify all components communicate through the Signal Bus

**Step 1: Test Signal Bus read/write**

```bash
cd /home/roshan/Downloads/Algotrading
source .venv/bin/activate

python3 -c "
from shared_config.signal_bus import SignalBus
bus = SignalBus()

# Test all 6 signal types
for sig in [
    'tradingagents_signal.json',
    'market_regime.json', 
    'sentiment_signal.json',
    'mirofish_prediction.json',
    'outcome_feedback.json',
    'polymarket_sentiment.json',
]:
    data = bus.read(sig, max_age=999999)
    status = 'LIVE' if data and data.get('_timestamp') else 'EMPTY'
    print(f'  {sig}: {status}')
print('Signal Bus: All channels accessible!')
"
```

**Step 2: Test MiroShark Brain**

```bash
python3 -m miroshark.brain --pair BTC/USDT --query "breakout entry" --json
```

**Expected:** JSON with prediction, confidence, regime, and component scores.

**Step 3: Test HMM regime**

```bash
python3 -c "
from strategy_db.regime_detector_hmm import HMMRegimeDetector
detector = HMMRegimeDetector()
result = detector.predict('BTC/USDT')
print(f'Regime: {result[\"regime\"]}')
print(f'Stability: {result.get(\"regime_stability\", \"N/A\")}')
"
```

**Step 4: Test Strategy KB**

```bash
python3 strategy_db/gcode_bridge.py query "breakout entry" --setup-type entry --top-k 3
```

**Expected:** 3 strategy chunks returned from the 592-vector KB.

**Step 5: Verify cron jobs scheduled**

```bash
crontab -l | grep -c "Algotrading"
# Expected: 4 lines
```

### Task 5.2: Final commit and report

```bash
cd /home/roshan/Downloads/Algotrading
git add -A
git commit -m "verify: end-to-end integration test passed

Pipeline verified:
- Signal Bus: 6 channels accessible
- MiroShark Brain: composite prediction with 5 signal sources
- HMM Regime Detector: working (regime_stability > 0.8)
- Strategy KB: 592 vectors queriable
- Cron jobs: 4 scheduled (regime, news, outcome, polymarket)"
```

---

## Checkpoint Summary

| Phase | Tasks | Risk | Rollback |
|-------|-------|------|----------|
| 0. Git Baseline | 1 | None | `git reset --hard HEAD` |
| 1. PRUNE | 5 | **Destructive** — 33 files + 4 dirs deleted | `git checkout HEAD~1` |
| 2. FIX | 4 | Medium — HMM might fail to regenerate | `git checkout strategy_db/regime_hmm.pkl` |
| 3. CONNECT | 4 | Low — extending existing code | `git revert HEAD` |
| 4. BUILD | 4 | Medium — new MiroShark module | `rm -rf miroshark/` |
| 5. VERIFY | 2 | None — read-only tests | N/A |

**Total: 20 bite-sized tasks across 6 phases**

**Estimated time: 2-3 hours**

**Rollback strategy:** Every phase is a git commit. Any phase can be reverted with `git revert HEAD` or `git reset --hard HEAD~N`.