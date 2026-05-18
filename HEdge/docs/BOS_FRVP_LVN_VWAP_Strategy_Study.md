# BOS + FRVP + LVN + VWAP Strategy — Deep Study

## Source
PDF: `/home/roshan/Downloads/Telegram Desktop/BOS_FRVP_LVN_VWAP_Strategy.pdf`

---

## BACKTEST RESULTS (May 1-18, 2026, 1h, 18 pairs, 10x leverage)

### Combined BOS_FRVP_LVN_VWAP (3-of-4 confluence, LONG+SHORT)
- 806 trades, +52.12%, PF 1.14, 39.5% WR
- SHORT side: +56.09% profit (dominant)
- LONG side: -3.98% (losing)
- 36.19% drawdown — UNACCEPTABLE
- Exit analysis:
  - Trailing stop: 303 trades, 100% WR, avg +15.73% (+$4267) ← WINNER
  - Stop loss: 479 trades, 0% WR, avg -8.84% (-$3787) ← PROBLEM
  - RSI exit: 18 shorts, 83.3% WR, avg +3.71%

### SHORT-Only BOS_FRVP_LVN_VWAP_Short (with RSI>35 filter)
- 372 trades, -7.49%, 37.4% WR, 71.20% DD — WORSE
- RSI filter killed profitable shorts too early

### Key Insight
60% of entries hit the 8% hard stop → too many low-quality entries.
The trailing stop winners are VERY profitable (avg +15.73%, 100% WR).
Need: tighter initial stop + stricter entry filter → fewer trades, higher quality.

### Top Performing Pairs
OP +17%, ARB +13%, KAS +10%, WLD +8%, SUI +7%, ENA +7%, TRX +5%, LINK +4.5%, SOL +1.4%

### Worst Pairs
AVAX -5.3%, DOT -4.8%, XLM -4.4%, XRP -3.3%, DOGE -1.8%, NEAR -1.6%, ALGO -1.2%

---

### REFINED: Top 10 Pairs Only (removed losers)
- 435 trades, **+397.41%**, PF 1.79, 43.0% WR
- Final balance: $4,974 from $1,000
- Sharpe 94.18, SQN 4.01
- Drawdown: 24.47% (down from 36.19%)
- SHORT side: +366% vs LONG side: +31%
- Trailing stop: 182 trades, 100% WR, avg +16.92%
- Stop loss: 241 trades, 0% WR, avg -8.85%
- Top pairs: OP +106%, ARB +57%, SUI +52%, ENA +45%, KAS +42%

---

## STRATEGY OVERVIEW

**Name:** BOS + FRVP + LVN + VWAP Confluence Entry
**Type:** Precision short (or long) entry strategy
**Timeframe:** 5m – 15m (intraday)
**Assets:** Forex, Indices, Crypto (universal)
**Philosophy:** 4-layer confluence filter — only trade when ALL four conditions align simultaneously

---

## THE 4 PILLARS

### PILLAR 1: Break of Structure (BOS)

**What:** Price breaks a significant swing high (bullish BOS) or swing low (bearish BOS)

**Downtrend Short Entry example:**
- Price makes series of Lower Highs and Lower Lows
- BOS occurs when price breaks below a prior swing low
- Confirms selling pressure / smart money has stepped in

**Uptrend Long Entry:**
- Price makes Higher Highs and Higher Lows
- BOS occurs when price breaks above a prior swing high
- Confirms buying pressure / institutions accumulating

**Why it matters:** BOS tells you the previous structure has been broken. Institutions left footprints in the volume profile. Now wait for retrace into a key area.

**Detection Method:**
- Identify swing highs/lows using zigzag or local extrema (lookback=5-10 bars)
- BOS = price breaks below last swing low (bearish) or above last swing high (bullish)
- In code: compare current low < min(prev_swing_lows) for bearish BOS

---

### PILLAR 2: Fixed Range Volume Profile (FRVP)

**What:** Histogram of volume traded at each price level over the consolidation/swing range

**How to apply:**
1. After BOS confirmed, anchor FRVP over the entire consolidation range that preceded the BOS
2. The profile shows:
   - **POC** (Point of Control): Highest volume node = strong support/resistance magnet
   - **HVN** (High Volume Node): Clustered trading = price tends to consolidate here
   - **LVN** (Low Volume Node): Thin volume = price moved fast through here = **ideal entry zone**

**Key Insight:** LVNs form because large participants moved price so fast that not everyone could get filled. When price returns to an LVN, those large participants "reload" — this is our edge.

**Detection Method (simplified for freqtrade):**
- Compute volume profile by slicing price range into N bins (e.g., 20-50 bins)
- For each bin: count total volume traded at prices within that bin range
- **LVN = bins with volume < 50% of POC volume** (thin volume zones)
- **POC = bin with maximum volume**
- Mark LVN price range as "rejection zone"

---

### PILLAR 3: Low Volume Node (LVN) Tap

**What:** After BOS and FRVP are set, WAIT for price to retrace back into the LVN

**Rules:**
- DO NOT chase price — wait for the retrace
- DO NOT enter as soon as price enters the LVN — wait for next confluence (VWAP)
- Use horizontal lines to mark top and bottom boundaries of the LVN
- Example LVN range from chart: 0.71520 – 0.71479 (approximately 4 pips)

**Why LVN works:**
- Little volume was traded there → price tends to reject quickly
- Large participants have unfilled orders → they "reload" at these levels
- Acts as a rejection magnet (price accelerates away from LVNs)

**Detection Method:**
- After BOS, compute FRVP for consolidation range
- Identify LVN zones (volume < 50% of POC)
- Current price retraces into LVN zone → condition 3 met

---

### PILLAR 4: VWAP Confluence — The Trigger

**What:** VWAP (Volume Weighted Average Price) intersects the LVN zone at the same price level

**Setup:**
- Anchor VWAP to session open (00:00 UTC for Forex, market open for equities/crypto)
- For shorts: VWAP should be sloping DOWN or FLAT as price retests
- For longs: VWAP should be sloping UP or FLAT as price retests
- When price taps BOTH LVN and VWAP simultaneously → entry trigger
- Final confirmation: bearish rejection candle (pin bar, engulfing, shooting star) at the zone

**VWAP Calculation:**
```
VWAP = cumsum(price * volume) / cumsum(volume)
```
Where price = typical price = (high + low + close) / 3

**Detection Method:**
- Compute VWAP from session start
- Check if current price is within LVN zone AND near VWAP (within 0.05% of VWAP)
- Check candle confirmation: bearish engulfilng, pin bar, or shooting star

---

## ENTRY RULES

| Condition | Rule | For SHORT |
|-----------|------|-----------|
| **BOS** | Price breaks significant swing structure | Breaks below prior swing low |
| **FRVP** | Volume profile shows LVN zone in consolidation range | LVN identified above current price |
| **LVN Tap** | Price retraces into LVN zone | Price taps LVN from below |
| **VWAP** | VWAP intersects LVN zone | VWAP is at/near LVN, sloping down |
| **Candle** | Confirmation candle at confluence | Bearish engulfing, pin bar, shooting star |
| **All 4?** | Must be YES for all | YES → ENTER SHORT |

---

## EXIT RULES

| Parameter | Rule | Example (AUD/USD) |
|-----------|------|-------------------|
| **Stop Loss** | Above BOS high OR above top of LVN + 5-10 pip buffer | SL above 0.71762 |
| **Take Profit 1** | Previous swing low inside FRVP range (1:1.5 R:R minimum) | TP1 at 0.71377 |
| **Take Profit 2** | Next HVN below or structural support (1:3 R:R or better) | TP2 at ~0.71200 |
| **Risk per Trade** | Max 1-2% of account equity | Non-negotiable |

---

## TRADE CHECKLIST (All must be YES)

- [ ] BOS confirmed — price has broken a significant swing high/low
- [ ] FRVP applied over the correct consolidation range
- [ ] LVN identified clearly on the volume profile histogram
- [ ] VWAP plotted and intersects the LVN zone at the same price level
- [ ] Bearish (or Bullish) confirmation candle printed at the confluence
- [ ] Stop Loss and Take Profit levels defined BEFORE entering the trade

---

## IMPLEMENTATION APPROACH FOR FREQTRADE

### Challenges:
1. **Volume Profile (FRVP)** — freqtrade doesn't compute volume profiles natively. We need to build a simplified version using rolling window volume-by-price bins.
2. **Swing Highs/Lows (BOS)** — detect using zigzag/local extrema with a lookback window.
3. **VWAP** — freqtrade can compute VWAP but it's session-anchored. We need to reset VWAP at session open.
4. **LVN Detection** — bins with volume < 50% of POC, within the swing range before BOS.

### Simplification for 1h timeframe (adapted from 5m):
- Use 20-bar lookback for swing detection (instead of 5-bar on 5m)
- Compute volume profile over last swing range (consolidation before BOS)
- Identify LVN zones from the profile
- VWAP reset daily (midnight UTC)
- Entry when price enters LVN zone + near VWAP + BOS confirmed + confirmation candle

### Key Parameters:
- `swing_lookback`: bars to identify swing highs/lows (default: 20 for 1h)
- `volume_bins`: number of price bins for volume profile (default: 20)
- `lvn_threshold`: volume threshold relative to POC for LVN (default: 0.5 = 50% of POC)
- `vwap_proximity_pct`: how close price must be to VWAP for confluence (default: 0.05%)
- `stop_buffer_atr`: ATR multiplier for stop loss buffer (default: 0.5)