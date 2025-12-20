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
    Python wrapper for Meteora DLMM TypeScript bridge.
    
    Calls the bundled JS file via subprocess and parses JSON output.
    """
    
    def __init__(self, bridge_path: Optional[str] = None):
        """
        Initialize the bridge.
        
        Args:
            bridge_path: Path to meteora_bridge.js. Defaults to bridges/meteora_bridge.js
        """
        if bridge_path:
            self.bridge_path = Path(bridge_path)
        else:
            # Default path relative to project root
            project_root = Path(__file__).parent.parent.parent.parent
            self.bridge_path = project_root / "bridges" / "meteora_bridge.js"
        
        if not self.bridge_path.exists():
            Logger.warning(f"[METEORA] Bridge not found at {self.bridge_path}")
            Logger.warning("[METEORA] Run: cd bridges && npm install && npm run build")
        
        # Cache for pool info
        self._pool_cache: Dict[str, MeteoraPriceResult] = {}
    
    def _run_command(self, *args) -> Dict[str, Any]:
        """Run the bridge command and parse JSON output."""
        cmd = ["node", str(self.bridge_path)] + list(args)
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.bridge_path.parent)
            )
            
            if result.returncode != 0:
                Logger.error(f"[METEORA] Bridge error: {result.stderr}")
                return {"success": False, "error": result.stderr or "Unknown error"}
            
            # Parse JSON output
            try:
                return json.loads(result.stdout.strip())
            except json.JSONDecodeError as e:
                Logger.error(f"[METEORA] JSON parse error: {e}")
                Logger.debug(f"[METEORA] Raw output: {result.stdout[:200]}")
                return {"success": False, "error": f"JSON parse error: {e}"}
                
        except subprocess.TimeoutExpired:
            Logger.error("[METEORA] Bridge timeout (30s)")
            return {"success": False, "error": "Timeout"}
        except FileNotFoundError:
            Logger.error("[METEORA] Node.js not found. Install Node.js to use Meteora bridge.")
            return {"success": False, "error": "Node.js not found"}
        except Exception as e:
            Logger.error(f"[METEORA] Bridge exception: {e}")
            return {"success": False, "error": str(e)}
    
    def get_price(self, pool_address: str, use_cache: bool = True) -> MeteoraPriceResult:
        """
        Get current price from a Meteora DLMM pool.
        
        Args:
            pool_address: The pool's public key
            use_cache: Use cached result if available (default True)
            
        Returns:
            MeteoraPriceResult with price data
        """
        if use_cache and pool_address in self._pool_cache:
            return self._pool_cache[pool_address]
        
        data = self._run_command("price", pool_address)
        
        result = MeteoraPriceResult(
            success=data.get("success", False),
            pool=data.get("pool", pool_address),
            token_x=data.get("tokenX", ""),
            token_y=data.get("tokenY", ""),
            price_x_to_y=data.get("priceXtoY", 0.0),
            price_y_to_x=data.get("priceYtoX", 0.0),
            active_bin_id=data.get("activeBinId", 0),
            error=data.get("error")
        )
        
        if result.success:
            self._pool_cache[pool_address] = result
            Logger.debug(f"[METEORA] Price: {result.token_x[:8]}/{result.token_y[:8]} = {result.price_x_to_y:.8f}")
        
        return result
    
    def get_quote(
        self, 
        pool_address: str, 
        input_mint: str, 
        amount_in: int
    ) -> MeteoraQuoteResult:
        """
        Get a swap quote from a Meteora DLMM pool.
        
        Args:
            pool_address: The pool's public key
            input_mint: Token mint address to swap FROM
            amount_in: Amount in smallest units (lamports, etc.)
            
        Returns:
            MeteoraQuoteResult with expected output
        """
        data = self._run_command("quote", pool_address, input_mint, str(amount_in))
        
        result = MeteoraQuoteResult(
            success=data.get("success", False),
            input_mint=data.get("inputMint", input_mint),
            output_mint=data.get("outputMint", ""),
            input_amount=int(data.get("inputAmount", amount_in)),
            output_amount=int(data.get("outputAmount", 0)),
            price_impact=float(data.get("priceImpact", 0)),
            fee=int(data.get("fee", 0)),
            error=data.get("error")
        )
        
        if result.success:
            Logger.debug(f"[METEORA] Quote: {result.input_amount} → {result.output_amount} (impact: {result.price_impact:.4f})")
        
        return result
    
    def swap(
        self,
        pool_address: str,
        input_mint: str,
        amount_in: int,
        slippage_bps: int,
        private_key: str
    ) -> MeteoraSwapResult:
        """
        Execute a swap on a Meteora DLMM pool.
        
        ⚠️ LIVE EXECUTION - Uses real funds!
        
        Args:
            pool_address: The pool's public key
            input_mint: Token mint address to swap FROM
            amount_in: Amount in smallest units
            slippage_bps: Slippage tolerance in basis points (100 = 1%)
            private_key: Base58-encoded wallet private key
            
        Returns:
            MeteoraSwapResult with transaction signature
        """
        Logger.info(f"[METEORA] Executing swap: {amount_in} of {input_mint[:8]}...")
        
        data = self._run_command(
            "swap",
            pool_address,
            input_mint,
            str(amount_in),
            str(slippage_bps),
            private_key
        )
        
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
        """Clear the price cache."""
        self._pool_cache.clear()
    
    def is_available(self) -> bool:
        """Check if the bridge is available."""
        return self.bridge_path.exists()


# ═══════════════════════════════════════════════════════════════════
# KNOWN METEORA DLMM POOLS
# ═══════════════════════════════════════════════════════════════════

# Common DLMM pools for arbitrage
# Verified from: https://dlmm-api.meteora.ag/pair/all
METEORA_POOLS = {
    # Format: "PAIR": ("POOL_ADDRESS", BIN_STEP)
    # SOL/USDC - bin step 10 (tighter spreads, more common)
    "SOL/USDC": "L2unwYfS6reFe7yqC4LwY7e4pEru23rE8rA7fX7e1e6",
    # SOL/USDC - bin step 100 (wider spreads, more stable)
    "SOL/USDC_100": "ARwi1S4DaiTG5DX7S4M4ZsrXqpMD1MrTmbu9ue2tpmEq",
    # USDC/USDT - bin step 2 (stables, very tight)
    "USDC/USDT": "6L689vto58p4fPMe3qT6nKxPz8zG5mC99vWscEym89G6",
}


# ═══════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("Meteora DLMM Bridge Test")
    print("=" * 60)
    
    bridge = MeteoraBridge()
    
    if not bridge.is_available():
        print("❌ Bridge not available. Run:")
        print("   cd bridges && npm install && npm run build")
        exit(1)
    
    print("\n1. Testing price fetch...")
    
    # Test with SOL/USDC pool
    pool = METEORA_POOLS.get("SOL/USDC")
    if pool:
        result = bridge.get_price(pool)
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
