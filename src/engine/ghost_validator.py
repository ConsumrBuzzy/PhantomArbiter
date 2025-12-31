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
        
    async def validate_later(self, cycle_id: str, path: list, original_profit: float, delay_seconds: float = 2.0) -> Optional[ValidationResult]:
        """
        Schedule a validation check after a delay.
        """
        self.pending_validations += 1
        try:
            await asyncio.sleep(delay_seconds)
            
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
                    current_profit_pct=-100.0, # Failed to route
                    is_still_profitable=False,
                    drift_pct=-100.0,
                    timestamp=time.time()
                )
                
            metrics = self.quote_builder.calculate_cycle_profit(quotes, input_amount)
            current_profit = metrics['profit_pct']
            
            # Check if still profitable
            still_profitable = current_profit > 0.1 # Min threshold
            drift = current_profit - original_profit
            
            log_icon = "✅" if still_profitable else "❌"
            Logger.info(
                f"[Ghost] {log_icon} Look-Back: {original_profit:.3f}% -> {current_profit:.3f}% (Drift: {drift:+.3f}%)"
            )
            
            return ValidationResult(
                cycle_id=cycle_id,
                original_profit_pct=original_profit,
                current_profit_pct=current_profit,
                is_still_profitable=still_profitable,
                drift_pct=drift,
                timestamp=time.time()
            )
            
        except Exception as e:
            Logger.error(f"[GhostValidator] Error: {e}")
            return None
        finally:
            self.pending_validations -= 1
