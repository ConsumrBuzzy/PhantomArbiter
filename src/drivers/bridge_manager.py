"""
Bridge Manager
==============
Orchestrates USDC movement between Coinbase (CEX) and Phantom (DEX).

Implements the "Liquidity Sensor" logic:
- Monitors CEX balance (Coinbase)
- Monitors DEX balance (Phantom/Solana)
- Triggers bridge when conditions are met

Components:
- LiquiditySensor: Monitors both sides and calculates bridge amounts
- BridgeManager: Orchestrates the actual bridge execution

V200: Initial implementation
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable, Dict, Any, List
from enum import Enum

from src.shared.system.logging import Logger
from src.drivers.coinbase_driver import (
    CoinbaseExchangeDriver,
    get_coinbase_driver,
    BridgeResponse,
    WithdrawalResult,
)


# ═══════════════════════════════════════════════════════════════════════════════
# STATE TYPES
# ═══════════════════════════════════════════════════════════════════════════════

class BridgeState(Enum):
    """Current state of the bridge pipeline."""
    IDLE = "IDLE"
    CHECKING = "CHECKING"
    BRIDGING = "BRIDGING"
    CONFIRMING = "CONFIRMING"
    ERROR = "ERROR"


@dataclass
class LiquiditySnapshot:
    """Snapshot of CEX and DEX liquidity."""
    cex_usdc: float = 0.0       # Coinbase USDC (available)
    dex_usdc: float = 0.0       # Phantom USDC (on-chain)
    total_usdc: float = 0.0     # Total across both
    cex_ratio: float = 0.0      # % of total in CEX
    dex_ratio: float = 0.0      # % of total in DEX
    timestamp: float = field(default_factory=time.time)
    
    def __post_init__(self):
        self.total_usdc = self.cex_usdc + self.dex_usdc
        if self.total_usdc > 0:
            self.cex_ratio = self.cex_usdc / self.total_usdc
            self.dex_ratio = self.dex_usdc / self.total_usdc
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "cex_usdc": self.cex_usdc,
            "dex_usdc": self.dex_usdc,
            "total_usdc": self.total_usdc,
            "cex_ratio": f"{self.cex_ratio:.1%}",
            "dex_ratio": f"{self.dex_ratio:.1%}",
            "timestamp": self.timestamp,
        }


@dataclass
class BridgeDecision:
    """Decision about whether to bridge and how much."""
    should_bridge: bool = False
    amount: float = 0.0
    reason: str = ""
    snapshot: Optional[LiquiditySnapshot] = None


# ═══════════════════════════════════════════════════════════════════════════════
# LIQUIDITY SENSOR
# ═══════════════════════════════════════════════════════════════════════════════

class LiquiditySensor:
    """
    Monitors CEX and DEX balances for bridge opportunities.
    
    Bridge Triggers:
    - CEX has ≥ MIN_BRIDGE_AMOUNT available
    - DEX is below target allocation (if ratio-based mode)
    
    Usage:
        sensor = LiquiditySensor(coinbase_driver=driver)
        snapshot = await sensor.get_snapshot()
        decision = sensor.evaluate(snapshot)
    """
    
    def __init__(
        self,
        coinbase_driver: CoinbaseExchangeDriver,
        dex_balance_fn: Optional[Callable[[], Awaitable[float]]] = None,
        min_bridge_threshold: Optional[float] = None,
        target_dex_ratio: float = 0.8,
    ):
        """
        Initialize the liquidity sensor.
        
        Args:
            coinbase_driver: Coinbase exchange driver
            dex_balance_fn: Async function to get DEX USDC balance
            min_bridge_threshold: Override for MIN_BRIDGE_AMOUNT_USD
            target_dex_ratio: Target ratio to keep on DEX (0.8 = 80%)
        """
        self._coinbase = coinbase_driver
        self._get_dex_balance = dex_balance_fn
        
        # Use driver's configured threshold if not overridden
        self.min_bridge_threshold = (
            min_bridge_threshold if min_bridge_threshold is not None
            else coinbase_driver._min_bridge_amount
        )
        self.target_dex_ratio = target_dex_ratio
        
        self._last_snapshot: Optional[LiquiditySnapshot] = None
        self._snapshot_count = 0
    
    async def get_snapshot(self) -> LiquiditySnapshot:
        """
        Get current liquidity across CEX and DEX.
        
        Returns:
            LiquiditySnapshot with current balances
        """
        # Fetch CEX balance
        cex_balance = await self._coinbase.get_withdrawable_usdc()
        
        # Fetch DEX balance (if callback provided)
        dex_balance = 0.0
        if self._get_dex_balance:
            try:
                dex_balance = await self._get_dex_balance()
            except Exception as e:
                Logger.debug(f"DEX balance fetch error: {e}")
        
        snapshot = LiquiditySnapshot(
            cex_usdc=cex_balance,
            dex_usdc=dex_balance,
        )
        
        self._last_snapshot = snapshot
        self._snapshot_count += 1
        
        return snapshot
    
    def evaluate(self, snapshot: LiquiditySnapshot) -> BridgeDecision:
        """
        Evaluate whether a bridge should be triggered.
        
        Conditions:
        1. CEX has enough to bridge (≥ min threshold)
        2. DEX ratio is below target (optional, for rebalancing)
        
        Args:
            snapshot: Current liquidity snapshot
            
        Returns:
            BridgeDecision with recommendation
        """
        # ─────────────────────────────────────────────────────────────────
        # Gate 1: Minimum Balance Check
        # ─────────────────────────────────────────────────────────────────
        if snapshot.cex_usdc < self.min_bridge_threshold:
            return BridgeDecision(
                should_bridge=False,
                reason=f"Insufficient balance to bridge: ${snapshot.cex_usdc:.2f} < ${self.min_bridge_threshold:.2f}",
                snapshot=snapshot,
            )
        
        # ─────────────────────────────────────────────────────────────────
        # Gate 2: DEX Ratio Check (rebalancing mode)
        # ─────────────────────────────────────────────────────────────────
        if snapshot.total_usdc > 0 and snapshot.dex_ratio >= self.target_dex_ratio:
            return BridgeDecision(
                should_bridge=False,
                reason=f"DEX ratio already at target: {snapshot.dex_ratio:.1%} >= {self.target_dex_ratio:.1%}",
                snapshot=snapshot,
            )
        
        # ─────────────────────────────────────────────────────────────────
        # Calculate Bridge Amount
        # ─────────────────────────────────────────────────────────────────
        amount = self.calculate_bridge_amount(snapshot)
        
        if amount < self.min_bridge_threshold:
            return BridgeDecision(
                should_bridge=False,
                reason=f"Calculated amount too small: ${amount:.2f}",
                snapshot=snapshot,
            )
        
        return BridgeDecision(
            should_bridge=True,
            amount=amount,
            reason=f"Bridge ${amount:.2f} to reach {self.target_dex_ratio:.0%} DEX allocation",
            snapshot=snapshot,
        )
    
    def calculate_bridge_amount(self, snapshot: LiquiditySnapshot) -> float:
        """
        Calculate optimal bridge amount.
        
        Bridges enough to reach target DEX ratio, respecting dust floor.
        
        Args:
            snapshot: Current liquidity snapshot
            
        Returns:
            Optimal bridge amount in USD
        """
        if snapshot.total_usdc <= 0:
            return 0.0
        
        # Calculate how much DEX needs to reach target
        target_dex = snapshot.total_usdc * self.target_dex_ratio
        needed_on_dex = target_dex - snapshot.dex_usdc
        
        if needed_on_dex <= 0:
            return 0.0
        
        # Respect CEX dust floor
        dust_floor = self._coinbase._dust_floor
        max_from_cex = max(0, snapshot.cex_usdc - dust_floor)
        
        return min(needed_on_dex, max_from_cex)
    
    @property
    def last_snapshot(self) -> Optional[LiquiditySnapshot]:
        return self._last_snapshot


# ═══════════════════════════════════════════════════════════════════════════════
# BRIDGE MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class BridgeManager:
    """
    Orchestrates the CEX-to-DEX bridge pipeline.
    
    Combines:
    - LiquiditySensor for monitoring
    - CoinbaseExchangeDriver for execution
    - Safety gate enforcement
    
    Usage:
        manager = BridgeManager()
        await manager.check_and_bridge()
    """
    
    def __init__(
        self,
        coinbase_driver: Optional[CoinbaseExchangeDriver] = None,
        dex_balance_fn: Optional[Callable[[], Awaitable[float]]] = None,
    ):
        """
        Initialize the bridge manager.
        
        Args:
            coinbase_driver: Coinbase driver (uses singleton if not provided)
            dex_balance_fn: Async function to get DEX USDC balance
        """
        self._coinbase = coinbase_driver or get_coinbase_driver()
        self._sensor = LiquiditySensor(
            coinbase_driver=self._coinbase,
            dex_balance_fn=dex_balance_fn,
        )
        
        # State tracking
        self._state = BridgeState.IDLE
        self._last_bridge_response: Optional[BridgeResponse] = None
        self._last_decision: Optional[BridgeDecision] = None
        self._bridge_count = 0
        self._total_bridged = 0.0
        self._bridge_history: List[BridgeResponse] = []
    
    @property
    def state(self) -> BridgeState:
        """Current bridge state."""
        return self._state
    
    @property
    def sensor(self) -> LiquiditySensor:
        """Access the liquidity sensor."""
        return self._sensor
    
    async def check_and_bridge(self) -> Optional[BridgeResponse]:
        """
        Check liquidity and bridge if conditions are met.
        
        This is the main entry point for automated bridging.
        
        Returns:
            BridgeResponse if bridge executed, None otherwise
        """
        self._state = BridgeState.CHECKING
        
        try:
            # Get current liquidity state
            snapshot = await self._sensor.get_snapshot()
            
            Logger.debug(
                f"📊 Liquidity: CEX=${snapshot.cex_usdc:.2f} "
                f"DEX=${snapshot.dex_usdc:.2f} "
                f"(CEX: {snapshot.cex_ratio:.1%})"
            )
            
            # Evaluate whether to bridge
            decision = self._sensor.evaluate(snapshot)
            self._last_decision = decision
            
            if not decision.should_bridge:
                Logger.info(f"⏸️ Bridge skipped: {decision.reason}")
                self._state = BridgeState.IDLE
                return None
            
            # Execute bridge
            self._state = BridgeState.BRIDGING
            Logger.info(f"🌉 Initiating bridge: ${decision.amount:.2f} USDC → Phantom")
            
            response = await self._coinbase.bridge_to_phantom(decision.amount)
            self._last_bridge_response = response
            self._bridge_history.append(response)
            
            if response.success:
                self._bridge_count += 1
                self._total_bridged += response.amount
                self._state = BridgeState.CONFIRMING
                Logger.info(
                    f"✅ Bridge #{self._bridge_count} initiated: {response.withdrawal_id} "
                    f"(Total bridged: ${self._total_bridged:.2f})"
                )
            else:
                self._state = BridgeState.ERROR
                Logger.warning(f"⚠️ Bridge failed: {response.message}")
            
            return response
            
        except Exception as e:
            self._state = BridgeState.ERROR
            Logger.error(f"❌ Bridge error: {e}")
            return None
        finally:
            # Reset to IDLE after a short delay if not in CONFIRMING
            if self._state == BridgeState.ERROR:
                await asyncio.sleep(1)
                self._state = BridgeState.IDLE
    
    async def force_bridge(self, amount: float) -> BridgeResponse:
        """
        Force a bridge of a specific amount (bypasses sensor evaluation).
        
        Still applies all safety gates in the driver.
        
        Args:
            amount: Amount to bridge
            
        Returns:
            BridgeResponse with result
        """
        Logger.info(f"🔧 Force bridge requested: ${amount:.2f}")
        
        self._state = BridgeState.BRIDGING
        response = await self._coinbase.bridge_to_phantom(amount)
        
        if response.success:
            self._bridge_count += 1
            self._total_bridged += response.amount
            self._state = BridgeState.CONFIRMING
        else:
            self._state = BridgeState.ERROR
        
        self._last_bridge_response = response
        self._bridge_history.append(response)
        
        return response
    
    async def get_status(self) -> Dict[str, Any]:
        """
        Get current bridge manager status.
        
        Returns:
            Dict with state, balances, and history
        """
        snapshot = await self._sensor.get_snapshot()
        
        return {
            "state": self._state.value,
            "cex_balance": snapshot.cex_usdc,
            "dex_balance": snapshot.dex_usdc,
            "total_liquidity": snapshot.total_usdc,
            "bridge_count": self._bridge_count,
            "total_bridged": self._total_bridged,
            "last_decision": self._last_decision.reason if self._last_decision else None,
            "driver_configured": self._coinbase.is_configured,
            "phantom_address": self._coinbase.phantom_address,
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get bridge statistics.
        
        Returns:
            Dict with historical stats
        """
        return {
            "state": self._state.value,
            "bridge_count": self._bridge_count,
            "total_bridged": self._total_bridged,
            "last_response": (
                self._last_bridge_response.to_dict() 
                if self._last_bridge_response else None
            ),
            "last_snapshot": (
                self._sensor.last_snapshot.to_dict()
                if self._sensor.last_snapshot else None
            ),
            "recent_bridges": [
                r.to_dict() for r in self._bridge_history[-5:]
            ],
        }


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON ACCESS
# ═══════════════════════════════════════════════════════════════════════════════

_manager_instance: Optional[BridgeManager] = None


def get_bridge_manager() -> BridgeManager:
    """Get or create the global BridgeManager instance."""
    global _manager_instance
    
    if _manager_instance is None:
        _manager_instance = BridgeManager()
    
    return _manager_instance


def reset_bridge_manager():
    """Reset the global manager (for testing)."""
    global _manager_instance
    _manager_instance = None
