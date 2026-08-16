"""
Swarm Runtime Engine — loads YAML presets, orchestrates agent execution.

5 presets available:
  - daily_committee:    CEO + 3 analysts, daily consensus
  - crisis_response:    Emergency drawdown management
  - strategy_optimizer: Parallel strategy optimization
  - macro_scan:         Macroeconomic analysis across assets
  - sub_agent_trading:  SubAgentOverseer trading agents

Usage:
  from swarm.engine import run_swarm, list_presets, load_preset
  result = run_swarm("daily_committee")
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PRESETS_DIR = Path(__file__).parent / "presets"


def list_presets() -> list[dict[str, str]]:
    presets = []
    for fpath in sorted(PRESETS_DIR.glob("*.yaml")):
        presets.append({
            "name": fpath.stem,
            "file": str(fpath.name),
        })
    return presets


def load_preset(name: str) -> Optional[dict[str, Any]]:
    path = PRESETS_DIR / f"{name}.yaml"
    if not path.exists():
        return None
    try:
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f)
        return data
    except ImportError:
        return _parse_yaml_simple(path)


def _parse_yaml_simple(path: Path) -> dict:
    content = path.read_text()
    lines = content.split("\n")
    data = {"agents": []}
    current_agent = None
    current_key = None
    prompt_lines = []

    for line in lines:
        if line.startswith("#") or not line.strip():
            if prompt_lines and current_agent:
                current_agent["prompt"] = "\n".join(prompt_lines).strip()
                prompt_lines = []
            continue
        if not line.startswith(" ") and ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if key == "agents":
                continue
            if key == "- role":
                if current_agent:
                    if prompt_lines:
                        current_agent["prompt"] = "\n".join(prompt_lines).strip()
                        prompt_lines = []
                    data["agents"].append(current_agent)
                current_agent = {"role": val}
                current_key = None
            elif current_agent and key.startswith("  "):
                k = key.strip()
                if k == "model" and val:
                    current_agent["model"] = val
                elif k == "prompt":
                    current_key = "prompt"
                elif k == "tools" and val:
                    current_agent["tools"] = [t.strip() for t in val.strip("[]").split(",") if t.strip()]
                elif k == "schedule" and val:
                    data["schedule"] = val
                elif k == "trigger":
                    current_key = "trigger"
                elif k == "topology" and val:
                    data["topology"] = val
                elif k == "max_agents" and val:
                    data["max_agents"] = int(val)
                elif k == "strategy" and val:
                    data["strategy"] = val
            else:
                data[key] = val
        elif prompt_lines is not None and current_key == "prompt" and current_agent:
            prompt_lines.append(line)

    if current_agent:
        if prompt_lines:
            current_agent["prompt"] = "\n".join(prompt_lines).strip()
        data["agents"].append(current_agent)

    return data


def validate_preset(config: dict) -> list[str]:
    errors = []
    if not config.get("name"):
        errors.append("Missing 'name'")
    if not config.get("agents"):
        errors.append("No agents defined")
    elif len(config["agents"]) > config.get("max_agents", 10):
        errors.append(f"Agent count exceeds max_agents")
    for i, agent in enumerate(config.get("agents", [])):
        if not agent.get("role"):
            errors.append(f"Agent {i}: missing 'role'")
        if not agent.get("prompt"):
            errors.append(f"Agent {i} '{agent.get('role', '?')}': missing 'prompt'")
    return errors


def simulate_agent(agent: dict, context: dict) -> dict:
    tools = agent.get("tools", [])
    results = {}
    for tool_name in tools:
        results[tool_name] = _call_tool(tool_name, context)
    return {
        "role": agent["role"],
        "model": agent.get("model", "unknown"),
        "tool_results": results,
        "simulated_decision": _simulate_decision(agent, results),
    }


_TOOL_REGISTRY = {}


def register_tool(name: str, func):
    _TOOL_REGISTRY[name] = func


def _call_tool(name: str, context: dict) -> dict:
    if name in _TOOL_REGISTRY:
        try:
            return _TOOL_REGISTRY[name](context)
        except Exception as e:
            return {"error": str(e), "tool": name}
    return {"status": "unavailable", "tool": name, "note": "Tool not registered at runtime"}


def _simulate_decision(agent: dict, tool_results: dict) -> str:
    role = agent.get("role", "").lower()
    if "risk" in role or "crisis" in role:
        return "CAUTION: Reduce exposure, enforce risk limits"
    if "ceo" in role or "manager" in role:
        return "CONSENSUS: Proceed with reduced position sizing"
    if "technical" in role:
        return "HOLD: Awaiting clearer technical signals"
    if "sentiment" in role:
        return "NEUTRAL: Mixed sentiment signals"
    return "HOLD: No clear signal"


def run_swarm(name: str, context: Optional[dict] = None) -> dict:
    config = load_preset(name)
    if config is None:
        return {"success": False, "error": f"Preset '{name}' not found"}
    errors = validate_preset(config)
    if errors:
        return {"success": False, "error": "; ".join(errors), "preset": name}
    if context is None:
        context = {}
    agent_results = []
    for agent in config.get("agents", []):
        result = simulate_agent(agent, context)
        agent_results.append(result)
    return {
        "success": True,
        "preset": name,
        "description": config.get("description", ""),
        "topology": config.get("topology", "unknown"),
        "max_agents": config.get("max_agents", 0),
        "strategy": config.get("strategy", ""),
        "schedule": config.get("schedule", ""),
        "agents": agent_results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def run_swarm_with_bridge(name: str) -> dict:
    from nexus.bridge import get_bridge
    bridge = get_bridge()
    ctx = {}
    try:
        ctx["trade_status"] = bridge.trade_status()
    except Exception:
        ctx["trade_status"] = {"status": "unknown"}
    return run_swarm(name, context=ctx)
