
import base64
import requests
from typing import Optional, Dict
from solders.pubkey import Pubkey
from config.settings import Settings
from src.shared.system.logging import Logger

class RaydiumStandardBridge:
    """
    Raydium Standard AMM (V4) Bridge
    Program ID: 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8
    
    Responsible for checking the "Migration Gap" - tokens that just graduated 
    from Pump.fun and are now on the Standard AMM (but not yet CLMM).
    """
    
    PROGRAM_ID = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
    LIQUIDITY_STATE_LAYOUT_V4_SIZE = 752
    
    def __init__(self):
        self.rpc_url = Settings.RPC_URL
    
    def find_pool(self, mint_a: str, mint_b: str) -> Optional[str]:
        """
        Find a Standard AMM pool account for the given pair.
        Check both permutations (A/B and B/A).
        """
        # Checks are expensive (getProgramAccounts), so we rely on RPC filtering.
        
        # Filter 1: coin=A, pc=B
        pool_a = self._query_pool(mint_a, mint_b)
        if pool_a: return pool_a
        
        # Filter 2: coin=B, pc=A
        pool_b = self._query_pool(mint_b, mint_a)
        if pool_b: return pool_b
        
        return None

    def _query_pool(self, coin_mint: str, pc_mint: str) -> Optional[str]:
        """Query RPC for pool execution."""
        # Raydium V4 Layout Offsets
        # coinMint: offset 400
        # pcMint: offset 432
        
        filters = [
            {"dataSize": self.LIQUIDITY_STATE_LAYOUT_V4_SIZE},
            {"memcmp": {"offset": 400, "bytes": coin_mint}},
            {"memcmp": {"offset": 432, "bytes": pc_mint}}
        ]
        
        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "getProgramAccounts",
            "params": [
                self.PROGRAM_ID,
                {"filters": filters, "encoding": "base64", "limit": 1} # Optimization: limit 1
            ]
        }
        
        try:
            resp = requests.post(self.rpc_url, json=payload, timeout=5)
            data = resp.json()
            
            if "result" in data and data["result"]:
                # Found the pool
                pool_pubkey = data["result"][0]["pubkey"]
                Logger.info(f"🏊 [RAY-STD] Found Pool {pool_pubkey} for {coin_mint[:4]}/{pc_mint[:4]}")
                return pool_pubkey
                
        except Exception as e:
            Logger.debug(f"[RAY-STD] RPC Query Failed: {e}")
            
        return None

    def get_pool_info(self, pool_address: str) -> Dict:
        """
        Get basic info (reserves) for a Standard Pool to gauge liquidity.
        """
        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
            "params": [pool_address, {"encoding": "base64"}]
        }
        try:
            resp = requests.post(self.rpc_url, json=payload, timeout=5)
            # Parsing would require struct unpacking. 
            # For now, just confirming existence and returning raw data size is enough for Phase 6A.
            if "result" in resp and resp["result"]["value"]:
                 return {"exists": True, "address": pool_address, "type": "STANDARD_AMM"}
        except:
            pass
        return {"exists": False}
