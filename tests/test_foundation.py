"""
Foundation Test - Verifies async testing infrastructure.

If this passes, the environment is stable for further testing.
This is the "Green Light" test that must pass before any other tests.
"""
from __future__ import annotations

import asyncio
import sys

import pytest


@pytest.mark.asyncio
async def test_asyncio_foundation() -> None:
    """If this passes, the Zombie state is cured."""
    await asyncio.sleep(0.1)
    assert True


@pytest.mark.asyncio
async def test_event_loop_type() -> None:
    """Verify we're using SelectorEventLoop on Windows."""
    loop = asyncio.get_running_loop()
    loop_name = type(loop).__name__
    
    if sys.platform == 'win32':
        # Should be _WindowsSelectorEventLoop, NOT _WindowsProactorEventLoop
        assert 'Selector' in loop_name or 'selector' in loop_name.lower(), \
            f"Expected Selector loop, got {loop_name}"
    
    assert loop.is_running()


@pytest.mark.asyncio
async def test_concurrent_tasks() -> None:
    """Verify concurrent async tasks work correctly."""
    results: list[int] = []
    
    async def task(n: int) -> None:
        await asyncio.sleep(0.01)
        results.append(n)
    
    await asyncio.gather(task(1), task(2), task(3))
    
    assert len(results) == 3
    assert set(results) == {1, 2, 3}
