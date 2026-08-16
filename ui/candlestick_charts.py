"""
candlestick_charts.py — Plotly chart rendering for Flowsurface.

Renders candlestick charts with custom indicators overlaid:
  - EMA stack (9, 20, 50)
  - VWAP
  - Bollinger Bands
  - SuperTrend
  - Volume Delta (buy/sell bars)
  - CVD
  - Delta Z-Score
  - RSI subplot
  - MACD subplot
  - Entry signal markers (from strategy logic)

Bloomberg dark theme. CPU-optimized for i5-5300U.
"""

import logging
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

log = logging.getLogger(__name__)

# Bloomberg dark theme
C = {
    "bg": "#0a0a0a", "grid": "#1a1a1a", "text": "#cccccc",
    "gold": "#ffd700", "green": "#00ff88", "red": "#ff4444",
    "blue": "#4488ff", "purple": "#bb77ff", "orange": "#ff8c00",
    "cyan": "#00e5ff", "pink": "#ff69b4",
}


def render_flowsurface_chart(
    df: pd.DataFrame,
    pair: str,
    timeframe: str,
    height: int = 900,
    live: bool = False,
    show: Optional[dict] = None,
) -> go.Figure:
    """Main Flowsurface chart: candlestick + overlays + subplots.

    Args:
        df: DataFrame with OHLCV + indicator columns
        pair: e.g. 'BTC/USDT'
        timeframe: e.g. '1h'
        height: chart height in px
        live: show LIVE badge
        show: dict of indicator toggles, default all True
    """
    if show is None:
        show = {
            "ema": True, "vwap": True, "bb": True, "supertrend": True,
            "volume_delta": True, "cvd": True, "rsi": True, "macd": True,
        }

    if df.empty:
        fig = go.Figure()
        fig.update_layout(title="No data", template="plotly_dark", height=height)
        return fig

    # Trim to last N candles for CPU performance
    max_display = 500
    if len(df) > max_display:
        df = df.tail(max_display).copy()

    x = df["timestamp"] if "timestamp" in df.columns else df.index

    # Subplot rows: candlestick + BB, volume, CVD, RSI, MACD
    rows = []
    heights = []
    # Row 1: Price chart (always)
    rows.append(True)
    heights.append(0.45)
    # Row 2: Volume
    rows.append(True)
    heights.append(0.12)
    # Row 3: CVD
    if show.get("cvd"):
        rows.append(True)
        heights.append(0.10)
    # Row 4: RSI
    if show.get("rsi"):
        rows.append(True)
        heights.append(0.10)
    # Row 5: MACD
    if show.get("macd"):
        rows.append(True)
        heights.append(0.10)

    n_rows = len(rows)
    fig = make_subplots(
        rows=n_rows, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=heights,
    )

    # ── Row 1: Candlestick + overlays ──
    fig.add_trace(
        go.Candlestick(
            x=x, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
            name="OHLCV",
            increasing_line_color=C["green"], decreasing_line_color=C["red"],
            increasing_fillcolor=C["green"], decreasing_fillcolor=C["red"],
        ),
        row=1, col=1,
    )

    # EMA stack
    if show.get("ema"):
        for ema_col, color, width in [
            ("ema_9", C["cyan"], 1.2),
            ("ema_20", C["orange"], 1.0),
            ("ema_50", C["pink"], 0.8),
        ]:
            if ema_col in df.columns:
                fig.add_trace(
                    go.Scatter(x=x, y=df[ema_col], name=ema_col.upper(), line=dict(color=color, width=width), opacity=0.7),
                    row=1, col=1,
                )

    # VWAP
    if show.get("vwap") and "vwap" in df.columns:
        fig.add_trace(
            go.Scatter(x=x, y=df["vwap"], name="VWAP", line=dict(color=C["gold"], width=1.5, dash="dot"), opacity=0.8),
            row=1, col=1,
        )

    # Bollinger Bands
    if show.get("bb") and "bb_upper" in df.columns:
        fig.add_trace(
            go.Scatter(x=x, y=df["bb_upper"], name="BB Upper", line=dict(color=C["blue"], width=0.6, dash="dash"), opacity=0.4),
            row=1, col=1,
        )
        fig.add_trace(
            go.Scatter(x=x, y=df["bb_lower"], name="BB Lower", line=dict(color=C["blue"], width=0.6, dash="dash"), opacity=0.4,
                       fill="tonexty", fillcolor="rgba(68,136,255,0.05)"),
            row=1, col=1,
        )

    # SuperTrend
    if show.get("supertrend") and "supertrend" in df.columns:
        st = df.dropna(subset=["supertrend"])
        if not st.empty:
            st_up = st[st["st_direction"] == 1]
            st_down = st[st["st_direction"] == -1]
            if not st_up.empty:
                fig.add_trace(
                    go.Scatter(x=st_up["timestamp"], y=st_up["supertrend"], name="ST Up",
                               line=dict(color=C["green"], width=1.2), opacity=0.7,
                               connectgaps=False),
                    row=1, col=1,
                )
            if not st_down.empty:
                fig.add_trace(
                    go.Scatter(x=st_down["timestamp"], y=st_down["supertrend"], name="ST Down",
                               line=dict(color=C["red"], width=1.2), opacity=0.7,
                               connectgaps=False),
                    row=1, col=1,
                )

    # Entry signal markers
    if "enter_long" in df.columns:
        entries = df[df["enter_long"] == 1]
        if not entries.empty:
            fig.add_trace(
                go.Scatter(
                    x=entries["timestamp"], y=entries["low"] * 0.997,
                    mode="markers", name="Long Entry",
                    marker=dict(symbol="triangle-up", size=12, color=C["green"], line=dict(width=1, color=C["gold"])),
                ),
                row=1, col=1,
            )

    # ── Row 2: Volume Delta ──
    if "buy_vol" in df.columns and "sell_vol" in df.columns:
        fig.add_trace(
            go.Bar(x=x, y=df["buy_vol"], name="Buy Vol", marker_color=C["green"], opacity=0.7),
            row=2, col=1,
        )
        fig.add_trace(
            go.Bar(x=x, y=-df["sell_vol"], name="Sell Vol", marker_color=C["red"], opacity=0.7),
            row=2, col=1,
        )
    elif "volume" in df.columns:
        colors = [C["green"] if c >= o else C["red"] for c, o in zip(df["close"], df["open"])]
        fig.add_trace(
            go.Bar(x=x, y=df["volume"], name="Volume", marker_color=colors, opacity=0.6),
            row=2, col=1,
        )

    # ── Row 3: CVD ──
    current_row = 3
    if show.get("cvd") and "cvd" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=x, y=df["cvd"], name="CVD",
                line=dict(color=C["purple"], width=1.2),
                fill="tozeroy" if len(df) < 200 else None,
                fillcolor="rgba(187,119,255,0.1)",
            ),
            row=current_row, col=1,
        )
        current_row += 1

    # ── Row 4: RSI ──
    if show.get("rsi") and "rsi" in df.columns:
        fig.add_trace(
            go.Scatter(x=x, y=df["rsi"], name="RSI(14)", line=dict(color=C["orange"], width=1.0)),
            row=current_row, col=1,
        )
        # Overbought/oversold lines
        fig.add_hline(y=70, line_dash="dash", line_color=C["red"], opacity=0.4, row=current_row, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color=C["green"], opacity=0.4, row=current_row, col=1)
        fig.add_hrect(y0=30, y1=70, fillcolor="rgba(255,140,0,0.03)", line_width=0, row=current_row, col=1)
        current_row += 1

    # ── Row 5: MACD ──
    if show.get("macd") and "macd" in df.columns:
        fig.add_trace(
            go.Scatter(x=x, y=df["macd"], name="MACD", line=dict(color=C["cyan"], width=1.0)),
            row=current_row, col=1,
        )
        if "macd_signal" in df.columns:
            fig.add_trace(
                go.Scatter(x=x, y=df["macd_signal"], name="Signal", line=dict(color=C["red"], width=0.8)),
                row=current_row, col=1,
            )
        if "macd_hist" in df.columns:
            colors = [C["green"] if v >= 0 else C["red"] for v in df["macd_hist"]]
            fig.add_trace(
                go.Bar(x=x, y=df["macd_hist"], name="MACD Hist", marker_color=colors, opacity=0.5),
                row=current_row, col=1,
            )

    # ── Layout ──
    badge = " LIVE" if live else ""
    title = f"<b>{pair}</b> {timeframe}{badge} | {len(df)} candles"

    fig.update_layout(
        title=dict(text=title, font=dict(size=15, color=C["gold"])),
        template="plotly_dark",
        height=height,
        paper_bgcolor=C["bg"],
        plot_bgcolor=C["bg"],
        font=dict(color=C["text"], family="Courier New", size=10),
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
            font=dict(size=9, color=C["text"]),
        ),
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        margin=dict(l=50, r=15, t=45, b=25),
    )

    fig.update_yaxes(gridcolor=C["grid"], zerolinecolor=C["grid"])
    fig.update_xaxes(gridcolor=C["grid"])
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])  # hide weekend gaps

    # Remove x-axis labels from all but bottom
    for i in range(1, n_rows):
        fig.update_xaxes(showticklabels=False, row=i, col=1)

    return fig