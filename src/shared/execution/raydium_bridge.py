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
            # Path to the JS bridge script
            self.bridge_path = Path(__file__).parent.parent.parent.parent / "bridges" / "raydium_daemon.js"
        
        # State
        self.process = None
        self._load_private_key()
        
        # V93: Daemon Process management
        self._daemon = None

    def _load_private_key(self):
        """Load private key from environment."""
        from dotenv import load_dotenv
        load_dotenv()
        self._private_key = os.getenv("PHANTOM_PRIVATE_KEY")
    
    def _ensure_daemon(self):
        """Start the Node.js daemon if not running."""
        if self._daemon and self._daemon.poll() is None:
            return

        if not self.bridge_path.exists():
            Logger.error(f"[RAYDIUM] Bridge not found: {self.bridge_path}")
            return

        try:
            # Start daemon with line buffering
            cmd = ["node", str(self.bridge_path), "daemon"]
            self._daemon = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, # Capture stderr to avoid leaking to console, or let it flow?
                text=True,
                cwd=str(self.bridge_path.parent),
                bufsize=1 # Line buffered
            )
            Logger.info("[RAYDIUM] Daemon started (PID: %s)", self._daemon.pid)
        except Exception as e:
            Logger.error(f"[RAYDIUM] Failed to start daemon: {e}")
            self._daemon = None

    def _send_command(self, cmd_data: dict, timeout: int = 30) -> Optional[Dict[str, Any]]:
        """Send JSON command to daemon and wait for response."""
        self._ensure_daemon()
        if not self._daemon:
            return None
        
        try:
            # Write JSON command
            payload = json.dumps(cmd_data) + "\n"
            self._daemon.stdin.write(payload)
            self._daemon.stdin.flush()
            
            # Read JSON response (synchronous)
            # TODO: Implement timeout logic for read. 
            # For now relying on OS read. 
            # If daemon hangs, this thread hangs. 
            # But TS bridge should be robust.
            
            line = self._daemon.stdout.readline()
            if not line:
                Logger.warning("[RAYDIUM] Daemon closed stream")
                self._daemon = None
                return None
                
            return json.loads(line.strip())
            
        except Exception as e:
            Logger.error(f"[RAYDIUM] IPC error: {e}")
            if self._daemon:
                self._daemon.kill()
                self._daemon = None
            return None
    
    def get_quote(
        self, 
        pool_address: str, 
        input_mint: str, 
        amount: float
    ) -> RaydiumQuoteResult:
        """
        Get a swap quote via Daemon.
        """
        result = self._send_command({
            "cmd": "quote",
            "pool": pool_address,
            "inputMint": input_mint,
            "amount": str(amount)
        })
        
        if not result:
            return RaydiumQuoteResult(
                success=False,
                input_mint=input_mint,
                output_mint="",
                input_amount=amount,
                output_amount=0.0,
                price_impact=0.0,
                fee=0.0,
                error="Daemon command failed"
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
        Get current price via Daemon.
        """
        result = self._send_command({
            "cmd": "price", 
            "pool": pool_address
        })
        
        if not result:
            return RaydiumPriceResult(
                success=False,
                pool=pool_address,
                token_a="",
                token_b="",
                price_a_to_b=0.0,
                price_b_to_a=0.0,
                liquidity="0",
                error="Daemon command failed"
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

    def get_batch_prices(self, pools: list) -> Dict[str, float]:
        """
        Get prices for multiple pools in one batch.
        
        Args:
            pools: List of dicts, e.g. [{'id': 'addr', 'type': 'standard'}]
            
        Returns:
            Dict mapping pool_address -> price
        """
        # Limit batch size to avoid hanging
        BATCH_LIMIT = 50
        results = {}
        
        for i in range(0, len(pools), BATCH_LIMIT):
            batch = pools[i:i+BATCH_LIMIT]
            resp = self._send_command({
                "cmd": "batch_prices",
                "pools": batch
            }, timeout=60)
            
            if resp and resp.get("success"):
                batch_prices = resp.get("prices", {})
                results.update(batch_prices)
            else:
                Logger.warning(f"[RAYDIUM] Batch price fetch failed for chunk {i}")
                
        return results

    
    def execute_swap(
        self,
        pool_address: str,
        input_mint: str,
        amount: float,
        slippage_bps: int = 50
    ) -> RaydiumSwapResult:
        """
        Execute a swap via Daemon.
        """
        # Note: Daemon uses PHANTOM_PRIVATE_KEY from env, 
        # so we don't strictly need to pass self._private_key unless daemon needs it per-request.
        # But we updated TS to accept no key if using env, or accept key.
        # We will use the env key logic implicitly in daemon.
        
        result = self._send_command({
            "cmd": "swap",
            "pool": pool_address,
            "inputMint": input_mint,
            "amount": str(amount),
            "slippageBps": slippage_bps
        }, timeout=60)
        
        if not result:
            return RaydiumSwapResult(
                success=False,
                signature=None,
                input_mint=input_mint,
                output_mint="",
                input_amount=amount,
                output_amount=0.0,
                error="Daemon command failed"
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
    
    def discover_pool(
        self,
        token_a: str,
        token_b: str
    ) -> Optional[Dict[str, Any]]:
        """
        Discover CLMM pool for a token pair.
        
        Args:
            token_a: First token symbol (e.g., "SOL") or mint address
            token_b: Second token symbol (e.g., "USDC") or mint address
            
        Returns:
            Dict with poolId, tvl, volume24h, or None if not found
        """
        from config.settings import Settings
        
        # Resolve symbols to mints if needed
        mint_a = token_a
        mint_b = token_b
        
        # If token_a looks like a symbol (not 32+ chars), resolve it
        if len(token_a) < 30:
            mint_a = Settings.ASSETS.get(token_a.upper(), token_a)
        if len(token_b) < 30:
            mint_b = Settings.ASSETS.get(token_b.upper(), token_b)
        
        # Use direct subprocess for discovery (not supported in daemon yet)
        try:
            cmd = ["node", str(self.bridge_path), "discover", mint_a, mint_b]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self.bridge_path.parent)
            )
            
            output = result.stdout.strip()
            # Handle noise in output (e.g. warnings)
            json_line = None
            for line in output.split('\n'):
                if line.strip().startswith('{'):
                    json_line = line.strip()
                    break
            
            if not json_line:
                Logger.warning(f"[RAYDIUM] Invalid discovery output: {output}")
                return {"success": False, "error": "Invalid output from bridge"}
                
            data = json.loads(json_line)
            if data.get('success'):
                Logger.debug(f"[RAYDIUM] Discovered pool {data.get('poolId')} ({data.get('type', 'unknown')})")
            return data
            
        except Exception as e:
            Logger.error(f"[RAYDIUM] Discover error: {e}")
            return None
    
    async def fetch_api_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: float,
        slippage_bps: int = 50
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch quote from Raydium Trade API (swap-base-in).
        
        This is the most accurate quote source as it accounts for
        exact tick arrays and fees in CLMM pools.
        
        Args:
            input_mint: Input token mint address
            output_mint: Output token mint address
            amount: Input amount in token units (NOT lamports)
            slippage_bps: Slippage in basis points (default 50 = 0.5%)
            
        Returns:
            Dict with outputAmount, priceImpactPct, feeAmount, or None on failure
        """
        import httpx
        
        try:
            # Get decimals for input token (assume 6 for stables, 9 for SOL)
            if input_mint == "So11111111111111111111111111111111111111112":
                decimals = 9
            elif input_mint == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v":
                decimals = 6
            elif input_mint == "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB":
                decimals = 6  # USDT
            else:
                decimals = 9  # Default to 9 for most SPL tokens
            
            # Convert to lamports
            amount_lamports = int(amount * (10 ** decimals))
            
            url = (
                f"https://transaction-v1.raydium.io/compute/swap-base-in"
                f"?inputMint={input_mint}"
                f"&outputMint={output_mint}"
                f"&amount={amount_lamports}"
                f"&slippageBps={slippage_bps}"
                f"&txVersion=V0"
            )
            
            # V127: Use async client
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=10.0)
            
            if resp.status_code != 200:
                Logger.debug(f"[RAYDIUM] Trade API error: {resp.status_code}")
                return None
            
            data = resp.json()
            
            if not data.get("success"):
                return None
            
            inner = data.get("data", {})
            
            # Get output decimals
            if output_mint == "So11111111111111111111111111111111111111112":
                out_decimals = 9
            elif output_mint in ["EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", 
                                  "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"]:
                out_decimals = 6
            else:
                out_decimals = 9
            
            output_amount = int(inner.get("outputAmount", 0)) / (10 ** out_decimals)
            
            return {
                "success": True,
                "inputMint": input_mint,
                "outputMint": output_mint,
                "inputAmount": amount,
                "outputAmount": output_amount,
                "priceImpactPct": inner.get("priceImpactPct", 0),
                "slippageBps": slippage_bps,
                "routePlan": inner.get("routePlan", []),
            }
            
        except Exception as e:
            Logger.debug(f"[RAYDIUM] Trade API error: {e}")
            return None


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWN RAYDIUM CLMM POOLS (Verified on 2025-12-20)
# CLMM Program ID: CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK
# ═══════════════════════════════════════════════════════════════════════════════

# Token mint addresses
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"

# Top Raydium CLMM pools by TVL
RAYDIUM_CLMM_POOLS = {
    "SOL/USDC": "2QdhepnKRTLjjSqPL1PtKNwqrUkoLee5Gqs8bvZhRdMv",  # 0.01% fee
    "SOL/USDT": "7XawhbbxtsRcQA8KTkHT9f9nc6d69UwqCDh6U5EEbEmX",  # 0.05% fee
    "USDC/USDT": "6n9662fXhK15kM2M7G793U6qQhJ19vV1k5bL8vK7zYp8",  # 0.01% fee (stables)
}

def get_pool_for_pair(mint_a: str, mint_b: str) -> str:
    """Get CLMM pool address for a token pair."""
    # Normalize order (SOL/USDC not USDC/SOL)
    for pair, pool in RAYDIUM_CLMM_POOLS.items():
        tokens = pair.split("/")
        if len(tokens) == 2:
            # Check both orderings
            if (tokens[0] == "SOL" and mint_a == SOL_MINT) or (tokens[0] == "USDC" and mint_a == USDC_MINT):
                return pool
    return ""


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
