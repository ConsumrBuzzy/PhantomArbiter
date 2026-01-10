"""
LST De-Pegger Logic
===================
Monitors LST/SOL ratios for discount opportunities.
"""

import asyncio
import time
import logging
from src.engines.lst_depeg.config import LSTConfig
from src.shared.drivers.virtual_driver import VirtualDriver, VirtualOrder

logger = logging.getLogger("phantom.lst")

from src.shared.feeds.jupiter_feed import JupiterFeed
from src.engines.base_engine import BaseEngine

class LSTEngine(BaseEngine):
    def __init__(self, mode: str = "paper"):
        super().__init__("lst", live_mode=(mode == "live"))
        self.config = LSTConfig
        self.jupiter = JupiterFeed()
        
        # Paper Wallet specific logic (if needed beyond VirtualDriver)
        if not self.live_mode:
             pass 
            
        # Determine real driver for live mode later
        if self.live_mode:
            logger.warning("[LST] Live mode not fully implemented, strictly monitoring.")

    async def tick(self):
        """Single execution step."""
        # 1. Fetch Prices
        prices = await self._fetch_lst_prices()
        
        # Update Driver Price Feed
        if not self.live_mode and self.driver:
            feed = {f"{t}/SOL": p for t, p in prices.items()}
            self.driver.set_price_feed(feed)
        
        # 2. Analyze & Updates
        update_data = {}
        
        for token, price in prices.items():
            fair = self.config.fair_value.get(token, 0)
            if fair == 0: continue
            
            deviation = (price - fair) / fair
            update_data[token] = {"price": price, "fair": fair, "diff": deviation}
            
            if deviation <= self.config.depeg_threshold:
                logger.info(f"🚨 DE-PEG DETECTED: {token} @ {price:.4f} SOL ({deviation*100:.2f}%)")
                await self._execute_signal(token, price, deviation)
        
        # 3. Broadcast
        if self._callback:
             await self._callback(update_data)

    async def _fetch_lst_prices(self):
        """Fetch real LST/SOL prices from Jupiter."""
        try:
            mints = [self.config.MINTS["jitoSOL"], self.config.MINTS["mSOL"]]
            results = await self.jupiter.get_multiple_prices(
                mints, vs_token=self.config.MINTS["SOL"]
            )
            
            prices = {}
            # Map mints back to symbols
            if self.config.MINTS["jitoSOL"] in results:
                prices["jitoSOL"] = results[self.config.MINTS["jitoSOL"]]
            else:
                prices["jitoSOL"] = self.config.fair_value["jitoSOL"] # Fallback
                
            if self.config.MINTS["mSOL"] in results:
                prices["mSOL"] = results[self.config.MINTS["mSOL"]]
            else:
                prices["mSOL"] = self.config.fair_value["mSOL"] # Fallback
                
            return prices
            
        except Exception as e:
            logger.error(f"[LST] Price fetch failed: {e}")
            return self.config.fair_value.copy() # Fallback to fair value (no diff)

    async def _execute_signal(self, token: str, price: float, deviation: float):
        if self.mode == "paper" and self.driver:
            # Create virtual order
            await self.driver.place_order(VirtualOrder(
                symbol=f"{token}/SOL",
                side="buy",
                size=10.0, # 10 SOL worth
                order_type="market",
                metadata={"strategy": "depeg", "deviation": deviation}
            ))
