
# Root conftest to force load plugins
import pytest
import sys

# Force pytest-asyncio to load
pytest_plugins = ["pytest_asyncio"]

def pytest_configure(config):
    # Debug print to verify this hook is called
    print("DEBUG: Root conftest pytest_configure called", file=sys.stderr)
    if config.pluginmanager.hasplugin("pytest_asyncio"):
        print("DEBUG: pytest-asyncio IS registered", file=sys.stderr)
    else:
        print("DEBUG: pytest-asyncio IS NOT registered", file=sys.stderr)
