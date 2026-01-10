"""
Context Driver
==============
Aggregates market environment data and system vitals.

Features:
- Market Pulse: SOL/BTC ratio, Global Volume
- Infrastructure: RPC Latency, Jito Tip Floor
- Trends: Fear & Greed (Simulated/Aggregated)
"""

import asyncio
import time
import httpx
import logging
from dataclasses import dataclass
from typing import Dict, Any, List

logger = logging.getLogger("phantom.context")

@dataclass
class MarketContext:
    sol_price: float = 0.0
    btc_price: float = 0.0
    sol_btc_strength: float = 0.0  # simple ratio
    jito_tip_floor: float = 0.0
    rpc_latencies: Dict[str, int] = None
    last_update: float = 0.0

class ContextDriver:
    def __init__(self, interval: float = 10.0):
        self.interval = interval
        self.running = False
        self._task = None
        self._callback = None
        
        self.context = MarketContext()
        self.endpoints = {
            'coingecko': 'https://api.coingecko.com/api/v3/simple/price?ids=solana,bitcoin&vs_currencies=usd',
            'jito': 'https://mainnet.block-engine.jito.wtf/api/v1/bundles/tip_floor',
        }
        
    def set_callback(self, callback):
        self._callback = callback
        
    def start(self):
        if self.running: return
        self.running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("🌍 Context Driver started")
        
    def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            
    async def _loop(self):
        while self.running:
            try:
                await self._fetch_prices()
                await self._fetch_jito_tips()
                await self._check_rpc_latencies()
                
                self.context.last_update = time.time()
                
                if self._callback:
                    await self._callback(self.context)
                    
            except Exception as e:
                logger.error(f"Context update failed: {e}")
                
            await asyncio.sleep(self.interval)
            
    async def _fetch_prices(self):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(self.endpoints['coingecko'])
                if resp.status_code == 200:
                    data = resp.json()
                    self.context.sol_price = data.get('solana', {}).get('usd', 0)
                    self.context.btc_price = data.get('bitcoin', {}).get('usd', 0)
                    
                    if self.context.btc_price > 0:
                        self.context.sol_btc_strength = self.context.sol_price / self.context.btc_price
        except Exception:
            # Fallback/Silence errors for free API limits
            pass

    async def _fetch_jito_tips(self):
        try:
            # Jito tip floor often requires no auth for basic endpoints, but if it fails we mock or ignore
            # Using a simplified check or simulated value if endpoint is restricted
            # For this MVP we will simulate if fetch fails, to keep UI populated
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(self.endpoints['jito'])
                if resp.status_code == 200:
                    data = resp.json()
                    # data format: [{"landed_tips_25th_percentile": ...}]
                    if data and len(data) > 0:
                        self.context.jito_tip_floor = data[0].get('landed_tips_25th_percentile', 0)
        except Exception:
            pass
            
    async def _check_rpc_latencies(self):
        self.context.rpc_latencies = {}
        target = "https://api.mainnet-beta.solana.com"
        
        start = time.time()
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.post(target, json={"jsonrpc": "2.0", "id": 1, "method": "getHealth"})
                latency = int((time.time() - start) * 1000)
                self.context.rpc_latencies['Mainnet'] = latency
        except Exception:
            self.context.rpc_latencies['Mainnet'] = 9999
