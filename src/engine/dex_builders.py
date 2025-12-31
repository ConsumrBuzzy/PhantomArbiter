"""
DEX Instruction Builders - Jupiter API Integration
===================================================
V140: Narrow Path Infrastructure (Phase 16)

Factory functions to create serialized swap instructions for multi-hop
execution. Uses Jupiter API for routing complexity, with fallback to
direct DEX calls for latency-critical paths.

Jupiter Flow:
1. Get quote with exact route
2. Get swap transaction
3. Extract instruction data
4. Pass to MultiHopBuilder
"""

from __future__ import annotations

import asyncio
import aiohttp
import base64
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum
import time

from src.shared.system.logging import Logger


class DEXType(Enum):
    """Supported DEX types."""

    JUPITER = "jupiter"
    RAYDIUM = "raydium"
    ORCA = "orca"
    METEORA = "meteora"


@dataclass
class SwapQuote:
    """Quote from Jupiter or direct DEX."""

    input_mint: str
    output_mint: str
    input_amount: int  # In base units (lamports/atoms)
    output_amount: int
    price_impact_pct: float
    route_plan: List[Dict[str, Any]]
    slippage_bps: int = 50  # 0.5% default
    dexes_used: List[str] = field(default_factory=list)
    quote_response: Optional[Dict] = None  # Raw Jupiter response
    timestamp: float = field(default_factory=time.time)  # Time of quote fetch


@dataclass
class SwapInstruction:
    """Serialized swap instruction ready for MultiHopBuilder."""

    pool_address: str
    dex: str
    input_mint: str
    output_mint: str
    instruction_data: bytes
    min_output_amount: int


class JupiterClient:
    """
    Jupiter V6 API client for quote and swap building.

    Jupiter handles the complexity of multi-DEX routing and instruction
    building, making it ideal for quick integration.
    """

    BASE_URL = "https://quote-api.jup.ag/v6"

    def __init__(
        self,
        slippage_bps: int = 50,
        only_direct_routes: bool = False,
        max_accounts: int = 64,
    ):
        self.slippage_bps = slippage_bps
        self.only_direct_routes = only_direct_routes
        self.max_accounts = max_accounts
        self._session: Optional[aiohttp.ClientSession] = None

        # Stats
        self.quotes_fetched = 0
        self.swaps_built = 0
        self.errors = 0

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: Optional[int] = None,
    ) -> Optional[SwapQuote]:
        """
        Get a swap quote from Jupiter.

        Args:
            input_mint: Input token mint address
            output_mint: Output token mint address
            amount: Amount in base units (lamports for SOL)
            slippage_bps: Slippage tolerance in basis points

        Returns:
            SwapQuote or None if failed
        """
        slippage = slippage_bps or self.slippage_bps

        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount),
            "slippageBps": slippage,
            "onlyDirectRoutes": str(self.only_direct_routes).lower(),
            "maxAccounts": self.max_accounts,
        }

        try:
            session = await self._get_session()
            async with session.get(f"{self.BASE_URL}/quote", params=params) as resp:
                if resp.status != 200:
                    Logger.warning(f"[Jupiter] Quote failed: {resp.status}")
                    self.errors += 1
                    return None

                data = await resp.json()
                self.quotes_fetched += 1

                # Parse route plan
                route_plan = data.get("routePlan", [])
                dexes = [
                    step.get("swapInfo", {}).get("ammKey", "unknown")
                    for step in route_plan
                ]

                return SwapQuote(
                    input_mint=input_mint,
                    output_mint=output_mint,
                    input_amount=int(data.get("inAmount", amount)),
                    output_amount=int(data.get("outAmount", 0)),
                    price_impact_pct=float(data.get("priceImpactPct", 0)),
                    route_plan=route_plan,
                    slippage_bps=slippage,
                    dexes_used=dexes,
                    quote_response=data,
                    timestamp=time.time(),
                )

        except asyncio.TimeoutError:
            Logger.warning("[Jupiter] Quote timeout")
            self.errors += 1
            return None
        except Exception as e:
            Logger.error(f"[Jupiter] Quote error: {e}")
            self.errors += 1
            return None

    async def get_swap_instructions(
        self,
        quote: SwapQuote,
        user_public_key: str,
        wrap_unwrap_sol: bool = True,
    ) -> Optional[List[SwapInstruction]]:
        """
        Get serialized swap instructions from Jupiter.

        Args:
            quote: Quote from get_quote()
            user_public_key: Wallet public key
            wrap_unwrap_sol: Whether to auto wrap/unwrap SOL

        Returns:
            List of SwapInstruction or None if failed
        """
        if not quote.quote_response:
            Logger.error("[Jupiter] Cannot build swap without quote response")
            return None

        payload = {
            "quoteResponse": quote.quote_response,
            "userPublicKey": user_public_key,
            "wrapAndUnwrapSol": wrap_unwrap_sol,
            "dynamicComputeUnitLimit": True,
            "prioritizationFeeLamports": "auto",
        }

        try:
            session = await self._get_session()
            async with session.post(
                f"{self.BASE_URL}/swap-instructions", json=payload
            ) as resp:
                if resp.status != 200:
                    Logger.warning(f"[Jupiter] Swap instructions failed: {resp.status}")
                    self.errors += 1
                    return None

                data = await resp.json()
                self.swaps_built += 1

                # Extract swap instruction
                swap_ix = data.get("swapInstruction", {})
                if not swap_ix:
                    Logger.warning("[Jupiter] No swap instruction in response")
                    return None

                # Decode instruction data
                ix_data = base64.b64decode(swap_ix.get("data", ""))

                instruction = SwapInstruction(
                    pool_address=swap_ix.get("programId", ""),
                    dex="jupiter",
                    input_mint=quote.input_mint,
                    output_mint=quote.output_mint,
                    instruction_data=ix_data,
                    min_output_amount=int(
                        quote.output_amount * (1 - quote.slippage_bps / 10000)
                    ),
                )

                return [instruction]

        except asyncio.TimeoutError:
            Logger.warning("[Jupiter] Swap instructions timeout")
            self.errors += 1
            return None
        except Exception as e:
            Logger.error(f"[Jupiter] Swap instructions error: {e}")
            self.errors += 1
            return None

    def get_stats(self) -> Dict[str, int]:
        """Get client statistics."""
        return {
            "quotes_fetched": self.quotes_fetched,
            "swaps_built": self.swaps_built,
            "errors": self.errors,
        }


class MultiHopQuoteBuilder:
    """
    Builds quotes for multi-hop arbitrage cycles.

    Takes a MultiverseCycle path and builds sequential swap quotes
    for each leg, ensuring proper chaining of output → input amounts.
    """

    def __init__(self, jupiter: JupiterClient):
        self.jupiter = jupiter

    async def build_cycle_quotes(
        self,
        path: List[str],
        input_amount: int,
        slippage_bps: int = 30,
    ) -> Optional[List[SwapQuote]]:
        """
        Build quotes for all legs of a cycle.

        Args:
            path: List of token mints in order (including return to start)
            input_amount: Starting amount in base units
            slippage_bps: Slippage per leg

        Returns:
            List of SwapQuotes for each leg, or None if any failed
        """
        if len(path) < 3:
            Logger.error(f"[MultiHopQuote] Invalid path length: {len(path)}")
            return None

        quotes = []
        current_amount = input_amount

        for i in range(len(path) - 1):
            input_mint = path[i]
            output_mint = path[i + 1]

            quote = await self.jupiter.get_quote(
                input_mint=input_mint,
                output_mint=output_mint,
                amount=current_amount,
                slippage_bps=slippage_bps,
            )

            if not quote:
                Logger.warning(
                    f"[MultiHopQuote] Failed to get quote for leg {i}: {input_mint[:8]}→{output_mint[:8]}"
                )
                return None

            quotes.append(quote)
            current_amount = quote.output_amount

        return quotes

    def calculate_cycle_profit(
        self,
        quotes: List[SwapQuote],
        input_amount: int,
    ) -> Dict[str, float]:
        """
        Calculate profit metrics for a cycle.

        Returns:
            Dict with profit_amount, profit_pct, total_price_impact
        """
        if not quotes:
            return {"profit_amount": 0, "profit_pct": 0, "total_price_impact": 0}

        final_amount = quotes[-1].output_amount
        profit_amount = final_amount - input_amount
        profit_pct = (profit_amount / input_amount) * 100 if input_amount > 0 else 0

        total_impact = sum(q.price_impact_pct for q in quotes)

        return {
            "profit_amount": profit_amount,
            "profit_pct": profit_pct,
            "total_price_impact": total_impact,
        }


# ═══════════════════════════════════════════════════════════════════════════
# SINGLETON FACTORY
# ═══════════════════════════════════════════════════════════════════════════

_jupiter_client: Optional[JupiterClient] = None


def get_jupiter_client(
    slippage_bps: int = 50,
    only_direct_routes: bool = False,
) -> JupiterClient:
    """Get or create the singleton Jupiter client."""
    global _jupiter_client
    if _jupiter_client is None:
        _jupiter_client = JupiterClient(
            slippage_bps=slippage_bps,
            only_direct_routes=only_direct_routes,
        )
    return _jupiter_client


async def close_jupiter_client():
    """Close the singleton Jupiter client."""
    global _jupiter_client
    if _jupiter_client:
        await _jupiter_client.close()
        _jupiter_client = None
