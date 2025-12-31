"""
V11.0 Decision Engine (DSA) - V37.0 Refactored
===============================================
Centralized trading logic component for TradingCore (P1).
V37.0: Now inherits from BaseStrategy for shared functionality.
"""

from config.settings import Settings
import time
from src.strategy.base_strategy import BaseStrategy
from src.strategy.watcher import Watcher
from src.strategy.risk import PositionSizer
from src.strategy.metrics import Metrics
from src.shared.system.logging import Logger


class DecisionEngine(BaseStrategy):
    """
    P1 Logic Engine for V11.0 DSA (Dynamic Strategy Adjustment).
    V37.0: Now inherits from BaseStrategy.
    """

    def __init__(self, portfolio):
        super().__init__(portfolio)

        # V11.0 Adaptive State (Extended from Base)
        self.MODE_UPDATE_INTERVAL = 300  # Reset every 5 mins

    def update_market_mode(self):
        """
        V11.0: Update adaptability based on Win Rate.
        Queries DBManager.
        """
        from src.shared.system.db_manager import db_manager

        if time.time() - self.last_mode_update < self.MODE_UPDATE_INTERVAL:
            return

        self.win_rate = db_manager.get_win_rate(limit=20)
        total_trades = db_manager.get_total_trades()

        # V16.1: Relaxed DSA - Stay aggressive until proven otherwise
        # Don't go conservative until we have at least 10 trades of history
        # V19.4 Fix: Prevent death spiral - 0% win rate defaults to NORMAL
        # This handles corrupted trade history or fresh paper wallet starts
        if total_trades < 10 or self.win_rate == 0:
            self.market_mode = "NORMAL"  # Fresh start or reset = Normal
        elif self.win_rate >= 0.50:
            self.market_mode = "AGGRESSIVE"  # Lowered from 55%
        elif self.win_rate <= 0.10:
            self.market_mode = "CONSERVATIVE"  # Lowered from 20%
        else:
            self.market_mode = "NORMAL"

        self.last_mode_update = time.time()
        Logger.info(
            f"🧠 DSA Mode: {self.market_mode} (Win Rate: {self.win_rate * 100:.1f}% | Trades: {total_trades})"
        )

    def analyze_tick(self, watcher: Watcher, price: float) -> tuple[str, str, float]:
        """
        Analyze a single watcher tick.
        Returns: (Action, Reason, Size)
        Action: 'BUY', 'SELL', 'HOLD'
        """
        # 0. Update Mode
        self.update_market_mode()

        # V37.0: Use shared cooldown check
        if self.check_cooldown(watcher):
            return "HOLD", "", 0.0

        # 1. Calculate Indicators
        rsi = watcher.get_rsi()  # Watcher should return RSI from sync'd data

        # 2. Check Exits (If in position)
        if watcher.in_position:
            return self._evaluate_exit(watcher, price, rsi)

        # 3. Check Entries (If handling active trading)
        if not Settings.ENABLE_TRADING:
            # Even if trading is disabled, we might want to check for PAPER TRADES (implied)
            # But the caller (TradingCore) handles ENABLE_TRADING logic for execution vs paper.
            # analyze_tick typically evaluates pure logic.
            # However, original code returned HOLD if !ENABLE_TRADING at step 3.
            # V11.15 allows Paper Trading, so logic must proceed to _evaluate_entry even if trading disabled?
            # Actually, TradingCore calls analyze_tick. If analyze_tick returns HOLD because !ENABLE_TRADING, paper trade won't happen.
            # Let's check original code:
            # if not Settings.ENABLE_TRADING: return 'HOLD', '', 0.0
            # This prevents Paper Trading! We must fix this if Paper Trading relies on analyze_tick returning BUY.
            pass  # Continue to evaluation so Paper Trading works

        return self._evaluate_entry(watcher, price, rsi)

    def _evaluate_entry(
        self, watcher: Watcher, price: float, rsi: float
    ) -> tuple[str, str, float]:
        """Check for buy signals."""

        # V89.14: Enable diagnostic logging in paper aggressive mode
        # V89.14: Diagnostic logging disabled
        is_paper_diagnostic = False

        # A. Validation
        validation_result = watcher.validator.validate(watcher.mint, watcher.symbol)
        if not validation_result.is_safe:
            if is_paper_diagnostic:
                print(f"   ❌ {watcher.symbol}: REJECTED by validation")
            return "HOLD", "", 0.0

        if is_paper_diagnostic:
            print(
                f"   🎯 {watcher.symbol}: PASSED validation, checking entry conditions..."
            )

        # V12.1: Slippage Filter (Hard reject >2%, soft filter >1%)
        from src.shared.system.data_source_manager import DataSourceManager

        dsm = DataSourceManager()
        passes, slippage, action = dsm.check_slippage_filter(watcher.mint)

        if not passes:
            if is_paper_diagnostic:
                print(f"      ❌ Slippage too high: {slippage:.2f}% > 2%")
            Logger.debug(
                f"   🚫 {watcher.symbol}: REJECTED (Slippage {slippage:.2f}% > 2%)"
            )
            return "HOLD", "", 0.0

        if is_paper_diagnostic and slippage > 0:
            print(f"      ✅ Slippage OK: {slippage:.2f}%")

        # B. Get ATR & Size
        atr = watcher.data_feed.get_atr()

        # V89.14: Fallback for insufficient data - estimate ATR from price
        if atr <= 0:
            if is_paper_diagnostic:
                print(f"      ⚠️ ATR invalid ({atr}), estimating from price...")

            # Estimate ATR as 1% of price (conservative volatility assumption)
            atr = price * 0.01

            if atr <= 0:
                if is_paper_diagnostic:
                    print(f"      ❌ Failed to estimate ATR (price: ${price:.6f})")
                return "HOLD", "", 0.0

            if is_paper_diagnostic:
                print(f"      ✅ Estimated ATR: {atr:.6f} (1% of price)")
        else:
            if is_paper_diagnostic:
                print(f"      ✅ ATR: {atr:.6f}")

        # Position Sizing (Adaptive V11.0)
        size_usd = PositionSizer.calculate_size(atr, win_rate=self.win_rate)

        # V12.2: Dynamic Position Sizing (DPS) based on Volatility
        volatility = dsm.get_volatility(watcher.symbol)
        HIGH_VOL_THRESHOLD = 3.0  # 3% RV = high volatility regime

        if volatility > HIGH_VOL_THRESHOLD:
            # High Volatility Regime: Reduce size by 33%, wider SL/TP
            size_usd = size_usd * 0.67
            Logger.debug(
                f"   📊 {watcher.symbol}: High Vol ({volatility:.2f}%) - Size reduced to 67%"
            )

        # V12.1: Soft slippage filter - halve size if >1% (stacks with V12.2)
        if action == "HALF_SIZE":
            size_usd = size_usd / 2
            Logger.debug(
                f"   ⚠️ {watcher.symbol}: Size halved (Slippage {slippage:.2f}% > 1%)"
            )

        # V12.4: Drawdown Protection - Reduce size during losing streaks
        # Get consecutive_losses from portfolio (shared state)
        consecutive_losses = getattr(self.portfolio, "_consecutive_losses", 0)

        if consecutive_losses >= 5:
            size_usd = size_usd * 0.25
            Logger.debug("   🔴 DRAWDOWN: 5+ losses - Size reduced to 25%")
        elif consecutive_losses >= 3:
            size_usd = size_usd * 0.50
            Logger.debug(
                f"   🟠 DRAWDOWN: {consecutive_losses} losses - Size reduced to 50%"
            )

        # C. Checks
        if price < Settings.MIN_PRICE_THRESHOLD:
            if is_paper_diagnostic:
                print(
                    f"      ❌ Price too low: ${price:.6f} < ${Settings.MIN_PRICE_THRESHOLD}"
                )
            return "HOLD", "", 0.0

        if watcher.get_price_count() < Settings.MIN_VALID_PRICES:
            if is_paper_diagnostic:
                print(
                    f"      ❌ Not enough price data: {watcher.get_price_count()} < {Settings.MIN_VALID_PRICES}"
                )
            return "HOLD", "", 0.0

        if watcher.hourly_trades >= Settings.MAX_TRADES_PER_HOUR:
            if is_paper_diagnostic:
                print(
                    f"      ❌ Trade limit reached: {watcher.hourly_trades} >= {Settings.MAX_TRADES_PER_HOUR}"
                )
            return "HOLD", "", 0.0

        if rsi < 5:
            if is_paper_diagnostic:
                print(f"      ❌ RSI too low (bad data): {rsi:.1f}")
            return "HOLD", "", 0.0  # Bad data

        if is_paper_diagnostic:
            print(
                f"      ✅ Pre-checks passed (Price: ${price:.6f}, RSI: {rsi:.1f}, Count: {watcher.get_price_count()})"
            )

        # D. Signal (Adaptive Thresholds V11.0)
        # V25.1: Loosened for more signals in simulation
        # V85.0: Use PAPER_RSI_THRESHOLD when in aggressive paper mode
        is_paper_aggressive = not Settings.ENABLE_TRADING and getattr(
            Settings, "PAPER_AGGRESSIVE_MODE", False
        )

        if is_paper_aggressive:
            rsi_threshold = getattr(Settings, "PAPER_RSI_THRESHOLD", 50)
        elif self.market_mode == "AGGRESSIVE":
            rsi_threshold = 50  # V25.0: Raised to 50 for max activity during tuning
        elif self.market_mode == "CONSERVATIVE":
            rsi_threshold = 35  # V25.1: Raised from 30 to 35
        else:
            rsi_threshold = 40  # V25.1: Raised from 35 to 40 for more entries

        if is_paper_diagnostic:
            print(
                f"      🎲 RSI Check: {rsi:.1f} < {rsi_threshold}? {rsi < rsi_threshold}"
            )

        if rsi < rsi_threshold:
            # V19.2: Check short-term Uptrend (SMA 20) for faster signals
            history = watcher.data_feed.raw_prices
            from src.strategy.signals import TechnicalAnalysis

            is_uptrend = TechnicalAnalysis.is_uptrend(
                price, history, sma_period=20
            )  # V19.2: SMA 20 (was 50)

            if is_paper_diagnostic:
                print(f"      🎲 Uptrend Check (SMA20): {is_uptrend}")

            if is_uptrend:
                info = PositionSizer.get_size_info(atr, size_usd)
                if is_paper_diagnostic:
                    print(
                        f"   ✅ BUY SIGNAL: {watcher.symbol} - RSI {rsi:.1f}<{rsi_threshold}, Uptrend confirmed"
                    )
                return (
                    "BUY",
                    f"DSA {self.market_mode} (RSI {rsi:.1f}<{rsi_threshold}) [{info}]",
                    size_usd,
                )
            else:
                if is_paper_diagnostic:
                    print(f"   ⏸️ {watcher.symbol}: RSI OK but NO uptrend - HOLD")
                pass
        else:
            if is_paper_diagnostic:
                print(f"   ⏸️ {watcher.symbol}: RSI {rsi:.1f} >= {rsi_threshold} - HOLD")

        return "HOLD", "", 0.0

    def _evaluate_exit(
        self, watcher: Watcher, price: float, rsi: float
    ) -> tuple[str, str, float]:
        """Check for sell signals. V37.0: Uses parent class for common exits."""

        # V37.0: Common exit checks (TSL, SL, TP)
        action, reason, size = self._evaluate_exit_common(watcher, price)
        if action == "SELL":
            return action, reason, size

        # Calculate PnL for RSI-based exits
        pnl_pct = Metrics.calculate_pnl_pct(watcher.entry_price, price)

        # E. Fast Scalp (RSI-specific - stays in DecisionEngine)
        if rsi > 70 and pnl_pct > Settings.FAST_SCALP_PCT:
            if watcher.trailing_stop_price == 0:  # Only if TSL not active
                return (
                    "SELL",
                    f"⚡ FAST SCALP (RSI {rsi:.1f}, +{pnl_pct * 100:.2f}%)",
                    0.0,
                )

        # F. Nuclear Exit (RSI-specific - stays in DecisionEngine)
        if rsi > 95 and pnl_pct > Settings.BREAKEVEN_FLOOR_PCT:
            return "SELL", f"🔥 NUCLEAR (RSI {rsi:.1f}, +{pnl_pct * 100:.2f}%)", 0.0

        return "HOLD", "", 0.0
