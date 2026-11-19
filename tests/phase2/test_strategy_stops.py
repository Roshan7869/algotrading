"""Phase 2.1 regression tests for the two candidate strategies' stop wiring.

Plain `unittest` (the venv has no pytest and installing is out of scope), no freqtrade
backtester needed:

  .venv/Scripts/python.exe tests/phase2/test_strategy_stops.py

What is locked in
-----------------
1. `use_custom_stoploss` must be True, otherwise freqtrade never calls custom_stoploss()
   (freqtrade/strategy/interface.py:85 default False, :1551 the only call site) and the ATR
   stop is dead code. This is the bug that made every BollingerMeanReversion stop the raw
   config stoploss.
2. The returned ratio, fed through freqtrade's own conversion
   `price * (1 - abs(stoploss / leverage))` (persistence/trade_model.py:833-837), must land
   on `open_rate - atr * multiplier` (long) / `open_rate + atr * multiplier` (short).
   The pre-fix code landed at one third of that distance at 3x.
3. The stop must not be re-anchored to the current rate: the implied price is identical when
   the trade is in profit.
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "user_data" / "strategies"))

from BollingerMeanReversion import BollingerMeanReversion  # noqa: E402


class _Dp:
    """Minimal DataProvider stand-in: one analysed candle with a known ATR."""

    def __init__(self, atr: float, entry: datetime):
        self._df = pd.DataFrame({
            "date": [entry],
            "atr": [atr],
        })

    def get_analyzed_dataframe(self, pair, timeframe):
        return self._df, self._df["date"].iloc[-1]


class _Trade:
    def __init__(self, open_rate: float, leverage: float, is_short: bool, entry: datetime):
        self.open_rate = open_rate
        self.leverage = leverage
        self.is_short = is_short
        self.open_date_utc = entry


def _strategy(atr: float, entry: datetime) -> BollingerMeanReversion:
    s = BollingerMeanReversion.__new__(BollingerMeanReversion)
    s.dp = _Dp(atr, entry)
    return s


def _price_from_ratio(ratio: float, price: float, leverage: float, is_short: bool = False) -> float:
    """freqtrade's own conversion: trade_model.py adjust_stop_loss."""
    if is_short:
        return price * (1 + abs(ratio / leverage))
    return price * (1 - abs(ratio / leverage))


class TestBollingerStopIsPriceTerms(unittest.TestCase):
    atr = 0.05
    entry = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)

    def test_custom_stoploss_is_enabled(self):
        self.assertTrue(
            BollingerMeanReversion.use_custom_stoploss,
            "without use_custom_stoploss=True freqtrade never calls custom_stoploss()",
        )

    def test_long_stop_sits_at_atr_distance_in_price_terms(self):
        s = _strategy(self.atr, self.entry)
        trade = _Trade(open_rate=2.0, leverage=3.0, is_short=False, entry=self.entry)
        lev = 3.0
        mult = float(s.atr_multiplier.value)
        expected = 2.0 - self.atr * mult          # 1.3 ATR below the fill by default
        ratio = s.custom_stoploss("XRP/USDT:USDT", trade, self.entry, 2.0, 0.0)
        got = _price_from_ratio(ratio, 2.0, lev)
        self.assertAlmostEqual(got, expected, places=9)
        # the pre-fix code produced expected = 2.0 - atr*mult/lev  (one third of the distance)
        self.assertGreater(abs(got - 2.0), abs(self.atr * mult / lev) * 2)

    def test_short_stop_sits_at_atr_distance_in_price_terms(self):
        s = _strategy(self.atr, self.entry)
        trade = _Trade(open_rate=2.0, leverage=3.0, is_short=True, entry=self.entry)
        mult = float(s.atr_multiplier.value)
        expected = 2.0 + self.atr * mult
        ratio = s.custom_stoploss("XRP/USDT:USDT", trade, self.entry, 2.0, 0.0)
        got = _price_from_ratio(ratio, 2.0, 3.0, is_short=True) if ratio else None
        self.assertIsNotNone(got)
        self.assertAlmostEqual(got, expected, places=9)

    def test_stop_price_does_not_follow_the_rate_up(self):
        """A fixed entry-anchored stop keeps the same *price*, not the same distance."""
        s = _strategy(self.atr, self.entry)
        trade = _Trade(open_rate=2.0, leverage=3.0, is_short=False, entry=self.entry)
        ratio_at_entry = s.custom_stoploss("XRP/USDT:USDT", trade, self.entry, 2.0, 0.0)
        ratio_in_profit = s.custom_stoploss("XRP/USDT:USDT", trade, self.entry, 2.02, 0.0)
        self.assertAlmostEqual(_price_from_ratio(ratio_at_entry, 2.0, 3.0),
                               _price_from_ratio(ratio_in_profit, 2.02, 3.0), places=9)


class TestSupertrendStopFlag(unittest.TestCase):
    def test_flag_is_recorded(self):
        """Documents the *unfixed* state: SupertrendEmaStrategy is lookahead-SUSPECT and was
        left untouched (quarantine is an orchestrator decision), so its ATR stop stays dead."""
        from SupertrendEmaStrategy import SupertrendEmaStrategy

        self.assertFalse(SupertrendEmaStrategy.use_custom_stoploss)


if __name__ == "__main__":
    unittest.main(verbosity=2)
