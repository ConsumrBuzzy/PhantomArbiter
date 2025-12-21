"""
V48.1: Jito Block Engine Adapter (Async)
========================================
Non-blocking priority transaction execution via Jito Labs.

Features:
- Async HTTP (httpx) to prevent event loop blocking
- Regional failover with rotation
- Pre-flight bundle simulation
"""

import time
import random
import asyncio
import httpx
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass

from solders.pubkey import Pubkey
from solders.system_program import transfer, TransferParams
from solders.transaction import Transaction
from src.shared.system.logging import Logger

@dataclass
class TipConfig:
    lamports: int = 10000
    max_lamports: int = 100000
    dynamic_tip: bool = False


class JitoAdapter:
    # Block Engine endpoints
    MAINNET_API = "https://mainnet.block-engine.jito.wtf/api/v1/bundles"
    
    REGIONAL_ENDPOINTS = {
        "mainnet": "https://mainnet.block-engine.jito.wtf/api/v1/bundles",
        "frankfurt": "https://frankfurt.mainnet.block-engine.jito.wtf/api/v1/bundles",
        "amsterdam": "https://amsterdam.mainnet.block-engine.jito.wtf/api/v1/bundles",
        "ny": "https://ny.mainnet.block-engine.jito.wtf/api/v1/bundles",
        "tokyo": "https://tokyo.mainnet.block-engine.jito.wtf/api/v1/bundles",
    }
    
    TIP_CACHE_TTL = 300
    REQUEST_TIMEOUT = 5
    RATE_LIMIT_COOLDOWN = 5
    
    def __init__(self, region: str = "ny"):
        all_endpoints = list(self.REGIONAL_ENDPOINTS.values())
        preferred = self.REGIONAL_ENDPOINTS.get(region, self.MAINNET_API)
        fallback = [ep for ep in all_endpoints if ep != preferred]
        random.shuffle(fallback)
        self._endpoints = [preferred] + fallback
        self._current_endpoint_idx = 0
        self.api_url = self._endpoints[0]
        
        self._tip_accounts = []
        self._tip_accounts_fetched = 0
        self._bundles_submitted = 0
        self._bundles_landed = 0
        self._rate_limited_until = 0

    def _rotate_endpoint(self):
        self._current_endpoint_idx = (self._current_endpoint_idx + 1) % len(self._endpoints)
        self.api_url = self._endpoints[self._current_endpoint_idx]
        Logger.info(f"   🔄 [JITO] Rotating endpoint to: {self.api_url.split('//')[1].split('.')[0]}...")

    async def _rpc_call(self, method: str, params: list = None, max_retries: int = 5) -> Optional[Dict]:
        if time.time() < self._rate_limited_until:
            return None
            
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}
        
        async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:
            for attempt in range(max_retries):
                try:
                    response = await client.post(self.api_url, json=payload)
                    
                    if response.status_code == 200:
                        return response.json()
                    elif response.status_code == 429:
                        Logger.warning(f"   ⚠️ [JITO] Rate Limit (429) on {self.api_url}")
                        self._rotate_endpoint()
                        # Use asyncio.sleep for non-blocking wait
                        await asyncio.sleep(0.2)
                        continue
                    else:
                        Logger.debug(f"   ⚠️ [JITO] HTTP {response.status_code}")
                        self._rotate_endpoint()
                        continue
                        
                except Exception as e:
                    Logger.debug(f"   ⚠️ [JITO] RPC Error: {e}")
                    self._rotate_endpoint()
                    await asyncio.sleep(0.5)
        
        self._rate_limited_until = time.time() + self.RATE_LIMIT_COOLDOWN
        Logger.warning(f"   ❌ [JITO] All regions failed. Cooldown {self.RATE_LIMIT_COOLDOWN}s")
        return None

    async def get_tip_accounts(self, force_refresh: bool = False) -> List[str]:
        now = time.time()
        if not force_refresh and self._tip_accounts:
            if now - self._tip_accounts_fetched < self.TIP_CACHE_TTL:
                return self._tip_accounts
        
        response = await self._rpc_call("getTipAccounts")
        if response and isinstance(response, dict):
            accounts = response.get("result", [])
            if isinstance(accounts, list) and len(accounts) > 0:
                self._tip_accounts = accounts
                self._tip_accounts_fetched = now
                Logger.info(f"   ✅ [JITO] Cached {len(accounts)} tip accounts")
                return accounts
        return self._tip_accounts or []

    async def get_random_tip_account(self) -> Optional[str]:
        accounts = await self.get_tip_accounts()
        return random.choice(accounts) if accounts else None
    
    async def is_available(self) -> bool:
        """Async availability check."""
        accounts = await self.get_tip_accounts()
        return len(accounts) > 0

    async def submit_bundle(self, serialized_transactions: List[str]) -> Optional[str]:
        if not serialized_transactions: return None
        
        # Note: Tip account logic handled by caller consuming get_random_tip_account
        
        response = await self._rpc_call("sendBundle", [serialized_transactions])
        self._bundles_submitted += 1
        
        if response and isinstance(response, dict):
            bundle_id = response.get("result")
            if bundle_id:
                Logger.info(f"   🚀 [JITO] Bundle submitted: {bundle_id[:16]}...")
                self._rate_limited_until = time.time() + 3
                return bundle_id
            error = response.get("error", {})
            Logger.warning(f"   ❌ [JITO] Submit failed: {error}")
            return None
        return None

    async def simulate_bundle(self, serialized_transactions: List[str]) -> Dict:
        # V123 Safety: Simulate before send
        response = await self._rpc_call("simulateBundle", [{"encodedTransactions": serialized_transactions}])
        if response and isinstance(response, dict):
            result = response.get("result", {}).get("value", {})
            err = result.get("err")
            logs = result.get("logs", [])
            if err:
                Logger.warning(f"   🛑 [JITO] Simulation Failed: {err}")
                return {"success": False, "error": str(err), "logs": logs}
            return {"success": True, "error": None, "logs": logs}
        return {"success": False, "error": "RPC failed", "logs": []}

    async def get_bundle_status(self, bundle_id: str) -> Optional[Dict]:
        response = await self._rpc_call("getInflightBundleStatuses", [[bundle_id]])
        if response and isinstance(response, dict):
            return response.get("result")
        return None

    async def wait_for_confirmation(self, bundle_id: str, timeout: float = 30.0) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            try:
                status = await self.get_bundle_status(bundle_id)
                if status:
                    values = status.get("value", [])
                    if values:
                        bundle_status = values[0] if isinstance(values, list) else values
                        state = bundle_status.get("status", "")
                        if state == "Landed":
                            self._bundles_landed += 1
                            Logger.info(f"   ✅ [JITO] Bundle LANDED: {bundle_id[:16]}...")
                            return True
                        elif state in ("Invalid", "Failed"):
                            Logger.warning(f"   ❌ [JITO] Bundle FAILED: {state}")
                            return False
            except Exception:
                pass
            await asyncio.sleep(2.0)
        return False
        
    def get_stats(self) -> Dict[str, int]:
        return {
            "bundles_submitted": self._bundles_submitted,
            "bundles_landed": self._bundles_landed
        }
