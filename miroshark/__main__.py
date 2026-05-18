"""
MiroShark CLI — Command-line interface for the MiroShark Brain.

Usage:
    python -m miroshark              # Run one decision cycle
    python -m miroshark daemon       # Start continuous daemon
    python -m miroshark status       # Show current signal bus state
    python -m miroshark history      # Show last 10 decisions
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared_config.signal_bus import get_bus
from miroshark.brain import MiroSharkBrain


def cmd_decide():
    """Run one decision cycle."""
    brain = MiroSharkBrain()
    sig = brain.run_once()
    print(json.dumps({
        "action": sig.action,
        "confidence": sig.confidence,
        "regime": sig.regime,
        "direction": sig.direction,
        "suggested_leverage": sig.suggested_leverage,
        "scores": sig.scores,
        "reasoning": sig.reasoning,
    }, indent=2))


def cmd_status():
    """Show current state of all signal bus channels."""
    bus = get_bus()
    channels = bus.list_signals()
    print("=" * 60)
    print("MIROSHARK SIGNAL BUS STATUS")
    print("=" * 60)
    for ch in channels:
        data = bus.read(ch, max_age=None)
        if data:
            ts = data.pop("_timestamp", "?")
            src = data.pop("_written_by", "?")
            print(f"\n  {ch}")
            print(f"    Updated: {ts}")
            print(f"    Source:  {src}")
            for k, v in data.items():
                val = json.dumps(v) if isinstance(v, (dict, list)) else v
                print(f"    {k}: {val}")
        else:
            print(f"\n  {ch}: (empty)")
    print()


def cmd_history():
    """Show last decisions from miroshark_brain.json."""
    bus = get_bus()
    data = bus.read("miroshark_brain.json", max_age=None)
    if data:
        print(json.dumps(data, indent=2))
    else:
        print("No brain decisions recorded yet.")


def main():
    if len(sys.argv) < 2:
        cmd_decide()
        return

    cmd = sys.argv[1]
    if cmd == "daemon":
        from miroshark.daemon import main_loop
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        main_loop(interval=interval)
    elif cmd == "status":
        cmd_status()
    elif cmd == "history":
        cmd_history()
    elif cmd == "decide":
        cmd_decide()
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python -m miroshark [decide|daemon|status|history]")
        sys.exit(1)


if __name__ == "__main__":
    main()