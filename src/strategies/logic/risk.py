"""
V5.5 Position Sizing Module - SRP: Capital Management
Calculates dynamic position sizes using ATR-based risk parity.
V9.5: Integrated WalletManager for floor protection.
V9.1: RS-based momentum multiplier for leaders.
"""

from config.settings import Settings
from config.thresholds import MAX_POSITION_SIZE_PCT


class PositionSizer:
    """
    Single Responsibility: Calculate position sizes based on volatility.

    Uses ATR (Average True Range) to normalize risk across assets.
    Formula: Size = FIXED_DOLLAR_RISK / (ATR × ATR_MULTIPLIER)

    V9.5: Respects CASH_FLOOR - never spends below reserve.
    V9.1: RS Leaders get larger positions.
    """

    # V9.5: Wallet Manager instance (lazy loaded)
    _wallet_manager = None
    _rs_analyzer = None

    # V9.1: RS-based multipliers
    RS_MULTIPLIERS = {
        1: 1.5,  # Rank 1: 150% size (top performer)
        2: 1.25,  # Rank 2: 125% size
        3: 1.0,  # Rank 3+: Normal size
    }

    @classmethod
    def _get_wallet_manager(cls):
        """Lazy load WalletManager to avoid circular imports."""
        if cls._wallet_manager is None:
            try:
                from src.core.wallet_manager import WalletManager

                cls._wallet_manager = WalletManager()
            except Exception:
                pass
        return cls._wallet_manager

    @classmethod
    def _get_rs_analyzer(cls):
        """Lazy load RS Analyzer."""
        if cls._rs_analyzer is None:
            try:
                from src.analysis.relative_strength import RelativeStrengthAnalyzer

                cls._rs_analyzer = RelativeStrengthAnalyzer()
            except Exception:
                pass
        return cls._rs_analyzer

    @staticmethod
    def get_rs_multiplier(symbol: str, held_symbols: list = None) -> float:
        """
        V9.1: Get RS-based position multiplier.

        Returns multiplier based on RS rank:
        - Rank 1: 1.5x (leader gets largest allocation)
        - Rank 2: 1.25x
        - Rank 3+: 1.0x (base)
        """
        analyzer = PositionSizer._get_rs_analyzer()
        if not analyzer or not held_symbols:
            return 1.0

        try:
            rankings = analyzer.analyze_portfolio(held_symbols)
            for r in rankings:
                if r.symbol == symbol:
                    return PositionSizer.RS_MULTIPLIERS.get(r.rank, 1.0)
        except Exception:
            pass

        return 1.0

    @staticmethod
    def calculate_size(
        atr: float, win_rate: float = 0.0, symbol: str = None, held_symbols: list = None
    ) -> float:
        """
        Calculate position size using ATR-based risk parity + Win Rate Scaling.

        V8.3 Formula: Size = ATR_Size * (1 + WinRate)
        V9.1 Enhancement: Size *= RS_Multiplier (leaders get more)
        V9.5: Clamped to available cash (respecting CASH_FLOOR)

        Args:
            atr: Current Average True Range
            win_rate: Rolling win rate (0.0 to 1.0)
            symbol: Symbol for RS lookup (optional)
            held_symbols: List of currently held symbols for RS comparison

        Returns:
            Position size in USD.
        """
        if atr <= 0:
            base = Settings.MIN_BUY_SIZE
        else:
            risk_per_unit = atr * Settings.ATR_MULTIPLIER
            if risk_per_unit <= 0:
                base = Settings.MIN_BUY_SIZE
            else:
                base = Settings.FIXED_DOLLAR_RISK / risk_per_unit

        # Clamp base size to limits first
        base = max(Settings.MIN_BUY_SIZE, min(base, Settings.MAX_BUY_SIZE))

        # V8.3: Apply Dynamic Confidence Multiplier
        safe_wr = max(0.0, min(win_rate, 1.0))
        wr_multiplier = 1.0 + safe_wr

        # V9.1: Apply RS Momentum Multiplier
        rs_multiplier = 1.0
        if symbol and held_symbols:
            rs_multiplier = PositionSizer.get_rs_multiplier(symbol, held_symbols)

        calculated_size = base * wr_multiplier * rs_multiplier

        # V9.5: Clamp to available cash (respecting floor)
        wm = PositionSizer._get_wallet_manager()
        if wm:
            available = wm.get_available_cash()
            max_allowed = available * MAX_POSITION_SIZE_PCT
            final_size = min(calculated_size, max_allowed)
        else:
            final_size = calculated_size

        return round(final_size, 2)

    @staticmethod
    def get_size_info(atr: float, size: float, rs_rank: int = 0) -> str:
        """
        Generate human-readable sizing info for logs.
        """
        if atr <= 0:
            return f"${size:.2f} (ATR warming up)"
        rs_str = f" RS#{rs_rank}" if rs_rank else ""
        return f"${size:.2f} (ATR: {atr:.6f}){rs_str}"

    @staticmethod
    def check_can_trade(required_amount: float) -> tuple:
        """
        V9.5: Check if trade amount is allowed by wallet floors.

        Returns: (can_trade: bool, reason: str)
        """
        wm = PositionSizer._get_wallet_manager()
        if wm:
            return wm.can_trade(required_amount)
        return True, "OK (No WalletManager)"


# ═══════════════════════════════════════════════════════════════════
# GLOBAL WALLET LOCK (Cross-Process Safety)
# ═══════════════════════════════════════════════════════════════════

import os
from filelock import FileLock, Timeout

# Lock file location
LOCK_FILE = os.path.join(os.path.dirname(__file__), "../../.wallet.lock")


class WalletLock:
    """
    File-based lock for cross-process wallet safety.
    Prevents Engine 1 and Engine 2 from trading simultaneously.
    """

    _lock = None
    _timeout = 5.0  # 5 seconds max wait

    @classmethod
    def acquire(cls, timeout: float = None) -> bool:
        """
        Acquire exclusive wallet access.

        Args:
            timeout: Max seconds to wait (default: 5s)

        Returns:
            True if acquired, False if timeout
        """
        if cls._lock is None:
            cls._lock = FileLock(LOCK_FILE)

        try:
            cls._lock.acquire(timeout=timeout or cls._timeout)
            return True
        except Timeout:
            print("   ⚠️ Wallet lock timeout - another engine is trading")
            return False

    @classmethod
    def release(cls):
        """Release wallet lock."""
        if cls._lock and cls._lock.is_locked:
            cls._lock.release()

    @classmethod
    def is_locked(cls) -> bool:
        """Check if lock is currently held."""
        if cls._lock is None:
            cls._lock = FileLock(LOCK_FILE)
        return cls._lock.is_locked


class WalletLockTimeout(Exception):
    """Raised when wallet lock cannot be acquired."""

    pass


class TrailingStopManager:
    """
    V8.2: Trailing Stop Loss Logic.
    Moved from Watcher.py (V10.2 Refactor).
    """

    @staticmethod
    def update_tsl(current_price: float, state: dict) -> tuple[dict, bool, str]:
        """
        Update TSL state based on price action.
        Returns: (new_state, triggered, reason)
        State dict must contain: 'in_position', 'entry_price', 'max_price_achieved', 'trailing_stop_price'
        """
        # Copy state to avoid mutation side-effects until confirmed
        new_state = state.copy()

        if not state.get("in_position") or state.get("entry_price", 0) == 0:
            return new_state, False, ""

        if not Settings.TSL_ENABLED:
            return new_state, False, ""

        # 1. Update High Water Mark
        max_price = state.get("max_price_achieved", 0.0)
        trailing_stop = state.get("trailing_stop_price", 0.0)

        if current_price > max_price:
            new_state["max_price_achieved"] = current_price

            # Recalculate Trail if active
            if trailing_stop > 0:
                new_stop = current_price * (1 - Settings.TSL_TRAIL_PCT)
                # Only move stop UP
                if new_stop > trailing_stop:
                    new_state["trailing_stop_price"] = new_stop
                    # TSL Ratchet up - no trigger

        # 2. Check Activation (Profit > Threshold)
        if new_state.get("trailing_stop_price", 0) == 0:
            entry = state["entry_price"]
            profit_pct = (current_price - entry) / entry
            if profit_pct >= Settings.TSL_ACTIVATION_PCT:
                # Activate TSL
                new_state["trailing_stop_price"] = new_state["max_price_achieved"] * (
                    1 - Settings.TSL_TRAIL_PCT
                )
                # print(f"   🦅 TSL ACTIVATED at ${new_state['trailing_stop_price']:.4f}")

        # 3. Check Trigger
        final_stop = new_state.get("trailing_stop_price", 0)
        if final_stop > 0 and current_price < final_stop:
            return new_state, True, f"TSL HIT (${final_stop:.4f})"

        return new_state, False, ""
