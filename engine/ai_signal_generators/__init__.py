"""AI Signal Generators — autonomous signal generation agents."""

from core import Signal
from engine.ai_signal_generators.base import SignalGenerator
from engine.ai_signal_generators.registry import GeneratorRegistry, get_registry
from engine.ai_signal_generators.orchestrator import SignalOrchestrator, get_orchestrator
from engine.ai_signal_generators.miroshark_wrapper import MiroSharkGenerator
from engine.ai_signal_generators.trading_agents_wrapper import TradingAgentsGenerator
from engine.ai_signal_generators.macro_analyst import MacroAnalystGenerator
from engine.ai_signal_generators.kronos_runner import KronosGenerator
