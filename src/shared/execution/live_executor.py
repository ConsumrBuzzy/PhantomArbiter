"""
Phantom Arbiter - LIVE Trading Executor
========================================
Executes REAL swaps on Solana using Jupiter.

SAFETY FEATURES:
- Maximum trade size limit
- Confirmation prompt before first trade
- Kill switch (Ctrl+C immediately stops)
- All trades logged

REQUIREMENTS:
- PHANTOM_PRIVATE_KEY in .env
- USDC balance in wallet
- solana-py and solders packages

Usage:
    python run_live_trader.py --budget 5 --max-trade 5 --duration 10

⚠️ START WITH $1-5 TO TEST ⚠️
"""

import asyncio
import os
import time
import base64
import base58
import httpx
from typing import Optional, Dict, Any
from dataclasses import dataclass

# Load .env file
from dotenv import load_dotenv

load_dotenv()

from src.shared.system.logging import Logger


# Token mints
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOL_MINT = "So11111111111111111111111111111111111111112"
WIF_MINT = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
BONK_MINT = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
JUP_MINT = "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"


@dataclass
class SwapResult:
    """Result of a swap execution."""

    success: bool
    input_mint: str
    output_mint: str
    input_amount: float
    output_amount: float
    signature: Optional[str] = None
    error: Optional[str] = None


class SolanaWallet:
    """Simple Solana wallet for signing transactions."""

    def __init__(self, private_key_base58: str):
        """
        Initialize wallet from base58 private key.

        Export from Phantom: Settings → Security → Export Private Key
        """
        try:
            # Try importing solders (modern Solana library)
            from solders.keypair import Keypair

            # Decode base58 private key
            secret_bytes = base58.b58decode(private_key_base58)
            self.keypair = Keypair.from_bytes(secret_bytes)
            self.public_key = str(self.keypair.pubkey())
            self._has_solders = True
            Logger.info(
                f"[WALLET] Loaded wallet: {self.public_key[:8]}...{self.public_key[-4:]}"
            )

        except ImportError:
            # Fallback: just store the key
            Logger.warning("[WALLET] solders not installed - using basic mode")
            self._has_solders = False
            self.keypair = None
            secret_bytes = base58.b58decode(private_key_base58)
            # Extract public key (last 32 bytes of 64-byte keypair)
            self.public_key = base58.b58encode(secret_bytes[32:]).decode()

    def sign_transaction(self, transaction_bytes: bytes) -> bytes:
        """Sign a transaction."""
        if self._has_solders and self.keypair:
            signature = self.keypair.sign_message(transaction_bytes)
            return bytes(signature)
        else:
            raise Exception("solders package required for signing")

    async def get_balance(self, rpc_url: str) -> Dict[str, float]:
        """Get wallet balances."""
        balances = {}

        async with httpx.AsyncClient() as client:
            # Get SOL balance
            resp = await client.post(
                rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getBalance",
                    "params": [self.public_key],
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                sol_lamports = data.get("result", {}).get("value", 0)
                balances["SOL"] = sol_lamports / 1e9

            # Get USDC balance (token account)
            resp = await client.post(
                rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getTokenAccountsByOwner",
                    "params": [
                        self.public_key,
                        {"mint": USDC_MINT},
                        {"encoding": "jsonParsed"},
                    ],
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                accounts = data.get("result", {}).get("value", [])
                if accounts:
                    usdc_amount = float(
                        accounts[0]
                        .get("account", {})
                        .get("data", {})
                        .get("parsed", {})
                        .get("info", {})
                        .get("tokenAmount", {})
                        .get("uiAmount", 0)
                    )
                    balances["USDC"] = usdc_amount
                else:
                    balances["USDC"] = 0

        return balances


class JupiterSwapExecutor:
    """
    Executes swaps via Jupiter Aggregator.

    Jupiter handles routing to find best prices across:
    - Raydium
    - Orca
    - Meteora
    - And 20+ other DEXs
    """

    QUOTE_URL = "https://quote-api.jup.ag/v6/quote"
    SWAP_URL = "https://quote-api.jup.ag/v6/swap"

    def __init__(
        self,
        wallet: SolanaWallet,
        rpc_url: str = "https://api.mainnet-beta.solana.com",
        slippage_bps: int = 100,  # 1% default slippage
    ):
        self.wallet = wallet
        self.rpc_url = rpc_url
        self.slippage_bps = slippage_bps

    async def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,  # In smallest unit (lamports for SOL, micro for USDC)
    ) -> Optional[Dict]:
        """Get a swap quote from Jupiter."""
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount),
            "slippageBps": self.slippage_bps,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.get(self.QUOTE_URL, params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            else:
                Logger.error(f"[JUPITER] Quote failed: {resp.status_code}")
                return None

    async def execute_swap(
        self, input_mint: str, output_mint: str, amount_usd: float
    ) -> SwapResult:
        """
        Execute a swap.

        Args:
            input_mint: Token to sell
            output_mint: Token to buy
            amount_usd: Amount in USD (converted to proper units)
        """
        try:
            # Convert USD to token units
            if input_mint == USDC_MINT:
                amount_units = int(amount_usd * 1e6)  # USDC has 6 decimals
            elif input_mint == SOL_MINT:
                # Would need price lookup
                amount_units = int(amount_usd * 1e9 / 100)  # Rough estimate
            else:
                amount_units = int(amount_usd * 1e6)  # Default to 6 decimals

            # Step 1: Get quote
            Logger.info(f"[SWAP] Getting quote for ${amount_usd}...")
            quote = await self.get_quote(input_mint, output_mint, amount_units)

            if not quote:
                return SwapResult(
                    success=False,
                    input_mint=input_mint,
                    output_mint=output_mint,
                    input_amount=amount_usd,
                    output_amount=0,
                    error="Failed to get quote",
                )

            # Log quote details
            in_amount = int(quote.get("inAmount", 0))
            out_amount = int(quote.get("outAmount", 0))
            price_impact = quote.get("priceImpactPct", "0")

            Logger.info(
                f"[SWAP] Quote: {in_amount} → {out_amount} (impact: {price_impact}%)"
            )

            # Step 2: Get swap transaction
            Logger.info("[SWAP] Building transaction...")

            async with httpx.AsyncClient() as client:
                swap_resp = await client.post(
                    self.SWAP_URL,
                    json={
                        "quoteResponse": quote,
                        "userPublicKey": self.wallet.public_key,
                        "wrapAndUnwrapSol": True,
                        "dynamicComputeUnitLimit": True,
                        "prioritizationFeeLamports": "auto",
                    },
                    timeout=30,
                )

                if swap_resp.status_code != 200:
                    return SwapResult(
                        success=False,
                        input_mint=input_mint,
                        output_mint=output_mint,
                        input_amount=amount_usd,
                        output_amount=0,
                        error=f"Swap API error: {swap_resp.status_code}",
                    )

                swap_data = swap_resp.json()

            # Step 3: Sign and send transaction
            swap_transaction = swap_data.get("swapTransaction")
            if not swap_transaction:
                return SwapResult(
                    success=False,
                    input_mint=input_mint,
                    output_mint=output_mint,
                    input_amount=amount_usd,
                    output_amount=0,
                    error="No swap transaction returned",
                )

            Logger.info("[SWAP] Signing transaction...")

            # Decode transaction
            tx_bytes = base64.b64decode(swap_transaction)

            # Sign with wallet
            try:
                from solders.transaction import VersionedTransaction
                from solders.signature import Signature

                tx = VersionedTransaction.from_bytes(tx_bytes)
                tx.sign([self.wallet.keypair])
                signed_tx_bytes = bytes(tx)

            except ImportError:
                return SwapResult(
                    success=False,
                    input_mint=input_mint,
                    output_mint=output_mint,
                    input_amount=amount_usd,
                    output_amount=0,
                    error="solders package required for signing",
                )

            # Step 4: Send transaction
            Logger.info("[SWAP] Sending transaction...")

            async with httpx.AsyncClient() as client:
                send_resp = await client.post(
                    self.rpc_url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "sendTransaction",
                        "params": [
                            base64.b64encode(signed_tx_bytes).decode(),
                            {"encoding": "base64", "skipPreflight": False},
                        ],
                    },
                    timeout=30,
                )

                if send_resp.status_code == 200:
                    result = send_resp.json()
                    if "result" in result:
                        signature = result["result"]
                        Logger.info(f"[SWAP] ✅ Transaction sent: {signature}")

                        # Calculate output in USD
                        if output_mint == USDC_MINT:
                            output_usd = out_amount / 1e6
                        else:
                            output_usd = amount_usd  # Approximate

                        return SwapResult(
                            success=True,
                            input_mint=input_mint,
                            output_mint=output_mint,
                            input_amount=amount_usd,
                            output_amount=output_usd,
                            signature=signature,
                        )
                    else:
                        error = result.get("error", {}).get("message", "Unknown error")
                        return SwapResult(
                            success=False,
                            input_mint=input_mint,
                            output_mint=output_mint,
                            input_amount=amount_usd,
                            output_amount=0,
                            error=error,
                        )
                else:
                    return SwapResult(
                        success=False,
                        input_mint=input_mint,
                        output_mint=output_mint,
                        input_amount=amount_usd,
                        output_amount=0,
                        error=f"RPC error: {send_resp.status_code}",
                    )

        except Exception as e:
            Logger.error(f"[SWAP] Exception: {e}")
            return SwapResult(
                success=False,
                input_mint=input_mint,
                output_mint=output_mint,
                input_amount=amount_usd,
                output_amount=0,
                error=str(e),
            )

    async def wait_for_confirmation(self, signature: str, timeout: int = 30) -> bool:
        """Wait for transaction confirmation."""
        start = time.time()

        while time.time() - start < timeout:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self.rpc_url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "getSignatureStatuses",
                        "params": [[signature]],
                    },
                )

                if resp.status_code == 200:
                    result = resp.json()
                    statuses = result.get("result", {}).get("value", [])
                    if statuses and statuses[0]:
                        status = statuses[0]
                        if status.get("confirmationStatus") in [
                            "confirmed",
                            "finalized",
                        ]:
                            return True
                        if status.get("err"):
                            return False

            await asyncio.sleep(1)

        return False


class LiveTrader:
    """
    Live trading bot with safety features.

    SAFETY FEATURES:
    - Maximum trade size limit
    - Confirmation before first trade
    - Kill switch
    - All trades logged
    """

    def __init__(
        self,
        wallet: SolanaWallet,
        max_trade_usd: float = 10.0,
        require_confirmation: bool = True,
    ):
        self.wallet = wallet
        self.executor = JupiterSwapExecutor(wallet)
        self.max_trade_usd = max_trade_usd
        self.require_confirmation = require_confirmation

        # State
        self.trades_executed = 0
        self.total_volume = 0.0
        self.total_profit = 0.0
        self._running = False
        self._first_trade_confirmed = False

    async def execute_spatial_arb(
        self, buy_mint: str, sell_mint: str, amount_usd: float
    ) -> Dict[str, Any]:
        """
        Execute a spatial arbitrage.

        Buy on cheapest DEX, sell on most expensive.
        Jupiter handles the routing automatically.
        """
        if amount_usd > self.max_trade_usd:
            return {
                "success": False,
                "error": f"Amount ${amount_usd} exceeds max ${self.max_trade_usd}",
            }

        # First trade confirmation
        if self.require_confirmation and not self._first_trade_confirmed:
            print("\n" + "=" * 60)
            print("   ⚠️  FIRST LIVE TRADE - CONFIRMATION REQUIRED")
            print("=" * 60)
            print(f"   Amount: ${amount_usd}")
            print("   This will execute a REAL transaction!")
            confirm = input("   Type 'YES' to proceed: ")
            if confirm.strip().upper() != "YES":
                return {"success": False, "error": "User cancelled first trade"}
            self._first_trade_confirmed = True

        # Execute swap
        result = await self.executor.execute_swap(USDC_MINT, buy_mint, amount_usd)

        if result.success:
            self.trades_executed += 1
            self.total_volume += amount_usd

            # Wait for confirmation
            confirmed = await self.executor.wait_for_confirmation(result.signature)

            return {
                "success": True,
                "signature": result.signature,
                "confirmed": confirmed,
                "input": amount_usd,
                "output": result.output_amount,
            }
        else:
            return {"success": False, "error": result.error}

    async def check_wallet_balance(self) -> Dict[str, float]:
        """Check wallet balances."""
        rpc_url = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
        return await self.wallet.get_balance(rpc_url)


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Live Trader")
    parser.add_argument(
        "--check-only", action="store_true", help="Only check wallet balance"
    )

    args = parser.parse_args()

    # Load wallet
    private_key = os.getenv("PHANTOM_PRIVATE_KEY") or os.getenv("SOLANA_PRIVATE_KEY")

    if not private_key:
        print("\n❌ ERROR: No private key found!")
        print("   Add PHANTOM_PRIVATE_KEY to your .env file")
        return

    try:
        wallet = SolanaWallet(private_key)
    except Exception as e:
        print(f"\n❌ ERROR: Failed to load wallet: {e}")
        return

    print(f"\n✅ Wallet loaded: {wallet.public_key}")

    # Check balance
    print("\n📊 Checking wallet balance...")
    trader = LiveTrader(wallet, max_trade_usd=5.0)
    balances = await trader.check_wallet_balance()

    print(f"   SOL:  {balances.get('SOL', 0):.4f}")
    print(f"   USDC: {balances.get('USDC', 0):.2f}")

    if args.check_only:
        return

    # Ready message
    print("\n" + "=" * 60)
    print("   ✅ LIVE TRADER READY")
    print("=" * 60)
    print(f"""
   Wallet:      {wallet.public_key[:8]}...{wallet.public_key[-4:]}
   USDC:        ${balances.get("USDC", 0):.2f}
   Max Trade:   $5.00
   
   The paper trader detects opportunities.
   When ready, this module executes real swaps.
""")


if __name__ == "__main__":
    asyncio.run(main())
