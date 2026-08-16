"""Tests for swarm/engine.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestSwarmEngine:
    def test_list_presets(self):
        from swarm.engine import list_presets
        presets = list_presets()
        assert len(presets) == 5
        names = [p["name"] for p in presets]
        assert "daily_committee" in names
        assert "crisis_response" in names

    def test_load_preset_daily_committee(self):
        from swarm.engine import load_preset
        config = load_preset("daily_committee")
        assert config is not None
        assert config["name"] == "daily_committee"
        assert len(config["agents"]) == 4
        roles = [a["role"] for a in config["agents"]]
        assert "ceo_analyst" in roles
        assert "technical_analyst" in roles

    def test_load_preset_crisis_response(self):
        from swarm.engine import load_preset
        config = load_preset("crisis_response")
        assert config is not None
        assert config["name"] == "crisis_response"
        assert len(config["agents"]) == 3

    def test_load_preset_strategy_optimizer(self):
        from swarm.engine import load_preset
        config = load_preset("strategy_optimizer")
        assert config is not None
        assert config["name"] == "strategy_optimizer"

    def test_load_preset_macro_scan(self):
        from swarm.engine import load_preset
        config = load_preset("macro_scan")
        assert config is not None

    def test_load_preset_sub_agent_trading(self):
        from swarm.engine import load_preset
        config = load_preset("sub_agent_trading")
        assert config is not None

    def test_validate_preset_valid(self):
        from swarm.engine import validate_preset
        config = {
            "name": "test",
            "max_agents": 2,
            "agents": [
                {"role": "agent1", "prompt": "do something"},
                {"role": "agent2", "prompt": "do something else"},
            ],
        }
        errors = validate_preset(config)
        assert len(errors) == 0

    def test_validate_preset_missing_name(self):
        from swarm.engine import validate_preset
        config = {"agents": [{"role": "a", "prompt": "p"}]}
        errors = validate_preset(config)
        assert any("name" in e for e in errors)

    def test_validate_preset_missing_prompt(self):
        from swarm.engine import validate_preset
        config = {"name": "test", "agents": [{"role": "a"}]}
        errors = validate_preset(config)
        assert any("prompt" in e for e in errors)

    def test_run_swarm_daily_committee(self):
        from swarm.engine import run_swarm
        result = run_swarm("daily_committee")
        assert result["success"] is True
        assert result["preset"] == "daily_committee"
        assert len(result["agents"]) == 4

    def test_run_swarm_crisis_response(self):
        from swarm.engine import run_swarm
        result = run_swarm("crisis_response")
        assert result["success"] is True
        assert len(result["agents"]) == 3

    def test_run_swarm_nonexistent(self):
        from swarm.engine import run_swarm
        result = run_swarm("nonexistent_preset")
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_simulate_agent_tool_call(self):
        from swarm.engine import simulate_agent, register_tool
        register_tool("test_tool", lambda ctx: {"result": 42})
        agent = {"role": "tester", "model": "test", "tools": ["test_tool"], "prompt": "test"}
        result = simulate_agent(agent, {})
        assert result["role"] == "tester"
        assert result["tool_results"]["test_tool"]["result"] == 42

    def test_simulate_agent_unavailable_tool(self):
        from swarm.engine import simulate_agent
        agent = {"role": "tester", "tools": ["nonexistent_tool"], "prompt": "test"}
        result = simulate_agent(agent, {})
        assert result["tool_results"]["nonexistent_tool"]["status"] == "unavailable"

    def test_agents_have_prompts_in_all_presets(self):
        from swarm.engine import load_preset, list_presets
        for preset in list_presets():
            config = load_preset(preset["name"])
            for agent in config.get("agents", []):
                assert agent.get("prompt"), f"{preset['name']}: agent {agent['role']} missing prompt"
