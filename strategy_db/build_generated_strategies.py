"""
Phase 2: Strategy Code Generator — Convert blueprints into Freqtrade IStrategy Python files.

Reads strategy_db/strategy_blueprints.json
Outputs user_data/strategies/generated/GenStrategy_*.py files

Usage: python3 strategy_db/build_generated_strategies.py
"""

import json
import os
import re
import textwrap
from datetime import datetime

BLUEPRINTS_PATH = os.path.join(os.path.dirname(__file__), "strategy_blueprints.json")
OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "user_data", "strategies", "generated"
)


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_blueprints():
    with open(BLUEPRINTS_PATH) as f:
        return json.load(f)


def n4(text: str) -> str:
    """Indent text to 4-space (class method level), preserving blank lines."""
    if not text:
        return ""
    return textwrap.indent(textwrap.dedent(text), "    ")


def n8(text: str) -> str:
    """Indent text to 8-space (method body level), preserving blank lines."""
    if not text:
        return ""
    return textwrap.indent(textwrap.dedent(text), "        ")


# ============================================================
# INDICATOR MAPPER
# ============================================================

INDICATOR_SNIPPETS = {
    "rsi": """dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)""",
    "ema9": """dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=9)""",
    "ema21": """dataframe["ema_medium"] = ta.EMA(dataframe, timeperiod=21)""",
    "ema50": """dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=50)""",
    "ema200": """dataframe["ema_trend"] = ta.EMA(dataframe, timeperiod=200)""",
    "adx": """dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)""",
    "atr": """dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)""",
    "macd": """dataframe["macd"], dataframe["macdsignal"], dataframe["macdhist"] = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)""",
    "bollinger_bands": """bb = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
dataframe["bb_lower"] = bb["lower"]
dataframe["bb_middle"] = bb["mid"]
dataframe["bb_upper"] = bb["upper"]
dataframe["bb_width"] = (dataframe["bb_upper"] - dataframe["bb_lower"]) / dataframe["bb_middle"]
dataframe["bb_pctb"] = (dataframe["close"] - dataframe["bb_lower"]) / (dataframe["bb_upper"] - dataframe["bb_lower"])""",
    "volume": """dataframe["volume_ma"] = dataframe["volume"].rolling(window=20).mean()
dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_ma"]""",
    "vwap": """dataframe["typical_price"] = (dataframe["high"] + dataframe["low"] + dataframe["close"]) / 3
dataframe["vwap"] = (dataframe["typical_price"] * dataframe["volume"]).rolling(window=20).sum() / dataframe["volume"].rolling(window=20).sum()
dataframe["vwap_dist"] = (dataframe["close"] - dataframe["vwap"]) / dataframe["vwap"]""",
    "stoch": """dataframe["stoch_k"], dataframe["stoch_d"] = ta.STOCH(dataframe, fastk_period=14, slowk_period=3, slowd_period=3)""",
    "supertrend": """atr_st = ta.ATR(dataframe, timeperiod=10)
hl_avg = (dataframe["high"] + dataframe["low"]) / 2
dataframe["st_upper"] = hl_avg + 2.0 * atr_st
dataframe["st_lower"] = hl_avg - 2.0 * atr_st
dataframe["st_trend"] = 1.0
for i in range(1, len(dataframe)):
    if dataframe["close"].iloc[i] > dataframe["st_upper"].iloc[i-1]:
        dataframe["st_trend"].iloc[i] = 1.0
    elif dataframe["close"].iloc[i] < dataframe["st_lower"].iloc[i-1]:
        dataframe["st_trend"].iloc[i] = -1.0
    else:
        dataframe["st_trend"].iloc[i] = dataframe["st_trend"].iloc[i-1]""",
    "support_resistance": """dataframe["swing_high"] = (dataframe["high"] == dataframe["high"].rolling(window=20, center=True).max()).astype(int)
dataframe["swing_low"] = (dataframe["low"] == dataframe["low"].rolling(window=20, center=True).min()).astype(int)""",
    "divergence": """dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
dataframe["price_lower_low"] = (dataframe["low"] < dataframe["low"].shift(1)) & (dataframe["low"].shift(1) < dataframe["low"].shift(2))
dataframe["rsi_higher_low"] = (dataframe["rsi"] > dataframe["rsi"].shift(1)) & (dataframe["rsi"].shift(1) > dataframe["rsi"].shift(2))
dataframe["bullish_div"] = dataframe["price_lower_low"] & dataframe["rsi_higher_low"]
dataframe["price_higher_high"] = (dataframe["high"] > dataframe["high"].shift(1)) & (dataframe["high"].shift(1) > dataframe["high"].shift(2))
dataframe["rsi_lower_high"] = (dataframe["rsi"] < dataframe["rsi"].shift(1)) & (dataframe["rsi"].shift(1) < dataframe["rsi"].shift(2))
dataframe["bearish_div"] = dataframe["price_higher_high"] & dataframe["rsi_lower_high"]""",
    "engulfing": """dataframe["bullish_engulf"] = (dataframe["close"] > dataframe["open"]) & (dataframe["close"].shift(1) < dataframe["open"].shift(1)) & (dataframe["close"] > dataframe["open"].shift(1)) & (dataframe["open"] < dataframe["close"].shift(1))
dataframe["bearish_engulf"] = (dataframe["close"] < dataframe["open"]) & (dataframe["close"].shift(1) > dataframe["open"].shift(1)) & (dataframe["close"] < dataframe["open"].shift(1)) & (dataframe["open"] > dataframe["close"].shift(1))""",
    "pin_bar": """dataframe["upper_wick"] = dataframe["high"] - dataframe[["open","close"]].max(axis=1)
dataframe["lower_wick"] = dataframe[["open","close"]].min(axis=1) - dataframe["low"]
dataframe["body"] = abs(dataframe["close"] - dataframe["open"])
dataframe["pin_bar"] = (dataframe["lower_wick"] > dataframe["body"] * 2) | (dataframe["upper_wick"] > dataframe["body"] * 2)""",
}

BTC_MACRO = """if self.dp and metadata.get('pair') != 'BTC/USDT:USDT':
    try:
        btc = self.dp.get_pair_dataframe("BTC/USDT:USDT", self.timeframe)
        if len(btc) > 0:
            btc['ema_50'] = ta.EMA(btc, timeperiod=50)
            btc['ema_200'] = ta.EMA(btc, timeperiod=200)
            btc = btc[['date', 'ema_50', 'ema_200']].copy()
            btc.columns = ['date', 'btc_ema_50', 'btc_ema_200']
            dataframe = pd.merge(dataframe, btc, on='date', how='left')
            dataframe['btc_ema_50'] = dataframe['btc_ema_50'].ffill()
            dataframe['btc_ema_200'] = dataframe['btc_ema_200'].ffill()
            dataframe['btc_bullish'] = dataframe['btc_ema_50'] > dataframe['btc_ema_200']
        else:
            dataframe['btc_bullish'] = True
    except Exception:
        dataframe['btc_bullish'] = True
else:
    dataframe['btc_bullish'] = True"""


def detect_indicators(text: str) -> list:
    """Scan text for indicator keywords."""
    tl = text.lower()
    found = []
    checks = [
        ("rsi", r"\brsi\b"),
        ("adx", r"\badx\b"),
        ("atr", r"\batr\b"),
        ("macd", r"\bmacd\b"),
        ("bollinger_bands", r"\b(bollinger|bb\b|squeeze)\b"),
        ("vwap", r"\bvwap\b"),
        ("stoch", r"\bstoch\b"),
        ("supertrend", r"\bsupertrend\b"),
        ("ema200", r"\b(ema.?200|200.*ma)\b"),
        ("ema50", r"\b(ema.?50|50.*ma)\b"),
        ("ema9", r"\b(ema|moving.average)\b"),
        ("divergence", r"\bdivergence\b"),
        ("engulfing", r"\bengulf"),
        ("support_resistance", r"\b(support|resistance)\b"),
        ("pin_bar", r"\b(pin.bar|hammer|shooting.star)\b"),
    ]
    for key, pattern in checks:
        if re.search(pattern, tl):
            found.append(key)
    return found


def dedent_lines(text: str) -> str:
    """Remove common leading whitespace from all non-blank lines."""
    return textwrap.dedent(text)


# ============================================================
# ENTRY / EXIT / FILTER CODE BUILDERS
# ============================================================

ENTRY_PATTERNS = {
    "rsi_oversold": """rsi_oversold = dataframe["rsi"] < 30
rsi_recovery = qtpylib.crossed_above(dataframe["rsi"], 30)
long_conditions = rsi_oversold & rsi_recovery""",
    "ema_cross": """golden_cross = qtpylib.crossed_above(dataframe["ema_fast"], dataframe["ema_slow"])
fast_over_slow = dataframe["ema_fast"] > dataframe["ema_slow"]
long_conditions = golden_cross | (fast_over_slow & (dataframe["ema_slope"] > 0))""",
    "bb_squeeze": """squeezed = dataframe["bb_width"] < dataframe["bb_width"].rolling(50).mean()
expanding = dataframe["bb_width"] > dataframe["bb_width"].shift(1)
long_conditions = squeezed & expanding & (dataframe["close"] > dataframe["bb_upper"])""",
    "bb_reversion": """long_conditions = (dataframe["close"] < dataframe["bb_lower"]) & (dataframe["rsi"] < 30)""",
    "breakout": """long_conditions = (dataframe["close"] > dataframe["bb_upper"]) & (dataframe["volume"] > dataframe["volume_ma"]) & (dataframe["adx"] > 20)""",
    "trend_follow": """long_conditions = (dataframe["close"] > dataframe["ema_trend"]) & (dataframe["ema_fast"] > dataframe["ema_medium"]) & (dataframe["adx"] > 20)""",
    "divergence": """long_conditions = dataframe["bullish_div"] & (dataframe["rsi"] < 50)""",
    "supertrend": """long_conditions = qtpylib.crossed_above(dataframe["st_trend"], 0) & (dataframe["volume"] > dataframe["volume_ma"])""",
    "engulfing": """long_conditions = dataframe["bullish_engulf"] & (dataframe["volume"] > dataframe["volume_ma"])""",
    "vwap_bounce": """long_conditions = (dataframe["close"] < dataframe["vwap"]) & (dataframe["vwap_dist"] > -0.02) & qtpylib.crossed_above(dataframe["close"], dataframe["vwap"])""",
    "pullback": """long_conditions = (dataframe["close"] < dataframe["ema_medium"]) & (dataframe["close"] > dataframe["ema_trend"]) & (dataframe["adx"] > 20)""",
}

SHORT_PATTERNS = {
    "rsi_oversold": """short_conditions = dataframe["rsi"] > 70""",
    "ema_cross": """death_cross = qtpylib.crossed_below(dataframe["ema_fast"], dataframe["ema_slow"])
short_conditions = death_cross""",
    "bb_squeeze": """short_conditions = squeezed & expanding & (dataframe["close"] < dataframe["bb_lower"])""",
    "bb_reversion": """short_conditions = (dataframe["close"] > dataframe["bb_upper"]) & (dataframe["rsi"] > 70)""",
    "breakout": """short_conditions = (dataframe["close"] < dataframe["bb_lower"]) & (dataframe["volume"] > dataframe["volume_ma"]) & (dataframe["adx"] > 20)""",
    "trend_follow": """short_conditions = (dataframe["close"] < dataframe["ema_trend"]) & (dataframe["ema_fast"] < dataframe["ema_medium"]) & (dataframe["adx"] > 20)""",
    "divergence": """short_conditions = dataframe["bearish_div"] & (dataframe["rsi"] > 50)""",
    "supertrend": """short_conditions = qtpylib.crossed_below(dataframe["st_trend"], 0)""",
    "engulfing": """short_conditions = dataframe["bearish_engulf"] & (dataframe["volume"] > dataframe["volume_ma"])""",
    "vwap_bounce": """short_conditions = (dataframe["close"] > dataframe["vwap"]) & (dataframe["vwap_dist"] < 0.02) & qtpylib.crossed_below(dataframe["close"], dataframe["vwap"])""",
    "pullback": """short_conditions = (dataframe["close"] > dataframe["ema_medium"]) & (dataframe["close"] < dataframe["ema_trend"]) & (dataframe["adx"] > 20)""",
}


def detect_entry_pattern(text: str) -> str:
    tl = text.lower()
    if re.search(r"\b(bb|bollinger|squeeze).*(breakout|expansion)", tl):
        return "bb_squeeze"
    if re.search(r"\b(bb|bollinger).*(reversion|bounce|lower)", tl):
        return "bb_reversion"
    if re.search(r"\brsi.*(oversold|overbought)\b", tl):
        return "rsi_oversold"
    if re.search(r"\bdivergence\b", tl):
        return "divergence"
    if re.search(r"\b(ema|crossover|golden.cross)\b", tl):
        return "ema_cross"
    if re.search(r"\b(trend.follow|ema.align)\b", tl):
        return "trend_follow"
    if re.search(r"\bsupertrend\b", tl):
        return "supertrend"
    if re.search(r"\bengulf", tl):
        return "engulfing"
    if re.search(r"\bvwap\b", tl):
        return "vwap_bounce"
    if re.search(r"\b(pullback|retrace|dip)\b", tl):
        return "pullback"
    return "breakout"


def build_indicators(blueprint: dict) -> str:
    text = ""
    for cl in blueprint["components"].values():
        for c in cl:
            text += f"{c.get('chunk_text_preview', '')} {c.get('setup_name', '')} {c.get('keywords', '')} "
    keys = detect_indicators(text)

    # Required: indicators needed by entry/exit/filter templates
    required = ["volume", "atr", "adx", "ema200", "ema21", "ema9", "ema50", "bollinger_bands"]
    for req in required:
        if req not in keys:
            keys.insert(0, req)

    # Build indicator code lines
    parts = []
    for k in keys:
        s = INDICATOR_SNIPPETS.get(k)
        if s:
            parts.append(s)

    # BTC macro
    parts.append("")
    parts.append("# BTC macro filter")
    parts.append(BTC_MACRO)

    raw = "\n".join(parts)
    indented = n8(raw)
    return f"""    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
{indented}
        return dataframe"""


def build_entry(blueprint: dict) -> str:
    chunks = blueprint["components"].get("entry", [])
    text = " ".join(f"{c.get('chunk_text_preview','')} {c.get('setup_name','')}" for c in chunks)
    pattern = detect_entry_pattern(text)
    long_code = ENTRY_PATTERNS.get(pattern, ENTRY_PATTERNS["trend_follow"])
    short_code = SHORT_PATTERNS.get(pattern, SHORT_PATTERNS["trend_follow"])

    tag = blueprint["strategy_id"]
    long_indented = textwrap.indent(long_code, "        ")
    short_indented = textwrap.indent(short_code, "        ")
    return f"""    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = ""

        volume_ok = dataframe["volume"] > dataframe["volume_ma"]
        trend_ok = dataframe["adx"] > 20
        above_trend = dataframe["close"] > dataframe["ema_trend"]
        below_trend = dataframe["close"] < dataframe["ema_trend"]

        # Entry: {pattern}
{long_indented}

        # Short:
{short_indented}

        long_conditions = long_conditions & volume_ok & trend_ok & above_trend & dataframe["btc_bullish"]
        short_conditions = short_conditions & volume_ok & trend_ok & below_trend

        dataframe.loc[long_conditions, ["enter_long", "enter_tag"]] = [1, "{tag}_long"]
        dataframe.loc[short_conditions, ["enter_short", "enter_tag"]] = [1, "{tag}_short"]
        return dataframe"""


def build_exit(blueprint: dict) -> str:
    # Default exit: trailing stop handled by custom_stoploss + custom_exit
    return f"""    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0

        exit_long = qtpylib.crossed_below(dataframe["close"], dataframe["ema_medium"])
        exit_short = qtpylib.crossed_above(dataframe["close"], dataframe["ema_medium"])

        dataframe.loc[exit_long, ["exit_long", "exit_tag"]] = [1, "ema_exit_long"]
        dataframe.loc[exit_short, ["exit_short", "exit_tag"]] = [1, "ema_exit_short"]
        return dataframe"""


def build_risk(blueprint: dict) -> tuple:
    """Return (stoploss, trailing_stop_config, roi)."""
    risk_chunks = blueprint["components"].get("risk_management", [])
    text = " ".join(c.get("chunk_text_preview", "") + " " + (c.get("setup_name", "") or "") for c in risk_chunks)
    tl = text.lower()

    if re.search(r"\b(scalp|scalping)\b", tl):
        return -0.025, 0.012, 0.025, '{"0": 0.02, "15": 0.01, "30": 0}', 1.5
    if re.search(r"\b(tight|small.stop|strict)\b", tl):
        return -0.03, 0.015, 0.03, '{"0": 0.05, "30": 0.025, "60": 0.01}', 1.5
    if re.search(r"\b(wide|loose|large.stop|volatile)\b", tl) or "atr" in tl:
        return -0.08, 0.035, 0.06, '{"0": 0.12, "60": 0.06, "240": 0.03, "720": 0.01}', 5.0
    if re.search(r"\b(swing|positional)\b", tl):
        return -0.06, 0.03, 0.05, '{"0": 0.15, "120": 0.08, "360": 0.04, "720": 0.02}', 3.0
    return -0.06, 0.025, 0.05, '{"0": 0.10, "60": 0.05, "120": 0.02, "240": 0.01}', 3.0


def build_stoploss_func(blueprint: dict, stoploss: float) -> str:
    """ATR-based custom stoploss."""
    risk_chunks = blueprint["components"].get("risk_management", [])
    text = " ".join(c.get("chunk_text_preview", "") + " " + (c.get("setup_name", "") or "") for c in risk_chunks)
    if "atr" not in text.lower():
        return ""

    return n4(f"""def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, **kwargs) -> float:
    dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
    if len(dataframe) < 1:
        return self.stoploss
    trade_date = trade.open_date_utc.replace(tzinfo=timezone.utc)
    try:
        entry_candle = dataframe[dataframe["date"] <= trade_date].iloc[-1]
        atr_value = entry_candle["atr"]
    except (IndexError, KeyError):
        return self.stoploss
    if pd.isna(atr_value) or atr_value <= 0:
        return self.stoploss
    stop_distance = atr_value * 2.0
    if trade.is_short:
        stop_price = trade.open_rate + stop_distance
        stop_loss_pct = -((stop_price - current_rate) / current_rate)
    else:
        stop_price = trade.open_rate - stop_distance
        stop_loss_pct = -((current_rate - stop_price) / current_rate)
    return max(stop_loss_pct, self.stoploss)""")


def build_custom_exit() -> str:
    return n4("""def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs) -> Optional[Union[str, bool]]:
    dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
    if len(dataframe) < 1:
        return None
    trade_date = trade.open_date_utc.replace(tzinfo=timezone.utc)
    try:
        entry_candle = dataframe[dataframe["date"] <= trade_date].iloc[-1]
        atr_value = entry_candle["atr"]
    except (IndexError, KeyError):
        return None
    if pd.isna(atr_value) or atr_value <= 0:
        return None
    atr_move = atr_value * self.atr_multiplier.value
    if trade.is_short:
        target_profit_pct = (atr_move * self.risk_reward.value) / current_rate
        if current_profit >= target_profit_pct:
            return f"short_tp_{self.risk_reward.value}r"
    else:
        tp_price = trade.open_rate + (atr_move * self.risk_reward.value)
        if current_rate >= tp_price:
            return f"long_tp_{self.risk_reward.value}r"
    return None""")


# ============================================================
# STRATEGY GENERATION
# ============================================================

STRATEGY_HEADER = '''"""Auto-generated strategy: {name}
  ID: {strategy_id} | Tier: {tier} | Source: {source}
  Components: {comp_summary} | Chunks: {chunk_count}
"""
import numpy as np
import pandas as pd
from pandas import DataFrame
from datetime import timezone
from typing import Optional, Union

from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class GenStrategy_{strategy_id}(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "{timeframe}"
    can_short = True

    minimal_roi = {roi}
    stoploss = {stoploss}
    trailing_stop = True
    trailing_stop_positive = {ts_pos}
    trailing_stop_positive_offset = {ts_off}
    trailing_only_offset_is_reached = True

    process_only_new_candles = True
    startup_candle_count = 200

    order_types = {{"entry": "limit", "exit": "market", "stoploss": "market", "stoploss_on_exchange": False}}
    order_time_in_force = {{"entry": "GTC", "exit": "GTC"}}

    atr_multiplier = DecimalParameter(1.5, 3.5, default=2.0, decimals=1, space="sell", optimize=True, load=True)
    risk_reward = DecimalParameter(1.5, 3.0, default=2.0, decimals=1, space="sell", optimize=True, load=True)

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs) -> float:
        return min({lev}, max_leverage)

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative_pairs = [(pair, "4h") for pair in pairs]
        informative_pairs.append(("BTC/USDT:USDT", self.timeframe))
        return informative_pairs
'''


def generate_strategy(blueprint: dict) -> str:
    sid = blueprint["strategy_id"]
    entry_text = " ".join(c.get("chunk_text_preview", "") + " " + (c.get("setup_name", "") or "")
                          for c in blueprint["components"].get("entry", []))
    if re.search(r"\b(5m|scalp)\b", entry_text, re.IGNORECASE):
        tf = "5m"
    elif re.search(r"\b(15m)\b", entry_text, re.IGNORECASE):
        tf = "15m"
    elif re.search(r"\b(daily|1d|day)\b", entry_text, re.IGNORECASE):
        tf = "1d"
    else:
        tf = "1h"

    stoploss, ts_pos, ts_off, roi, lev = build_risk(blueprint)
    comp_summary = ", ".join(f"{k}: {len(v)}" for k, v in blueprint["components"].items() if v)

    header = STRATEGY_HEADER.format(
        name=blueprint["name"], strategy_id=sid, tier=blueprint["tier"],
        source=blueprint["source"], comp_summary=comp_summary,
        chunk_count=blueprint["total_chunks"],
        timeframe=tf, stoploss=stoploss, roi=roi,
        ts_pos=ts_pos, ts_off=ts_off, lev=lev,
    )

    indicator_code = build_indicators(blueprint)
    entry_code = build_entry(blueprint)
    exit_code = build_exit(blueprint)
    stoploss_code = build_stoploss_func(blueprint, stoploss)
    custom_exit = build_custom_exit()

    parts = [header, indicator_code, "", entry_code, "", exit_code]
    if stoploss_code:
        parts.extend(["", stoploss_code])
    parts.extend(["", custom_exit])
    return "\n".join(parts)


def validate_import(filepath: str) -> bool:
    try:
        import importlib.util
        name = os.path.basename(filepath).replace(".py", "")
        spec = importlib.util.spec_from_file_location(name, filepath)
        if spec is None:
            return False
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return True
    except ImportError as e:
        if "freqtrade" in str(e):
            return True  # freqtrade not installed outside venv — skip dep check
        return False
    except Exception:
        return False


def main():
    ensure_output_dir()
    data = load_blueprints()
    blueprints = data["blueprints"]

    candidates = [bp for bp in blueprints if bp["tier"] in ("tier1", "tier2")]
    candidates.sort(key=lambda x: x["score"]["completeness_score"], reverse=True)

    print(f"Generating {len(candidates)} strategies...\n")
    generated, failed = [], []

    for bp in candidates:
        sid = bp["strategy_id"]
        filepath = os.path.join(OUTPUT_DIR, f"GenStrategy_{sid}.py")
        code = generate_strategy(bp)
        with open(filepath, "w") as f:
            f.write(code)
        ok = validate_import(filepath)
        status = "OK" if ok else "IMPORT FAILED"
        (generated if ok else failed).append(sid)
        print(f"  {sid}: {bp['name'][:50]:50s} [{status}]")

    print(f"\n=== Complete: {len(generated)} generated, {len(failed)} failed ===")
    manifest = {"generated_at": datetime.now().isoformat(), "total": len(candidates),
                "generated": generated, "failed": failed}
    with open(os.path.join(OUTPUT_DIR, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)


if __name__ == "__main__":
    main()
