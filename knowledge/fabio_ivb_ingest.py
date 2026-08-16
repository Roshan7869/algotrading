#!/usr/bin/env python3
"""Ingest Fabio IVB ORB strategy into ChromaDB."""

import chromadb
from sentence_transformers import SentenceTransformer
import uuid

model = SentenceTransformer('all-MiniLM-L6-v2')
client = chromadb.PersistentClient(path='strategy_db/chroma_db')
collection = client.get_or_create_collection('trading_strategies')

strategy_text = """Fabio IVB ORB - Institutional Validation Protocol

Type: entry
Author: Fabio Valentini (validated by Matteo Conti / IVB)
Timeframe: 5min (entry) / 30min (delta accumulation)
Market Condition: trending (NQ morning session)
Strategy Style: intraday breakout
Risk Reward: 1:1 fixed (1R take-profit)
Keywords: ORB, opening_range_breakout, volume_delta, cumulative_delta, NQ, futures, institutional_validation, bootstrap, monte_carlo, statistical_significance, EV, expectancy, Fabio_Valentini

Entry Rules:
1. Define opening range from 08:30 to 09:00 NY time (30-minute window)
2. On a 5-minute close ABOVE the range high, check volume delta
3. Bar delta must exceed DeltaThreshold (default: 200) or CumDeltaThreshold (default: 500 if UseCumulativeDelta)
4. If delta confirmed, enter LONG at close of breakout bar (stop-entry)
5. Only ONE entry per session (Long_Done_Today flag prevents re-entry)
6. Entry price = Close of breakout bar; Stop = ORB Low; TP = Entry + 1R * (Entry - ORB Low)

Exit Rules:
1. Take-profit: Fixed 1R multiple of the range width above entry (TP_RR_Ratio = 1.0)
2. Stop-loss: ORB range low (SL_Price = ORB_Low)
3. End-of-day exit: Flatten any open position at 14:00 ET
4. TP and SL are re-armed every bar while position is open

Statistical Validation (823 trades, Jan 2021 - Apr 2026, NQ Futures):
- Net Profit: $165,715 gross / $151,013 net (after commission + slippage)
- Annual Return: 31.4% gross / 28.6% net
- Win Rate: 58.32% (480W / 343L)
- Profit Factor: 1.31 gross / 1.28 net
- Max Drawdown: $25,295 (17.63%)
- Return on Max DD: 6.55 (institutional first-gate screen > 3)
- Avg Trade: $201.35 gross / $183.49 net
- Avg Winner: $1,474.41 / Avg Loser: $1,580.17
- Win/Loss Ratio: 0.93 (sub-unity; win-rate premium strategy)
- Sharpe (annualized from monthly): ~1.4
- Monthly t-stat: 2.4

Bootstrap Edge Significance:
- EV per trade: $194.26 / 0.1295 R
- 95% CI (EV $): [$65.62, $323.70]
- 95% CI (EV R): [0.0437 R, 0.2158 R]
- P(EV <= 0): 0.001 (null hypothesis of no edge REJECTED at 0.001 level)

Monte Carlo (20,000 simulations):
- Median terminal PnL: $159,588
- 95th pct terminal PnL: $248,083
- Median DD: $28,838
- 95th pct DD: $50,521 (live-sizing budget)
- P(DD >= $15K): 99.4%

Shuffled Sequences (1,000 permutations):
- All 1,000 permutations terminate positive
- Realised DD ($22,215) is near median
- Max sequential wins: 12, avg: 2.39
- Max sequential losses: 5, avg: 1.71

Deployment Verdict: VALIDATED / DEPLOYABLE
- Edge is real and statistically significant
- Path is not flattering (base DD near permutation median)
- Sample is sufficient (823 trades over 5 years)
- Budget for $50K peak-to-trough (95th pct MC DD)
- Next checks: walk-forward, slippage stress, regime breakdown by VIX quintile

Key Insight: Profitability carried by frequency not home runs. Win/Loss ratio 0.93 means the model pays a win-rate premium to compensate for slightly negative payoff asymmetry. This is the defining shape of a 1R fixed-TP breakout.

Same author as KB chunk Risk to Zero ASAP. ORB concept overlaps with Four-Criteria Area of Interest Framework. Volume delta filter overlaps with Model 1 Range Fade."""

embedding = model.encode(strategy_text)
chunk_id = f"fabio_ivb_orb_{uuid.uuid4().hex[:8]}"
collection.add(
    ids=[chunk_id],
    embeddings=[embedding.tolist()],
    documents=[strategy_text],
    metadatas=[{
        'setup_name': 'Fabio IVB ORB - Institutional Validation Protocol',
        'setup_type': 'entry',
        'timeframe': '5min / 30min',
        'market_condition': 'trending',
        'strategy_style': 'intraday_breakout',
        'channel_name': 'Fabio Valentini / Chart Fanatics',
        'video_title': 'Fabio IVB Model - The Institutional Protocol',
        'risk_reward': '1:1 fixed 1R',
        'keywords': 'ORB,opening_range_breakout,volume_delta,cumulative_delta,NQ,futures,institutional_validation,bootstrap,monte_carlo,statistical_significance',
        'assets': 'NQ_futures',
        'author_concept': 'True'
    }]
)

print(f'Added chunk to ChromaDB: {chunk_id}')
print(f'Collection now has {collection.count()} items')