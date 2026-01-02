"""
Risk Gate - Pre-Trade Safety Validation.

The "Never Late" layer that validates signals before execution.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Any
from enum import Enum


class RiskRejection(str, Enum):
    """Reason for rejecting a trade."""
    NONE = "NONE"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    POSITION_SIZE_LIMIT = "POSITION_SIZE_LIMIT"
    REGIME_FILTER = "REGIME_FILTER"
    RSI_OVERSOLD = "RSI_OVERSOLD"
    RSI_OVERBOUGHT = "RSI_OVERBOUGHT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    MANUAL_HALT = "MANUAL_HALT"


@dataclass
class RiskResult:
    """Result of risk validation."""
    approved: bool
    rejection_reason: RiskRejection = RiskRejection.NONE
    message: str = ""
    indicators: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "approved": self.approved,
            "rejection_reason": self.rejection_reason.value,
            "message": self.message,
            "indicators": self.indicators,
        }


@dataclass
class RiskConfig:
    """Risk gate configuration."""
    # Daily loss limit (USD)
    max_daily_loss: float = 50.0
    
    # Max single position size (USD)
    max_position_size: float = 100.0
    
    # Max total exposure (USD)
    max_total_exposure: float = 500.0
    
    # RSI thresholds
    rsi_oversold_threshold: float = 30.0  # Block buys below this
    rsi_overbought_threshold: float = 70.0  # Block sells above this
    
    # Require minimum data points
    min_data_points: int = 10
    
    # Enable/disable specific checks
    enable_regime_filter: bool = True
    enable_rsi_filter: bool = True
    enable_loss_limit: bool = True


class RiskGate:
    """
    Pre-trade validation gate.
    
    Intercepts all trade signals and validates against safety rules.
    The "Common Sense" layer that prevents catastrophic mistakes.
    """
    
    def __init__(self, config: Optional[RiskConfig] = None) -> None:
        self.config = config or RiskConfig()
        
        # Session tracking
        self._session_pnl: float = 0.0
        self._session_trades: int = 0
        self._rejections: List[Dict] = []
        self._halted: bool = False
        
        # Warm buffer reference (set externally)
        self._warm_buffer = None
    
    def set_warm_buffer(self, buffer) -> None:
        """Set the warm trend buffer for indicator access."""
        self._warm_buffer = buffer
    
    def validate(
        self,
        action: str,
        mint: str,
        size_usd: float,
        symbol: str = "",
        current_position: float = 0.0,
    ) -> RiskResult:
        """
        Validate a trade signal.
        
        Returns RiskResult with approval status and reason if rejected.
        """
        # Manual halt check
        if self._halted:
            return RiskResult(
                approved=False,
                rejection_reason=RiskRejection.MANUAL_HALT,
                message="Trading halted by operator",
            )
        
        # Daily loss limit
        if self.config.enable_loss_limit:
            result = self._check_daily_loss()
            if not result.approved:
                return result
        
        # Position size limit
        result = self._check_position_size(size_usd, current_position)
        if not result.approved:
            return result
        
        # RSI and regime filters (require warm buffer)
        if self._warm_buffer:
            indicators = self._warm_buffer.get_indicators(mint)
            
            # RSI filter
            if self.config.enable_rsi_filter:
                result = self._check_rsi(action, indicators.rsi_14)
                if not result.approved:
                    result.indicators = indicators.to_dict()
                    return result
            
            # Regime filter
            if self.config.enable_regime_filter:
                result = self._check_regime(action, indicators.regime.value, mint)
                if not result.approved:
                    result.indicators = indicators.to_dict()
                    return result
        
        # All checks passed
        return RiskResult(
            approved=True,
            message="Signal approved",
            indicators=self._warm_buffer.get_indicators(mint).to_dict() if self._warm_buffer else {},
        )
    
    def _check_daily_loss(self) -> RiskResult:
        """Check daily loss limit."""
        if self._session_pnl < -self.config.max_daily_loss:
            return RiskResult(
                approved=False,
                rejection_reason=RiskRejection.DAILY_LOSS_LIMIT,
                message=f"Daily loss limit reached: ${abs(self._session_pnl):.2f} >= ${self.config.max_daily_loss}",
            )
        return RiskResult(approved=True)
    
    def _check_position_size(self, size_usd: float, current_position: float) -> RiskResult:
        """Check position size limits."""
        if size_usd > self.config.max_position_size:
            return RiskResult(
                approved=False,
                rejection_reason=RiskRejection.POSITION_SIZE_LIMIT,
                message=f"Position size ${size_usd:.2f} exceeds limit ${self.config.max_position_size}",
            )
        return RiskResult(approved=True)
    
    def _check_rsi(self, action: str, rsi: float) -> RiskResult:
        """Check RSI thresholds."""
        action_upper = action.upper()
        
        # Block buys in oversold (falling knife)
        if action_upper == "BUY" and rsi < self.config.rsi_oversold_threshold:
            return RiskResult(
                approved=False,
                rejection_reason=RiskRejection.RSI_OVERSOLD,
                message=f"RSI {rsi:.1f} < {self.config.rsi_oversold_threshold} - Falling knife risk",
            )
        
        # Block sells in overbought (could run higher)
        if action_upper == "SELL" and rsi > self.config.rsi_overbought_threshold:
            return RiskResult(
                approved=False,
                rejection_reason=RiskRejection.RSI_OVERBOUGHT,
                message=f"RSI {rsi:.1f} > {self.config.rsi_overbought_threshold} - Momentum may continue",
            )
        
        return RiskResult(approved=True)
    
    def _check_regime(self, action: str, regime: str, mint: str) -> RiskResult:
        """Check market regime compatibility."""
        action_upper = action.upper()
        
        # Block buys in strong downtrend
        if action_upper == "BUY" and regime == "TRENDING_DOWN":
            return RiskResult(
                approved=False,
                rejection_reason=RiskRejection.REGIME_FILTER,
                message=f"Regime is TRENDING_DOWN - Not buying into downtrend",
            )
        
        # Block sells in strong uptrend (let winners run)
        # if action_upper == "SELL" and regime == "TRENDING_UP":
        #     return RiskResult(
        #         approved=False,
        #         rejection_reason=RiskRejection.REGIME_FILTER,
        #         message=f"Regime is TRENDING_UP - Let position run",
        #     )
        
        return RiskResult(approved=True)
    
    def record_trade(self, pnl: float) -> None:
        """Record a completed trade for PnL tracking."""
        self._session_pnl += pnl
        self._session_trades += 1
    
    def halt(self) -> None:
        """Halt all trading."""
        self._halted = True
    
    def resume(self) -> None:
        """Resume trading."""
        self._halted = False
    
    def reset_session(self) -> None:
        """Reset session tracking (new day)."""
        self._session_pnl = 0.0
        self._session_trades = 0
        self._rejections = []
    
    def get_stats(self) -> Dict:
        """Get risk gate statistics."""
        return {
            "session_pnl": self._session_pnl,
            "session_trades": self._session_trades,
            "rejections_count": len(self._rejections),
            "halted": self._halted,
            "config": {
                "max_daily_loss": self.config.max_daily_loss,
                "max_position_size": self.config.max_position_size,
                "rsi_oversold": self.config.rsi_oversold_threshold,
            },
        }


# Global instance
_gate: Optional[RiskGate] = None


def get_risk_gate() -> RiskGate:
    """Get or create the global RiskGate instance."""
    global _gate
    if _gate is None:
        _gate = RiskGate()
    return _gate
