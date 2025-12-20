"""
Raydium CLMM Bridge
===================
Python wrapper for Raydium Concentrated Liquidity swaps via TypeScript bridge.

Usage:
    from src.shared.execution.raydium_bridge import RaydiumBridge
    
    bridge = RaydiumBridge()
    quote = bridge.get_quote(pool_address, input_mint, amount)
    result = bridge.execute_swap(pool_address, input_mint, amount, slippage_bps)
"""

import subprocess
import json
import os
from typing import Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path

from src.shared.system.logging import Logger


@dataclass
class RaydiumQuoteResult:
    """Quote result from Raydium CLMM."""
    success: bool
    input_mint: str
    output_mint: str
    input_amount: float
    output_amount: float
    price_impact: float
    fee: float
    error: Optional[str] = None


@dataclass
class RaydiumSwapResult:
    """Swap execution result from Raydium CLMM."""
    success: bool
    signature: Optional[str]
    input_mint: str
    output_mint: str
    input_amount: float
    output_amount: float
    error: Optional[str] = None


@dataclass
class RaydiumPriceResult:
    """Pool price from Raydium CLMM."""
    success: bool
    pool: str
    token_a: str
    token_b: str
    price_a_to_b: float
    price_b_to_a: float
    liquidity: str
    error: Optional[str] = None


class RaydiumBridge:
    """
    Python bridge to Raydium CLMM via Node.js subprocess.
    
    Calls the compiled raydium_clmm.js CLI for quotes and swaps.
    """
    
    def __init__(self, bridge_path: str = None):
        """
        Initialize Raydium bridge.
        
        Args:
            bridge_path: Path to raydium_clmm.js (auto-detected if None)
        """
        if bridge_path:
            self.bridge_path = Path(bridge_path)
        else:
            # Auto-detect path relative to project root
            project_root = Path(__file__).parent.parent.parent.parent
            self.bridge_path = project_root / "bridges" / "raydium_clmm.js"
        
        self._private_key = None
        self._load_private_key()
    
    def _load_private_key(self):
        """Load private key from environment."""
        from dotenv import load_dotenv
        load_dotenv()
        self._private_key = os.getenv("PHANTOM_PRIVATE_KEY")
    
    def _run_command(self, *args, timeout: int = 30) -> Optional[Dict[str, Any]]:
        """Run the Node.js bridge with given arguments."""
        if not self.bridge_path.exists():
            Logger.error(f"[RAYDIUM] Bridge not found: {self.bridge_path}")
            Logger.info("[RAYDIUM] Run: cd bridges && npm install && npm run build:raydium")
            return None
        
        try:
            cmd = ["node", str(self.bridge_path)] + list(args)
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.bridge_path.parent)
            )
            
            if result.returncode != 0 and result.stderr:
                Logger.debug(f"[RAYDIUM] stderr: {result.stderr[:200]}")
            
            # Parse JSON from stdout
            if result.stdout:
                return json.loads(result.stdout.strip())
            return None
            
        except subprocess.TimeoutExpired:
            Logger.warning("[RAYDIUM] Command timeout")
            return None
        except json.JSONDecodeError as e:
            Logger.debug(f"[RAYDIUM] JSON parse error: {e}")
            return None
        except Exception as e:
            Logger.error(f"[RAYDIUM] Bridge error: {e}")
            return None
    
    def get_quote(
        self, 
        pool_address: str, 
        input_mint: str, 
        amount: float
    ) -> RaydiumQuoteResult:
        """
        Get a swap quote from Raydium CLMM pool.
        
        Args:
            pool_address: CLMM pool address
            input_mint: Input token mint
            amount: Amount to swap (in token units, not lamports)
            
        Returns:
            RaydiumQuoteResult with output amount and price impact
        """
        result = self._run_command("quote", pool_address, input_mint, str(amount))
        
        if not result:
            return RaydiumQuoteResult(
                success=False,
                input_mint=input_mint,
                output_mint="",
                input_amount=amount,
                output_amount=0.0,
                price_impact=0.0,
                fee=0.0,
                error="Bridge command failed"
            )
        
        return RaydiumQuoteResult(
            success=result.get("success", False),
            input_mint=result.get("inputMint", input_mint),
            output_mint=result.get("outputMint", ""),
            input_amount=float(result.get("inputAmount", amount)),
            output_amount=float(result.get("outputAmount", 0)),
            price_impact=float(result.get("priceImpact", 0)),
            fee=float(result.get("fee", 0)),
            error=result.get("error")
        )
    
    def get_price(self, pool_address: str) -> RaydiumPriceResult:
        """
        Get current price from Raydium CLMM pool.
        
        Args:
            pool_address: CLMM pool address
            
        Returns:
            RaydiumPriceResult with current prices
        """
        result = self._run_command("price", pool_address)
        
        if not result:
            return RaydiumPriceResult(
                success=False,
                pool=pool_address,
                token_a="",
                token_b="",
                price_a_to_b=0.0,
                price_b_to_a=0.0,
                liquidity="0",
                error="Bridge command failed"
            )
        
        return RaydiumPriceResult(
            success=result.get("success", False),
            pool=result.get("pool", pool_address),
            token_a=result.get("tokenA", ""),
            token_b=result.get("tokenB", ""),
            price_a_to_b=float(result.get("priceAtoB", 0)),
            price_b_to_a=float(result.get("priceBtoA", 0)),
            liquidity=result.get("liquidity", "0"),
            error=result.get("error")
        )
    
    def execute_swap(
        self,
        pool_address: str,
        input_mint: str,
        amount: float,
        slippage_bps: int = 50
    ) -> RaydiumSwapResult:
        """
        Execute a swap on Raydium CLMM pool.
        
        Args:
            pool_address: CLMM pool address
            input_mint: Input token mint
            amount: Amount to swap (in token units)
            slippage_bps: Slippage tolerance in basis points (default 50 = 0.5%)
            
        Returns:
            RaydiumSwapResult with transaction signature
        """
        if not self._private_key:
            return RaydiumSwapResult(
                success=False,
                signature=None,
                input_mint=input_mint,
                output_mint="",
                input_amount=amount,
                output_amount=0.0,
                error="No private key configured"
            )
        
        result = self._run_command(
            "swap",
            pool_address,
            input_mint,
            str(amount),
            str(slippage_bps),
            self._private_key,
            timeout=60
        )
        
        if not result:
            return RaydiumSwapResult(
                success=False,
                signature=None,
                input_mint=input_mint,
                output_mint="",
                input_amount=amount,
                output_amount=0.0,
                error="Bridge command failed"
            )
        
        return RaydiumSwapResult(
            success=result.get("success", False),
            signature=result.get("signature"),
            input_mint=result.get("inputMint", input_mint),
            output_mint=result.get("outputMint", ""),
            input_amount=float(result.get("inputAmount", amount)),
            output_amount=float(result.get("outputAmount", 0)),
            error=result.get("error")
        )


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWN RAYDIUM CLMM POOLS
# ═══════════════════════════════════════════════════════════════════════════════

# Top Raydium CLMM pools by volume
RAYDIUM_CLMM_POOLS = {
    "SOL/USDC": "2QdhepnKRTLjjSqPL1PtKNwqrUkoLee5Gqs8bvZhRdMv",  # CLMM SOL/USDC
    "SOL/USDT": "7XawhbbxtsRcQA8KTkHT9f9nc6d69UwqCDh6U5EEbEmX",  # CLMM SOL/USDT
}


# Quick test
if __name__ == "__main__":
    bridge = RaydiumBridge()
    
    print("Testing Raydium CLMM Bridge...")
    print(f"Bridge path: {bridge.bridge_path}")
    print(f"Exists: {bridge.bridge_path.exists()}")
    
    if bridge.bridge_path.exists():
        # Test price fetch
        pool = RAYDIUM_CLMM_POOLS.get("SOL/USDC")
        if pool:
            print(f"\nFetching price for SOL/USDC pool...")
            price = bridge.get_price(pool)
            print(f"Result: {price}")
    else:
        print("\n⚠️ Bridge not built. Run:")
        print("   cd bridges && npm install && npm run build:raydium")
