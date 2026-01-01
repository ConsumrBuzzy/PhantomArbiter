"""
V67.0: Congestion Multiplier (Phase 5D)
=======================================
Dynamically scales Jito tips based on network congestion (execution lag)
to ensure transaction inclusion during high-competition periods.

Logic:
- Lag > 1000ms: 5x Tip (Emergency)
- Lag > 500ms:  3x Tip (Heavy Load)
- Lag > 100ms:  2x Tip (Moderate Load)
- Lag < 100ms:  1x Tip (Normal)

Auto-Abort:
- If tip > MAX_TIP_PROFIT_RATIO of expected profit, abort trade
"""

from typing import Optional
from src.shared.system.logging import Logger
from src.shared.infrastructure.jito_adapter import JitoAdapter
from src.engine.shadow_manager import ShadowManager

# Constants
LAMPORTS_PER_SOL = 1_000_000_000
SOL_PRICE_USD = 200  # Fallback, should be fetched dynamically


class CongestionMonitor:
    """
    Monitors execution lag and adjusts Jito bundle tips dynamically.
    Includes Auto-Abort logic to prevent overpaying for inclusion.
    """

    def __init__(
        self,
        shadow_manager: ShadowManager,
        jito_adapter: JitoAdapter,
        base_tip_lamports: int = 10_000,
        max_tip_lamports: int = 100_000,
        window_size: int = 5,
        max_tip_profit_ratio: float = 0.50,  # Abort if tip > 50% of expected profit
    ):
        self.shadow = shadow_manager
        self.jito = jito_adapter
        self.base_tip = base_tip_lamports
        self.max_tip = max_tip_lamports
        self.window_size = window_size
        self.max_tip_profit_ratio = max_tip_profit_ratio

        # State
        self.current_multiplier = 1.0
        self.last_lag_ms = 0.0
        self.abort_count = 0

        Logger.info(
            f"🔥 [CONGESTION] Monitor initialized (Base: {self.base_tip}, Max: {self.max_tip}, AbortRatio: {self.max_tip_profit_ratio})"
        )

    def maybe_adjust_tip(self) -> bool:
        """
        Check recent execution lag and adjust Jito tip if needed.
        Returns True if tip was updated.
        """
        try:
            audits = self.shadow.get_recent_audits(self.window_size)
            if len(audits) < self.window_size:
                return False

            # Calculate average lag from recent audits
            lags = [getattr(a, "execution_lag_ms", 0) for a in audits]
            avg_lag = sum(lags) / len(lags)
            self.last_lag_ms = avg_lag

            # Determine multiplier
            if avg_lag > 1000:
                multiplier = 5.0
                status = "EMERGENCY"
            elif avg_lag > 500:
                multiplier = 3.0
                status = "HEAVY"
            elif avg_lag > 100:
                multiplier = 2.0
                status = "MODERATE"
            else:
                multiplier = 1.0
                status = "NORMAL"

            # Calculate new tip
            new_tip = min(int(self.base_tip * multiplier), self.max_tip)

            # Update if changed
            if new_tip != self.jito.tip_lamports:
                old_tip = self.jito.tip_lamports
                self.jito.tip_lamports = new_tip
                self.current_multiplier = multiplier

                Logger.info(
                    f"🔥 [CONGESTION] {status}: Tip {old_tip} -> {new_tip} lamports "
                    f"(x{multiplier:.1f}, Lag: {avg_lag:.0f}ms)"
                )
                return True

            return False

        except Exception as e:
            Logger.warn(f"🔥 [CONGESTION] Error adjusting tip: {e}")
            return False

    def should_abort_trade(
        self, expected_profit_usd: float, sol_price: float = None
    ) -> bool:
        """
        Auto-Abort Check: Returns True if the current Jito tip would consume
        more than max_tip_profit_ratio of the expected profit.

        Example: If tip = 100k lamports (~$0.02) and profit = $0.03,
                 ratio = 0.67 > 0.50 → ABORT
        """
        if sol_price is None:
            sol_price = SOL_PRICE_USD

        # Convert tip to USD
        tip_sol = self.jito.tip_lamports / LAMPORTS_PER_SOL
        tip_usd = tip_sol * sol_price

        # Calculate ratio
        if expected_profit_usd <= 0:
            return True  # No profit = don't trade

        ratio = tip_usd / expected_profit_usd

        if ratio > self.max_tip_profit_ratio:
            self.abort_count += 1
            Logger.warn(
                f"🛑 [AUTO-ABORT] Trade blocked: Tip ${tip_usd:.4f} > {self.max_tip_profit_ratio * 100:.0f}% "
                f"of profit ${expected_profit_usd:.4f} (Ratio: {ratio:.2f})"
            )
            return True

        return False

    def get_tip_cost_usd(self, sol_price: float = None) -> float:
        """Get current tip cost in USD."""
        if sol_price is None:
            sol_price = SOL_PRICE_USD
        return (self.jito.tip_lamports / LAMPORTS_PER_SOL) * sol_price

    def get_status(self) -> dict:
        """Get current status for dashboard."""
        return {
            "tip_lamports": self.jito.tip_lamports,
            "multiplier": self.current_multiplier,
            "avg_lag_ms": self.last_lag_ms,
            "status": "NORMAL"
            if self.current_multiplier == 1.0
            else ("EMERGENCY" if self.current_multiplier >= 5.0 else "ELEVATED"),
            "aborts": self.abort_count,
        }


# Singleton (optional, generally managed by TacticalStrategy)
_monitor: Optional[CongestionMonitor] = None


def get_congestion_monitor(shadow_manager=None, jito_adapter=None) -> CongestionMonitor:
    global _monitor
    if _monitor is None and shadow_manager and jito_adapter:
        _monitor = CongestionMonitor(shadow_manager, jito_adapter)
    return _monitor
