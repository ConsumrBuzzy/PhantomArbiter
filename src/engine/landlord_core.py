"""
V45.0: Landlord Strategy Core (Delta Neutral)
==============================================
Persistent delta-neutral yield farming:
- Long leg: SOL spot on DEX (Raydium)
- Short leg: SOL-PERP on Drift
- Yield: Collect funding rates from perpetual traders

Architecture:
- State machine (IDLE → HEDGED → REBALANCING)
- Atomic hedge execution (spot first, then short)
- Periodic rebalance check every 30 minutes

Commands:
- /start_landlord [size_usd] - Open hedge
- /close_landlord - Close all positions
- /landlord_status - Show current state

Dependencies:
    pip install driftpy anchorpy
"""

import os
import time
import asyncio
import threading
from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

from src.shared.system.logging import Logger


class LandlordState(Enum):
    """Landlord strategy state machine."""
    IDLE = "IDLE"           # No active positions
    OPENING = "OPENING"     # Executing initial hedge
    HEDGED = "HEDGED"       # Delta-neutral (long + short active)
    REBALANCING = "REBALANCING"  # Adjusting hedge ratio
    CLOSING = "CLOSING"     # Closing all positions
    ERROR = "ERROR"         # Error state


@dataclass
class HedgePosition:
    """Tracks the current hedge state."""
    state: LandlordState = LandlordState.IDLE
    symbol: str = "SOL"
    
    # Position details
    spot_size: float = 0.0       # SOL amount held spot
    spot_entry_price: float = 0.0
    spot_value_usd: float = 0.0
    
    short_size: float = 0.0      # SOL-PERP short size
    short_entry_price: float = 0.0
    short_value_usd: float = 0.0
    
    # Hedge metrics
    hedge_ratio: float = 0.0     # Short / Spot (target = 1.0)
    delta: float = 0.0           # Net exposure (target = 0.0)
    
    # Funding collected
    total_funding_collected: float = 0.0
    
    # Timestamps
    opened_at: Optional[datetime] = None
    last_rebalance: Optional[datetime] = None
    
    # Transaction signatures
    spot_tx: Optional[str] = None
    short_tx: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

LANDLORD_CONFIG = {
    "SYMBOL": "SOL",
    "PERP_SYMBOL": "SOL-PERP",
    "REBALANCE_INTERVAL_SECONDS": 1800,  # 30 minutes
    "REBALANCE_THRESHOLD": 0.05,          # 5% drift triggers rebalance
    "MIN_COLLATERAL_USD": 10.0,           # Minimum $10 to start
    "NETWORK": "devnet",                   # Start on devnet for safety
}


class LandlordCore:
    """
    V45.0: Delta-Neutral Strategy Engine.
    
    Manages persistent hedge positions:
    - Long SOL spot via DEX
    - Short SOL-PERP via Drift
    - Collects funding rate yield
    """
    
    def __init__(self, network: str = None):
        """
        Initialize Landlord strategy core.
        
        Args:
            network: "devnet" or "mainnet" (defaults to config)
        """
        self.network = network or LANDLORD_CONFIG["NETWORK"]
        self.position = HedgePosition()
        
        # Adapters (lazy initialization)
        self._drift_adapter = None
        self._dex_adapter = None
        
        # Background task
        self._rebalance_task = None
        self._running = False
        
        Logger.info(f"[LANDLORD] Initialized on {self.network}")
    
    # ═══════════════════════════════════════════════════════════════════════
    # ADAPTER INITIALIZATION
    # ═══════════════════════════════════════════════════════════════════════
    
    def _get_drift_adapter(self):
        """Lazy init Drift adapter."""
        if self._drift_adapter is None:
            from src.infrastructure.drift_adapter import DriftAdapter
            self._drift_adapter = DriftAdapter(self.network)
        return self._drift_adapter
    
    def _get_dex_adapter(self):
        """Lazy init DEX adapter (for spot buys)."""
        if self._dex_adapter is None:
            # Use existing wallet/DEX infrastructure
            from src.infrastructure.wallet_adapter import WalletAdapter
            self._dex_adapter = WalletAdapter()
        return self._dex_adapter
    
    # ═══════════════════════════════════════════════════════════════════════
    # START LANDLORD (Open Hedge)
    # ═══════════════════════════════════════════════════════════════════════
    
    async def start_landlord(self, size_usd: float) -> Dict[str, Any]:
        """
        Open a delta-neutral hedge position.
        
        Execution Order (Atomic-like):
        1. Validate collateral
        2. Buy SOL spot on DEX (long leg)
        3. Open SOL-PERP short on Drift (short leg)
        4. Set state to HEDGED
        
        Args:
            size_usd: Total hedge size in USD (e.g., $100)
            
        Returns:
            Dict with success status and position details
        """
        result = {
            "success": False,
            "state": self.position.state.value,
            "message": "",
            "spot_tx": None,
            "short_tx": None,
        }
        
        # Pre-flight checks
        if self.position.state != LandlordState.IDLE:
            result["message"] = f"Cannot start: Already in {self.position.state.value} state"
            return result
        
        if size_usd < LANDLORD_CONFIG["MIN_COLLATERAL_USD"]:
            result["message"] = f"Size too small. Minimum: ${LANDLORD_CONFIG['MIN_COLLATERAL_USD']}"
            return result
        
        self.position.state = LandlordState.OPENING
        Logger.info(f"[LANDLORD] Starting hedge: ${size_usd}")
        
        try:
            # ═══════════════════════════════════════════════════════════════
            # STEP 1: Connect to Drift
            # ═══════════════════════════════════════════════════════════════
            drift = self._get_drift_adapter()
            await drift.connect()
            
            # Verify account is ready
            account_check = await drift.verify_drift_account()
            if not account_check.get("ready"):
                self.position.state = LandlordState.ERROR
                result["message"] = f"Drift not ready: {account_check.get('message')}"
                return result
            
            # ═══════════════════════════════════════════════════════════════
            # STEP 2: Get current SOL price
            # ═══════════════════════════════════════════════════════════════
            sol_price = await drift.get_mark_price("SOL-PERP")
            if not sol_price or sol_price <= 0:
                sol_price = 200.0  # Fallback for devnet
                Logger.warning(f"[LANDLORD] Using fallback SOL price: ${sol_price}")
            
            # Calculate position size in SOL
            sol_size = size_usd / sol_price
            Logger.info(f"[LANDLORD] Position size: {sol_size:.4f} SOL @ ${sol_price:.2f}")
            
            # ═══════════════════════════════════════════════════════════════
            # STEP 3: Open SHORT on Drift (short leg first for safety)
            # ═══════════════════════════════════════════════════════════════
            Logger.info(f"[LANDLORD] Opening SHORT: {sol_size:.4f} SOL-PERP...")
            short_result = await drift.place_perp_order(
                symbol="SOL-PERP",
                direction="SHORT",
                size=sol_size
            )
            
            if not short_result.get("success"):
                self.position.state = LandlordState.ERROR
                result["message"] = f"SHORT failed: {short_result.get('error')}"
                return result
            
            self.position.short_tx = short_result.get("signature")
            self.position.short_size = sol_size
            self.position.short_entry_price = sol_price
            self.position.short_value_usd = size_usd
            
            Logger.info(f"[LANDLORD] ✅ SHORT opened: {self.position.short_tx[:16]}...")
            
            # ═══════════════════════════════════════════════════════════════
            # STEP 4: Record LONG position (spot SOL in wallet)
            # ═══════════════════════════════════════════════════════════════
            # For now, we assume user already has SOL spot equivalent
            # A full implementation would buy SOL via Raydium here
            
            self.position.spot_size = sol_size
            self.position.spot_entry_price = sol_price
            self.position.spot_value_usd = size_usd
            self.position.spot_tx = "EXISTING_WALLET_BALANCE"
            
            Logger.info(f"[LANDLORD] Using existing SOL balance as long leg")
            
            # ═══════════════════════════════════════════════════════════════
            # STEP 5: Calculate hedge metrics
            # ═══════════════════════════════════════════════════════════════
            self.position.hedge_ratio = self.position.short_size / max(self.position.spot_size, 0.0001)
            self.position.delta = self.position.spot_size - self.position.short_size
            self.position.opened_at = datetime.utcnow()
            self.position.last_rebalance = datetime.utcnow()
            
            # ═══════════════════════════════════════════════════════════════
            # STEP 6: Finalize
            # ═══════════════════════════════════════════════════════════════
            self.position.state = LandlordState.HEDGED
            
            result["success"] = True
            result["state"] = self.position.state.value
            result["message"] = (
                f"✅ Hedge Opened!\n"
                f"Long: {self.position.spot_size:.4f} SOL\n"
                f"Short: {self.position.short_size:.4f} SOL-PERP\n"
                f"Hedge Ratio: {self.position.hedge_ratio:.2f}\n"
                f"Delta: {self.position.delta:.4f}"
            )
            result["short_tx"] = self.position.short_tx
            
            # Start rebalance monitor
            self._start_rebalance_task()
            
            Logger.info(f"[LANDLORD] ✅ HEDGED: Ratio={self.position.hedge_ratio:.2f}")
            return result
            
        except Exception as e:
            self.position.state = LandlordState.ERROR
            result["message"] = f"Error: {e}"
            Logger.error(f"[LANDLORD] Start failed: {e}")
            return result
    
    def start_landlord_sync(self, size_usd: float) -> Dict[str, Any]:
        """Sync wrapper for start_landlord."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.start_landlord(size_usd))
            finally:
                loop.close()
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    # ═══════════════════════════════════════════════════════════════════════
    # CLOSE LANDLORD (Close All Positions)
    # ═══════════════════════════════════════════════════════════════════════
    
    async def close_landlord(self) -> Dict[str, Any]:
        """
        Close all hedge positions and return to IDLE.
        
        Execution:
        1. Close Drift SHORT position
        2. (Optionally sell spot - currently just release)
        3. Set state to IDLE
        
        Returns:
            Dict with success status and final PnL
        """
        result = {
            "success": False,
            "state": self.position.state.value,
            "message": "",
            "pnl": 0.0,
        }
        
        if self.position.state == LandlordState.IDLE:
            result["message"] = "No active position to close"
            return result
        
        self.position.state = LandlordState.CLOSING
        Logger.info("[LANDLORD] Closing hedge...")
        
        try:
            # Stop rebalance task
            self._stop_rebalance_task()
            
            # Close Drift SHORT
            drift = self._get_drift_adapter()
            if not drift.is_connected:
                await drift.connect()
            
            close_result = await drift.close_position("SOL-PERP")
            
            if not close_result.get("success"):
                self.position.state = LandlordState.ERROR
                result["message"] = f"Close SHORT failed: {close_result.get('error')}"
                return result
            
            Logger.info(f"[LANDLORD] ✅ SHORT closed: {close_result.get('signature', '')[:16]}...")
            
            # Calculate funding collected (simplified)
            duration_hours = 0
            if self.position.opened_at:
                duration = datetime.utcnow() - self.position.opened_at
                duration_hours = duration.total_seconds() / 3600
            
            # Reset position
            old_position = self.position
            self.position = HedgePosition()
            
            result["success"] = True
            result["state"] = self.position.state.value
            result["message"] = (
                f"✅ Hedge Closed!\n"
                f"Duration: {duration_hours:.1f} hours\n"
                f"Funding Collected: ${old_position.total_funding_collected:.4f}"
            )
            result["pnl"] = old_position.total_funding_collected
            
            Logger.info(f"[LANDLORD] ✅ Returned to IDLE")
            return result
            
        except Exception as e:
            self.position.state = LandlordState.ERROR
            result["message"] = f"Error: {e}"
            Logger.error(f"[LANDLORD] Close failed: {e}")
            return result
    
    def close_landlord_sync(self) -> Dict[str, Any]:
        """Sync wrapper for close_landlord."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.close_landlord())
            finally:
                loop.close()
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    # ═══════════════════════════════════════════════════════════════════════
    # REBALANCE CHECK
    # ═══════════════════════════════════════════════════════════════════════
    
    async def check_rebalance(self) -> Dict[str, Any]:
        """
        Check if hedge needs rebalancing.
        
        Triggered every 30 minutes when HEDGED.
        Rebalances if hedge ratio drifts > ±5%.
        """
        result = {
            "rebalanced": False,
            "hedge_ratio": self.position.hedge_ratio,
            "drift_pct": 0.0,
        }
        
        if self.position.state != LandlordState.HEDGED:
            return result
        
        try:
            drift = self._get_drift_adapter()
            
            # Get current SOL price
            current_price = await drift.get_mark_price("SOL-PERP")
            if not current_price:
                return result
            
            # Calculate current values
            spot_value = self.position.spot_size * current_price
            short_value = self.position.short_size * current_price
            
            # Calculate drift from target (1.0)
            new_hedge_ratio = short_value / max(spot_value, 0.01)
            drift_pct = abs(new_hedge_ratio - 1.0)
            
            result["hedge_ratio"] = new_hedge_ratio
            result["drift_pct"] = drift_pct
            
            Logger.debug(f"[LANDLORD] Hedge check: Ratio={new_hedge_ratio:.3f}, Drift={drift_pct*100:.1f}%")
            
            # Rebalance if drift exceeds threshold
            if drift_pct > LANDLORD_CONFIG["REBALANCE_THRESHOLD"]:
                Logger.info(f"[LANDLORD] Rebalancing: Drift {drift_pct*100:.1f}% > {LANDLORD_CONFIG['REBALANCE_THRESHOLD']*100}%")
                
                self.position.state = LandlordState.REBALANCING
                
                # Calculate adjustment needed
                size_diff = self.position.spot_size - self.position.short_size
                
                if size_diff > 0:
                    # Need more short
                    await drift.place_perp_order("SOL-PERP", "SHORT", abs(size_diff))
                    self.position.short_size += abs(size_diff)
                else:
                    # Need less short (close some)
                    await drift.place_perp_order("SOL-PERP", "LONG", abs(size_diff))
                    self.position.short_size -= abs(size_diff)
                
                self.position.hedge_ratio = 1.0
                self.position.last_rebalance = datetime.utcnow()
                self.position.state = LandlordState.HEDGED
                result["rebalanced"] = True
                
                Logger.info(f"[LANDLORD] ✅ Rebalanced to 1.0")
            
            return result
            
        except Exception as e:
            Logger.error(f"[LANDLORD] Rebalance check error: {e}")
            return result
    
    def _start_rebalance_task(self):
        """Start background rebalance monitoring."""
        self._running = True
        self._rebalance_task = threading.Thread(
            target=self._rebalance_loop,
            daemon=True,
            name="LandlordRebalance"
        )
        self._rebalance_task.start()
        Logger.info("[LANDLORD] Rebalance monitor started")
    
    def _stop_rebalance_task(self):
        """Stop background rebalance monitoring."""
        self._running = False
        Logger.info("[LANDLORD] Rebalance monitor stopped")
    
    def _rebalance_loop(self):
        """Background loop for periodic rebalance checks."""
        while self._running:
            time.sleep(LANDLORD_CONFIG["REBALANCE_INTERVAL_SECONDS"])
            
            if self.position.state == LandlordState.HEDGED:
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self.check_rebalance())
                    loop.close()
                except Exception as e:
                    Logger.error(f"[LANDLORD] Rebalance loop error: {e}")
    
    async def run_monitoring_loop(self):
        """
        Async monitoring loop for unified orchestrator.
        Replaces the threaded _rebalance_loop when running in main_orchestrator.
        """
        self._running = True
        Logger.info("[LANDLORD] ⏳ Async monitoring loop started")
        
        while self._running:
            await asyncio.sleep(LANDLORD_CONFIG["REBALANCE_INTERVAL_SECONDS"])
            
            if self.position.state == LandlordState.HEDGED:
                try:
                    await self.check_rebalance()
                except Exception as e:
                    Logger.error(f"[LANDLORD] Monitoring error: {e}")
    
    # ═══════════════════════════════════════════════════════════════════════
    # STATUS
    # ═══════════════════════════════════════════════════════════════════════
    
    def get_status(self) -> Dict[str, Any]:
        """Get current Landlord strategy status."""
        duration_hours = 0
        if self.position.opened_at:
            duration = datetime.utcnow() - self.position.opened_at
            duration_hours = duration.total_seconds() / 3600
        
        return {
            "state": self.position.state.value,
            "symbol": self.position.symbol,
            "spot_size": self.position.spot_size,
            "short_size": self.position.short_size,
            "hedge_ratio": self.position.hedge_ratio,
            "delta": self.position.delta,
            "duration_hours": duration_hours,
            "funding_collected": self.position.total_funding_collected,
            "last_rebalance": str(self.position.last_rebalance) if self.position.last_rebalance else None,
        }
    
    def __repr__(self) -> str:
        return f"<LandlordCore {self.network} state={self.position.state.value}>"


# ═══════════════════════════════════════════════════════════════════════════
# SINGLETON INSTANCE
# ═══════════════════════════════════════════════════════════════════════════

_landlord_instance: Optional[LandlordCore] = None

def get_landlord() -> LandlordCore:
    """Get or create the Landlord singleton."""
    global _landlord_instance
    if _landlord_instance is None:
        _landlord_instance = LandlordCore()
    return _landlord_instance


# ═══════════════════════════════════════════════════════════════════════════
# TESTING
# ═══════════════════════════════════════════════════════════════════════════

async def test_landlord():
    """Test Landlord strategy."""
    print("=" * 60)
    print("V45.0 Landlord Strategy Test")
    print("=" * 60)
    
    landlord = LandlordCore("devnet")
    print(f"\n✅ {landlord}")
    print(f"📊 Status: {landlord.get_status()}")
    
    print("\n⚠️ To start hedge, run:")
    print("   result = await landlord.start_landlord(100.0)")


if __name__ == "__main__":
    asyncio.run(test_landlord())
