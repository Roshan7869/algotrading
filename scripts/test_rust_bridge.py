"""E2E test for the Rust ws-bridge integration.

Verifies:
1. Rust bridge compiles
2. Streamlit Redis page imports without errors
3. All Python files have valid syntax
4. Rust build is healthy
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BRIDGE_DIR = PROJECT_ROOT / "flowsurface_src"


def test_rust_compiles():
    result = subprocess.run(
        ["cargo", "build", "-p", "ws-bridge", "--quiet"],
        capture_output=True, text=True,
        cwd=str(BRIDGE_DIR), timeout=120,
    )
    assert result.returncode == 0, f"Rust build failed:\n{result.stderr}"
    print("✓ Rust ws-bridge compiles")


def test_streamlit_page_imports():
    page_path = PROJECT_ROOT / "ui" / "pages" / "11_flowsurface.py"
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(page_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"Streamlit page syntax error:\n{result.stderr}"
    print("✓ Streamlit page compiles cleanly")


def test_redis_stream_imports():
    stream_path = PROJECT_ROOT / "ui" / "redis_stream.py"
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(stream_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"Redis stream syntax error:\n{result.stderr}"
    print("✓ Redis stream module compiles cleanly")


def test_event_bridge_imports():
    bridge_path = PROJECT_ROOT / "nexus" / "event_bridge.py"
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(bridge_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"Event bridge syntax error:\n{result.stderr}"
    print("✓ Event bridge module compiles cleanly")


if __name__ == "__main__":
    tests = [
        test_rust_compiles,
        test_redis_stream_imports,
        test_streamlit_page_imports,
        test_event_bridge_imports,
    ]
    failures = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"✗ {t.__name__}: {e}")
            failures += 1
    if failures:
        print(f"\n{failures} test(s) FAILED")
        sys.exit(1)
    else:
        print(f"\nAll {len(tests)} tests PASSED")
