"""
Meteora DLMM Python Bridge
===========================
Wrapper for the TypeScript Meteora DLMM CLI bridge.

Uses subprocess to call the bundled JS file for:
- Price fetching (for scanning)
- Quote fetching (pre-trade check)
- Swap execution (live trades)

Usage:
    bridge = MeteoraBridge()
    price = bridge.get_price("POOL_ADDRESS")
    quote = bridge.get_quote("POOL_ADDRESS", "INPUT_MINT", 1000000)
    result = bridge.swap("POOL_ADDRESS", "INPUT_MINT", 1000000, 100, "PRIVATE_KEY")
"""

import subprocess
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

from src.shared.system.logging import Logger


@dataclass
class MeteoraPriceResult:
    """Result from price query."""
    success: bool
    pool: str
    token_x: str
    token_y: str
    price_x_to_y: float
    price_y_to_x: float
    active_bin_id: int
    error: Optional[str] = None


@dataclass
class MeteoraQuoteResult:
    """Result from quote query."""
    success: bool
    input_mint: str
    output_mint: str
    input_amount: int
    output_amount: int
    price_impact: float
    fee: int
    error: Optional[str] = None


@dataclass
class MeteoraSwapResult:
    """Result from swap execution."""
    success: bool
    signature: Optional[str]
    input_mint: str
    output_mint: str
    input_amount: int
    output_amount: int
    error: Optional[str] = None


class MeteoraBridge:
    """
    Python wrapper for Meteora DLMM TypeScript bridge via Persistent Daemon.
    """
    
    def __init__(self, bridge_path: Optional[str] = None):
        """
        Initialize the bridge.
        """
        if bridge_path:
            self.bridge_path = Path(bridge_path)
        else:
            project_root = Path(__file__).parent.parent.parent.parent
            self.bridge_path = project_root / "bridges" / "meteora_bridge.js"
        
        if not self.bridge_path.exists():
            Logger.warning(f"[METEORA] Bridge not found at {self.bridge_path}")
            Logger.warning("[METEORA] Run: cd bridges && npm install && npm run build")
        
        self._daemon = None
        self._pool_cache: Dict[str, MeteoraPriceResult] = {}

    def _ensure_daemon(self):
        """Start daemon if not running."""
        if self._daemon and self._daemon.poll() is None:
            return

        try:
            cmd = ["node", str(self.bridge_path), "daemon"]
            self._daemon = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(self.bridge_path.parent),
                bufsize=1
            )
            Logger.info("[METEORA] Daemon started (PID: %s)", self._daemon.pid)
        except Exception as e:
            Logger.error(f"[METEORA] Failed to start daemon: {e}")
            self._daemon = None

    def _send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Send command to daemon via IPC."""
        self._ensure_daemon()
        if not self._daemon:
            return {"success": False, "error": "Daemon failed to start"}
            
        try:
            payload = json.dumps(command) + "\n"
            self._daemon.stdin.write(payload)
            self._daemon.stdin.flush()
            
            line = self._daemon.stdout.readline()
            if not line:
                Logger.error("[METEORA] Daemon closed stream")
                self._daemon = None
                return {"success": False, "error": "Daemon closed stream"}
                
            return json.loads(line.strip())
        except Exception as e:
            Logger.error(f"[METEORA] IPC error: {e}")
            if self._daemon:
                self._daemon.kill()
                self._daemon = None
            return {"success": False, "error": str(e)}

    def get_price(self, pool_address: str, use_cache: bool = True) -> MeteoraPriceResult:
        if use_cache and pool_address in self._pool_cache:
            return self._pool_cache[pool_address]
        
        data = self._send_command({"command": "price", "pool": pool_address})
        
        result = MeteoraPriceResult(
            success=data.get("success", False),
            pool=data.get("pool", pool_address),
            token_x=data.get("tokenX", ""),
            token_y=data.get("tokenY", ""),
            price_x_to_y=float(data.get("priceXtoY", 0)),
            price_y_to_x=float(data.get("priceYtoX", 0)),
            active_bin_id=int(data.get("activeBinId", 0)),
            error=data.get("error")
        )
        
        if result.success:
            self._pool_cache[pool_address] = result
        
        return result
    
    def get_quote(
        self, 
        pool_address: str, 
        input_mint: str, 
        amount_in: int
    ) -> MeteoraQuoteResult:
        data = self._send_command({
            "command": "quote",
            "pool": pool_address,
            "inputMint": input_mint,
            "amount": str(amount_in)
        })
        
        return MeteoraQuoteResult(
            success=data.get("success", False),
            input_mint=data.get("inputMint", input_mint),
            output_mint=data.get("outputMint", ""),
            input_amount=int(data.get("inputAmount", amount_in)),
            output_amount=int(data.get("outputAmount", 0)),
            price_impact=float(data.get("priceImpact", 0)),
            fee=int(data.get("fee", 0)),
            error=data.get("error")
        )
    
    def swap(
        self,
        pool_address: str,
        input_mint: str,
        amount_in: int,
        slippage_bps: int,
        private_key: str
    ) -> MeteoraSwapResult:
        Logger.info(f"[METEORA] Executing swap: {amount_in} of {input_mint[:8]}...")
        
        data = self._send_command({
            "command": "swap",
            "pool": pool_address,
            "inputMint": input_mint,
            "amount": str(amount_in),
            "slippageBps": slippage_bps,
            "privateKey": private_key
        })
        
        result = MeteoraSwapResult(
            success=data.get("success", False),
            signature=data.get("signature"),
            input_mint=data.get("inputMint", input_mint),
            output_mint=data.get("outputMint", ""),
            input_amount=int(data.get("inputAmount", amount_in)),
            output_amount=int(data.get("outputAmount", 0)),
            error=data.get("error")
        )
        
        if result.success:
            Logger.info(f"[METEORA] ✅ Swap success: {result.signature}")
        else:
            Logger.error(f"[METEORA] ❌ Swap failed: {result.error}")
        
        return result
    
    def clear_cache(self):
        self._pool_cache.clear()
    
    def is_available(self) -> bool:
        return self.bridge_path.exists()


# ═══════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from src.shared.execution.pool_fetcher import MeteoraPoolFetcher
    
    print("=" * 60)
    print("Meteora DLMM Bridge Test")
    print("=" * 60)
    
    bridge = MeteoraBridge()
    
    if not bridge.is_available():
        print("❌ Bridge not available. Run:")
        print("   cd bridges; npm install; npm run build")
        exit(1)
    
    # Dynamically fetch valid pool
    print("\n1. Fetching valid pool from Meteora API...")
    fetcher = MeteoraPoolFetcher()
    best_pool = fetcher.get_best_pool("SOL", "USDC", min_liquidity=50000)
    
    if not best_pool:
        print("   ❌ Could not find SOL/USDC pool")
        exit(1)
    
    print(f"   ✅ Found: {best_pool.name}")
    print(f"   Address: {best_pool.address}")
    print(f"   Liquidity: ${best_pool.liquidity:,.0f}")
    
    print("\n2. Testing price fetch via bridge...")
    result = bridge.get_price(best_pool.address)
    
    if result.success:
        print(f"   ✅ Price fetched!")
        print(f"   Token X: {result.token_x[:16]}...")
        print(f"   Token Y: {result.token_y[:16]}...")
        print(f"   Price X→Y: {result.price_x_to_y:.6f}")
        print(f"   Active Bin: {result.active_bin_id}")
    else:
        print(f"   ❌ Error: {result.error}")
    
    print("\n" + "=" * 60)
    print("Test complete!")
