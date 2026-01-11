
import pytest
import sys
import pluggy

def test_plugin_list():
    pm = pytest.PytestPluginManager()
    from _pytest.config import get_plugin_manager
    # This is a bit hacky, normally we'd run pytest options
    print(f"Pytest Version: {pytest.__version__}")
    try:
        import pytest_asyncio
        print(f"pytest-asyncio imported successfully: {pytest_asyncio.__version__}")
        print(f"pytest-asyncio file: {pytest_asyncio.__file__}")
    except ImportError as e:
        print(f"FAILED to import pytest_asyncio: {e}")

if __name__ == "__main__":
    test_plugin_list()
