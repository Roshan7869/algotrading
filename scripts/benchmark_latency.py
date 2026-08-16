"""Latency benchmark: Python vs Rust indicator pipeline.

Generates N candles of synthetic OHLCV data, then times:
- Python: compute_indicators(df) from ui.indicators
- Rust:  subprocess call to ws-bridge --benchmark

Reports speedup factor.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
N_CANDLES = 500
SEED = 42


def _generate_candles(n: int) -> pd.DataFrame:
    np.random.seed(SEED)
    closes = 50000 + np.cumsum(np.random.randn(n) * 10)
    highs = closes + np.abs(np.random.randn(n) * 5)
    lows = closes - np.abs(np.random.randn(n) * 5)
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    volumes = np.random.rand(n) * 1000
    taker_buy = volumes * np.random.uniform(0.3, 0.7, n)
    timestamps = np.arange(1700000000000, 1700000000000 + n * 60_000, 60_000)

    return pd.DataFrame({
        "open_time": timestamps,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
        "close_time": timestamps + 60_000,
        "quote_volume": closes * volumes,
        "trades": np.random.randint(100, 5000, n),
        "taker_buy_volume": taker_buy,
        "taker_buy_quote_volume": taker_buy * closes,
        "timestamp": pd.to_datetime(timestamps, unit="ms", utc=True),
    })


def benchmark_python(df: pd.DataFrame) -> float:
    from ui.indicators import compute_indicators

    # warmup
    _ = compute_indicators(df)

    trials = 10
    start = time.perf_counter()
    for _ in range(trials):
        _ = compute_indicators(df.copy())
    elapsed = (time.perf_counter() - start) / trials
    return elapsed


def benchmark_rust(df: pd.DataFrame) -> float:
    bridge_bin = (
        PROJECT_ROOT / "flowsurface_src" / "target" / "debug" / "ws-bridge"
    )
    if not bridge_bin.exists():
        print("  Building ws-bridge first...")
        subprocess.run(
            ["cargo", "build", "-p", "ws-bridge", "--quiet"],
            cwd=str(PROJECT_ROOT / "flowsurface_src"),
            timeout=120, check=True,
        )

    candles_json = df.to_json(orient="records", date_format="epoch")
    result = subprocess.run(
        [str(bridge_bin), "--benchmark", str(N_CANDLES)],
        input=candles_json,
        capture_output=True, text=True,
        timeout=30,
    )
    if result.returncode != 0:
        print(f"  Rust benchmark stderr: {result.stderr.strip()}")
        return -1.0
    try:
        report = json.loads(result.stdout.strip())
        return report.get("mean_ms", -1) / 1000.0
    except (json.JSONDecodeError, KeyError):
        print(f"  Raw output: {result.stdout.strip()[:200]}")
        return -1.0


if __name__ == "__main__":
    print(f"Generating {N_CANDLES} synthetic candles...")
    df = _generate_candles(N_CANDLES)

    print(f"\nBenchmarking Python compute_indicators ({N_CANDLES} candles)...")
    py_time = benchmark_python(df)
    print(f"  Python mean: {py_time*1000:.1f}ms")

    print(f"\nBenchmarking Rust ws-bridge compute ({N_CANDLES} candles)...")
    rs_time = benchmark_rust(df)
    if rs_time > 0:
        print(f"  Rust mean:    {rs_time*1000:.1f}ms")
        speedup = py_time / rs_time if rs_time > 0 else float("inf")
        print(f"\n  Speedup: {speedup:.1f}x")
    else:
        print("  Rust benchmark skipped (process error)")

    print("\nDone.")
