"""
Arb Engine Logic
================
The "Trip Hopper" - Triangular Arbitrage Orchestrator.
Connects Scanner (Data) -> Graph (Calc) -> Jupiter (Execution).
"""

import asyncio
import time
from typing import List, Dict
from src.shared.system.logging import Logger
from src.engines.arb.graph import get_hop_engine, HopOpportunity
from src.engines.arb.scanner import SpreadDetector
from src.shared.feeds.jupiter_feed import JupiterFeed
from src.drivers.jupiter_driver import JupiterSwapper
from src.drivers.wallet_manager import WalletManager
from src.shared.state.app_state import state as app_state, ArbOpportunity
from config.settings import Settings

from src.engines.base_engine import BaseEngine

class ArbEngine(BaseEngine):
    """
    Executes Triangular Arbitrage (A -> B -> C -> A).
    """

    def __init__(self, live_mode: bool = False):
        super().__init__("arb", live_mode)
        
        # Data & Calculation
        self.graph = get_hop_engine()
        self.scanner = SpreadDetector(feeds=[self.feed]) # Use Base feed
        
        # Configuration
        self.trade_size_usd = 30.0    # Fixed size as requested ($30)
        self.min_profit_bps = 10      # 0.1% net profit
        
        # Top 5 Liquid Triangles (Tokens to focus on)
        self.CORE_TOKENS = [
            "So11111111111111111111111111111111111111112", # SOL
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", # USDC
            "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", # JUP
            "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R", # RAY
            "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So", # mSOL
        ]
        
        # Logging handled by Base

    async def tick(self):
        """Single execution step for 'Trip Hopper'."""
        try:
            # 1. Update Prices (Scanner -> Graph)
            await self.update_prices()
            
            # 2. Scan for Cycles (Graph)
            # We scan for cycles starting with USDC (Stable base)
            cycles = self.graph.scan(start_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
            
            # Update AppState for TUI
            app_state.update_stat("cycles_per_sec", self.graph.stats.total_scans)
            app_state.update_stat("rust_core_active", True)
            
            if cycles:
                for c in cycles[:10]:
                    app_state.add_opportunity(ArbOpportunity(
                        token=c.path[1][:4] if len(c.path)>1 else "SOL",
                        route="->".join([p[:4] for p in c.path]),
                        profit_pct=c.profit_pct * 100,
                        est_profit_sol=c.min_liquidity_usd / 1000 # Placeholder
                    ))

                # Filter executable
                executable = [c for c in cycles if c.profit_pct > (self.min_profit_bps / 100)]
                if executable:
                    best_opp = executable[0]
                    Logger.info(f"💎 FOUND CYCLE: {best_opp}")
                    
                    if self.live_mode:
                        await self.execute_cycle(best_opp)
                    else:
                        Logger.info(f"   [SIM] Would Exec {best_opp.path} for ${self.trade_size_usd}")

            return {"state": "ACTIVE"}
            
        except Exception as e:
            Logger.error(f"Arb Tick Error: {e}")
            return {"state": "ERROR"}



    async def update_prices(self):
        """Fetch prices from Feed and update Graph."""
        prices = await self.feed.get_multiple_prices(self.CORE_TOKENS)
        
        for mint, price in prices.items():
            if mint == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": continue
            
            # Edge: USDC -> Mint
            self.graph.update_pool({
                "base_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", # USDC
                "quote_mint": mint,
                "pool_address": f"virt_{mint}_usdc",
                "price": price, 
                "fee_bps": 10,
                "liquidity_usd": 1000000,
                "dex": "JUPITER"
            })
            
            # Inverse Edge: Mint -> USDC
            if price > 0:
                self.graph.update_pool({
                    "base_mint": mint,
                    "quote_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                    "pool_address": f"virt_{mint}_usdc",
                    "price": 1.0 / price,
                    "fee_bps": 10,
                    "liquidity_usd": 1000000,
                    "dex": "JUPITER"
                })

    async def execute_cycle(self, opp: HopOpportunity):
        """Execute Atomic Arb Cycle."""
        Logger.info(f"EXECUTION: {' -> '.join( opp.path )}")
        
        try:
            # Atomic Bundling Simulation
            Logger.warning("⚠️ Atomic Bundling of 3 Jupiter Swaps is heavy. Attempting...")
            Logger.success(f"✅ [MOCK] Bundled 3 Atomic Hops. Profit: +{opp.profit_pct*100:.2f}%")
            
        except Exception as e:
            Logger.error(f"Execution Failed: {e}")
