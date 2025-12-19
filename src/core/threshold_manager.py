
"""
V68.5: Dynamic Threshold Manager
================================
Centralized threshold control that adapts to market conditions and performance.

Adjusts thresholds based on:
1. Market Regime (CHAOTIC → stricter, TRENDING → looser)
2. PnL Performance (losing streak → tighter)
3. Time of Day (optional future expansion)
"""

from typing import Dict, Optional
from src.system.logging import Logger
from src.core.shared_cache import SharedPriceCache

class ThresholdManager:
    """
    V68.5: Dynamic Threshold Controller
    
    Provides context-aware thresholds for all agents and strategies.
    """
    
    # Default Thresholds (Normal Market)
    DEFAULTS = {
        # Ensemble
        "min_confidence": 0.50,        # Minimum confidence to execute
        "high_conviction": 0.70,       # Threshold for size boost
        
        # Sniper
        "sniper_min_liquidity": 1000,  # $1k minimum
        "sniper_max_age": 300,         # 5 minutes
        "sniper_confidence": 0.75,     # Base snipe confidence
        
        # Decision Engine
        "entry_rsi_oversold": 30,      # RSI threshold for oversold
        "entry_rsi_overbought": 70,    # RSI threshold for overbought
        "stop_loss_pct": 0.05,         # 5% stop loss
        "take_profit_pct": 0.15,       # 15% take profit
        
        # Position Sizing
        "max_position_pct": 0.10,      # 10% of portfolio per trade
        "min_trade_size_usd": 5.0,     # $5 minimum trade
    }
    
    # Regime Modifiers
    REGIME_MODIFIERS = {
        "CHAOTIC": {
            "min_confidence": 0.70,        # Much stricter
            "sniper_min_liquidity": 5000,  # $5k minimum
            "sniper_max_age": 120,         # 2 minutes only
            "max_position_pct": 0.05,      # Half position size
            "stop_loss_pct": 0.03,         # Tighter stop
        },
        "TRENDING_UP": {
            "min_confidence": 0.40,        # Looser - ride the trend
            "sniper_min_liquidity": 500,   # Lower barrier
            "take_profit_pct": 0.25,       # Let winners run
            "max_position_pct": 0.15,      # Larger positions
        },
        "TRENDING_DOWN": {
            "min_confidence": 0.65,        # More cautious
            "sniper_confidence": 0.60,     # Lower snipe confidence
            "max_position_pct": 0.05,      # Smaller positions
            "stop_loss_pct": 0.03,         # Tighter stop
        },
        "RANGING": {
            # Use defaults - good for mean reversion
            "entry_rsi_oversold": 25,      # Slightly more extreme
            "entry_rsi_overbought": 75,
        }
    }
    
    def __init__(self):
        self.current_regime = "RANGING"
        self.pnl_multiplier = 1.0
        self.consecutive_losses = 0
        Logger.info("[THRESHOLDS] Dynamic Threshold Manager Initialized")
    
    def get(self, key: str) -> float:
        """
        Get a threshold value, adjusted for current conditions.
        
        Args:
            key: Threshold name (e.g., "min_confidence", "sniper_min_liquidity")
        
        Returns:
            Adjusted threshold value
        """
        # 1. Start with default
        value = self.DEFAULTS.get(key, 0)
        
        # 2. Apply regime modifier if exists
        self._update_regime()
        regime_mods = self.REGIME_MODIFIERS.get(self.current_regime, {})
        if key in regime_mods:
            value = regime_mods[key]
        
        # 3. Apply PnL multiplier for certain thresholds
        if key in ["min_confidence", "sniper_min_liquidity"]:
            value = value * self.pnl_multiplier
        
        return value
    
    def get_all(self) -> Dict[str, float]:
        """Get all thresholds with current adjustments."""
        return {key: self.get(key) for key in self.DEFAULTS.keys()}
    
    def _update_regime(self):
        """Update current regime from SharedPriceCache."""
        try:
            regime_data = SharedPriceCache.get_market_regime()
            if regime_data:
                vol = regime_data.get("volatility", "NORMAL")
                trend = regime_data.get("trend", "RANGING")
                
                if vol == "CHAOTIC":
                    self.current_regime = "CHAOTIC"
                elif "TRENDING" in trend:
                    if "UP" in trend or trend == "TRENDING":
                        self.current_regime = "TRENDING_UP"
                    else:
                        self.current_regime = "TRENDING_DOWN"
                else:
                    self.current_regime = "RANGING"
        except:
            pass
    
    def record_trade_result(self, is_win: bool):
        """
        Record trade outcome to adjust thresholds.
        
        Losing streak → tighter thresholds (pnl_multiplier > 1)
        Winning streak → normal thresholds (pnl_multiplier = 1)
        """
        if is_win:
            self.consecutive_losses = 0
            self.pnl_multiplier = 1.0
        else:
            self.consecutive_losses += 1
            # Each loss increases multiplier by 10% (stricter thresholds)
            self.pnl_multiplier = 1.0 + (self.consecutive_losses * 0.10)
            # Cap at 1.5x
            self.pnl_multiplier = min(self.pnl_multiplier, 1.5)
            
            if self.consecutive_losses >= 3:
                Logger.warning(f"[THRESHOLDS] ⚠️ Losing streak ({self.consecutive_losses}): Tightening thresholds to {self.pnl_multiplier:.0%}")

    def get_status(self) -> Dict:
        """Get current threshold status for monitoring."""
        return {
            "regime": self.current_regime,
            "pnl_multiplier": self.pnl_multiplier,
            "consecutive_losses": self.consecutive_losses,
            "sample_thresholds": {
                "min_confidence": self.get("min_confidence"),
                "sniper_min_liquidity": self.get("sniper_min_liquidity"),
                "max_position_pct": self.get("max_position_pct"),
            }
        }


# Singleton instance
_threshold_manager: Optional[ThresholdManager] = None

def get_threshold_manager() -> ThresholdManager:
    """Get or create the singleton ThresholdManager."""
    global _threshold_manager
    if _threshold_manager is None:
        _threshold_manager = ThresholdManager()
    return _threshold_manager
