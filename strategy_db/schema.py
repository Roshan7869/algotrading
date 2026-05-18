from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class StrategyChunk:
    chunk_id: str
    source_type: str
    youtube_url: str
    video_title: str
    channel_name: str
    setup_name: str
    setup_type: str
    timeframe: str
    market_condition: str
    strategy_style: str
    assets_applicable: list[str]
    chunk_text: str
    entry_condition: str
    confirmation_signal: str
    stop_loss_rule: str
    target_exit_rule: str
    invalidation_condition: str
    risk_reward: str
    position_sizing: str
    psychology_note: str
    edge_description: str
    confluence_factors: list[str]
    keywords: list[str]
    transcript_evidence: str
    start_timestamp: str
    end_timestamp: str
    source_section: str
    author_concept: bool
    confidence: Optional[float] = None

    @classmethod
    def from_dict(cls, d: dict) -> "StrategyChunk":
        return cls(
            chunk_id=str(d.get("chunk_id", "")),
            source_type=d.get("source_type", ""),
            youtube_url=d.get("youtube_url", ""),
            video_title=d.get("video_title", ""),
            channel_name=d.get("channel_name", ""),
            setup_name=d.get("setup_name", ""),
            setup_type=d.get("setup_type", ""),
            timeframe=d.get("timeframe", ""),
            market_condition=d.get("market_condition", ""),
            strategy_style=d.get("strategy_style", ""),
            assets_applicable=d.get("assets_applicable", []),
            chunk_text=d.get("chunk_text", ""),
            entry_condition=d.get("entry_condition", ""),
            confirmation_signal=d.get("confirmation_signal", ""),
            stop_loss_rule=d.get("stop_loss_rule", ""),
            target_exit_rule=d.get("target_exit_rule", ""),
            invalidation_condition=d.get("invalidation_condition", ""),
            risk_reward=d.get("risk_reward", ""),
            position_sizing=d.get("position_sizing", ""),
            psychology_note=d.get("psychology_note", ""),
            edge_description=d.get("edge_description", ""),
            confluence_factors=d.get("confluence_factors", []),
            keywords=d.get("keywords", []),
            transcript_evidence=d.get("transcript_evidence", ""),
            start_timestamp=d.get("start_timestamp", ""),
            end_timestamp=d.get("end_timestamp", ""),
            source_section=d.get("source_section", ""),
            author_concept=d.get("author_concept", False),
            confidence=d.get("confidence"),
        )


def text_for_embedding(chunk: StrategyChunk) -> str:
    parts = [
        f"Setup: {chunk.setup_name}",
        f"Type: {chunk.setup_type}",
        chunk.chunk_text,
        f"Entry: {chunk.entry_condition}",
        f"Stop Loss: {chunk.stop_loss_rule}",
        f"Target: {chunk.target_exit_rule}",
        f"Edge: {chunk.edge_description}",
    ]
    return "\n".join(p for p in parts if p and not p.endswith(": "))
