from __future__ import annotations

from .schemas import AgentResult, TradeDecision, clamp


class DecisionAggregator:
    def combine(self, pair: str, results: list[AgentResult]) -> TradeDecision:
        hard_rejects = [r for r in results if r.decision == "reject"]
        approvals = [r for r in results if r.decision == "approve"]
        reasons = [reason for result in results for reason in result.reasons]
        reject_if = [item for result in results for item in result.reject_if]

        if hard_rejects:
            return TradeDecision(
                pair=pair,
                side="none",
                decision="reject",
                confidence=max(r.confidence for r in hard_rejects),
                max_leverage=min(r.max_leverage for r in results),
                stake_pct=0.0,
                reasons=reasons,
                reject_if=reject_if,
                agent_results=[r.to_dict() for r in results],
            )

        if not approvals:
            return TradeDecision(
                pair=pair,
                side="none",
                decision="wait",
                confidence=sum(r.confidence for r in results) / max(len(results), 1),
                max_leverage=min(r.max_leverage for r in results),
                stake_pct=0.0,
                reasons=reasons,
                reject_if=reject_if,
                agent_results=[r.to_dict() for r in results],
            )

        side_votes = [r.side for r in approvals if r.side in {"long", "short"}]
        side = max(set(side_votes), key=side_votes.count) if side_votes else "none"
        confidence = sum(r.confidence for r in approvals) / len(approvals)
        return TradeDecision(
            pair=pair,
            side=side,
            decision="approve" if side != "none" else "wait",
            confidence=clamp(confidence, 0.0, 1.0),
            max_leverage=min(r.max_leverage for r in results),
            stake_pct=min([r.stake_pct for r in approvals if r.stake_pct > 0] or [0.0]),
            reasons=reasons,
            reject_if=reject_if,
            agent_results=[r.to_dict() for r in results],
        )

