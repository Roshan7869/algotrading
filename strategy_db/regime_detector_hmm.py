"""
Gaussian HMM Regime Detector
=============================
4-state Hidden Markov Model that detects market regimes from OHLCV features.

States: trending_up, trending_down, ranging, volatile
Features: returns, realized_vol, high_low_range, ema_slope

Usage:
    from strategy_db.regime_detector_hmm import HMMRegimeDetector
    
    detector = HMMRegimeDetector()
    detector.train(btc_dataframe)  # requires OHLCV columns
    regime, metrics = detector.predict(btc_dataframe)
    print(f"Current regime: {regime}, metrics: {metrics}")

CLI:
    python3 strategy_db/regime_detector_hmm.py --train
    python3 strategy_db/regime_detector_hmm.py --predict
    python3 strategy_db/regime_detector_hmm.py --analyze
"""

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from pathlib import Path
import json
import sys

# Try joblib for model persistence; fall back to pickle
try:
    import joblib
    SAVE_LOAD = "joblib"
except ImportError:
    import pickle
    SAVE_LOAD = "pickle"

REGIME_LABELS = {0: "ranging", 1: "trending_up", 2: "trending_down", 3: "volatile"}

DB_DIR = Path(__file__).parent / "chroma_db"
MODEL_PATH = Path(__file__).parent / "regime_hmm.pkl"
DATA_PATH = Path(__file__).parent.parent / "user_data" / "data" / "binance" / "futures"


class HMMRegimeDetector:
    """4-state Gaussian HMM for market regime detection on OHLCV data."""

    def __init__(self, n_states=4, model_path=None):
        self.n_states = n_states
        self.model_path = model_path or str(MODEL_PATH)
        self.model = None
        self.feature_means = None
        self.feature_stds = None
        self.regime_labels = dict(REGIME_LABELS)
        self._trained = False

    def _compute_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute OHLCV features for HMM input.
        
        Features:
        - returns: percentage price change
        - realized_vol: 20-period rolling std of returns
        - high_low_range: (high - low) / close (normalized range)
        - ema_slope: 21-period EMA percentage change (trend direction proxy)
        """
        df = df.copy()
        df["returns"] = df["close"].pct_change()
        df["realized_vol"] = df["returns"].rolling(20).std()
        df["high_low_range"] = (df["high"] - df["low"]) / df["close"]
        # EMA slope as trend direction proxy
        df["ema_21"] = df["close"].ewm(span=21).mean()
        df["ema_slope"] = df["ema_21"].pct_change()
        # Volume change (optional, adds info about participation)
        df["volume_change"] = df["volume"].pct_change().clip(-5, 5)
        df = df.dropna()
        return df

    def _prepare_matrix(self, feat_df: pd.DataFrame) -> np.ndarray:
        """Extract and standardize feature matrix."""
        features = ["returns", "realized_vol", "high_low_range", "ema_slope"]
        X = feat_df[features].values
        return X, features

    def train(self, df: pd.DataFrame, save=True) -> "HMMRegimeDetector":
        """Train HMM on OHLCV data.
        
        Args:
            df: DataFrame with columns: open, high, low, close, volume
            save: Whether to save model to disk after training
            
        Returns:
            self (for chaining)
        """
        feat_df = self._compute_features(df)
        X, features = self._prepare_matrix(feat_df)

        # Standardize features
        self.feature_means = X.mean(axis=0)
        self.feature_stds = X.std(axis=0)
        # Avoid division by zero for near-constant features
        self.feature_stds[self.feature_stds < 1e-10] = 1.0
        X_scaled = (X - self.feature_means) / self.feature_stds

        # Train with multiple initializations for robustness
        best_model = None
        best_score = -np.inf
        for seed in range(5):
            model = GaussianHMM(
                n_components=self.n_states,
                covariance_type="full",
                n_iter=300,
                random_state=seed,
                tol=1e-4,
            )
            try:
                model.fit(X_scaled)
                score = model.score(X_scaled)
                if score > best_score:
                    best_score = score
                    best_model = model
            except Exception:
                continue

        if best_model is None:
            raise RuntimeError("All HMM training attempts failed")

        self.model = best_model
        self._trained = True

        # Map states to labels by examining emission means
        self._map_states(X_scaled, feat_df)

        if save:
            self.save()

        print(f"HMM trained: {self.n_states} states, log-likelihood: {best_score:.2f}")
        print(f"Regime mapping: {self.regime_labels}")
        return self

    def _map_states(self, X_scaled: np.ndarray, feat_df: pd.DataFrame):
        """Map HMM states to regime labels by examining emission means.
        
        Strategy:
        - Sort states by (volatility, slope) characteristics
        - High vol -> volatile
        - Low vol + positive slope -> trending_up
        - Low vol + negative slope -> trending_down
        - Low vol + flat slope -> ranging
        """
        means = self.model.means_
        # Column order: returns, realized_vol, high_low_range, ema_slope

        # Classify each state
        labels = {}
        for i in range(self.n_states):
            vol_mean = means[i][1]   # realized_vol (standardized)
            slope_mean = means[i][3]  # ema_slope (standardized)
            ret_mean = means[i][0]    # returns (standardized)

            if vol_mean > 0.5:        # High volatility state
                labels[i] = "volatile"
            elif ret_mean > 0.15:     # Positive returns + low vol
                labels[i] = "trending_up"
            elif ret_mean < -0.15:    # Negative returns + low vol
                labels[i] = "trending_down"
            elif slope_mean > 0.1:    # Positive EMA slope
                labels[i] = "trending_up"
            elif slope_mean < -0.1:   # Negative EMA slope
                labels[i] = "trending_down"
            else:                      # Flat, low vol
                labels[i] = "ranging"

        # Handle duplicates: if 2+ states map to same label, differentiate
        label_counts = {}
        for i, label in labels.items():
            label_counts[label] = label_counts.get(label, 0) + 1

        if any(c > 1 for c in label_counts.values()):
            # Re-sort: assign labels by primary metric ranking
            # Sort states by (vol desc, slope desc)
            state_order = sorted(
                range(self.n_states),
                key=lambda i: (-means[i][1], means[i][3])
            )
            for rank, i in enumerate(state_order):
                if rank == 0:
                    labels[i] = "volatile"      # Highest vol
                elif rank == 1:
                    labels[i] = "trending_up"   # High slope
                elif rank == 2:
                    labels[i] = "trending_down"  # Low slope
                else:
                    labels[i] = "ranging"       # Flat

        self.regime_labels = labels

    def predict(self, df: pd.DataFrame, lookback: int = 200) -> tuple:
        """Predict current market regime.
        
        Args:
            df: DataFrame with OHLCV columns
            lookback: Use only last N candles for prediction
            
        Returns:
            (regime_label, metrics_dict)
        """
        if self.model is None:
            self.load()

        # Use last N candles
        df_recent = df.tail(lookback).reset_index(drop=True) if len(df) > lookback else df
        feat_df = self._compute_features(df_recent)
        X, features = self._prepare_matrix(feat_df)
        X_scaled = (X - self.feature_means) / self.feature_stds

        # Predict states
        states = self.model.predict(X_scaled)
        probabilities = self.model.predict_proba(X_scaled)

        # Current state (last candle)
        current_state = states[-1]
        current_regime = self.regime_labels.get(current_state, "ranging")
        current_probs = {
            self.regime_labels.get(i, f"state_{i}"): round(float(prob), 4)
            for i, prob in enumerate(probabilities[-1])
        }

        # Regime duration (consecutive candles in same state)
        regime_duration = 1
        for j in range(len(states) - 2, -1, -1):
            if states[j] == current_state:
                regime_duration += 1
            else:
                break

        # Regime transition count in last 50 candles
        recent_states = states[-50:] if len(states) >= 50 else states
        transitions = sum(1 for i in range(1, len(recent_states)) 
                         if recent_states[i] != recent_states[i-1])

        metrics = {
            "regime": current_regime,
            "regime_probs": current_probs,
            "regime_duration_hours": regime_duration,
            "regime_transitions_50": transitions,
            "regime_stability": round(1.0 - (transitions / max(len(recent_states) - 1, 1)), 3),
            "returns_20": round(float(feat_df["returns"].iloc[-20:].mean()) * 100, 4) if len(feat_df) >= 20 else 0,
            "volatility_20": round(float(feat_df["realized_vol"].iloc[-1]) * 100, 4),
            "atr_pct": round(float(feat_df["high_low_range"].iloc[-1]) * 100, 4),
            "ema_slope": round(float(feat_df["ema_slope"].iloc[-1]) * 100, 4),
        }

        return current_regime, metrics

    def predict_series(self, df: pd.DataFrame) -> pd.Series:
        """Predict regime for each candle in the dataframe.
        
        Returns a Series of regime labels aligned with the input dataframe.
        Useful for backtest integration where you need per-candle regimes.
        """
        if self.model is None:
            self.load()

        feat_df = self._compute_features(df)
        X, features = self._prepare_matrix(feat_df)
        X_scaled = (X - self.feature_means) / self.feature_stds

        states = self.model.predict(X_scaled)
        labels = pd.Series(
            [self.regime_labels.get(s, "ranging") for s in states],
            index=feat_df.index
        )
        return labels

    def save(self, path: str = None):
        """Save model and preprocessing params."""
        path = path or self.model_path
        data = {
            "model": self.model,
            "means": self.feature_means.tolist() if isinstance(self.feature_means, np.ndarray) else self.feature_means,
            "stds": self.feature_stds.tolist() if isinstance(self.feature_stds, np.ndarray) else self.feature_stds,
            "labels": self.regime_labels,
            "n_states": self.n_states,
        }
        if SAVE_LOAD == "joblib":
            joblib.dump(data, path)
        else:
            with open(path, "wb") as f:
                pickle.dump(data, f)
        print(f"Model saved to {path}")

    def load(self, path: str = None):
        """Load saved model."""
        path = path or self.model_path
        if SAVE_LOAD == "joblib":
            data = joblib.load(path)
        else:
            with open(path, "rb") as f:
                data = pickle.load(f)

        self.model = data["model"]
        self.feature_means = np.array(data["means"])
        self.feature_stds = np.array(data["stds"])
        self.regime_labels = data["labels"]
        self.n_states = data.get("n_states", 4)
        self._trained = True
        return self


def load_btc_data(pair: str = "BTC_USDT_USDT") -> pd.DataFrame:
    """Load BTC OHLCV data from feather file."""
    # Try multiple path patterns
    paths = [
        DATA_PATH / f"{pair}-1h-futures.feather",
        DATA_PATH / f"{pair}-1h.feather",
        DATA_PATH / f"{pair.replace('_', '/')}-1h-futures.feather",
    ]
    for p in paths:
        if p.exists():
            df = pd.read_feather(p)
            # Standardize column names
            df.columns = [c.lower().replace('_', '') for c in df.columns]
            # Ensure we have the right columns
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
            print(f"Loaded {len(df)} candles from {p.name}")
            return df
    
    raise FileNotFoundError(f"No data found for {pair} in {DATA_PATH}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="HMM Regime Detector")
    parser.add_argument("--train", action="store_true", help="Train HMM on BTC data")
    parser.add_argument("--predict", action="store_true", help="Predict current regime")
    parser.add_argument("--analyze", action="store_true", help="Analyze regime distribution")
    parser.add_argument("--pair", default="BTC_USDT_USDT", help="Trading pair (default: BTC_USDT_USDT)")
    args = parser.parse_args()

    if args.train:
        print("Loading BTC 1h data...")
        df = load_btc_data(args.pair)
        print(f"Data range: {df['date'].iloc[0]} to {df['date'].iloc[-1]}")
        print(f"Candles: {len(df)}")
        
        detector = HMMRegimeDetector()
        detector.train(df)
        
        # Quick prediction test
        regime, metrics = detector.predict(df)
        print(f"\nCurrent regime: {regime}")
        print(f"Regime probabilities: {metrics['regime_probs']}")
        print(f"Regime duration: {metrics['regime_duration_hours']} hours")
        print(f"Regime stability: {metrics['regime_stability']}")
        
    elif args.predict:
        df = load_btc_data(args.pair)
        detector = HMMRegimeDetector()
        detector.load()
        regime, metrics = detector.predict(df)
        print(json.dumps(metrics, indent=2, default=str))
        
    elif args.analyze:
        df = load_btc_data(args.pair)
        detector = HMMRegimeDetector()
        detector.load()
        
        # Predict regimes for all candles
        labels = detector.predict_series(df)
        
        # Distribution
        from collections import Counter
        dist = Counter(labels)
        total = len(labels)
        print("=== Regime Distribution ===")
        for regime, count in sorted(dist.items(), key=lambda x: -x[1]):
            pct = count / total * 100
            print(f"  {regime}: {count} candles ({pct:.1f}%)")
        
        # Average returns per regime
        df_with_regime = df.copy()
        feat_df = detector._compute_features(df_with_regime)
        feat_df = feat_df.reset_index(drop=True)
        labels_aligned = labels.reset_index(drop=True)
        
        print("\n=== Regime Characteristics ===")
        for regime in sorted(dist.keys()):
            mask = labels_aligned == regime
            if mask.sum() > 0:
                regime_data = feat_df.loc[mask]
                print(f"\n  {regime}:")
                print(f"    Avg return: {regime_data['returns'].mean()*100:.4f}%")
                print(f"    Avg vol: {regime_data['realized_vol'].mean()*100:.4f}%")
                print(f"    Avg range: {regime_data['high_low_range'].mean()*100:.4f}%")
                print(f"    Avg slope: {regime_data['ema_slope'].mean()*100:.4f}%")
    else:
        parser.print_help()