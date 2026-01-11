"""
Recovery Manager
================
Partial fill detection and emergency rollback.

The "Medic" of the execution pipeline.
Ensures safe exit when atomic bundles partially execute.

Responsibilities:
- Detect partial fills by comparing pre/post state
- Calculate recovery paths to return to neutral
- Execute emergency exit trades
- Log and alert on recovery events
"""

from __future__ import annotations

import time
import asyncio
from typing import Optional, Any, List, Dict
from dataclasses import dataclass, field
from enum import Enum

from src.shared.system.logging import Logger
from src.shared.execution.execution_result import ExecutionResult, ExecutionStatus, ErrorCode


# ═══════════════════════════════════════════════════════════════════════════════
# POSITION STATE
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class PositionState:
    """Snapshot of current position state."""
    
    # Spot balances
    sol_balance: float = 0.0
    usdc_balance: float = 0.0
    other_tokens: Dict[str, float] = field(default_factory=dict)
    
    # Perp position
    perp_size: float = 0.0  # Positive = long, negative = short
    perp_entry_price: float = 0.0
    perp_unrealized_pnl: float = 0.0
    
    # Timestamps
    captured_at: float = field(default_factory=time.time)
    block_height: int = 0
    
    def is_neutral(self, tolerance: float = 0.01) -> bool:
        """Check if position is approximately delta-neutral."""
        # Net position = spot SOL - |perp short|
        net_exposure = self.sol_balance - abs(self.perp_size)
        return abs(net_exposure) < tolerance


class PartialFillType(Enum):
    """Type of partial fill detected."""
    SPOT_ONLY = "SPOT_ONLY"      # Spot executed, perp failed
    PERP_ONLY = "PERP_ONLY"      # Perp executed, spot failed
    NEITHER = "NEITHER"          # Both failed (not partial)
    BOTH = "BOTH"                # Both executed (not partial)


@dataclass
class PartialFillAnalysis:
    """Analysis of partial fill state."""
    
    fill_type: PartialFillType
    is_partial_fill: bool
    
    # What executed
    spot_executed: bool = False
    perp_executed: bool = False
    
    # Delta mismatch
    spot_delta: float = 0.0  # Change in spot
    perp_delta: float = 0.0  # Change in perp
    net_exposure: float = 0.0  # Current unhedged exposure
    
    # Recovery target
    recovery_needed: bool = False
    recovery_action: Optional[str] = None  # "SELL_SPOT", "CLOSE_PERP", etc.
    recovery_size: float = 0.0


@dataclass(frozen=True)
class RecoveryPath:
    """
    A calculated path back to safety.
    
    Represents the "shortest path to neutral" after a partial fill.
    """
    
    action: str  # "SELL_SPOT", "CLOSE_SHORT", "BUY_SPOT", "OPEN_SHORT"
    asset: str  # "SOL", "SOL-PERP"
    size: float  # Amount to trade
    urgency: str  # "IMMEDIATE", "SOON", "ROUTINE"
    reason: str  # Human-readable explanation
    estimated_cost_usd: float = 0.0  # Expected slippage/fees
    
    @property
    def description(self) -> str:
        return f"{self.action} {self.size:.4f} {self.asset} ({self.urgency}): {self.reason}"


# ═══════════════════════════════════════════════════════════════════════════════
# RECOVERY MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class RecoveryManager:
    """
    Manages partial fill detection and recovery.
    
    Workflow:
    1. Capture pre-trade snapshot
    2. After trade, compare to post-trade state
    3. If mismatch detected, calculate recovery path
    4. Execute recovery trades
    
    Usage:
        recovery = RecoveryManager(wallet, drift)
        await recovery.capture_pre_trade(signal)
        
        # ... execute trade ...
        
        analysis = await recovery.analyze_post_trade()
        if analysis.is_partial_fill:
            path = recovery.calculate_recovery_path(analysis)
            await recovery.execute_recovery(path)
    """
    
    # Maximum exposure before emergency recovery
    MAX_UNHEDGED_EXPOSURE_SOL = 0.5  # $75 at $150/SOL
    
    # Emergency slippage (generous to ensure fill)
    EMERGENCY_SLIPPAGE_BPS = 500  # 5%
    
    def __init__(
        self,
        wallet: Any,
        drift_adapter: Any,
        swapper: Any = None,
    ):
        """
        Initialize recovery manager.
        
        Args:
            wallet: WalletManager for balance queries
            drift_adapter: DriftAdapter for perp queries
            swapper: JupiterSwapper for emergency trades
        """
        self.wallet = wallet
        self.drift = drift_adapter
        self.swapper = swapper
        
        # Pre-trade snapshot
        self._pre_trade_state: Optional[PositionState] = None
        self._current_snapshot_key: Optional[str] = None
        
        # Statistics
        self._partials_detected = 0
        self._recoveries_executed = 0
        self._recoveries_failed = 0
    
    async def capture_pre_trade(
        self,
        signal: Any = None,
        block_height: int = 0,
    ) -> str:
        """
        Capture position state before trade.
        
        Returns snapshot key for later comparison.
        """
        state = await self._capture_current_state(block_height)
        self._pre_trade_state = state
        self._current_snapshot_key = f"snapshot_{int(time.time() * 1000)}"
        
        Logger.debug(
            f"[RecoveryManager] Pre-trade snapshot: "
            f"SOL={state.sol_balance:.4f}, Perp={state.perp_size:.4f}"
        )
        
        return self._current_snapshot_key
    
    async def _capture_current_state(self, block_height: int = 0) -> PositionState:
        """Capture current position state from chain."""
        try:
            # Get spot balances
            sol_balance = self.wallet.get_sol_balance() if hasattr(self.wallet, 'get_sol_balance') else 0.0
            usdc_balance = 0.0
            
            try:
                live_data = self.wallet.get_current_live_usd_balance()
                usdc_balance = live_data.get("breakdown", {}).get("USDC", 0.0)
            except Exception:
                pass
            
            # Get perp position
            perp_size = 0.0
            perp_entry = 0.0
            perp_pnl = 0.0
            
            try:
                if hasattr(self.drift, 'get_perp_position'):
                    pos = self.drift.get_perp_position(0)  # SOL-PERP
                    if pos:
                        perp_size = pos.get("size", 0.0)
                        perp_entry = pos.get("entry_price", 0.0)
                        perp_pnl = pos.get("unrealized_pnl", 0.0)
            except Exception:
                pass
            
            return PositionState(
                sol_balance=sol_balance,
                usdc_balance=usdc_balance,
                perp_size=perp_size,
                perp_entry_price=perp_entry,
                perp_unrealized_pnl=perp_pnl,
                block_height=block_height,
            )
            
        except Exception as e:
            Logger.error(f"[RecoveryManager] State capture failed: {e}")
            return PositionState()
    
    async def analyze_post_trade(self) -> PartialFillAnalysis:
        """
        Compare post-trade state to pre-trade snapshot.
        
        Returns analysis of what executed.
        """
        if not self._pre_trade_state:
            Logger.warning("[RecoveryManager] No pre-trade snapshot available")
            return PartialFillAnalysis(
                fill_type=PartialFillType.NEITHER,
                is_partial_fill=False,
            )
        
        post_state = await self._capture_current_state()
        pre_state = self._pre_trade_state
        
        # Calculate deltas
        spot_delta = post_state.sol_balance - pre_state.sol_balance
        perp_delta = post_state.perp_size - pre_state.perp_size
        
        # Determine what executed
        spot_executed = abs(spot_delta) > 0.001  # >0.001 SOL change
        perp_executed = abs(perp_delta) > 0.001
        
        # Classify fill type
        if spot_executed and perp_executed:
            fill_type = PartialFillType.BOTH
            is_partial = False
        elif spot_executed and not perp_executed:
            fill_type = PartialFillType.SPOT_ONLY
            is_partial = True
            self._partials_detected += 1
        elif perp_executed and not spot_executed:
            fill_type = PartialFillType.PERP_ONLY
            is_partial = True
            self._partials_detected += 1
        else:
            fill_type = PartialFillType.NEITHER
            is_partial = False
        
        # Calculate net exposure
        net_exposure = post_state.sol_balance - abs(post_state.perp_size)
        
        # Determine recovery action
        recovery_needed = is_partial and abs(net_exposure) > 0.01
        recovery_action = None
        recovery_size = 0.0
        
        if recovery_needed:
            if fill_type == PartialFillType.SPOT_ONLY:
                # Spot bought, perp failed → sell spot
                recovery_action = "SELL_SPOT"
                recovery_size = abs(spot_delta)
            else:  # PERP_ONLY
                # Perp opened, spot failed → close perp
                recovery_action = "CLOSE_PERP"
                recovery_size = abs(perp_delta)
        
        Logger.info(
            f"[RecoveryManager] Analysis: {fill_type.value}, "
            f"Spot Δ={spot_delta:+.4f}, Perp Δ={perp_delta:+.4f}, "
            f"Net exposure={net_exposure:.4f}"
        )
        
        return PartialFillAnalysis(
            fill_type=fill_type,
            is_partial_fill=is_partial,
            spot_executed=spot_executed,
            perp_executed=perp_executed,
            spot_delta=spot_delta,
            perp_delta=perp_delta,
            net_exposure=net_exposure,
            recovery_needed=recovery_needed,
            recovery_action=recovery_action,
            recovery_size=recovery_size,
        )
    
    def calculate_recovery_path(
        self,
        analysis: PartialFillAnalysis,
        sol_price: float = 150.0,
    ) -> Optional[RecoveryPath]:
        """
        Calculate the optimal recovery path.
        
        Returns None if no recovery needed.
        """
        if not analysis.recovery_needed:
            return None
        
        # Estimate cost (5% slippage + fees)
        estimated_cost = analysis.recovery_size * sol_price * 0.05
        
        if analysis.fill_type == PartialFillType.SPOT_ONLY:
            return RecoveryPath(
                action="SELL_SPOT",
                asset="SOL",
                size=analysis.recovery_size,
                urgency="IMMEDIATE",
                reason="Perp leg failed - selling spot to return to neutral",
                estimated_cost_usd=estimated_cost,
            )
        
        elif analysis.fill_type == PartialFillType.PERP_ONLY:
            # Determine if we need to close long or short
            action = "CLOSE_SHORT" if analysis.perp_delta < 0 else "CLOSE_LONG"
            
            return RecoveryPath(
                action=action,
                asset="SOL-PERP",
                size=abs(analysis.recovery_size),
                urgency="IMMEDIATE",
                reason="Spot leg failed - closing perp to return to neutral",
                estimated_cost_usd=estimated_cost,
            )
        
        return None
    
    async def execute_recovery(
        self,
        path: RecoveryPath,
        simulate: bool = False,
    ) -> ExecutionResult:
        """
        Execute recovery trade.
        
        Args:
            path: The calculated recovery path
            simulate: If True, don't actually trade
            
        Returns:
            ExecutionResult of recovery attempt
        """
        Logger.warning(f"[RecoveryManager] 🚨 EXECUTING RECOVERY: {path.description}")
        
        if simulate:
            Logger.info("[RecoveryManager] Simulation mode - no trade executed")
            return ExecutionResult(
                success=True,
                status=ExecutionStatus.SIMULATED,
            )
        
        try:
            if path.action == "SELL_SPOT" and self.swapper:
                result = self.swapper.execute_swap(
                    direction="SELL",
                    amount_usd=path.size * 150,  # Approximate
                    reason="EMERGENCY_RECOVERY",
                )
                
                if result.get("success"):
                    self._recoveries_executed += 1
                    Logger.info("[RecoveryManager] ✅ Spot recovery successful")
                    return ExecutionResult(success=True, status=ExecutionStatus.SUCCESS)
                else:
                    self._recoveries_failed += 1
                    return ExecutionResult(
                        success=False,
                        status=ExecutionStatus.FAILED,
                        error_code=ErrorCode.UNKNOWN,
                        error_message=result.get("error", "Unknown error"),
                    )
            
            elif path.action in ("CLOSE_SHORT", "CLOSE_LONG"):
                # Perp recovery via Drift
                # This requires more complex implementation
                Logger.warning("[RecoveryManager] Perp recovery requires Drift SDK")
                self._recoveries_failed += 1
                return ExecutionResult(
                    success=False,
                    status=ExecutionStatus.FAILED,
                    error_code=ErrorCode.UNKNOWN,
                    error_message="Perp recovery not yet implemented",
                )
            
            else:
                Logger.error(f"[RecoveryManager] Unknown action: {path.action}")
                return ExecutionResult(success=False, status=ExecutionStatus.FAILED)
                
        except Exception as e:
            self._recoveries_failed += 1
            Logger.error(f"[RecoveryManager] Recovery failed: {e}")
            return ExecutionResult(
                success=False,
                status=ExecutionStatus.FAILED,
                error_code=ErrorCode.UNKNOWN,
                error_message=str(e),
            )
    
    def get_stats(self) -> dict:
        """Get recovery statistics."""
        return {
            "partials_detected": self._partials_detected,
            "recoveries_executed": self._recoveries_executed,
            "recoveries_failed": self._recoveries_failed,
        }
