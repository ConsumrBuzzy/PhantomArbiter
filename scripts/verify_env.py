#!/usr/bin/env python
"""
Environment Verification Script for PhantomArbiter Test Suite.

Run this BEFORE running any tests to confirm the "Zombie" state is cured.

Usage:
    .\.venv\Scripts\python.exe scripts/verify_env.py
"""
from __future__ import annotations

import sys
import asyncio


def check_python_version() -> None:
    """Verify Python 3.12+ is being used."""
    print(f"[CHECK] Python version: {sys.version}")
    assert sys.version_info >= (3, 12), "Requires Python 3.12+"
    print("[PASS] Python version OK")


def check_event_loop_policy() -> None:
    """Verify Windows uses SelectorEventLoopPolicy."""
    if sys.platform == 'win32':
        policy = asyncio.get_event_loop_policy()
        policy_name = type(policy).__name__
        print(f"[CHECK] Event loop policy: {policy_name}")
        if 'Selector' not in policy_name:
            print("[WARN] Still using ProactorEventLoopPolicy, setting Selector...")
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        print("[PASS] Event loop policy OK")


def check_pytest_versions() -> None:
    """Verify correct pytest and pytest-asyncio versions."""
    try:
        import pytest
        import pytest_asyncio
    except ImportError as e:
        raise AssertionError(f"Missing test dependency: {e}")
    
    print(f"[CHECK] pytest version: {pytest.__version__}")
    print(f"[CHECK] pytest-asyncio version: {pytest_asyncio.__version__}")
    
    # Allow 7.4.x series
    if not pytest.__version__.startswith("7.4"):
        print(f"[WARN] Expected pytest 7.4.x, got {pytest.__version__}")
    else:
        print("[PASS] pytest version OK")
    
    # Allow 0.23.x series
    if not pytest_asyncio.__version__.startswith("0.23"):
        print(f"[WARN] Expected pytest-asyncio 0.23.x, got {pytest_asyncio.__version__}")
    else:
        print("[PASS] pytest-asyncio version OK")


def check_venv_priority() -> None:
    """Verify VENV is first in sys.path."""
    print(f"[CHECK] sys.executable: {sys.executable}")
    if '.venv' in sys.executable or 'venv' in sys.executable:
        print("[PASS] Running from VENV")
    else:
        print("[WARN] May not be running from VENV - check sys.executable")
    
    print(f"[CHECK] sys.path[0]: {sys.path[0]}")


async def async_smoke_test() -> bool:
    """Simple async function to verify event loop works."""
    await asyncio.sleep(0.01)
    return True


def main() -> int:
    """Run all environment checks."""
    print("=" * 60)
    print("PhantomArbiter Environment Verification")
    print("=" * 60)
    
    try:
        check_python_version()
        check_event_loop_policy()
        check_pytest_versions()
        check_venv_priority()
        
        # Async smoke test
        print("[CHECK] Running async smoke test...")
        result = asyncio.run(async_smoke_test())
        assert result is True
        print("[PASS] Async smoke test OK")
        
        print("=" * 60)
        print("[SUCCESS] Environment is READY for testing!")
        print("=" * 60)
        return 0
        
    except Exception as e:
        print(f"[FAIL] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
