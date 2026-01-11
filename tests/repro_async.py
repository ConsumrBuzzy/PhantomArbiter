
import pytest
import asyncio

@pytest.mark.asyncio
async def test_async_basic():
    await asyncio.sleep(0.01)
    assert True
