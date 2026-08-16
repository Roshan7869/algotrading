"""
Flowsurface Charts — Binance WebSocket only with custom indicators.

Mode 1: Binance WebSocket (default) — live real-time candles
Mode 2: Binance REST API — historical backfill bootstrap

Both modes apply custom indicators on the stream:
  EMA stack (9/20/50), VWAP, Bollinger Bands, SuperTrend,
  Volume Delta, CVD, RSI, MACD, Delta Z-Score
"""

import time
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from ui.binance_ws import BinanceStream
from ui.indicators import compute_indicators
from ui.candlestick_charts import render_flowsurface_chart, C
from ui.redis_stream import RedisStream

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

AVAILABLE_PAIRS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "LINK/USDT",
    "DOGE/USDT", "AVAX/USDT", "NEAR/USDT", "DOT/USDT", "SUI/USDT",
    "ADA/USDT", "BCH/USDT", "APT/USDT", "ARB/USDT", "ATOM/USDT",
]

TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "1d"]


def _get_stream(pair: str, tf: str, market: str, source: str = "binance"):
    """Get or create a live stream in session state.

    source="binance" returns BinanceStream, source="redis" returns RedisStream.
    """
    if source == "redis":
        stream_cls = RedisStream
        prefix = "redis_stream"
    else:
        stream_cls = BinanceStream
        prefix = "binance_ws"

    key = f"{prefix}_{pair}_{tf}_{market}"
    stream = st.session_state.get(key)

    if stream is not None:
        if stream.pair == pair and stream.timeframe == tf and stream.market == market:
            if stream.is_connected():
                return stream
        stream.stop()
        del st.session_state[key]

    stream = stream_cls(pair=pair, timeframe=tf, market=market, max_candles=600)
    connected = stream.start()
    if connected:
        st.session_state[key] = stream
        return stream
    else:
        st.warning(f"{stream_cls.__name__} connection failed: {stream._error}")
        stream.stop()
        return None


def _merge_indicator_values(df: pd.DataFrame, ind_values: dict) -> pd.DataFrame:
    """Overlay Rust-computed indicator values on the latest bar.

    Maps Rust IndicatorUpdate field names to chart column names.
    Fields not present in ind_values are left as-is (computed by Python).
    """
    if not ind_values or df.empty:
        return df

    df = df.copy()
    idx = df.index[-1]

    field_map = {
        "rsi_14": "rsi",
        "macd_line": "macd",
        "macd_signal": "macd_signal",
        "macd_histogram": "macd_hist",
        "bb_middle": "bb_mid",
        "bb_upper": "bb_upper",
        "bb_lower": "bb_lower",
        "atr_14": "atr",
        "vwap": "vwap",
    }

    for rust_key, chart_key in field_map.items():
        val = ind_values.get(rust_key)
        if val is not None and chart_key in df.columns:
            df.loc[idx, chart_key] = val

    st = ind_values.get("super_trend")
    if isinstance(st, dict):
        if st.get("value") is not None and "supertrend" in df.columns:
            df.loc[idx, "supertrend"] = st["value"]
        if st.get("direction") is not None and "st_direction" in df.columns:
            df.loc[idx, "st_direction"] = st["direction"]

    vd = ind_values.get("volume_delta")
    if vd is not None and "delta" in df.columns:
        df.loc[idx, "delta"] = vd

    bv = ind_values.get("buy_vol")
    if bv is not None and "buy_vol" in df.columns:
        df.loc[idx, "buy_vol"] = bv

    sv = ind_values.get("sell_vol")
    if sv is not None and "sell_vol" in df.columns:
        df.loc[idx, "sell_vol"] = sv

    cvd_val = ind_values.get("cvd")
    if cvd_val is not None and "cvd" in df.columns:
        df.loc[idx, "cvd"] = cvd_val

    dz = ind_values.get("delta_zscore")
    if dz is not None and "delta_zscore" in df.columns:
        df.loc[idx, "delta_zscore"] = dz

    return df


def _bootstrap_rest(pair: str, tf: str, market: str, limit: int = 500) -> pd.DataFrame:
    """Bootstrap with Binance REST API for initial candle history.

    Uses public REST endpoint - no API key needed.
    """
    import requests

    symbol = pair.replace("/", "").replace(":USDT", "")
    interval_map = {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1h", "2h": "2h", "4h": "4h", "1d": "1d",
    }
    interval = interval_map.get(tf, "1h")

    if market == "futures":
        url = "https://fapi.binance.com/fapi/v1/klines"
    else:
        url = "https://api.binance.com/api/v3/klines"

    try:
        resp = requests.get(url, params={
            "symbol": symbol, "interval": interval, "limit": limit,
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        rows = []
        for k in data:
            rows.append({
                "open_time": k[0],
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "close_time": k[6],
                "quote_volume": float(k[7]),
                "trades": int(k[8]),
                "taker_buy_volume": float(k[9]),
                "taker_buy_quote_volume": float(k[10]),
                "timestamp": pd.Timestamp(k[0], unit="ms", tz="UTC"),
            })

        return pd.DataFrame(rows)

    except Exception as e:
        st.error(f"REST API failed: {e}")
        return pd.DataFrame()


# ─── Page ──────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Flowsurface Charts",
    page_icon="📊",
    layout="wide",
)

st.markdown(f"""
<style>
    .stApp {{ background-color: {C['bg']}; }}
    .stSidebar {{ background-color: #111111; }}
    h1, h2, h3 {{ color: {C['gold']} !important; font-family: 'Courier New', monospace; }}
    .stMarkdown, .stText {{ color: {C['text']}; font-family: 'Courier New', monospace; }}
    .stButton button {{
        background-color: #1a1a1a; color: {C['gold']};
        border: 1px solid #333; font-family: 'Courier New', monospace;
    }}
    .stButton button:hover {{ border-color: {C['gold']}; }}
    .stSelectbox label, .stRadio label, .stCheckbox label {{ color: {C['gold']} !important; }}
    .stRadio > div > div {{ color: {C['text']}; }}
    .stMetric label {{ color: {C['gold']}; }}
    .stMetric value {{ color: #00ff00; }}
</style>
""", unsafe_allow_html=True)

st.title("📊 Flowsurface Charts")
st.markdown("**Binance WebSocket** with custom indicators. No local data — live stream only.")

# ─── Sidebar ──────────────────────────────────────────────────────────────

st.sidebar.markdown("---")
st.sidebar.markdown("## ⚙️ Settings")

market = st.sidebar.radio("🏪 Market", ["futures", "spot"], index=0)
pair = st.sidebar.selectbox("💱 Pair", AVAILABLE_PAIRS, index=0)
tf = st.sidebar.selectbox("⏱ Timeframe", TIMEFRAMES, index=4)

max_candles = st.sidebar.slider("📜 Max Candles", 100, 600, 400, step=50)

auto_refresh = st.sidebar.checkbox("🔄 Auto Refresh (5s)", value=True)

st.sidebar.markdown("---")
st.sidebar.markdown("### 📈 Indicators")

show_ema = st.sidebar.checkbox("EMA Stack (9/20/50)", value=True)
show_vwap = st.sidebar.checkbox("VWAP", value=True)
show_bb = st.sidebar.checkbox("Bollinger Bands", value=True)
show_st = st.sidebar.checkbox("SuperTrend", value=True)
show_vd = st.sidebar.checkbox("Volume Delta (Buy/Sell)", value=True)
show_cvd = st.sidebar.checkbox("CVD Line", value=True)
show_rsi = st.sidebar.checkbox("RSI(14)", value=True)
show_macd = st.sidebar.checkbox("MACD (12/26/9)", value=True)

show = {
    "ema": show_ema, "vwap": show_vwap, "bb": show_bb, "supertrend": show_st,
    "volume_delta": show_vd, "cvd": show_cvd, "rsi": show_rsi, "macd": show_macd,
}

# ─── Data Source ──────────────────────────────────────────────────────────

source = st.sidebar.radio(
    "📡 Data Source",
    ["🔴 Binance WebSocket (Live)", "🟠 Redis Stream (Rust Bridge)", "📦 Binance REST (Bootstrap)"],
    index=0,
)

# ─── Main ─────────────────────────────────────────────────────────────────

if "WebSocket" in source:
    # ── LIVE MODE ──
    stream = _get_stream(pair, tf, market)

    if stream and stream.is_connected():
        status = stream.status()
        col1, col2, col3 = st.columns(3)
        col1.metric("Status", "🟢 Connected")
        col2.metric("Candles", str(status["candles"]))
        col3.metric("Trades", f"{status['trades']:,}")

        # If stream is empty, bootstrap via REST first
        df = stream.get_candles()
        if len(df) < 50:
            st.info("⏳ Bootstrapping candle history via REST API...")
            boot_df = _bootstrap_rest(pair, tf, market, limit=max_candles)
            if not boot_df.empty:
                df = boot_df
                # Also feed seed into stream
                for _, row in boot_df.iterrows():
                    stream._candles[row["open_time"]] = row.to_dict()

        if not df.empty:
            # Compute indicators
            df = compute_indicators(df)
            df = df.tail(max_candles)

            # Render
            fig = render_flowsurface_chart(
                df, pair, tf,
                height=900,
                live=True,
                show=show,
            )
            st.plotly_chart(fig, use_container_width=True)

            # Stats
            latest = df.iloc[-1]
            with st.expander("📊 Latest Bar Details", expanded=False):
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Close", f"${latest.get('close', 0):,.2f}")
                col1.metric("Volume", f"{latest.get('volume', 0):,.0f}")
                col2.metric("RSI", f"{latest.get('rsi', 0):.1f}")
                col2.metric("ATR", f"{latest.get('atr', 0):,.2f}")
                col3.metric("EMA 9", f"${latest.get('ema_9', 0):,.2f}")
                col3.metric("VWAP", f"${latest.get('vwap', 0):,.2f}")
                col4.metric("Delta Z", f"{latest.get('delta_zscore', 0):.2f}")
                if "supertrend" in df.columns and not pd.isna(latest.get("supertrend")):
                    st_dir = "🟢 UP" if latest.get("st_direction", 0) == 1 else "🔴 DOWN"
                    col4.metric("SuperTrend", f"{st_dir}")
        else:
            st.info("⏳ Waiting for candle data... The first bar will appear after the current candle closes.")

        # Auto-refresh
        try:
            from streamlit_autorefresh import st_autorefresh
            if auto_refresh:
                st_autorefresh(interval=5000, key="flowsurface_refresh")
        except ImportError:
            if auto_refresh:
                st.caption("Auto-refresh: install streamlit-autorefresh, or use manual refresh.")

        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

        # Disconnect
        if st.sidebar.button("⛔ Disconnect", use_container_width=True):
            stream.stop()
            key = f"binance_ws_{pair}_{tf}_{market}"
            if key in st.session_state:
                del st.session_state[key]
            st.rerun()

    else:
        st.error(f"❌ WebSocket connection failed for {pair} {tf}")

elif "Redis" in source:
    # ── REDIS STREAM MODE (Rust Bridge) ──
    stream = _get_stream(pair, tf, market, source="redis")

    if stream and stream.is_connected():
        status = stream.status()
        col1, col2, col3 = st.columns(3)
        col1.metric("Status", "🟢 Connected (Rust Bridge)")
        col2.metric("Candles", str(status["candles"]))
        col3.metric("Pair", pair)

        # Bootstrap if empty
        df = stream.get_candles()
        if len(df) < 50:
            st.info("⏳ Bootstrapping candle history via REST API...")
            boot_df = _bootstrap_rest(pair, tf, market, limit=max_candles)
            if not boot_df.empty:
                df = boot_df
                for _, row in boot_df.iterrows():
                    stream._candles[row["open_time"]] = row.to_dict()

        if not df.empty:
            # Base indicators from Python, then overlay Rust-computed values
            df = compute_indicators(df)
            df = _merge_indicator_values(df, stream.get_indicator_values())
            df = df.tail(max_candles)

            fig = render_flowsurface_chart(
                df, pair, tf, height=900, live=True, show=show,
            )
            st.plotly_chart(fig, use_container_width=True)

            latest = df.iloc[-1]
            with st.expander("📊 Latest Bar Details", expanded=False):
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Close", f"${latest.get('close', 0):,.2f}")
                col1.metric("Volume", f"{latest.get('volume', 0):,.0f}")
                col2.metric("RSI", f"{latest.get('rsi', 0):.1f}")
                col2.metric("ATR", f"{latest.get('atr', 0):,.2f}")
                col3.metric("EMA 9", f"${latest.get('ema_9', 0):,.2f}")
                col3.metric("VWAP", f"${latest.get('vwap', 0):,.2f}")
                col4.metric("Delta Z", f"{latest.get('delta_zscore', 0):.2f}")
                if "supertrend" in df.columns and not pd.isna(latest.get("supertrend")):
                    st_dir = "🟢 UP" if latest.get("st_direction", 0) == 1 else "🔴 DOWN"
                    col4.metric("SuperTrend", f"{st_dir}")

        try:
            from streamlit_autorefresh import st_autorefresh
            if auto_refresh:
                st_autorefresh(interval=5000, key="flowsurface_redis_refresh")
        except ImportError:
            if auto_refresh:
                st.caption("Auto-refresh: install streamlit-autorefresh.")

        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

        if st.sidebar.button("⛔ Disconnect Redis", use_container_width=True):
            stream.stop()
            key = f"redis_stream_{pair}_{tf}_{market}"
            if key in st.session_state:
                del st.session_state[key]
            st.rerun()

    else:
        st.error(f"❌ Redis stream connection failed for {pair} {tf}")

elif "REST" in source:
    # ── REST BOOTSTRAP MODE ──
    st.markdown(f"### 📦 REST Bootstrap · {pair} · {tf} · {market}")

    with st.spinner(f"Loading {max_candles} candles from Binance REST API..."):
        df = _bootstrap_rest(pair, tf, market, limit=max_candles)

    if not df.empty:
        # Compute indicators
        df = compute_indicators(df)
        df = df.tail(max_candles)

        # Render
        fig = render_flowsurface_chart(
            df, pair, tf,
            height=900,
            live=False,
            show=show,
        )
        st.plotly_chart(fig, use_container_width=True)

        # Summary
        latest = df.iloc[-1]
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Price", f"${latest['close']:,.2f}")
        col2.metric("RSI", f"{latest.get('rsi', 0):.1f}")
        col3.metric("VWAP", f"${latest.get('vwap', 0):,.2f}")
        col4.metric("ATR", f"${latest.get('atr', 0):,.2f}")
        col5.metric("Delta Z", f"{latest.get('delta_zscore', 0):.2f}")

        with st.expander("📋 Raw Data", expanded=False):
            cols = ["timestamp", "open", "high", "low", "close", "volume",
                     "buy_vol", "sell_vol", "delta", "cvd", "rsi", "atr",
                     "ema_9", "ema_20", "ema_50", "vwap",
                     "bb_upper", "bb_lower", "supertrend", "st_direction"]
            display_cols = [c for c in cols if c in df.columns]
            st.dataframe(df[display_cols].tail(100), use_container_width=True)
    else:
        st.error("REST API returned no data. Check pair and timeframe.")

# ─── Export ────────────────────────────────────────────────────────────────

st.divider()
with st.expander("📤 Export to Flowsurface (NDJSON)"):
    st.markdown("Export current chart data to Flowsurface desktop app format.")
    if st.button("Export Current View", use_container_width=True):
        from engine.flowsurface_bridge import export_ohlcv
        try:
            out_dir = Path.home() / ".local" / "share" / "flowsurface" / "market_data"
            path = export_ohlcv(pair, tf, output_dir=out_dir, max_rows=5000)
            st.success(f"Exported: {path.name}")
        except Exception as e:
            st.warning(f"Export failed: {e}")