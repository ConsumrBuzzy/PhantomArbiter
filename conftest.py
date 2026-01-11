
# Root conftest to ensure pytest-asyncio is loaded early
import sys
import pytest

try:
    import pytest_asyncio.plugin
    def pytest_configure(config):
        if not config.pluginmanager.hasplugin("pytest_asyncio"):
            config.pluginmanager.register(pytest_asyncio.plugin, name="pytest_asyncio")
            print("DEBUG: Manually registered pytest-asyncio in root conftest", file=sys.stderr)
except ImportError:
    print("DEBUG: Could not import pytest_asyncio.plugin", file=sys.stderr)
