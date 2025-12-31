"""
Ghost Validator
===============
Phase 17: Modular Industrialization

Validates dry-run (Paper/Ghost) trades by performing a "Look-Back" check.
It waits for a short period after the simulated execution and then checks
if the opportunity would have actually been profitable.

This helps distinguish between:
1. Ghost Success (Stable arbitrage, would have printed)
2. Ghost Mirage (Flash arbitrage, disappeared before landing)
"""

import asyncio
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass

from src.shared.system.logging import Logger
from src.engine.dex_builders import MultiHopQuoteBuilder

@dataclass
class ValidationResult:
    cycle_id: str
    original_profit_pct: float
    current_profit_pct: float
    is_still_profitable: bool
    drift_pct: float
    timestamp: float

class GhostValidator:
    """
    Asynchronous validator for Ghost Trades.
    """
    
    def __init__(self, quote_builder: MultiHopQuoteBuilder):
        self.quote_builder = quote_builder
        self.pending_validations = 0
        
    async def validate_later(self, cycle_id: str, path: list, original_profit: float, delay_seconds: float = 0.450) -> Optional[ValidationResult]:
        """
        Schedule a validation check after a delay (Jito Inclusion Latency).
        Standard Jito Bundle Inclusion ~400ms.
        """
        self.pending_validations += 1
        try:
            await asyncio.sleep(delay_seconds)
            current_time = time.time()
            
            # Re-fetch quotes for the same path
            # Assume 1 SOL input as standard baseline
            input_amount = 1_000_000_000
            
            quotes = await self.quote_builder.build_cycle_quotes(
                path=path,
                input_amount=input_amount,
                slippage_bps=30 
            )
            
            if not quotes:
                Logger.debug(f"[Ghost] 👻 Mirage: Opportunity vanished for {cycle_id}")
                return ValidationResult(
                    cycle_id=cycle_id,
                    original_profit_pct=original_profit,
                    current_profit_pct=-100.0,
                    is_still_profitable=False,
                    drift_pct=-100.0,
                    timestamp=current_time
                )

            # HONEST GHOSTING CHECK 1: Data Staleness
            # If the quote is older than 2.0s, it's stale and invalid.
            latest_quote_time = max(q.timestamp for q in quotes)
            age = current_time - latest_quote_time
            if age > 2.0:
                Logger.warning(f"[Ghost] ⚠️ STALE DATA VOID: Quote is {age:.2f}s old. Rejected.")
                return ValidationResult(
                    cycle_id=cycle_id,
                    original_profit_pct=original_profit,
                    current_profit_pct=0.0,
                    is_still_profitable=False,
                    drift_pct=0.0,
                    timestamp=current_time
                )
                
            # HONEST GHOSTING CHECK 2: Inclusion Probability
            # Real bundles drop ~10% of the time due to auction loss or block packing
            import random
            if random.random() < 0.10:
                 Logger.warning(f"[Ghost] 🎲 BUNDLE DROPPED: Simulated Jito Auction Failure (10% chance)")
                 return ValidationResult(
                    cycle_id=cycle_id,
                    original_profit_pct=original_profit,
                    current_profit_pct=0.0, # Didn't lose money, just didn't execute
                    is_still_profitable=False, # Did not profit
                    drift_pct=0.0,
                    timestamp=current_time
                )

            metrics = self.quote_builder.calculate_cycle_profit(quotes, input_amount)
            current_profit = metrics['profit_pct']
            
            # REALITY CHECK: Deduct Estimated Fees
            fixed_cost_sol = 0.008 
            cost_pct = (fixed_cost_sol / (input_amount / 1e9)) * 100
            net_profit = current_profit - cost_pct
            
            # Check if still profitable
            still_profitable = net_profit > 0.05
            drift = current_profit - original_profit
            
            log_icon = "✅" if still_profitable else "❌"
            if still_profitable:
                 Logger.info(
                    f"[Ghost] {log_icon} CONFIRMED: {original_profit:.3f}% -> {current_profit:.3f}% (Net: {net_profit:.3f}%)"
                )
            else:
                 Logger.warning(
                    f"[Ghost] {log_icon} REJECTED: {original_profit:.3f}% -> {current_profit:.3f}% (Fees ate profit)"
                )
            
            return ValidationResult(
                cycle_id=cycle_id,
                original_profit_pct=original_profit,
                current_profit_pct=net_profit,
                is_still_profitable=still_profitable,
                drift_pct=drift,
                timestamp=current_time
            )
            
        except Exception as e:
            Logger.error(f"[GhostValidator] Error: {e}")
            return None
        finally:
            self.pending_validations -= 1
