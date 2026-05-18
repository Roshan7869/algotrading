#!/usr/bin/env python3
"""Refresh market regime signal via HMM detector.

Reads latest candle data, runs HMM prediction, writes to Signal Bus.
Meant to run every 5 minutes via cron.
"""

import sys
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared_config.signal_bus import get_bus

logging.basicConfig(level=logging.INFO, format="%(asctime)s [regime] %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "user_data" / "data" / "binance"
HMM_PATH = PROJECT_ROOT / "strategy_db" / "regime_hmm.pkl"

REGIME_MULTIPLIERS = {
    "trending_up": 1.2,
    "trending_down": 1.2,
    "ranging": 0.7,
    "volatile": 0.5,
}


def detect_regime_direct(pair_symbol: str) -> dict:
    """Run HMM regime detection directly using the saved model."""
    base = pair_symbol.split("/")[0]
    feather_path = DATA_DIR / f"{base}_USDT-1h.feather"

    if not feather_path.exists():
        log.warning(f"No feather data for {pair_symbol} at {feather_path}")
        return _fallback_regime(pair_symbol, "no_data")

    try:
        model_data = joblib.load(HMM_PATH)
        model = model_data["model"]
        regime_labels = model_data["regime_labels"]
        feature_means = model_data["feature_means"]
        feature_stds = model_data["feature_stds"]

        df = pd.read_feather(feather_path)
        if len(df) < 200:
            log.warning(f"Not enough data for {pair_symbol}: {len(df)} rows")
            return _fallback_regime(pair_symbol, "insufficient_data")

        # Use last 200 candles
        df_recent = df.tail(200).copy()

        # Compute all 4 HMM features (matching training)
        df_recent["returns"] = df_recent["close"].pct_change()
        df_recent["volatility"] = df_recent["returns"].rolling(20).std()
        df_recent["volume_change"] = df_recent["volume"].pct_change() if "volume" in df_recent.columns else df_recent["returns"].rolling(5).std()
        df_recent["high_low_range"] = ((df_recent["high"] - df_recent["low"]) / df_recent["close"]) if "high" in df_recent.columns and "low" in df_recent.columns else df_recent["returns"].abs()
        df_recent = df_recent.dropna()

        if len(df_recent) < 50:
            return _fallback_regime(pair_symbol, "insufficient_features")

        # Prepare observation sequence (4 features)
        obs = df_recent[["returns", "volatility", "volume_change", "high_low_range"]].values[-100:]

        # Normalize using training stats
        obs_norm = (obs - feature_means) / (feature_stds + 1e-8)

        # Predict states
        _, states = model.decode(obs_norm, algorithm="viterbi")

        # Get the current state (last observation)
        current_state = int(states[-1])
        state_label = regime_labels.get(current_state, f"state_{current_state}")

        # Compute state probabilities
        posteriors = model.predict_proba(obs_norm)
        current_probs = dict(zip(
            [regime_labels.get(i, f"state_{i}") for i in range(model.n_components)],
            [round(float(p), 4) for p in posteriors[-1]]
        ))

        # Stability = probability of current state
        stability = round(float(posteriors[-1][current_state]), 4)

        # Recent stats
        volatility = round(float(df_recent["volatility"].iloc[-1]), 4) if not df_recent.empty else 0.0
        returns = round(float(df_recent["returns"].iloc[-20:].mean()), 4) if len(df_recent) >= 20 else 0.0

        multiplier = REGIME_MULTIPLIERS.get(state_label, 1.0)

        log.info(f"{pair_symbol}: {state_label} (stability={stability})")

        return {
            "pair": pair_symbol,
            "regime": state_label,
            "regime_probs": current_probs,
            "regime_stability": stability,
            "volatility_20": volatility,
            "returns_20": returns,
            "regime_multiplier": multiplier,
        }

    except Exception as e:
        log.warning(f"HMM detection failed for {pair_symbol}: {e}")
        return _fallback_regime(pair_symbol, str(e))


def _fallback_regime(pair_symbol: str, reason: str = "") -> dict:
    """Return unknown regime with error details."""
    return {
        "pair": pair_symbol,
        "regime": "unknown",
        "regime_probs": {},
        "regime_stability": 0.0,
        "volatility_20": 0.0,
        "returns_20": 0.0,
        "regime_multiplier": 1.0,
        "error": reason,
    }


def main():
    bus = get_bus()
    log.info("Refreshing market regime signals...")

    primary = detect_regime_direct("BTC/USDT:USDT")
    log.info(f"BTC regime: {primary['regime']} (stability={primary.get('regime_stability', 0)})")

    all_regimes = {"BTC/USDT:USDT": primary["regime"]}
    for pair in ["ETH/USDT:USDT"]:
        r = detect_regime_direct(pair)
        all_regimes[pair] = r["regime"]

    bus.write("market_regime.json", {
        "pair": primary["pair"],
        "regime": primary["regime"],
        "regime_probs": primary.get("regime_probs", {}),
        "regime_duration_hours": 1,
        "regime_stability": primary.get("regime_stability", 0),
        "volatility_20": primary.get("volatility_20", 0),
        "returns_20": primary.get("returns_20", 0),
        "regime_multiplier": primary.get("regime_multiplier", 1.0),
        "all_regimes": all_regimes,
    })

    log.info(f"Regime signal written: {primary['regime']}")


if __name__ == "__main__":
    main()