from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schemas import MarketSnapshot, utc_now


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_config(config_path: str) -> dict[str, Any]:
    path = PROJECT_ROOT / config_path
    with path.open() as handle:
        return json.load(handle)


def _pair_to_feather_name(pair: str, timeframe: str) -> str:
    return f"{pair.replace('/', '_').replace(':', '_')}-{timeframe}-futures.feather"


def load_latest_snapshot(config: dict[str, Any], pair: str) -> MarketSnapshot:
    """Load latest local candle if available; otherwise return config-only snapshot."""
    timeframe = config.get("timeframe", "1h")
    data_dir = PROJECT_ROOT / "user_data" / "data" / "binance" / "futures"
    data_file = data_dir / _pair_to_feather_name(pair, timeframe)

    snapshot = MarketSnapshot(timestamp=utc_now(), pair=pair, timeframe=timeframe)
    if not data_file.exists():
        snapshot.raw["warning"] = f"missing_local_data:{data_file.name}"
        return snapshot

    try:
        import pandas as pd

        frame = pd.read_feather(data_file)
        if frame.empty:
            snapshot.raw["warning"] = f"empty_local_data:{data_file.name}"
            return snapshot
        row = frame.iloc[-1].to_dict()
        snapshot.close = _to_float(row.get("close"))
        snapshot.volume = _to_float(row.get("volume"))
        snapshot.raw["last_candle"] = {
            key: str(value) if key == "date" else _json_safe(value)
            for key, value in row.items()
            if key in {"date", "open", "high", "low", "close", "volume"}
        }
    except Exception as exc:
        snapshot.raw["warning"] = f"failed_to_load_local_data:{exc}"

    return snapshot


def _to_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)

