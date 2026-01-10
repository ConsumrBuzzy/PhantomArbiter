"""
Funding Rate Engine - Cartridge Implementation
===============================================
Delta-neutral yield farming strategy via Drift funding rates.

Implements the BaseStrategy interface for integration with the
Command Center orchestrator.

Strategy Logic:
    1. Hold spot SOL (long exposure)
    2. Short SOL-PERP on Drift (hedge)
    3. Collect positive funding when shorts pay longs
    4. Auto-rebalance when delta drifts beyond tolerance
"""

import asyncio
from typing import Dict, Any, Optional
from dataclasses import dataclass

from src.shared.base_strategy import (
    BaseStrategy, 
    Decision, 
    TradingSignal, 
    OrderUpdate, 
    OrderStatus
)
from src.shared.system.persistence import get_db, Position, Trade
from src.shared.system.logging import Logger


@dataclass
class FundingConfig:
    """Configuration for the Funding Rate Engine."""
    leverage: float = 2.0
    watchdog_threshold: float = -0.0005  # -0.05% funding = close position
    drift_tolerance_pct: float = 1.0  # Rebalance when delta drifts > 1%
    cooldown_seconds: int = 1800  # 30 min between rebalances
    max_position_usd: float = 500.0
    min_trade_size: float = 0.005  # Min SOL
    loop_interval_seconds: int = 60
    rebalance_enabled: bool = True


class FundingCartridge(BaseStrategy):
    """
    Funding Rate Engine - Delta-Neutral Yield Strategy.
    
    Collects funding payments from Drift perp shorts while maintaining
    a hedged position with spot SOL.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(engine_name="funding", config=config or {})
        
        # Parse config into typed object
        self.funding_config = self._parse_config()
        
        # State
        self.spot_balance: float = 0.0
        self.perp_position: float = 0.0
        self.current_funding_rate: float = 0.0
        self.last_rebalance_time: float = 0.0
        self.accumulated_funding: float = 0.0
        
        # Connections (initialized in initialize())
        self._drift_client = None
        self._rpc_client = None
    
    def _parse_config(self) -> FundingConfig:
        """Parse dict config into typed FundingConfig."""
        return FundingConfig(
            leverage=self.config.get("leverage", 2.0),
            watchdog_threshold=self.config.get("watchdog_threshold", -0.0005),
            drift_tolerance_pct=self.config.get("drift_tolerance_pct", 1.0),
            cooldown_seconds=self.config.get("cooldown_seconds", 1800),
            max_position_usd=self.config.get("max_position_usd", 500.0),
            min_trade_size=self.config.get("min_trade_size", 0.005),
            loop_interval_seconds=self.config.get("loop_interval_seconds", 60),
            rebalance_enabled=self.config.get("rebalance_enabled", True)
        )
    
    # ═══════════════════════════════════════════════════════════════
    # LIFECYCLE METHODS (Required by BaseStrategy)
    # ═══════════════════════════════════════════════════════════════
    
    async def initialize(self) -> bool:
        """
        Initialize the Funding engine.
        
        - Recover state from SQLite
        - Connect to Drift
        - Validate current positions
        """
        self.log("INFO", "Initializing Funding Rate Engine...")
        
        db = get_db()
        
        # 1. Load saved state
        await self.load_state()
        
        # 2. Recover open positions from DB
        positions = db.get_positions_by_engine(self.engine_name)
        for pos in positions:
            self.positions[pos.symbol] = {
                "side": pos.side,
                "size": pos.size,
                "entry_price": pos.entry_price
            }
            self.log("INFO", f"Recovered position: {pos.symbol} {pos.side} {pos.size}")
        
        # 3. Initialize Drift connection
        try:
            # Note: In production, this would connect to actual Drift client
            # For now, we just validate the config
            self.log("INFO", f"Config: leverage={self.funding_config.leverage}x, "
                           f"watchdog={self.funding_config.watchdog_threshold}")
            
        except Exception as e:
            self.log("ERROR", f"Failed to initialize Drift: {e}")
            return False
        
        # 4. Get current funding rate
        await self._fetch_funding_rate()
        
        self.log("INFO", f"Funding engine initialized. Current rate: {self.current_funding_rate:.4%}")
        return True
    
    async def get_decision(self, market_data: Dict[str, Any]) -> Decision:
        """
        Analyze market data and decide on action.
        
        Decision Logic:
            1. Check if funding rate is profitable
            2. Check if position needs rebalancing
            3. Check watchdog threshold (emergency exit)
        
        Args:
            market_data: Dict with sol_price, funding_rate, spot_balance, perp_position
        """
        # Extract market data
        sol_price = market_data.get("sol_price", 0.0)
        funding_rate = market_data.get("funding_rate", self.current_funding_rate)
        self.current_funding_rate = funding_rate
        
        # Update balances from market data
        if "spot_balance" in market_data:
            self.spot_balance = market_data["spot_balance"]
        if "perp_position" in market_data:
            self.perp_position = market_data["perp_position"]
        
        # === WATCHDOG CHECK ===
        # If funding goes very negative, close position
        if funding_rate < self.funding_config.watchdog_threshold:
            self.log("WARNING", f"🚨 Watchdog triggered! Funding rate {funding_rate:.4%} < threshold")
            
            db = get_db()
            db.log_signal(
                engine=self.engine_name,
                signal_type="WATCHDOG_TRIGGER",
                symbol="SOL-PERP",
                direction="close",
                confidence=1.0,
                reason=f"Funding rate {funding_rate:.4%} below threshold {self.funding_config.watchdog_threshold:.4%}"
            )
            
            return Decision(
                signal=TradingSignal.CLOSE,
                symbol="SOL-PERP",
                size=abs(self.perp_position),
                confidence=1.0,
                reason="Watchdog: Funding rate below threshold"
            )
        
        # === DELTA REBALANCE CHECK ===
        if self.funding_config.rebalance_enabled:
            delta = self._calculate_delta()
            
            if abs(delta) > self.funding_config.drift_tolerance_pct:
                # Check cooldown
                import time
                if time.time() - self.last_rebalance_time < self.funding_config.cooldown_seconds:
                    self.log("DEBUG", f"Rebalance needed but cooling down ({delta:.2f}% drift)")
                else:
                    return self._create_rebalance_decision(delta, sol_price)
        
        # === NO ACTION NEEDED ===
        return Decision(
            signal=TradingSignal.HOLD,
            symbol="SOL-PERP",
            confidence=0.5,
            reason=f"Funding rate {funding_rate:.4%} - collecting yield"
        )
    
    async def on_order_update(self, update: OrderUpdate) -> None:
        """
        Handle order fill/reject notifications.
        
        Updates internal state and persists to database.
        """
        db = get_db()
        
        if update.status == OrderStatus.FILLED:
            self.log("INFO", f"✅ Order filled: {update.side} {update.filled_size} @ {update.filled_price}")
            
            # Update internal position
            if update.side == "buy":
                self.perp_position += update.filled_size
            else:
                self.perp_position -= update.filled_size
            
            # Log trade to DB
            trade = Trade(
                engine=self.engine_name,
                symbol=update.symbol,
                side=update.side,
                size=update.filled_size,
                price=update.filled_price,
                fee=update.fee,
                status="filled",
                order_id=update.order_id,
                tx_signature=update.tx_signature,
                executed_at=update.timestamp
            )
            db.log_trade(trade)
            
            # Update position in DB
            position = Position(
                engine=self.engine_name,
                symbol=update.symbol,
                side="short" if self.perp_position < 0 else "long",
                size=abs(self.perp_position),
                entry_price=update.filled_price if abs(self.perp_position) == update.filled_size else 0,
                current_price=update.filled_price
            )
            db.upsert_position(position)
            
            # Update last rebalance time
            import time
            self.last_rebalance_time = time.time()
            
        elif update.status == OrderStatus.REJECTED:
            self.log("ERROR", f"❌ Order rejected: {update.error_msg}")
            
            db.log_signal(
                engine=self.engine_name,
                signal_type="ORDER_REJECTED",
                symbol=update.symbol,
                reason=update.error_msg
            )
            
        elif update.status == OrderStatus.CANCELLED:
            self.log("WARNING", f"Order cancelled: {update.order_id}")
    
    # ═══════════════════════════════════════════════════════════════
    # OPTIONAL HOOKS
    # ═══════════════════════════════════════════════════════════════
    
    async def on_heartbeat(self) -> Dict[str, Any]:
        """Return health metrics for monitoring."""
        return {
            "engine": self.engine_name,
            "is_running": self.is_running,
            "uptime": self.uptime,
            "spot_balance": self.spot_balance,
            "perp_position": self.perp_position,
            "funding_rate": self.current_funding_rate,
            "accumulated_funding": self.accumulated_funding,
            "delta_pct": self._calculate_delta(),
            "config": {
                "leverage": self.funding_config.leverage,
                "watchdog": self.funding_config.watchdog_threshold
            }
        }
    
    async def shutdown(self) -> None:
        """Graceful shutdown - save state."""
        self.log("INFO", "Shutting down Funding engine...")
        
        # Save final state
        await self.save_state()
        
        # Close connections
        if self._drift_client:
            # self._drift_client.close()
            pass
        
        await super().shutdown()
    
    # ═══════════════════════════════════════════════════════════════
    # PRIVATE HELPERS
    # ═══════════════════════════════════════════════════════════════
    
    def _calculate_delta(self) -> float:
        """Calculate delta drift percentage between spot and perp."""
        if self.spot_balance == 0:
            return 0.0
        
        # Ideal: spot = -perp (fully hedged)
        # Positive perp_position means we're long (unusual in this strategy)
        # Negative perp_position means we're short (expected)
        expected_hedge = self.spot_balance
        actual_hedge = abs(self.perp_position)
        
        if expected_hedge == 0:
            return 0.0
        
        delta_pct = ((actual_hedge - expected_hedge) / expected_hedge) * 100
        return delta_pct
    
    def _create_rebalance_decision(self, delta: float, sol_price: float) -> Decision:
        """Create a rebalance decision based on delta drift."""
        db = get_db()
        
        # Positive delta = overhedged, need to reduce short
        # Negative delta = underhedged, need to increase short
        if delta > 0:
            action = TradingSignal.BUY  # Reduce short position
            size = (delta / 100) * self.spot_balance
            side = "buy"
        else:
            action = TradingSignal.SELL  # Increase short position
            size = (abs(delta) / 100) * self.spot_balance
            side = "sell"
        
        # Clamp to min trade size
        if size < self.funding_config.min_trade_size:
            return Decision(
                signal=TradingSignal.HOLD,
                reason=f"Rebalance size {size:.4f} below minimum"
            )
        
        self.log("INFO", f"📊 Rebalance: {side.upper()} {size:.4f} SOL (delta: {delta:.2f}%)")
        
        db.log_signal(
            engine=self.engine_name,
            signal_type="REBALANCE",
            symbol="SOL-PERP",
            direction=side,
            confidence=0.8,
            reason=f"Delta drift {delta:.2f}%"
        )
        
        return Decision(
            signal=action,
            symbol="SOL-PERP",
            size=size,
            confidence=0.8,
            reason=f"Rebalance: delta drift {delta:.2f}%"
        )
    
    async def _fetch_funding_rate(self) -> None:
        """Fetch current funding rate from Drift."""
        # In production, this would call Drift API
        # For now, return a simulated rate
        import random
        self.current_funding_rate = random.uniform(-0.0002, 0.0008)


# ═══════════════════════════════════════════════════════════════
# CLI ENTRYPOINT (for subprocess execution)
# ═══════════════════════════════════════════════════════════════

async def main():
    """Standalone execution for testing."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Funding Rate Engine")
    parser.add_argument("--leverage", type=float, default=2.0, help="Leverage multiplier")
    parser.add_argument("--watchdog", type=float, default=-0.0005, help="Watchdog threshold")
    parser.add_argument("--simulate", action="store_true", help="Run in simulation mode")
    args = parser.parse_args()
    
    config = {
        "leverage": args.leverage,
        "watchdog_threshold": args.watchdog
    }
    
    cartridge = FundingCartridge(config)
    
    if not await cartridge.start():
        Logger.error("Failed to start Funding cartridge")
        return
    
    Logger.info(f"Funding Cartridge running (simulate={args.simulate})")
    
    # Main loop
    try:
        while cartridge.is_running:
            # Simulate market data
            market_data = {
                "sol_price": 150.0,
                "funding_rate": 0.0003,
                "spot_balance": 10.0,
                "perp_position": -9.8
            }
            
            decision = await cartridge.get_decision(market_data)
            
            if decision.is_actionable:
                Logger.info(f"Decision: {decision.signal.value} {decision.size:.4f} - {decision.reason}")
            
            await asyncio.sleep(cartridge.funding_config.loop_interval_seconds)
            
    except KeyboardInterrupt:
        Logger.info("Interrupt received")
    finally:
        await cartridge.stop()


if __name__ == "__main__":
    asyncio.run(main())
