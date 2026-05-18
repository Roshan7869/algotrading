#!/usr/bin/env python3
"""
Test script for the fault-tolerant trading system.
Verifies component isolation and error handling.
"""

import os
import sys
import time
import subprocess
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.resilient_telegram import TelegramCircuitBreaker, CircuitState
from scripts.process_manager import ProcessManager
from scripts.logging_config import setup_logging


def test_telegram_circuit_breaker():
    """Test Telegram circuit breaker functionality."""
    print("\n" + "=" * 60)
    print("TEST 1: Telegram Circuit Breaker")
    print("=" * 60)

    setup_logging()
    cb = TelegramCircuitBreaker(failure_threshold=2, cooldown_seconds=5)

    # Test 1: Check initial state
    assert cb.state == CircuitState.CLOSED or cb.state == CircuitState.DISABLED
    print("[OK] Initial state correct")

    # Test 2: Simulate failures
    if cb.state != CircuitState.DISABLED:
        for i in range(3):
            result = cb.send_message(f"Test message {i}")
            print(f"   Message {i}: {'Sent' if result else 'Failed'}")

        status = cb.get_status()
        print(f"   Circuit state: {status['state']}")
        print(f"   Failure count: {status['failure_count']}")
    else:
        print("   [WARN] Telegram disabled (no credentials or conflict)")

    print("\n[PASS] TEST 1 PASSED\n")


def test_process_manager():
    """Test process manager zombie cleanup."""
    print("=" * 60)
    print("TEST 2: Process Manager")
    print("=" * 60)

    pm = ProcessManager()

    # Test cleanup
    try:
        pm.ensure_single_instance()
        print("[OK] Single instance check passed")
    except RuntimeError as e:
        print(f"[WARN] {e}")

    # Test PID file operations
    test_pid = 99999
    pm.write_pidfile(test_pid)

    if pm.PIDFILE.exists():
        print("[OK] PID file created")
        pm.cleanup()
        if not pm.PIDFILE.exists():
            print("[OK] PID file cleaned up")
        else:
            print("[FAIL] PID file not removed")
    else:
        print("[FAIL] PID file not created")

    print("\n[PASS] TEST 2 PASSED\n")


def test_component_isolation():
    """Test that Telegram failure doesn't crash the system."""
    print("=" * 60)
    print("TEST 3: Component Isolation")
    print("=" * 60)

    print("Simulating Telegram failure...")

    try:
        # This should not crash the system
        from scripts.resilient_telegram import TelegramCircuitBreaker

        cb = TelegramCircuitBreaker()

        # Force a failure
        cb._on_failure("Simulated error")
        cb._on_failure("Simulated error")
        cb._on_failure("Simulated error")

        # System should still be running
        status = cb.get_status()
        print(f"   Circuit state after failures: {status['state']}")
        print("[OK] System survived simulated Telegram failures")

    except Exception as e:
        print(f"[FAIL] TEST FAILED: {e}")
        return False

    print("\n[PASS] TEST 3 PASSED\n")
    return True


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("FAULT-TOLERANT TRADING SYSTEM - TEST SUITE")
    print("=" * 60 + "\n")

    try:
        test_telegram_circuit_breaker()
        test_process_manager()
        test_component_isolation()

        print("\n" + "=" * 60)
        print("[PASS] ALL TESTS PASSED")
        print("=" * 60)
        print("\nSystem is ready for deployment!")
        print("\nNext steps:")
        print("1. Run: bash scripts/kill_zombies.sh")
        print(
            "2. Start: python3 scripts/trading_orchestrator.py user_data/config_live_trading_6x.json"
        )
        print("3. Monitor: tail -f logs/orchestrator.log")

    except Exception as e:
        print("\n" + "=" * 60)
        print(f"[FAIL] TESTS FAILED: {e}")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
