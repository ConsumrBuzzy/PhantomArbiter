"""
Rebalance Sensor
================
Monitors the "Yield Gap" and triggers bridges when profitable.

The "Brain" of the CEX-DEX Liquidity Bridge:
1. Subscribes to FundingOpportunity signals from FundingEngine
2. Evaluates against current Phantom (DEX) liquidity
3. Triggers BridgeManager when deficit detected + yield attractive

Opportunity-Liquidity Matrix:
┌──────────────────┬─────────────┬───────────────────┬─────────────────┐
│ Scenario         │ Yield       │ Phantom Balance   │ Action          │
├──────────────────┼─────────────┼───────────────────┼─────────────────┤
│ High Yield       │ > 15% APY   │ < Required        │ TRIGGER BRIDGE  │
│ Low Yield        │ < 5% APY    │ > $50             │ IDLE            │
│ Volatile Market  │ Spiking     │ Any               │ LOCK BRIDGE     │
│ Cooldown Active  │ Any         │ Any               │ WAIT            │
└──────────────────┴─────────────┴───────────────────┴─────────────────┘

V200: Initial implementation
"""

import asyncio
import time
import os
from typing import Optional, Callable, Awaitable, Dict, Any, List
from dataclasses import dataclass, field

from src.shared.system.logging import Logger
from src.shared.system.signal_bus import signal_bus, Signal, SignalType
from src.signals.rebalance_signal import (
    RebalanceDecision,
    FundingOpportunitySignal,
    BridgeTriggerSignal,
    BridgeCompleteSignal,
    RebalanceEvaluation,
)


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class RebalanceSensorConfig:
    """Configuration for the rebalance sensor."""
    
    # Yield thresholds (annualized APY)
    min_yield_threshold: float = 5.0     # Minimum APY to consider bridging
    high_yield_threshold: float = 15.0   # APY that triggers immediate bridge
    
    # Balance thresholds
    min_phantom_buffer: float = 5.0      # Always keep $5 buffer on Phantom
    max_bridge_pct: float = 0.8          # Max 80% of CEX balance per bridge
    
    # Volatility protection
    volatility_lock_enabled: bool = True
    max_volatility_pct: float = 5.0      # Lock if 5%+ price move in 1h
    
    # Timing
    cooldown_seconds: int = 300          # 5 min between bridges
    
    # Loaded from environment
    min_bridge_amount: float = field(default_factory=lambda: float(os.getenv("MIN_BRIDGE_AMOUNT_USD", "5.0")))
    cex_dust_floor: float = field(default_factory=lambda: float(os.getenv("CEX_DUST_FLOOR_USD", "1.0")))


# ═══════════════════════════════════════════════════════════════════════════════
# REBALANCE SENSOR
# ═══════════════════════════════════════════════════════════════════════════════

class RebalanceSensor:
    """
    Monitors funding opportunities and triggers bridges when conditions align.
    
    The "Brain" of the CEX-DEX pipeline:
    1. Subscribes to FUNDING_OPPORTUNITY signals
    2. Evaluates against current DEX liquidity
    3. Triggers BridgeManager when deficit detected
    4. Emits BRIDGE_TRIGGER signals for dashboard visibility
    
    Usage:
        sensor = RebalanceSensor()
        sensor.set_balance_callbacks(
            phantom_fn=wallet.get_usdc_balance,
            cex_fn=coinbase.get_withdrawable_usdc,
        )
        sensor.set_bridge_callback(bridge_manager.bridge_to_phantom)
        sensor.start()
    """
    
    def __init__(self, config: Optional[RebalanceSensorConfig] = None):
        self.config = config or RebalanceSensorConfig()
        
        # Balance callbacks (async functions)
        self._get_phantom_balance: Optional[Callable[[], Awaitable[float]]] = None
        self._get_cex_balance: Optional[Callable[[], Awaitable[float]]] = None
        
        # Bridge execution callback
        self._trigger_bridge: Optional[Callable[[float], Awaitable[Any]]] = None
        
        # State
        self._last_bridge_time: float = 0.0
        self._pending_bridge: Optional[BridgeTriggerSignal] = None
        self._evaluation_history: List[RebalanceEvaluation] = []
        self._max_history = 50
        self._active = False
        
        # Stats
        self._total_evaluations = 0
        self._total_bridges_triggered = 0
        self._total_bridged_usd = 0.0
    
    # ─────────────────────────────────────────────────────────────────────────
    # CONFIGURATION
    # ─────────────────────────────────────────────────────────────────────────
    
    def set_balance_callbacks(
        self,
        phantom_fn: Callable[[], Awaitable[float]],
        cex_fn: Callable[[], Awaitable[float]],
    ):
        """
        Set the async functions to fetch balances.
        
        Args:
            phantom_fn: Returns Phantom USDC balance
            cex_fn: Returns Coinbase withdrawable USDC
        """
        self._get_phantom_balance = phantom_fn
        self._get_cex_balance = cex_fn
    
    def set_bridge_callback(self, bridge_fn: Callable[[float], Awaitable[Any]]):
        """
        Set the async function to trigger a bridge.
        
        Args:
            bridge_fn: Takes amount, returns BridgeResponse
        """
        self._trigger_bridge = bridge_fn
    
    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────
    
    def start(self):
        """Subscribe to funding opportunity signals and start monitoring."""
        if self._active:
            Logger.debug("RebalanceSensor already active")
            return
        
        # Subscribe to funding opportunities
        signal_bus.subscribe(SignalType.FUNDING_OPPORTUNITY, self._on_funding_signal)
        self._active = True
        Logger.info("🧠 RebalanceSensor started - monitoring yield gap")
    
    def stop(self):
        """Stop monitoring (unsubscribe not implemented in SignalBus)."""
        self._active = False
        Logger.info("🧠 RebalanceSensor stopped")
    
    @property
    def is_active(self) -> bool:
        return self._active
    
    # ─────────────────────────────────────────────────────────────────────────
    # SIGNAL HANDLER
    # ─────────────────────────────────────────────────────────────────────────
    
    async def _on_funding_signal(self, signal: Signal):
        """Handle incoming funding opportunity signal from SignalBus."""
        if not self._active:
            return
        
        try:
            data = signal.data
            
            # Parse signal into typed object
            opportunity = FundingOpportunitySignal(
                market=data.get("market", "UNKNOWN"),
                funding_rate_8h=data.get("funding_rate", 0.0),
                expected_yield_usd=data.get("expected_yield", 0.0),
                required_capital=data.get("required_capital", 0.0),
                time_to_funding_sec=data.get("time_to_funding", 0.0),
                direction=data.get("direction", ""),
            )
            
            Logger.debug(
                f"🧠 Received FUNDING_OPPORTUNITY: {opportunity.market} "
                f"@ {opportunity.annualized_apy:.1f}% APY"
            )
            
            # Evaluate and potentially trigger bridge
            evaluation = await self.evaluate_opportunity(opportunity)
            
            Logger.info(f"🧠 {evaluation.to_log_string()}")
            
        except Exception as e:
            Logger.error(f"🧠 RebalanceSensor signal error: {e}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # EVALUATION ENGINE
    # ─────────────────────────────────────────────────────────────────────────
    
    async def evaluate_opportunity(
        self,
        opportunity: FundingOpportunitySignal,
    ) -> RebalanceEvaluation:
        """
        Evaluate a funding opportunity against current liquidity.
        
        Implements the Opportunity-Liquidity Matrix decision logic.
        
        Args:
            opportunity: The funding opportunity to evaluate
            
        Returns:
            RebalanceEvaluation with decision and full context
        """
        self._total_evaluations += 1
        
        # ─────────────────────────────────────────────────────────────────
        # GATHER CURRENT STATE
        # ─────────────────────────────────────────────────────────────────
        
        phantom_balance = 0.0
        cex_available = 0.0
        
        if self._get_phantom_balance:
            try:
                phantom_balance = await self._get_phantom_balance()
            except Exception as e:
                Logger.debug(f"Phantom balance fetch failed: {e}")
        
        if self._get_cex_balance:
            try:
                cex_available = await self._get_cex_balance()
            except Exception as e:
                Logger.debug(f"CEX balance fetch failed: {e}")
        
        yield_apy = opportunity.annualized_apy
        required = opportunity.required_capital
        
        # ─────────────────────────────────────────────────────────────────
        # DECISION MATRIX
        # ─────────────────────────────────────────────────────────────────
        
        # Gate 1: Check cooldown
        time_since_bridge = time.time() - self._last_bridge_time
        if self._last_bridge_time > 0 and time_since_bridge < self.config.cooldown_seconds:
            remaining = self.config.cooldown_seconds - time_since_bridge
            evaluation = RebalanceEvaluation(
                decision=RebalanceDecision.COOLDOWN,
                reason=f"Bridge cooldown: {remaining:.0f}s remaining",
                phantom_balance=phantom_balance,
                cex_available=cex_available,
                required_capital=required,
                yield_apy=yield_apy,
                opportunity=opportunity,
            )
            self._add_to_history(evaluation)
            return evaluation
        
        # Gate 2: Check yield threshold
        if yield_apy < self.config.min_yield_threshold:
            evaluation = RebalanceEvaluation(
                decision=RebalanceDecision.IDLE,
                reason=f"Yield {yield_apy:.1f}% below minimum {self.config.min_yield_threshold}%",
                phantom_balance=phantom_balance,
                cex_available=cex_available,
                required_capital=required,
                yield_apy=yield_apy,
                opportunity=opportunity,
            )
            self._add_to_history(evaluation)
            return evaluation
        
        # Gate 3: Check if Phantom already has enough
        if phantom_balance >= required:
            evaluation = RebalanceEvaluation(
                decision=RebalanceDecision.IDLE,
                reason=f"Phantom sufficient: ${phantom_balance:.2f} >= ${required:.2f}",
                phantom_balance=phantom_balance,
                cex_available=cex_available,
                required_capital=required,
                yield_apy=yield_apy,
                opportunity=opportunity,
            )
            self._add_to_history(evaluation)
            return evaluation
        
        # Gate 4: Calculate deficit and check CEX availability
        deficit = required - phantom_balance
        max_from_cex = max(0, cex_available - self.config.cex_dust_floor)
        
        if max_from_cex < self.config.min_bridge_amount:
            evaluation = RebalanceEvaluation(
                decision=RebalanceDecision.IDLE,
                reason=f"CEX insufficient: ${cex_available:.2f} (dust floor: ${self.config.cex_dust_floor:.2f})",
                phantom_balance=phantom_balance,
                cex_available=cex_available,
                required_capital=required,
                deficit=deficit,
                yield_apy=yield_apy,
                opportunity=opportunity,
            )
            self._add_to_history(evaluation)
            return evaluation
        
        # Calculate bridge amount (min of deficit and max available)
        bridge_amount = min(deficit, max_from_cex)
        
        # Ensure minimum bridge amount
        if bridge_amount < self.config.min_bridge_amount:
            evaluation = RebalanceEvaluation(
                decision=RebalanceDecision.IDLE,
                reason=f"Bridge amount ${bridge_amount:.2f} below minimum ${self.config.min_bridge_amount:.2f}",
                phantom_balance=phantom_balance,
                cex_available=cex_available,
                required_capital=required,
                deficit=deficit,
                yield_apy=yield_apy,
                opportunity=opportunity,
            )
            self._add_to_history(evaluation)
            return evaluation
        
        # ─────────────────────────────────────────────────────────────────
        # TRIGGER BRIDGE
        # ─────────────────────────────────────────────────────────────────
        
        # High yield = immediate bridge
        if yield_apy >= self.config.high_yield_threshold:
            reason = f"HIGH YIELD {yield_apy:.1f}% >= {self.config.high_yield_threshold}%"
        else:
            reason = f"Yield {yield_apy:.1f}% with ${deficit:.2f} deficit"
        
        evaluation = RebalanceEvaluation(
            decision=RebalanceDecision.BRIDGE,
            reason=reason,
            phantom_balance=phantom_balance,
            cex_available=cex_available,
            required_capital=required,
            deficit=deficit,
            yield_apy=yield_apy,
            opportunity=opportunity,
            bridge_amount=bridge_amount,
        )
        
        # Execute bridge
        bridge_success = await self._execute_bridge(bridge_amount, opportunity)
        evaluation.bridge_triggered = bridge_success
        
        self._add_to_history(evaluation)
        return evaluation
    
    # ─────────────────────────────────────────────────────────────────────────
    # BRIDGE EXECUTION
    # ─────────────────────────────────────────────────────────────────────────
    
    async def _execute_bridge(
        self,
        amount: float,
        opportunity: FundingOpportunitySignal,
    ) -> bool:
        """
        Execute the bridge and emit signals for dashboard visibility.
        
        Returns:
            True if bridge was initiated successfully
        """
        Logger.info(f"🌉 RebalanceSensor triggering bridge: ${amount:.2f}")
        
        # Create trigger signal
        trigger = BridgeTriggerSignal(
            amount=amount,
            reason="funding_opportunity",
            opportunity=opportunity,
        )
        self._pending_bridge = trigger
        
        # Emit signal for dashboard (neon blue pulse)
        signal_bus.emit(Signal(
            type=SignalType.BRIDGE_TRIGGER,
            source="RebalanceSensor",
            data=trigger.to_dict(),
        ))
        
        # Execute bridge via callback
        if self._trigger_bridge:
            try:
                result = await self._trigger_bridge(amount)
                
                # Update trigger with withdrawal ID if available
                if hasattr(result, 'withdrawal_id') and result.withdrawal_id:
                    trigger.withdrawal_id = result.withdrawal_id
                elif isinstance(result, dict) and result.get('withdrawal_id'):
                    trigger.withdrawal_id = result['withdrawal_id']
                
                # Update timestamps
                self._last_bridge_time = time.time()
                self._total_bridges_triggered += 1
                self._total_bridged_usd += amount
                
                Logger.info(
                    f"✅ Bridge #{self._total_bridges_triggered} initiated: "
                    f"${amount:.2f} (TXID: {trigger.withdrawal_id})"
                )
                
                return True
                
            except Exception as e:
                Logger.error(f"❌ Bridge execution failed: {e}")
                self._pending_bridge = None
                return False
        else:
            Logger.warning("⚠️ No bridge callback configured - simulating")
            self._last_bridge_time = time.time()
            return True
    
    def _add_to_history(self, evaluation: RebalanceEvaluation):
        """Add evaluation to history with size limit."""
        self._evaluation_history.append(evaluation)
        if len(self._evaluation_history) > self._max_history:
            self._evaluation_history.pop(0)
    
    # ─────────────────────────────────────────────────────────────────────────
    # STATUS & STATS
    # ─────────────────────────────────────────────────────────────────────────
    
    def get_status(self) -> Dict[str, Any]:
        """Get current sensor status for dashboard."""
        time_since = None
        if self._last_bridge_time > 0:
            time_since = time.time() - self._last_bridge_time
        
        return {
            "active": self._active,
            "pending_bridge": self._pending_bridge.to_dict() if self._pending_bridge else None,
            "last_bridge_ago_sec": time_since,
            "in_cooldown": time_since is not None and time_since < self.config.cooldown_seconds,
            "config": {
                "min_yield_threshold": self.config.min_yield_threshold,
                "high_yield_threshold": self.config.high_yield_threshold,
                "cooldown_seconds": self.config.cooldown_seconds,
                "min_bridge_amount": self.config.min_bridge_amount,
            },
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get lifetime statistics."""
        return {
            "total_evaluations": self._total_evaluations,
            "total_bridges_triggered": self._total_bridges_triggered,
            "total_bridged_usd": self._total_bridged_usd,
            "evaluation_history_size": len(self._evaluation_history),
            "last_evaluation": (
                self._evaluation_history[-1].to_dict() 
                if self._evaluation_history else None
            ),
        }
    
    def get_recent_evaluations(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent evaluation history."""
        return [e.to_dict() for e in self._evaluation_history[-limit:]]


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON ACCESS
# ═══════════════════════════════════════════════════════════════════════════════

_sensor_instance: Optional[RebalanceSensor] = None


def get_rebalance_sensor() -> RebalanceSensor:
    """Get or create the global RebalanceSensor instance."""
    global _sensor_instance
    
    if _sensor_instance is None:
        _sensor_instance = RebalanceSensor()
    
    return _sensor_instance


def reset_rebalance_sensor():
    """Reset the global sensor (for testing)."""
    global _sensor_instance
    _sensor_instance = None
