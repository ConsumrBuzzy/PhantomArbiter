
import sys
import pytest
from _pytest.config import get_plugin_manager
from _pytest.config import get_config
from _pytest.main import Session

try:
    pm = get_plugin_manager()
    print("Loading pytest_asyncio manually...")
    # Try filtering for pytest_asyncio
    # In recent pytest, we might need a Config object
    
    import pytest_asyncio.plugin
    print(f"Successfully imported pytest_asyncio.plugin: {pytest_asyncio.plugin}")
    
    # Try registering it logic
    pm.register(pytest_asyncio.plugin, name="pytest_asyncio")
    print("Registered successfully manually.")
    
except Exception as e:
    print(f"FAILED to load/register: {e}")
    import traceback
    traceback.print_exc()

print("Verifying if pytest sees it automatically:")
import subprocess
subprocess.run([sys.executable, "-m", "pytest", "--trace-config", "tests/repro_async.py"], stderr=sys.stderr, stdout=sys.stdout)
