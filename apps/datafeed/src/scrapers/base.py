import abc
import asyncio
import logging
from typing import Dict, Any, Callable, Awaitable

# Unified log format
logger = logging.getLogger("DataFeed")

class BaseScraper(abc.ABC):
    """
    Abstract Base Class for all DataFeed Scrapers.
    Enforces a standard interface for 'start', 'stop', and 'health'.
    """

    def __init__(self, name: str, source_id: str, interval: float = 1.0):
        self.name = name
        self.source_id = source_id
        self.interval = interval
        self._running = False
        self._callback: Callable[[Dict[str, Any]], Awaitable[None]] = None
        self._stats = {"updates": 0, "errors": 0, "last_update": 0.0}

    def register_callback(self, callback: Callable[[Dict[str, Any]], Awaitable[None]]):
        """Register an async callback to receive normalized data."""
        self._callback = callback

    async def start(self):
        """Start the scraping loop."""
        if self._running:
            return
        self._running = True
        logger.info(f"[{self.name}] Starting scraper callback loop ({self.interval}s)...")
        asyncio.create_task(self._loop())

    async def stop(self):
        """Stop the scraping loop."""
        self._running = False
        logger.info(f"[{self.name}] Stopping scraper...")

    async def _loop(self):
        """Internal loop handling frequency and errors."""
        while self._running:
            try:
                start_time = asyncio.get_running_loop().time()
                data = await self.scrape()
                if data and self._callback:
                    # If list, emit multiple
                    if isinstance(data, list):
                        for item in data:
                            await self._callback(item)
                            self._stats["updates"] += 1
                    else:
                        await self._callback(data)
                        self._stats["updates"] += 1
                    
                    self._stats["last_update"] = asyncio.get_running_loop().time()

                # Sleep balance
                elapsed = asyncio.get_running_loop().time() - start_time
                sleep_time = max(0.01, self.interval - elapsed)
                await asyncio.sleep(sleep_time)

            except Exception as e:
                self._stats["errors"] += 1
                logger.error(f"[{self.name}] Error in loop: {e}")
                await asyncio.sleep(5.0)  # Error cool-off

    @abc.abstractmethod
    async def scrape(self) -> Any:
        """
        Implement the actual gathering logic here.
        Must return a dict or list of dicts with standardized keys:
        {
            "token": str,
            "price": float,
            "source": str,
            "timestamp": int (ms)
        }
        """
        pass

    def get_stats(self) -> Dict[str, Any]:
        return self._stats
