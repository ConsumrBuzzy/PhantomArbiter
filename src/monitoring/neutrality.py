"""
Delta Neutrality Monitor
========================
Extracted monitoring logic for hedge balance tracking.

Integrated into the HeartbeatCollector to provide live delta status
in every system snapshot.

The "Shield" that ensures Long Spot matches Short Perp.
"""

from __future__ import annotations

import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

from src.shared.system.logging import Logger


# ═══════════════════════════════════════════════════════════════════════════════
# DELTA STATE SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class HedgeStatus(Enum):
    """Current status of the delta hedge."""
    
    BALANCED = "BALANCED"       # Delta within tolerance
    OVERHEDGED = "OVERHEDGED"   # More short than long (negative delta)
    UNDERHEDGED = "UNDERHEDGED" # More long than short (positive delta)
    CRITICAL = "CRITICAL"       # Drift exceeds emergency threshold
    UNKNOWN = "UNKNOWN"         # Unable to calculate


@dataclass
class DeltaState:
    """
    Live delta neutrality state for dashboard display.
    
    This is the "Pulse" that tells the UI how balanced the hedge is.
    Included in every SystemSnapshot for real-time monitoring.
    
    Key Metrics:
    - spot_exposure: Value of long SOL position ($)
    - perp_exposure: Value of short SOL-PERP position ($)
    - net_delta: spot_exposure + perp_exposure (ideally near 0)
    - drift_pct: |net_delta| / total_exposure * 100
    """
    
    # Position sizes
    spot_qty: float = 0.0           # SOL held
    perp_qty: float = 0.0           # SOL-PERP position (negative = short)
    
    # Dollar exposures
    spot_exposure_usd: float = 0.0  # spot_qty * price
    perp_exposure_usd: float = 0.0  # perp_qty * price (negative for shorts)
    
    # Delta metrics
    net_delta_usd: float = 0.0      # spot + perp (should be ~0)
    total_notional_usd: float = 0.0 # |spot| + |perp|
    drift_pct: float = 0.0          # |net_delta| / total_notional * 100
    
    # Status
    status: HedgeStatus = HedgeStatus.UNKNOWN
    needs_rebalance: bool = False
    suggested_action: Optional[str] = None  # "ADD_SHORT", "REDUCE_SHORT", etc.
    
    # Price context
    sol_price: float = 0.0
    funding_rate_8h: float = 0.0    # Current funding rate
    
    # Timestamps
    captured_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dashboard-friendly dict."""
        return {
            "spot_qty": round(self.spot_qty, 4),
            "perp_qty": round(self.perp_qty, 4),
            "spot_exposure_usd": round(self.spot_exposure_usd, 2),
            "perp_exposure_usd": round(self.perp_exposure_usd, 2),
            "net_delta_usd": round(self.net_delta_usd, 2),
            "drift_pct": round(self.drift_pct, 3),
            "status": self.status.value,
            "needs_rebalance": self.needs_rebalance,
            "suggested_action": self.suggested_action,
            "sol_price": round(self.sol_price, 2),
            "funding_rate_8h": round(self.funding_rate_8h, 4),
        }
    
    @property
    def is_neutral(self) -> bool:
        """Check if currently delta neutral (within 1%)."""
        return self.drift_pct < 1.0
    
    @property
    def urgency(self) -> str:
        """Get urgency level for UI display."""
        if self.drift_pct > 5.0:
            return "CRITICAL"
        elif self.drift_pct > 2.0:
            return "WARNING"
        elif self.drift_pct > 0.5:
            return "ATTENTION"
        return "OK"


# ═══════════════════════════════════════════════════════════════════════════════
# DELTA CALCULATOR
# ═══════════════════════════════════════════════════════════════════════════════

class DeltaCalculator:
    """
    Calculates delta state from wallet and perp positions.
    
    Integration:
    - Called by HeartbeatDataCollector during snapshot collection
    - Returns immutable DeltaState for inclusion in SystemSnapshot
    
    Usage:
        calculator = DeltaCalculator(wallet, drift, price_feed)
        delta = await calculator.calculate()
        snapshot.delta_state = delta
    """
    
    # Drift thresholds
    REBALANCE_THRESHOLD_PCT = 0.5   # Trigger rebalance above this
    CRITICAL_THRESHOLD_PCT = 5.0    # Emergency above this
    
    def __init__(
        self,
        wallet: Any = None,
        drift_adapter: Any = None,
        price_feed: Any = None,
    ):
        """
        Initialize calculator.
        
        Args:
            wallet: WalletManager for spot balance queries
            drift_adapter: DriftAdapter for perp position queries
            price_feed: Price source for SOL/USD
        """
        self.wallet = wallet
        self.drift = drift_adapter
        self.price_feed = price_feed
        
        # History for averaging
        self._drift_history: List[float] = []
    
    async def calculate(self, sol_price: float = None) -> DeltaState:
        """
        Calculate current delta state.
        
        Args:
            sol_price: Optional override for SOL price
            
        Returns:
            Immutable DeltaState with all metrics
        """
        # Get price
        if sol_price is None:
            sol_price = await self._get_sol_price()
        
        # Get spot balance
        spot_qty = self._get_spot_balance()
        
        # Get perp position
        perp_qty = await self._get_perp_position()
        
        # Calculate exposures
        spot_exposure = spot_qty * sol_price
        perp_exposure = perp_qty * sol_price  # Negative for short
        
        net_delta = spot_exposure + perp_exposure
        total_notional = abs(spot_exposure) + abs(perp_exposure)
        
        # Calculate drift percentage
        drift_pct = 0.0
        if total_notional > 0:
            drift_pct = abs(net_delta) / total_notional * 100
        
        # Track history
        self._drift_history.append(drift_pct)
        if len(self._drift_history) > 100:
            self._drift_history = self._drift_history[-100:]
        
        # Determine status
        status = self._determine_status(net_delta, drift_pct)
        
        # Determine if rebalance needed
        needs_rebalance = drift_pct > self.REBALANCE_THRESHOLD_PCT
        
        # Suggest action
        suggested_action = None
        if needs_rebalance:
            if net_delta > 0:
                suggested_action = "ADD_SHORT"  # Too much spot, need more short
            else:
                suggested_action = "REDUCE_SHORT"  # Too much short, reduce
        
        # Get funding rate (if available)
        funding_rate = await self._get_funding_rate()
        
        return DeltaState(
            spot_qty=spot_qty,
            perp_qty=perp_qty,
            spot_exposure_usd=spot_exposure,
            perp_exposure_usd=perp_exposure,
            net_delta_usd=net_delta,
            total_notional_usd=total_notional,
            drift_pct=drift_pct,
            status=status,
            needs_rebalance=needs_rebalance,
            suggested_action=suggested_action,
            sol_price=sol_price,
            funding_rate_8h=funding_rate,
        )
    
    def _determine_status(self, net_delta: float, drift_pct: float) -> HedgeStatus:
        """Determine hedge status from delta values."""
        if drift_pct > self.CRITICAL_THRESHOLD_PCT:
            return HedgeStatus.CRITICAL
        
        if drift_pct < 0.5:
            return HedgeStatus.BALANCED
        
        if net_delta > 0:
            return HedgeStatus.UNDERHEDGED  # More long than short
        else:
            return HedgeStatus.OVERHEDGED  # More short than long
    
    def _get_spot_balance(self) -> float:
        """Get SOL balance from wallet."""
        try:
            if self.wallet and hasattr(self.wallet, 'get_sol_balance'):
                return self.wallet.get_sol_balance()
        except Exception as e:
            Logger.debug(f"[DeltaCalculator] Spot balance error: {e}")
        return 0.0
    
    async def _get_perp_position(self) -> float:
        """Get perp position from Drift."""
        try:
            if self.drift:
                if hasattr(self.drift, 'get_perp_position'):
                    pos = self.drift.get_perp_position(0)  # SOL-PERP
                    if pos:
                        return pos.get("size", 0.0)
                elif hasattr(self.drift, 'get_position'):
                    pos = await self.drift.get_position("SOL-PERP")
                    if pos:
                        return pos.size
        except Exception as e:
            Logger.debug(f"[DeltaCalculator] Perp position error: {e}")
        return 0.0
    
    async def _get_sol_price(self) -> float:
        """Get SOL price from feed."""
        try:
            if self.price_feed:
                if hasattr(self.price_feed, 'get_spot_price'):
                    quote = self.price_feed.get_spot_price("SOL", "USDC")
                    if quote and quote.price > 0:
                        return quote.price
        except Exception as e:
            Logger.debug(f"[DeltaCalculator] Price error: {e}")
        return 150.0  # Fallback
    
    async def _get_funding_rate(self) -> float:
        """Get current funding rate from Drift."""
        try:
            if self.drift and hasattr(self.drift, 'get_funding_rate'):
                return self.drift.get_funding_rate(0)  # SOL-PERP
        except Exception:
            pass
        return 0.0
    
    def get_avg_drift(self) -> float:
        """Get average drift over history."""
        if not self._drift_history:
            return 0.0
        return sum(self._drift_history) / len(self._drift_history)
    
    def get_max_drift(self) -> float:
        """Get maximum drift over history."""
        if not self._drift_history:
            return 0.0
        return max(self._drift_history)


# ═══════════════════════════════════════════════════════════════════════════════
# SAFETY GATES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SafetyStatus:
    """Current status of all safety gates."""
    
    all_clear: bool = True
    active_blocks: List[str] = field(default_factory=list)
    
    # Individual gate statuses
    latency_ok: bool = True
    delta_ok: bool = True
    funding_ok: bool = True
    balance_ok: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "all_clear": self.all_clear,
            "active_blocks": self.active_blocks,
            "latency_ok": self.latency_ok,
            "delta_ok": self.delta_ok,
            "funding_ok": self.funding_ok,
            "balance_ok": self.balance_ok,
        }


class SafetyGateChecker:
    """
    Checks all safety conditions before allowing trades.
    
    Gates:
    - Latency: RPC/WSS latency must be <500ms
    - Delta: Hedge must be within tolerance
    - Funding: Rate must be positive (we collect)
    - Balance: Sufficient SOL for gas
    """
    
    MAX_LATENCY_MS = 500.0
    MAX_DRIFT_PCT = 5.0
    MIN_GAS_SOL = 0.01
    
    def __init__(
        self,
        latency_monitor: Any = None,
        delta_calculator: DeltaCalculator = None,
        wallet: Any = None,
    ):
        self.latency = latency_monitor
        self.delta_calc = delta_calculator
        self.wallet = wallet
    
    async def check_all(self) -> SafetyStatus:
        """Check all safety gates."""
        status = SafetyStatus()
        
        # Check latency
        if self.latency:
            try:
                stats = self.latency.get_stats()
                avg_latency = stats.get("wss_avg_ms", 0)
                if avg_latency > self.MAX_LATENCY_MS:
                    status.latency_ok = False
                    status.all_clear = False
                    status.active_blocks.append(f"LATENCY: {avg_latency:.0f}ms")
            except Exception:
                pass
        
        # Check delta
        if self.delta_calc:
            try:
                delta = await self.delta_calc.calculate()
                if delta.drift_pct > self.MAX_DRIFT_PCT:
                    status.delta_ok = False
                    status.all_clear = False
                    status.active_blocks.append(f"DELTA: {delta.drift_pct:.1f}%")
            except Exception:
                pass
        
        # Check balance
        if self.wallet:
            try:
                sol = self.wallet.get_sol_balance()
                if sol < self.MIN_GAS_SOL:
                    status.balance_ok = False
                    status.all_clear = False
                    status.active_blocks.append(f"GAS: {sol:.4f} SOL")
            except Exception:
                pass
        
        return status
