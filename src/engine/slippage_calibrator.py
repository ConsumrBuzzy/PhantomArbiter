"""
V67.0: Auto-Slippage Calibrator (Phase 5C)
==========================================
Self-healing execution loop that adjusts slippage tolerance based on
observed drift from ShadowManager audits.

Behavior:
- Drift > 1.5%: LOOSEN slippage (+50 bps) to ensure trades land
- Drift < 0.5%: TIGHTEN slippage (-25 bps) to minimize MEV leakage
- Drift 0.5-1.5%: HOLD (system is in sync)

Integration:
- Called by TradeExecutor after each executed trade
- Updates ScorerConfig.max_slippage_bps in Rust core
- Dashboard shows current slippage with color gauge
"""

from typing import Optional, List
from collections import deque
from src.shared.system.logging import Logger


class SlippageCalibrator:
    """
    Adaptive slippage governor that calibrates based on execution drift.
    
    Monitors the last N trades and adjusts slippage tolerance to balance
    "aggressive filling" vs "capital preservation".
    """
    
    def __init__(
        self,
        scorer_config,
        shadow_manager=None,
        window_size: int = 5,
        min_bps: int = 100,
        max_bps: int = 800
    ):
        """
        Initialize the calibrator.
        
        Args:
            scorer_config: Rust ScorerConfig object (PyO3)
            shadow_manager: ShadowManager for drift history
            window_size: Number of trades to average for calibration
            min_bps: Minimum slippage (tight/precision mode)
            max_bps: Maximum slippage (loose/aggressive mode)
        """
        self.config = scorer_config
        self.shadow = shadow_manager
        self.window_size = window_size
        self.min_bps = min_bps
        self.max_bps = max_bps
        
        # Internal tracking
        self.drift_history: deque = deque(maxlen=window_size)
        self.calibration_count = 0
        self.last_action = "INIT"
        
        Logger.info(f"⚙️ [CALIBRATOR] Initialized (window={window_size}, range={min_bps}-{max_bps} bps)")
    
    def record_drift(self, delta_pct: float) -> None:
        """Record a single drift observation."""
        self.drift_history.append(delta_pct)
    
    def maybe_recalibrate(self) -> bool:
        """
        Check drift history and adjust slippage if needed.
        
        Returns:
            True if slippage was adjusted, False otherwise
        """
        # Method 1: Use ShadowManager if available
        if self.shadow:
            try:
                audits = self.shadow.get_recent_audits(self.window_size)
                if len(audits) >= self.window_size:
                    drifts = [getattr(a, 'delta_pct', 0.0) for a in audits]
                    avg_drift = sum(drifts) / len(drifts)
                    return self._apply_calibration(avg_drift)
            except Exception as e:
                Logger.debug(f"[CALIBRATOR] Shadow read failed: {e}")
        
        # Method 2: Use internal history
        if len(self.drift_history) < self.window_size:
            return False
        
        avg_drift = sum(self.drift_history) / len(self.drift_history)
        return self._apply_calibration(avg_drift)
    
    def _apply_calibration(self, avg_drift: float) -> bool:
        """Apply calibration based on average drift."""
        current_bps = self.config.max_slippage_bps
        new_bps = current_bps
        action = "HOLD"
        
        # High drift: LOOSEN slippage (prioritize landing trades)
        if abs(avg_drift) > 1.5:
            new_bps = min(current_bps + 50, self.max_bps)
            action = "LOOSEN"
        
        # Low drift: TIGHTEN slippage (minimize MEV leakage)
        elif abs(avg_drift) < 0.5:
            new_bps = max(current_bps - 25, self.min_bps)
            action = "TIGHTEN"
        
        # Apply if changed
        if new_bps != current_bps:
            self.config.max_slippage_bps = new_bps
            self.calibration_count += 1
            self.last_action = action
            
            # Determine emoji based on action
            emoji = "📈" if action == "LOOSEN" else "📉"
            Logger.info(
                f"⚙️ [AUTO-CAL] {emoji} Slippage: {current_bps}→{new_bps} bps "
                f"({action}, Drift: {avg_drift:+.2f}%)"
            )
            return True
        
        return False
    
    def force_loosen(self, reason: str = "Manual") -> None:
        """Emergency: Force slippage to maximum."""
        old = self.config.max_slippage_bps
        self.config.max_slippage_bps = self.max_bps
        self.last_action = "EMERGENCY_LOOSEN"
        Logger.warn(f"⚠️ [CALIBRATOR] EMERGENCY LOOSEN: {old}→{self.max_bps} bps ({reason})")
    
    def force_tighten(self, reason: str = "Manual") -> None:
        """Force slippage to minimum."""
        old = self.config.max_slippage_bps
        self.config.max_slippage_bps = self.min_bps
        self.last_action = "FORCE_TIGHTEN"
        Logger.info(f"🔒 [CALIBRATOR] FORCE TIGHTEN: {old}→{self.min_bps} bps ({reason})")
    
    def get_status(self) -> dict:
        """Get current calibrator status for dashboard."""
        current_bps = self.config.max_slippage_bps
        
        # Determine gauge level
        if current_bps <= 300:
            gauge = "GREEN"
            label = "Precision"
        elif current_bps <= 600:
            gauge = "YELLOW"
            label = "Volatility Buffer"
        else:
            gauge = "RED"
            label = "Aggressive"
        
        return {
            "current_bps": current_bps,
            "min_bps": self.min_bps,
            "max_bps": self.max_bps,
            "gauge": gauge,
            "label": label,
            "last_action": self.last_action,
            "calibrations": self.calibration_count,
            "history_len": len(self.drift_history),
        }
    
    def get_gauge_display(self) -> str:
        """Get formatted gauge for dashboard display."""
        status = self.get_status()
        bps = status["current_bps"]
        
        # Build visual bar (10 segments)
        filled = int((bps - self.min_bps) / (self.max_bps - self.min_bps) * 10)
        bar = "█" * filled + "░" * (10 - filled)
        
        return f"[{bar}] {bps} bps ({status['label']})"


# Singleton instance
_calibrator: Optional[SlippageCalibrator] = None


def get_calibrator(scorer_config=None, shadow_manager=None) -> SlippageCalibrator:
    """Get or create singleton calibrator."""
    global _calibrator
    if _calibrator is None and scorer_config:
        _calibrator = SlippageCalibrator(scorer_config, shadow_manager)
    return _calibrator
