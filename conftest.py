"""
Root conftest.py to force pytest-asyncio plugin loading.
"""
import sys
import asyncio

# Force plugin load
pytest_plugins = ["pytest_asyncio"]

# Windows Selector Policy Workaround (Global)
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
