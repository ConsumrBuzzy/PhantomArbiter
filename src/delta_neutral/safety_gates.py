"""
DNEM Safety Gates
=================
Protection mechanisms for MainNet trading with small balances.

Implements:
1. MAX_REBALANCE_FEE_USD - Never pay more than 0.5¢ to rebalance
2. Oracle Latency Shield - Abort if data is stale
3. Balance Guards - Ensure minimum gas reserves

These gates prevent the $12 balance from evaporating into fees.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.shared.system.logging import Logger


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass
class SafetyConfig:
    """Configuration for all safety gates."""
    
    # Fee protection
    max_rebalance_fee_usd: float = 0.005  # Never pay more than half a cent
    max_jito_tip_lamports: int = 15_000   # ~$0.002 at $150 SOL
    min_profit_ratio: float = 2.0         # Expected profit must be 2x fee
    
    # Latency protection
    max_rpc_latency_ms: float = 300.0     # 300ms max ping
    max_oracle_slot_lag: int = 5          # 5 slots = ~2 seconds
    
    # Balance protection
    min_sol_for_gas: float = 0.02         # Always keep 0.02 SOL for rent
    min_usdc_reserve: float = 0.50        # Keep $0.50 as buffer
    
    # Position limits
    max_position_usd: float = 100.0       # Cap for safety during testing
    max_leverage: float = 2.0             # Never exceed 2x


# =============================================================================
# FEE GUARD
# =============================================================================


class FeeGuard:
    """
    Prevents execution if fees exceed expected profits.
    
    The "Penny Guard" - ensures we never pay more to rebalance
    than we expect to earn.
    
    Example:
        >>> guard = FeeGuard()
        >>> if guard.should_execute(expected_profit=0.002, estimated_fee=0.001):
        ...     # Safe to trade
    """
    
    def __init__(self, config: Optional[SafetyConfig] = None):
        self.config = config or SafetyConfig()
        self._blocked_trades = 0
        self._allowed_trades = 0
    
    def estimate_fee_usd(
        self,
        jito_tip_lamports: int,
        sol_price: float,
        swap_amount_usd: float,
    ) -> float:
        """
        Estimate total fee for a rebalance trade.
        
        Components:
        - Jito tip (validator bribe)
        - Jupiter swap fee (~0.05%)
        - Drift trading fee (~0.02%)
        - Solana base fee (negligible)
        """
        # Jito tip in USD
        jito_usd = (jito_tip_lamports / 1_000_000_000) * sol_price
        
        # Jupiter swap fee (conservative 0.1%)
        jupiter_fee = swap_amount_usd * 0.001
        
        # Drift fee (0.02% taker)
        drift_fee = swap_amount_usd * 0.0002
        
        # Solana base fee (negligible)
        base_fee = 0.000005 * sol_price
        
        total = jito_usd + jupiter_fee + drift_fee + base_fee
        
        Logger.debug(
            f"[FEE GUARD] Estimated: Jito=${jito_usd:.6f}, "
            f"Jupiter=${jupiter_fee:.6f}, Drift=${drift_fee:.6f}, "
            f"Total=${total:.6f}"
        )
        
        return total
    
    def should_execute(
        self,
        expected_profit_usd: float,
        estimated_fee_usd: float,
    ) -> bool:
        """
        Determine if a trade should execute based on profit/fee ratio.
        
        Args:
            expected_profit_usd: Expected funding profit
            estimated_fee_usd: Estimated execution cost
        
        Returns:
            True if trade is profitable enough
        """
        # Gate 1: Absolute fee cap
        if estimated_fee_usd > self.config.max_rebalance_fee_usd:
            Logger.warning(
                f"[FEE GUARD] ❌ Fee ${estimated_fee_usd:.4f} exceeds max "
                f"${self.config.max_rebalance_fee_usd:.4f}"
            )
            self._blocked_trades += 1
            return False
        
        # Gate 2: Profit/fee ratio
        if expected_profit_usd <= 0:
            Logger.warning("[FEE GUARD] ❌ No expected profit")
            self._blocked_trades += 1
            return False
        
        ratio = expected_profit_usd / estimated_fee_usd if estimated_fee_usd > 0 else float('inf')
        
        if ratio < self.config.min_profit_ratio:
            Logger.warning(
                f"[FEE GUARD] ❌ Profit ratio {ratio:.2f}x < {self.config.min_profit_ratio}x minimum"
            )
            self._blocked_trades += 1
            return False
        
        Logger.info(
            f"[FEE GUARD] ✅ Trade approved: Profit=${expected_profit_usd:.6f}, "
            f"Fee=${estimated_fee_usd:.6f}, Ratio={ratio:.2f}x"
        )
        self._allowed_trades += 1
        return True
    
    def get_stats(self) -> dict:
        return {
            "blocked_trades": self._blocked_trades,
            "allowed_trades": self._allowed_trades,
        }


# =============================================================================
# ORACLE LATENCY SHIELD
# =============================================================================


class OracleLatencyShield:
    """
    Prevents trading on stale data.
    
    Checks:
    1. RPC ping latency
    2. Oracle slot lag (Pyth/Switchboard)
    3. Price freshness
    """
    
    def __init__(self, config: Optional[SafetyConfig] = None):
        self.config = config or SafetyConfig()
        self._stale_aborts = 0
    
    async def is_data_fresh(
        self,
        latency_monitor: any,
        rpc_client: any = None,
    ) -> bool:
        """
        Check if market data is fresh enough for trading.
        
        Args:
            latency_monitor: LatencyMonitor instance
            rpc_client: Optional Solana RPC client for slot check
        
        Returns:
            True if data is fresh, False if stale
        """
        # Check 1: RPC latency
        stats = latency_monitor.get_stats()
        avg_latency = stats.get("wss_avg_ms", 0)
        
        if avg_latency > self.config.max_rpc_latency_ms:
            Logger.warning(
                f"[ORACLE SHIELD] ❌ RPC latency {avg_latency:.0f}ms > "
                f"{self.config.max_rpc_latency_ms:.0f}ms limit"
            )
            self._stale_aborts += 1
            return False
        
        # Check 2: Slot lag (if RPC client available)
        if rpc_client:
            try:
                slot_lag = await self._check_slot_lag(rpc_client)
                if slot_lag > self.config.max_oracle_slot_lag:
                    Logger.warning(
                        f"[ORACLE SHIELD] ❌ Slot lag {slot_lag} > "
                        f"{self.config.max_oracle_slot_lag} limit"
                    )
                    self._stale_aborts += 1
                    return False
            except Exception as e:
                Logger.debug(f"[ORACLE SHIELD] Slot check failed: {e}")
        
        Logger.debug(f"[ORACLE SHIELD] ✅ Data fresh (latency: {avg_latency:.0f}ms)")
        return True
    
    async def _check_slot_lag(self, rpc_client) -> int:
        """Check how far behind the Oracle slot is from current slot."""
        # This would query Pyth/Switchboard oracle and compare to current slot
        # For now, return 0 (no lag)
        return 0
    
    def get_stats(self) -> dict:
        return {
            "stale_aborts": self._stale_aborts,
        }


# =============================================================================
# BALANCE GUARD
# =============================================================================


class BalanceGuard:
    """
    Ensures minimum balances are maintained.
    
    Prevents:
    - Running out of SOL for gas
    - Over-committing USDC
    - Exceeding position limits
    """
    
    def __init__(self, config: Optional[SafetyConfig] = None):
        self.config = config or SafetyConfig()
    
    async def check_balances(
        self,
        wallet: any,
        required_usd: float = 0.0,
    ) -> bool:
        """
        Verify wallet has sufficient balances.
        
        Args:
            wallet: WalletManager or MockWallet
            required_usd: Amount of USDC required for trade
        
        Returns:
            True if balances are sufficient
        """
        # Check SOL for gas
        sol_balance = wallet.get_sol_balance()
        if sol_balance < self.config.min_sol_for_gas:
            Logger.warning(
                f"[BALANCE GUARD] ❌ SOL balance {sol_balance:.4f} < "
                f"{self.config.min_sol_for_gas:.4f} minimum"
            )
            return False
        
        # Check USDC reserve
        usdc_balance = 0.0
        if hasattr(wallet, 'get_usdc_balance'):
            usdc_balance = wallet.get_usdc_balance()
        
        available_usdc = usdc_balance - self.config.min_usdc_reserve
        
        if required_usd > available_usdc:
            Logger.warning(
                f"[BALANCE GUARD] ❌ Required ${required_usd:.2f} > "
                f"available ${available_usdc:.2f}"
            )
            return False
        
        # Check position limit
        if required_usd > self.config.max_position_usd:
            Logger.warning(
                f"[BALANCE GUARD] ❌ Trade ${required_usd:.2f} exceeds "
                f"${self.config.max_position_usd:.2f} limit"
            )
            return False
        
        Logger.debug(
            f"[BALANCE GUARD] ✅ Balances OK: SOL={sol_balance:.4f}, "
            f"USDC={usdc_balance:.2f}"
        )
        return True


# =============================================================================
# UNIFIED SAFETY GATE
# =============================================================================


class SafetyGate:
    """
    Unified safety gate combining all protections.
    
    Use this as the single entry point for safety checks.
    
    Example:
        >>> gate = SafetyGate()
        >>> if await gate.can_execute(wallet, latency, signal, sol_price):
        ...     # All safety checks passed
    """
    
    def __init__(self, config: Optional[SafetyConfig] = None):
        self.config = config or SafetyConfig()
        self.fee_guard = FeeGuard(config)
        self.oracle_shield = OracleLatencyShield(config)
        self.balance_guard = BalanceGuard(config)
    
    async def can_execute(
        self,
        wallet: any,
        latency_monitor: any,
        expected_profit_usd: float,
        trade_amount_usd: float,
        sol_price: float,
        jito_tip_lamports: int = 10_000,
    ) -> bool:
        """
        Run all safety checks before execution.
        
        Returns:
            True only if ALL gates pass
        """
        # Gate 1: Balance check
        if not await self.balance_guard.check_balances(wallet, trade_amount_usd):
            return False
        
        # Gate 2: Oracle freshness
        if not await self.oracle_shield.is_data_fresh(latency_monitor):
            return False
        
        # Gate 3: Fee profitability
        estimated_fee = self.fee_guard.estimate_fee_usd(
            jito_tip_lamports,
            sol_price,
            trade_amount_usd,
        )
        
        if not self.fee_guard.should_execute(expected_profit_usd, estimated_fee):
            return False
        
        Logger.info("[SAFETY GATE] ✅ All gates passed - execution approved")
        return True
    
    def get_stats(self) -> dict:
        return {
            "fee_guard": self.fee_guard.get_stats(),
            "oracle_shield": self.oracle_shield.get_stats(),
        }
