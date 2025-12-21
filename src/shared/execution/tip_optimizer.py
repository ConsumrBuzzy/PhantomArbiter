
import time
from typing import Dict, Optional
from src.shared.system.logging import Logger
from src.shared.system.db_manager import DBManager

class TipOptimizer:
    """
    V110: Competitive Jito Tip Optimizer (Auction Sniper)
    Progressively learns the 'Floor' tip required for block inclusion.
    """
    
    def __init__(self):
        self.db = DBManager()
        self.min_tip_lamports = 10000
        self.max_multiplier = 0.50
        self.min_multiplier = 0.05
        
    def get_optimized_tip(self, pair: str, expected_profit_usd: float) -> int:
        """
        Calculate the most competitive Jito tip for the current block.
        """
        # 1. Get learned multiplier for this pair
        current_mult = self.db.get_tip_multiplier(pair)
        
        # 2. Get recent inclusion stats
        stats = self.db.get_inclusion_stats(pair, limit=10)
        
        new_mult = current_mult
        
        # 3. Adjust based on performance
        if stats['total'] >= 3:
            if stats['inclusion_rate'] < 0.6:
                # We are being ghosted/outbid -> Aggressive bump
                new_mult = min(self.max_multiplier, current_mult + 0.05)
                Logger.info(f"📈 [TIP] inclusion low ({stats['inclusion_rate']*100:.0f}%), bumping mult: {new_mult:.2f}")
            elif stats['success_rate'] > 0.8:
                # We are winning consistently -> Shave the tip
                new_mult = max(self.min_multiplier, current_mult - 0.02)
                # Logger.info(f"📉 [TIP] High success, shaving mult: {new_mult:.2f}")

        # 4. Save learned multiplier if changed
        if new_mult != current_mult:
            self.db.save_tip_multiplier(pair, new_mult)
            
        # 5. Convert USD profit to Lamports tip
        # Tip = Profit * Multiplier
        tip_usd = expected_profit_usd * new_mult
        
        # Simple SOL price fallback (can be improved with price cache)
        sol_price = 200.0
        try:
            from src.arbiter.core.fee_estimator import get_fee_estimator
            sol_price = get_fee_estimator()._sol_price_cache or 200.0
        except:
            pass
            
        tip_lamports = int((tip_usd / sol_price) * 1e9)
        
        # Cap at 50% of profit for safety, but ensure min floor
        hard_cap = int((expected_profit_usd * 0.5 / sol_price) * 1e9)
        final_tip = max(self.min_tip_lamports, min(tip_lamports, hard_cap))
        
        if final_tip > self.min_tip_lamports:
             Logger.debug(f"[TIP] Optimized tip for {pair}: {final_tip} lamps ({new_mult*100:.1f}% of ${expected_profit_usd:.2f})")
             
        return final_tip

# Singleton access
_tip_optimizer = None
def get_tip_optimizer():
    global _tip_optimizer
    if _tip_optimizer is None:
        _tip_optimizer = TipOptimizer()
    return _tip_optimizer
