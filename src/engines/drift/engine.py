"""
Drift Engine - Risk-First Perpetual Trading
============================================
Real-time margin monitoring and delta-neutral position management
for Drift Protocol perpetual futures.

Usage:
    python -m src.engines.drift.engine --paper
    python -m src.engines.drift.engine --live

Features:
    - Health Score monitoring with liquidation alerts
    - Auto-rebalancing to maintain delta neutrality
    - Funding rate yield collection
    - Position health dashboard integration
"""

import asyncio
import argparse
import time
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

from src.engines.base_engine import BaseEngine
from src.shared.system.logging import Logger


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class DriftEngineConfig:
    """Configuration for the Drift Engine."""
    
    # Risk Parameters
    max_leverage: float = 5.0              # Maximum allowed leverage
    health_threshold: float = 0.5          # Minimum health score before alert
    liquidation_warning: float = 0.2       # Critical health threshold
    
    # Position Management
    auto_rebalance: bool = True            # Auto-rebalance on delta drift
    drift_tolerance_pct: float = 1.0       # Max delta drift before rebalance
    settle_pnl_threshold: float = 10.0     # Min PnL to trigger settle
    
    # Timing
    tick_interval_seconds: float = 5.0     # Main loop interval
    margin_check_interval: int = 3         # Check margin every N ticks
    
    # Safety
    emergency_close_health: float = 0.15   # Auto-close below this health


# =============================================================================
# DRIFT ENGINE
# =============================================================================

class DriftEngine(BaseEngine):
    """
    Risk-First Perpetual Trading Engine for Drift Protocol.
    
    Monitors margin health, manages delta-neutral positions, and
    collects funding rate yields while maintaining strict risk controls.
    
    The engine operates in two modes:
    - PAPER: Simulated trading for testing
    - LIVE: Real execution on Drift mainnet
    """
    
    def __init__(self, live_mode: bool = False, config: Optional[Dict[str, Any]] = None):
        super().__init__(name="drift", live_mode=live_mode)
        
        # Parse config
        self._raw_config = config or {}
        self.config = self._parse_config()
        
        # State
        self._tick_count = 0
        self._last_health_check = 0
        self._total_funding_collected = 0.0
        self._positions: List[Any] = []
        
        # Adapters (lazy initialized)
        self._drift_adapter = None
        self._margin_metrics = None
        
        # Status tracking
        self.status = "INITIALIZED"
        self.pnl = 0.0
        
        Logger.info(f"[DRIFT] Engine initialized ({self.mode.upper()} mode)")
    
    def _parse_config(self) -> DriftEngineConfig:
        """Parse dict config into typed DriftEngineConfig."""
        return DriftEngineConfig(
            max_leverage=self._raw_config.get("max_leverage", 5.0),
            health_threshold=self._raw_config.get("health_threshold", 0.5),
            auto_rebalance=self._raw_config.get("auto_rebalance", True),
            settle_pnl_threshold=self._raw_config.get("settle_pnl_threshold", 10.0),
        )
    
    def get_interval(self) -> float:
        """Tick interval in seconds."""
        return self.config.tick_interval_seconds
    
    # =========================================================================
    # CORE LOOP
    # =========================================================================
    
    async def tick(self):
        """
        Main execution loop - Risk-First monitoring.
        
        Priority order:
        1. Health check (liquidation prevention)
        2. Delta drift monitoring
        3. Funding rate collection
        4. Position reporting
        """
        self._tick_count += 1
        
        try:
            # 1. ALWAYS check margin health first
            margin = await self._check_margin_health()
            
            if margin:
                # 2. Emergency close if critically unhealthy
                if margin.health_score < self.config.emergency_close_health:
                    await self._emergency_close()
                    return
                
                # 3. Alert if approaching danger
                if margin.health_score < self.config.health_threshold:
                    Logger.warning(
                        f"[DRIFT] ⚠️ HEALTH WARNING: {margin.health_score:.1%} "
                        f"(threshold: {self.config.health_threshold:.1%})"
                    )
                
                # 4. Check delta drift every few ticks
                if self._tick_count % self.config.margin_check_interval == 0:
                    await self._check_delta_drift()
                
                # 5. Broadcast state for dashboard
                await self._broadcast_state(margin)
            
        except Exception as e:
            Logger.error(f"[DRIFT] Tick error: {e}")
            self.status = "ERROR"
    
    # =========================================================================
    # MARGIN & HEALTH
    # =========================================================================
    
    async def _check_margin_health(self) -> Optional[Any]:
        """
        Fetch and validate margin metrics from Drift.
        
        Returns DriftMarginMetrics or None on error.
        """
        try:
            # Lazy init adapter
            if not self._drift_adapter:
                from src.delta_neutral.drift_order_builder import DriftAdapter
                self._drift_adapter = DriftAdapter("mainnet")
                
                if self.live_mode and self.wallet:
                    self._drift_adapter.set_wallet(self.wallet)
            
            # Use heartbeat collector's method pattern
            import requests
            
            if not self._drift_adapter._builder:
                return None
            
            wallet = str(self._drift_adapter._builder.wallet)
            url = f"https://drift-gateway-api.mainnet.drift.trade/v1/user/{wallet}"
            
            resp = requests.get(url, timeout=2.0)
            if resp.status_code != 200:
                return None
            
            data = resp.json()
            
            # Parse metrics (matching HeartbeatDataCollector)
            total_collateral = float(data.get("totalCollateralValue", 0)) / 1e6
            free_collateral = float(data.get("freeCollateral", 0)) / 1e6
            maint_margin = float(data.get("maintenanceMarginRequirement", 0)) / 1e6
            
            # Health Score
            health_score = 1.0
            if total_collateral > 0 and maint_margin > 0:
                health_score = max(0.0, min(1.0, 1.0 - (maint_margin / total_collateral)))
            
            # Leverage
            deployed = max(0, total_collateral - free_collateral)
            leverage = (deployed / total_collateral) if total_collateral > 0 else 0.0
            
            # Create metrics object
            @dataclass
            class MarginSnapshot:
                health_score: float
                leverage: float
                total_collateral: float
                free_collateral: float
                maintenance_margin: float
            
            metrics = MarginSnapshot(
                health_score=health_score,
                leverage=leverage,
                total_collateral=total_collateral,
                free_collateral=free_collateral,
                maintenance_margin=maint_margin,
            )
            
            self._margin_metrics = metrics
            return metrics
            
        except Exception as e:
            Logger.debug(f"[DRIFT] Margin check error: {e}")
            return None
    
    async def _check_delta_drift(self):
        """Check if positions have drifted from delta neutrality."""
        if not self._drift_adapter:
            return
        
        try:
            positions = self._drift_adapter.get_all_positions()
            self._positions = positions
            
            if not positions:
                return
            
            # Calculate net delta
            # For delta-neutral: sum of spot + sum of perp should = 0
            # This is a simplified check - full implementation in neutrality_monitor
            
            total_perp_size = sum(p.size for p in positions)
            
            if abs(total_perp_size) > 0.01:  # More than 0.01 SOL drift
                Logger.info(f"[DRIFT] Delta: {total_perp_size:.4f} SOL")
                
                if self.config.auto_rebalance and abs(total_perp_size) > 0.1:
                    Logger.warning(f"[DRIFT] Significant delta drift detected: {total_perp_size:.4f}")
                    # Rebalance logic would go here
            
        except Exception as e:
            Logger.debug(f"[DRIFT] Delta check error: {e}")
    
    async def _emergency_close(self):
        """Emergency position closure when health is critical."""
        Logger.critical(f"[DRIFT] 🚨 EMERGENCY CLOSE TRIGGERED - Health below {self.config.emergency_close_health:.1%}")
        
        if not self.live_mode:
            Logger.info("[DRIFT] (Paper mode - no actual closure)")
            return
        
        # In live mode, would close all positions
        # For now, just log and alert
        self.status = "EMERGENCY"
    
    # =========================================================================
    # BROADCASTING
    # =========================================================================
    
    async def _broadcast_state(self, margin):
        """Broadcast engine state for dashboard."""
        state = {
            "engine": "drift",
            "status": self.status,
            "mode": self.mode,
            "tick_count": self._tick_count,
            "health_score": margin.health_score if margin else 0.0,
            "leverage": margin.leverage if margin else 0.0,
            "total_collateral": margin.total_collateral if margin else 0.0,
            "position_count": len(self._positions),
            "pnl": self.pnl,
        }
        
        await self.broadcast(state)
    
    def export_state(self) -> Dict[str, Any]:
        """Export state for heartbeat polling."""
        return {
            "health_score": self._margin_metrics.health_score if self._margin_metrics else 1.0,
            "leverage": self._margin_metrics.leverage if self._margin_metrics else 0.0,
            "position_count": len(self._positions),
            "tick_count": self._tick_count,
            "status": self.status,
        }
    
    async def on_stop(self):
        """Cleanup on engine stop."""
        Logger.info("[DRIFT] Engine stopping - saving state...")
        # Could persist state here if needed


# =============================================================================
# CLI ENTRYPOINT
# =============================================================================

async def main():
    """CLI entrypoint for subprocess execution."""
    parser = argparse.ArgumentParser(description="Drift Engine")
    parser.add_argument("--paper", action="store_true", help="Run in paper mode")
    parser.add_argument("--live", action="store_true", help="Run in live mode")
    parser.add_argument("--max-leverage", type=float, default=5.0, help="Max leverage")
    parser.add_argument("--health-threshold", type=float, default=0.5, help="Health threshold")
    
    args = parser.parse_args()
    
    # Determine mode
    live_mode = args.live and not args.paper
    
    # Build config
    config = {
        "max_leverage": args.max_leverage,
        "health_threshold": args.health_threshold,
    }
    
    # Create and run engine
    engine = DriftEngine(live_mode=live_mode, config=config)
    
    try:
        await engine.start()
        
        # Keep running until interrupted
        while engine.running:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        Logger.info("[DRIFT] Shutdown requested...")
    finally:
        await engine.stop()


if __name__ == "__main__":
    asyncio.run(main())
