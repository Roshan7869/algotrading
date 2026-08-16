"""Macro Analyst — rule-based macro + sentiment signal generator."""

from core import Signal
from engine.ai_signal_generators.base import SignalGenerator


class MacroAnalystGenerator(SignalGenerator):
    name = "macro_analyst"
    description = "Macro analyst — rule-based macro + regime classification"

    def __init__(self):
        super().__init__()
        self._mcp = None

    def _lazy_init(self):
        if self._mcp is not None:
            return
        try:
            from mcp_layer.mcp_client import McpClient
            self._mcp = McpClient()
            self._mcp.connect()
        except Exception:
            self._mcp = None

    def generate(self, pair: str) -> Signal:
        self._lazy_init()
        if self._mcp is None:
            return self._rule_based_fallback(pair)

        try:
            quote = self._mcp.get_quote(pair)
            ohlcv = self._mcp.get_ohlcv(pair, "1d", period="50d")
            ta = self._mcp.get_ta(pair)

            price = quote.get("price", 0)
            change_pct = quote.get("change_pct", 0)
            sma_20 = ta.get("sma_20", 0) if isinstance(ta, dict) else 0
            sma_50 = ta.get("sma_50", 0) if isinstance(ta, dict) else 0
            rsi = ta.get("rsi", 50) if isinstance(ta, dict) else 50

            score = 0.0
            reasons = []

            if change_pct > 2:
                score += 0.3
                reasons.append("strong daily gain")
            elif change_pct > 0.5:
                score += 0.1
                reasons.append("moderate gain")
            elif change_pct < -2:
                score -= 0.3
                reasons.append("strong daily loss")
            elif change_pct < -0.5:
                score -= 0.1
                reasons.append("moderate loss")

            if sma_20 and sma_50 and sma_20 > sma_50:
                score += 0.2
                reasons.append("golden cross (20>50 SMA)")
            elif sma_20 and sma_50 and sma_20 < sma_50:
                score -= 0.2
                reasons.append("death cross (20<50 SMA)")

            if rsi > 70:
                score -= 0.2
                reasons.append(f"overbought RSI={rsi:.0f}")
            elif rsi < 30:
                score += 0.2
                reasons.append(f"oversold RSI={rsi:.0f}")

            confidence = min(abs(score), 0.95)
            if score >= 0.3:
                action = "BUY"
            elif score <= -0.3:
                action = "SELL"
            else:
                action = "NEUTRAL"

            return Signal(
                pair=pair,
                action=action,
                confidence=round(confidence, 4),
                direction="long" if score > 0 else "short" if score < 0 else "neutral",
                source=self.name,
                price=price,
                reason="; ".join(reasons) if reasons else "no clear signal",
                metadata={"score": score, "rsi": rsi, "change_pct": change_pct},
            )
        except Exception as e:
            return self._rule_based_fallback(pair, str(e))

    def _rule_based_fallback(self, pair: str, error: str = "") -> Signal:
        return Signal(
            pair=pair,
            action="NEUTRAL",
            confidence=0.0,
            direction="neutral",
            source=self.name,
            reason=f"Macro analyst unavailable: {error}" if error else "Macro analyst unavailable",
        )
