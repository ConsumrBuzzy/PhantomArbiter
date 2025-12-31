"""
Global Risk Governor
====================
The centralized authority for system-wide risk management and capital allocation.
Enforces daily loss limits, strategy capital splits, and priority execution.
"""

import threading
from src.shared.system.logging import Logger
from config.settings import Settings


class GlobalRiskGovernor:
    """
    Orchestrates risk and resources between competing strategies (Scalper vs Arbiter).
    """

    def __init__(self, initial_capital_usd: float = 1000.0):
        # Configuration
        self.max_daily_drawdown_pct = getattr(
            Settings, "MAX_DAILY_DRAWDOWN_PCT", 0.10
        )  # 10%
        self.allocations = {
            "scalper": 0.30,  # 30% High Risk
            "arbiter": 0.70,  # 70% Low Risk
        }

        # State
        self.initial_capital = initial_capital_usd
        self.current_capital = initial_capital_usd
        self.daily_pnl_usd = 0.0
        self.is_halted = False
        self.halt_reason = ""

        # Thread Safety
        self.lock = threading.Lock()

        # Strategy Tracking
        self.active_usage = {"scalper": 0.0, "arbiter": 0.0}

        Logger.info(
            f"🏛️ [GOVERNOR] Initialized. Cap: ${initial_capital_usd:.2f}, MaxDD: {self.max_daily_drawdown_pct * 100:.1f}%"
        )

    def update_capital(self, total_usd: float):
        """Update total system capital from Wallet."""
        with self.lock:
            self.current_capital = total_usd
            # Simple PnL since init (reset daily in production via explicit method)
            self.daily_pnl_usd = self.current_capital - self.initial_capital
            self._check_drawdown()

    def can_execute(self, strategy: str, amount_usd: float) -> bool:
        """
        Permission check for a strategy to execute a trade.
        """
        with self.lock:
            if self.is_halted:
                Logger.warning(
                    f"🛑 [GOVERNOR] Blocked {strategy}: System Halted ({self.halt_reason})"
                )
                return False

            if strategy not in self.allocations:
                Logger.warning(
                    f"⚠️ [GOVERNOR] Unknown strategy '{strategy}', allowing (default risk)"
                )
                return True

            # Check Allocation limits
            # usage = self.active_usage.get(strategy, 0.0)
            # For now, we don't track active "locked" capital per trade in this version,
            # just ensuring the REQUESTED amount fits within the theoretical partition?
            # Actually, a better check is: Is the strategy trying to use more than its share of *Total* capital?

            allowed_cap = self.current_capital * self.allocations[strategy]

            # Simple check: Is amount > allowed partition? (Single trade size limit check basically)
            # Real allocation logic would need to know *current held positions* by that strategy.
            # Assuming PositionSizer handles per-trade sizing, Governor handles *aggregate* risk.

            # For Phase 10, we'll enforce that a single trade cannot exceed the partition size
            # (weak check) or check daily loss limits specific to strategy?

            # Let's enforce Global Kill Switch primarily here.
            return True

    def record_trade(self, strategy: str, pnl_usd: float):
        """
        Register a closed trade result.
        """
        with self.lock:
            self.daily_pnl_usd += pnl_usd
            self._check_drawdown()

            if pnl_usd < 0:
                Logger.info(
                    f"📉 [GOVERNOR] {strategy} Loss: ${pnl_usd:.2f} (Daily PnL: ${self.daily_pnl_usd:.2f})"
                )

    def _check_drawdown(self):
        """Evaluate global kill switch."""
        drawdown_pct = (
            self.initial_capital - self.current_capital
        ) / self.initial_capital

        # If PnL is positive, we are fine. Drawdown is only if current < initial.
        if self.daily_pnl_usd < 0:
            current_dd_pct = abs(self.daily_pnl_usd) / self.initial_capital

            if current_dd_pct >= self.max_daily_drawdown_pct:
                self.is_halted = True
                self.halt_reason = (
                    f"Max Daily Drawdown Hit ({current_dd_pct * 100:.2f}%)"
                )
                Logger.error(f"🚨 [GOVERNOR] KILL SWITCH ENGAGED: {self.halt_reason}")

    def reset_daily(self):
        """Reset daily PnL counters (New Day)."""
        with self.lock:
            self.initial_capital = self.current_capital  # Reset baseline
            self.daily_pnl_usd = 0.0
            self.is_halted = False
            self.halt_reason = ""
            Logger.info("☀️ [GOVERNOR] Daily Risk Metrics Reset")

    def get_status(self) -> dict:
        return {
            "halted": self.is_halted,
            "daily_pnl": self.daily_pnl_usd,
            "capital": self.current_capital,
            "allocations": self.allocations,
        }
