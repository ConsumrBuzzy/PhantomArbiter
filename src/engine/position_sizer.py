"""
V133: PositionSizer - Extracted from TradingCore (SRP Refactor)
================================================================
Calculates position sizes based on confidence tiers.

Responsibilities:
- Map confidence scores to position size tiers
- Apply cash percentage limits
- Enforce global position caps
"""

from typing import Optional
from config.settings import Settings
from src.shared.system.logging import Logger
from src.shared.system.capital_manager import get_capital_manager


class PositionSizer:
    """
    V133: Calculates position sizes based on confidence.
    
    Tiers:
    - HIGH (≥0.75): Settings.POSITION_SIZE_HIGH_PCT of cash (default 30%)
    - MEDIUM (0.5-0.75): Settings.POSITION_SIZE_MED_PCT of cash (default 10%)  
    - LOW (<0.5): Settings.POSITION_SIZE_LOW_PCT of cash (default 5%)
    """
    
    # Default tier percentages (can be overridden by Settings)
    DEFAULT_HIGH_PCT = 0.30
    DEFAULT_MED_PCT = 0.10
    DEFAULT_LOW_PCT = 0.05
    
    # Confidence thresholds
    HIGH_THRESHOLD = 0.75
    MED_THRESHOLD = 0.50
    
    def __init__(self, engine_name: str = "PRIMARY"):
        """
        Initialize PositionSizer.
        
        Args:
            engine_name: Engine name for CapitalManager lookup
        """
        self.engine_name = engine_name
    
    def calculate_size(
        self, 
        confidence: float, 
        base_size: float,
        max_size: Optional[float] = None
    ) -> float:
        """
        Calculate position size based on confidence tier.
        
        Args:
            confidence: Confidence score (0.0 - 1.0)
            base_size: Base position size (pre-calculated limit)
            max_size: Optional override for max position size
            
        Returns:
            Final position size in USD
        """
        try:
            cm = get_capital_manager()
            engine = cm.get_engine_state(self.engine_name)
            
            if not engine:
                return base_size
                
            cash = engine.get("cash_balance", 0)
            
            # Determine tier
            tier, pct = self._get_tier(confidence)
            
            # Calculate size based on cash percentage
            tier_size = cash * pct
            
            # Apply caps
            max_cap = max_size or Settings.POSITION_SIZE_USD
            final_size = min(tier_size, base_size, max_cap)
            
            Logger.debug(
                f"[V79.0] Confidence {confidence:.2f} → {tier} tier → "
                f"${final_size:.2f} (was ${base_size:.2f})"
            )
            
            return final_size
            
        except Exception as e:
            Logger.debug(f"[V79.0] Confidence sizing error: {e}")
            return base_size
    
    def _get_tier(self, confidence: float) -> tuple:
        """
        Get tier name and percentage for a confidence value.
        
        Returns:
            (tier_name, percentage)
        """
        if confidence >= self.HIGH_THRESHOLD:
            pct = getattr(Settings, 'POSITION_SIZE_HIGH_PCT', self.DEFAULT_HIGH_PCT)
            return "HIGH", pct
        elif confidence >= self.MED_THRESHOLD:
            pct = getattr(Settings, 'POSITION_SIZE_MED_PCT', self.DEFAULT_MED_PCT)
            return "MED", pct
        else:
            pct = getattr(Settings, 'POSITION_SIZE_LOW_PCT', self.DEFAULT_LOW_PCT)
            return "LOW", pct
    
    def get_recommended_size(self, confidence: float, cash_available: float) -> dict:
        """
        Get recommended size with full breakdown.
        
        Returns:
            Dict with tier, percentage, raw_size, capped_size
        """
        tier, pct = self._get_tier(confidence)
        raw_size = cash_available * pct
        capped_size = min(raw_size, Settings.POSITION_SIZE_USD)
        
        return {
            "confidence": confidence,
            "tier": tier,
            "percentage": pct,
            "raw_size": raw_size,
            "capped_size": capped_size,
            "max_allowed": Settings.POSITION_SIZE_USD
        }
