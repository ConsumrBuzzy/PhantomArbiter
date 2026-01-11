"""
Pre-Flight Injection for pytest-asyncio.

This script bypasses the broken pytest plugin metadata loader by
manually registering the pytest-asyncio plugin before pytest starts.

Usage:
    .\.venv\Scripts\python.exe tests/inject_async.py tests -v
"""
import sys
import pytest
import pytest_asyncio.plugin


class AsyncInjector:
    """Forces pytest-asyncio to register even if the env loader fails."""
    
    def pytest_configure(self, config):
        # Check if already registered to avoid double-init
        if not config.pluginmanager.has_plugin("asyncio"):
            print("💉 Injecting pytest-asyncio plugin manually...")
            config.pluginmanager.register(pytest_asyncio.plugin, "asyncio")


if __name__ == "__main__":
    # 1. Force the Selector Loop Policy for Windows 3.12 stability
    import asyncio
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        print("✅ Windows Selector Loop Policy enforced.")

    # 2. Run pytest with the injector class passed as a plugin
    sys.exit(pytest.main(sys.argv[1:], plugins=[AsyncInjector()]))
