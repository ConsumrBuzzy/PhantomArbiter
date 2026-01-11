"""
Root conftest.py - Force pytest-asyncio plugin loading.
Must be at project root to ensure plugin is loaded before test collection.
"""
import sys
import asyncio

# Register pytest-asyncio plugin BEFORE any tests are collected
pytest_plugins = ["pytest_asyncio"]

# Windows: Force SelectorEventLoopPolicy to avoid ProactorEventLoop issues
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
