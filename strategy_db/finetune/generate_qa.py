"""Generate synthetic query-document pairs for adapter fine-tuning.

Template-based generation using strategy chunk metadata. No LLM API cost.
Produces train_pairs.json and eval_pairs.json in strategy_db/finetune/data/.
"""

import json
import os
import random
import sys

TEMPLATES: dict[str, list[str]] = {
    "entry": [
        "How to enter a {setup_name} trade?",
        "{setup_name} entry rules for {market_condition} markets",
        "Entry conditions for {setup_name} strategy",
        "What triggers an entry in {setup_name}?",
        "Best entry for {setup_name} setup",
    ],
    "exit": [
        "How to exit a {setup_name} trade?",
        "{setup_name} take profit rules",
        "Exit strategy for {setup_name}",
        "When to exit {setup_name} positions?",
    ],
    "risk_management": [
        "Stop loss placement for {setup_name}",
        "Risk management rules for {setup_name}",
        "How to size positions in {setup_name}?",
        "{setup_name} risk reward ratio",
    ],
    "market_structure": [
        "What is {setup_name} in trading?",
        "{setup_name} market structure analysis",
        "How to identify {setup_name} on a chart?",
        "{setup_name} pattern recognition",
        "Understanding {setup_name} market patterns",
    ],
    "psychology": [
        "{setup_name} trading psychology tips",
        "Common mistakes in {setup_name}",
        "Mindset for trading {setup_name}",
    ],
}

# Fallback templates when setup_type doesn't match any category
_FALLBACK_TEMPLATES: list[str] = [
    "How to use {setup_name} in trading?",
    "{setup_name} trading strategy explained",
    "Best practices for {setup_name}",
    "{setup_name} strategy for {market_condition} markets",
    "Learning {setup_name} for beginners",
    "Advanced {setup_name} techniques",
    "{setup_name} vs other strategies",
]


def generate_queries_for_chunk(chunk, num_queries: int = 3) -> list[str]:
    """Generate diverse synthetic queries for a single strategy chunk.

    Args:
        chunk: StrategyChunk dataclass or dict-like object.
        num_queries: Max queries to generate per chunk.

    Returns:
        List of query strings.
    """
    setup_name = (
        chunk.setup_name
        if hasattr(chunk, "setup_name")
        else chunk.get("setup_name", "Unknown")
    )
    setup_type = (
        chunk.setup_type
        if hasattr(chunk, "setup_type")
        else chunk.get("setup_type", "entry")
    )
    market_condition = (
        getattr(chunk, "market_condition", None)
        or chunk.get("market_condition", None)
        or "any"
    )

    type_templates = TEMPLATES.get(setup_type, _FALLBACK_TEMPLATES)

    # Select distinct templates with sampling
    selected = random.sample(
        type_templates, min(num_queries, len(type_templates))
    )

    queries: list[str] = []
    for tpl in selected:
        q = tpl.format(
            setup_name=setup_name,
            market_condition=market_condition,
        )
        queries.append(q)

    # Add abbreviation queries for setups with common acronyms
    trading_acronyms = [
        "FVG", "OB", "ICT", "SMC", "BOS", "OTE", "IFVG", "MSS",
        "CE", "AMD", "LQ", "HTF", "LTF", "PO3", "NWOG", "NDOG",
    ]
    if any(abbr in setup_name.upper() for abbr in trading_acronyms):
        queries.append(f"Trading {setup_name} strategy for beginners")

    return queries


def generate_dataset(
    chunks: list,
    train_ratio: float = 0.8,
    queries_per_chunk: int = 4,
) -> tuple[list, list]:
    """Generate (query, chunk_text) pairs split into train/eval sets.

    Args:
        chunks: List of StrategyChunk objects or dicts.
        train_ratio: Fraction of pairs to use for training.
        queries_per_chunk: Max queries generated per chunk.

    Returns:
        Tuple of (train_pairs, eval_pairs), each as list[tuple[str, str]].
    """
    random.seed(42)  # Reproducible split

    all_pairs: list[tuple[str, str]] = []
    for chunk in chunks:
        chunk_text = (
            chunk.chunk_text
            if hasattr(chunk, "chunk_text")
            else chunk.get("chunk_text", "")
        )
        if not chunk_text:
            continue
        queries = generate_queries_for_chunk(chunk, num_queries=queries_per_chunk)
        for q in queries:
            all_pairs.append((q, chunk_text))

    random.shuffle(all_pairs)
    split = int(len(all_pairs) * train_ratio)

    return all_pairs[:split], all_pairs[split:]


def save_pairs(
    train_pairs: list[tuple[str, str]],
    eval_pairs: list[tuple[str, str]],
    output_dir: str,
) -> None:
    """Save train/eval pairs to JSON files."""
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "train_pairs.json"), "w") as f:
        json.dump(train_pairs, f)
    with open(os.path.join(output_dir, "eval_pairs.json"), "w") as f:
        json.dump(eval_pairs, f)
    print(
        f"Saved {len(train_pairs)} train + {len(eval_pairs)} eval pairs "
        f"to {output_dir}"
    )


def load_pairs(input_dir: str) -> tuple[list, list]:
    """Load train/eval pairs from JSON files.

    Args:
        input_dir: Directory containing train_pairs.json and eval_pairs.json.

    Returns:
        Tuple of (train_pairs, eval_pairs) as list[tuple[str, str]].
    """
    with open(os.path.join(input_dir, "train_pairs.json")) as f:
        train = json.load(f)
    with open(os.path.join(input_dir, "eval_pairs.json")) as f:
        eval_pairs = json.load(f)
    return train, eval_pairs


if __name__ == "__main__":
    # Add strategy_db to path for direct execution
    strategy_db_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, strategy_db_dir)

    from ingest import load_all_chunks, load_simple_chunks

    chunks = load_all_chunks()
    simple = load_simple_chunks()
    chunks.extend(simple)
    print(f"Loaded {len(chunks)} total chunks")

    train, eval_pairs = generate_dataset(chunks, queries_per_chunk=4)
    output_dir = os.path.join(os.path.dirname(__file__), "data")
    save_pairs(train, eval_pairs, output_dir)
