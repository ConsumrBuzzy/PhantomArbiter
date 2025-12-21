"""
Arbiter Opportunity Verifier
============================
Specialized service for parallel verification of arbitrage opportunities.
Integrates safety checks, liquidity verification, and impact analysis.
"""

import asyncio
import time
from typing import List, Dict, Any, Tuple
from src.arbiter.core.spread_detector import SpreadOpportunity
from src.arbiter.core.executor import ArbitrageExecutor
from src.shared.system.data_source_manager import DataSourceManager
from src.shared.infrastructure.validator import TokenValidator
from src.shared.system.logging import Logger

class OpportunityVerifier:
    """
    Orchestrates multi-layer verification for arbitrage opportunities.
    """
    
    def __init__(self, executor: ArbitrageExecutor, batch_size: int = 6):
        self.executor = executor
        self.batch_size = batch_size
        self.dsm = DataSourceManager()
        self.validator = TokenValidator()

    async def verify(self, opportunities: List[SpreadOpportunity], trade_size: float) -> List[SpreadOpportunity]:
        """
        Run parallel verification on a list of opportunities.
        
        Layers:
        1. DSM Pre-check (Liquidity/Slippage)
        2. Token Safety (Honeypot/Authority/Ownership)
        3. Real Quote Verification (Price Impact)
        """
        if not opportunities:
            return []

        # 1. DSM & Safety Filter (Fast)
        candidates = []
        for opp in opportunities:
            # A. DSM Check
            liq_usd = self.dsm.get_liquidity(opp.base_mint)
            if liq_usd > 0 and liq_usd < 5000:
                opp.verification_status = f"❌ LOW LIQ (${liq_usd/1000:.1f}k)"
                continue
            
            passes, slip_pct, _ = self.dsm.check_slippage_filter(opp.base_mint)
            if not passes:
                opp.verification_status = f"❌ HIGH SLIP ({slip_pct:.1f}%)"
                continue
                
            # B. Token Safety Check (Cached)
            security = self.validator.validate(opp.base_mint, opp.pair.split('/')[0])
            if not security.is_safe:
                opp.verification_status = "❌ UNSAFE"
                continue
            
            candidates.append(opp)

        if not candidates:
            return []

        # 2. Parallel Quote Verification (Slow, RPC intensive)
        # Limit to top N to avoid RPC spam
        candidates = sorted(candidates, key=lambda x: x.net_profit_usd, reverse=True)[:self.batch_size]
        
        async def verify_one(opp: SpreadOpportunity) -> SpreadOpportunity:
            # We use executor's verify_liquidity which fetches Jupiter quotes
            is_valid, real_net, status = await self.executor.verify_liquidity(opp, trade_size)
            
            # Update object state
            opp.verification_status = status
            if is_valid:
                opp.net_profit_usd = real_net
                # If status is SCALED, it means the executor successfully adapted the size
            return opp

        # Run in parallel
        tasks = [verify_one(opp) for opp in candidates]
        results = await asyncio.gather(*tasks)
        
        # Return only those that were attempted (status will be updated)
        return results
