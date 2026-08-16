"""
Kronos+ChromaDB Shared Indicators.

Candlestick pattern detection (Kronos engine),
session filters (ChromaDB kill zones),
volatility regime filter, and ATR risk management.
"""
import numpy as np
import pandas as pd
import talib.abstract as ta


# ── Kronos: Candlestick Pattern Detection ──────────────────────────

def detect_candle_patterns(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Add candlestick pattern columns using TA-Lib pattern recognition."""
    # Single-candle patterns
    dataframe["cdl_doji"] = ta.CDLDOJI(dataframe["open"], dataframe["high"],
                                       dataframe["low"], dataframe["close"])
    dataframe["cdl_hammer"] = ta.CDLHAMMER(dataframe["open"], dataframe["high"],
                                           dataframe["low"], dataframe["close"])
    dataframe["cdl_shooting_star"] = ta.CDLSHOOTINGSTAR(dataframe["open"], dataframe["high"],
                                                         dataframe["low"], dataframe["close"])
    dataframe["cdl_marubozu"] = ta.CDLMARUBOZU(dataframe["open"], dataframe["high"],
                                               dataframe["low"], dataframe["close"])

    # Two-candle patterns
    dataframe["cdl_engulfing"] = ta.CDLENGULFING(dataframe["open"], dataframe["high"],
                                                  dataframe["low"], dataframe["close"])
    dataframe["cdl_harami"] = ta.CDLHARAMI(dataframe["open"], dataframe["high"],
                                           dataframe["low"], dataframe["close"])
    dataframe["cdl_piercing"] = ta.CDLPIERCING(dataframe["open"], dataframe["high"],
                                               dataframe["low"], dataframe["close"])
    dataframe["cdl_dark_cloud"] = ta.CDLDARKCLOUDCOVER(dataframe["open"], dataframe["high"],
                                                        dataframe["low"], dataframe["close"])

    # Three-candle patterns
    dataframe["cdl_morning_star"] = ta.CDLMORNINGSTAR(dataframe["open"], dataframe["high"],
                                                       dataframe["low"], dataframe["close"],
                                                       penetration=0.3)
    dataframe["cdl_evening_star"] = ta.CDLEVENINGSTAR(dataframe["open"], dataframe["high"],
                                                       dataframe["low"], dataframe["close"],
                                                       penetration=0.3)
    dataframe["cdl_3_white_soldiers"] = ta.CDL3WHITESOLDIERS(dataframe["open"], dataframe["high"],
                                                              dataframe["low"], dataframe["close"])
    dataframe["cdl_3_black_crows"] = ta.CDL3BLACKCROWS(dataframe["open"], dataframe["high"],
                                                        dataframe["low"], dataframe["close"])

    return dataframe


def candle_score(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Aggregate candlestick signals into bullish/bearish scores."""
    # Bullish patterns
    bullish = (
        dataframe["cdl_hammer"].clip(0, 1) +
        dataframe["cdl_engulfing"].clip(0, 1) +
        dataframe["cdl_morning_star"].clip(0, 1) +
        dataframe["cdl_piercing"].clip(0, 1) +
        dataframe["cdl_3_white_soldiers"].clip(0, 1) +
        dataframe["cdl_harami"].clip(0, 1)
    )
    # Bearish patterns
    bearish = (
        (-dataframe["cdl_shooting_star"].clip(-1, 0)) +
        (-dataframe["cdl_engulfing"].clip(-1, 0)) +
        (-dataframe["cdl_evening_star"].clip(-1, 0)) +
        (-dataframe["cdl_dark_cloud"].clip(-1, 0)) +
        (-dataframe["cdl_3_black_crows"].clip(-1, 0)) +
        (-dataframe["cdl_harami"].clip(-1, 0))
    )
    dataframe["candle_bullish"] = bullish
    dataframe["candle_bearish"] = bearish
    dataframe["candle_signal"] = bullish - bearish
    return dataframe


# ── ChromaDB: Session Filters ──────────────────────────────────────

def add_session_filters(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Add session-based filters from ChromaDB kill zone concepts.

    Maps candle time to trading sessions with probability ratings.
    """
    hour = dataframe["date"].dt.hour
    # Session masks (UTC → approximate crypto market)
    asian_session = (hour >= 0) & (hour < 8)       # Low volatility
    london_open = (hour >= 7) & (hour < 9)          # Kill zone
    london_ny_overlap = (hour >= 13) & (hour < 17)  # Peak volume
    ny_afternoon = (hour >= 17) & (hour < 21)       # Late push

    # Probability ratings from ChromaDB session chunks
    dataframe["session_high_prob"] = london_open | london_ny_overlap
    dataframe["session_med_prob"] = ny_afternoon
    dataframe["session_low_prob"] = asian_session
    # Everything else (NY morning pre-open, etc.) = neutral
    dataframe["session_high_prob"] = dataframe["session_high_prob"].astype(int)
    dataframe["session_med_prob"] = dataframe["session_med_prob"].astype(int)
    dataframe["session_low_prob"] = dataframe["session_low_prob"].astype(int)

    return dataframe


# ── ChromaDB: Volatility Regime Filter ────────────────────────────

def add_regime_filter(dataframe: pd.DataFrame, atr_period: int = 20) -> pd.DataFrame:
    """Add volatility regime detection from ChromaDB filter concepts."""
    # ATR percentile rank for regime detection
    atr = dataframe["atr"] if "atr" in dataframe.columns else ta.ATR(dataframe, timeperiod=14)
    dataframe["atr_rank"] = atr.rank(pct=True)
    # Low volatility: ATR in bottom 20% (squeeze → breakout expected)
    dataframe["regime_low_vol"] = (dataframe["atr_rank"] < 0.20).astype(int)
    # High volatility: ATR in top 20% (trending / risky)
    dataframe["regime_high_vol"] = (dataframe["atr_rank"] > 0.80).astype(int)
    # Normal volatility
    dataframe["regime_normal"] = (
        (~dataframe["regime_low_vol"].astype(bool)) &
        (~dataframe["regime_high_vol"].astype(bool))
    ).astype(int)

    # Volume regime
    if "volume_ratio" not in dataframe.columns:
        vol_mean = ta.SMA(dataframe["volume"], timeperiod=20)
        dataframe["volume_ratio"] = (dataframe["volume"] / vol_mean).replace([np.inf, -np.inf], 1).fillna(1)
    dataframe["volume_surge"] = (dataframe["volume_ratio"] > 1.5).astype(int)
    dataframe["volume_anemic"] = (dataframe["volume_ratio"] < 0.5).astype(int)

    return dataframe


# ── ChromaDB: Risk Management ─────────────────────────────────────

def atr_stoploss_pct(dataframe: pd.DataFrame, atr_mult: float = 2.0) -> float:
    """Calculate ATR-based stoploss percentage for the latest candle."""
    atr = dataframe["atr"].iloc[-1] if "atr" in dataframe.columns else 0
    close = dataframe["close"].iloc[-1]
    if close > 0 and atr > 0:
        return min(max(atr * atr_mult / close, 0.02), 0.15)
    return 0.06  # fallback to default


# ── Confluence Boost: Combine candle + session + regime ───────────

def chromadb_confluence_boost(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Compute ChromaDB-derived confluence boost signals.

    Returns signals that can be used as additional confluence factors
    in populate_entry_trend.
    """
    # Candle confirmation: strong bullish pattern + good session
    candle_confirmed_long = (
        (dataframe["candle_bullish"] > 0) &
        (dataframe["session_high_prob"] == 1)
    ).astype(int)

    candle_confirmed_short = (
        (dataframe["candle_bearish"] > 0) &
        (dataframe["session_high_prob"] == 1)
    ).astype(int)

    # Regime alignment: enter when regime matches signal type
    # Longs better in normal/low vol, shorts can work in any regime
    regime_ok_long = (
        dataframe["regime_normal"] | dataframe["regime_low_vol"]
    ).astype(int)

    return candle_confirmed_long, candle_confirmed_short, regime_ok_long
