"""
Execution Server - gRPC server for trade execution.

Second-layer execution engine.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Dict, Any, Optional

from execution.order_bus import (
    OrderBus,
    TradeSignal,
    SignalAction,
    get_order_bus,
)
from execution.backends.paper import PaperBackend, get_paper_backend


# --- Configuration ---
EXECUTION_PORT = int(os.getenv("EXECUTION_PORT", "9001"))
EXECUTION_HOST = os.getenv("EXECUTION_HOST", "0.0.0.0")
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "paper")  # paper or live


class ExecutionServicer:
    """
    gRPC service implementation for ExecutionService.
    
    Provides:
    - SubmitSignal: Queue trade signal
    - GetPositions: Current positions
    - StreamExecutions: Execution confirmations
    - HealthCheck: Service health
    """
    
    def __init__(self, order_bus: OrderBus, backend: PaperBackend) -> None:
        self.order_bus = order_bus
        self.backend = backend
        self._start_time = time.time()
    
    async def SubmitSignal(self, request, context):
        """Submit a trade signal for execution."""
        signal = TradeSignal(
            symbol=request.get("symbol", ""),
            mint=request.get("mint", ""),
            action=SignalAction(request.get("action", "BUY")),
            size_usd=float(request.get("size_usd", 0)),
            reason=request.get("reason", ""),
            confidence=float(request.get("confidence", 0.5)),
            target_price=float(request.get("target_price", 0)),
            stop_loss=float(request.get("stop_loss", 0)),
            source=request.get("source", "UNKNOWN"),
        )
        
        try:
            signal_id = await self.order_bus.submit(signal)
            return {
                "signal_id": signal_id,
                "status": "ACCEPTED",
                "message": "Signal queued for execution",
                "timestamp_ms": int(time.time() * 1000),
            }
        except ValueError as e:
            return {
                "signal_id": signal.id,
                "status": "REJECTED",
                "message": str(e),
                "timestamp_ms": int(time.time() * 1000),
            }
    
    async def GetPositions(self, request, context):
        """Get current positions."""
        positions = self.backend.get_positions()
        
        return {
            "positions": [p.to_dict() for p in positions],
            "total_value_usd": sum(p.balance * p.avg_price for p in positions),
            "open_count": sum(1 for p in positions if p.status == "OPEN"),
        }
    
    async def GetPnL(self, request, context):
        """Get portfolio PnL."""
        pnl = self.backend.get_pnl()
        return {
            "realized_pnl": pnl["realized_pnl"],
            "unrealized_pnl": pnl["unrealized_pnl"],
            "total_pnl": pnl["realized_pnl"] + pnl["unrealized_pnl"],
            "trades_count": pnl["trades_count"],
            "win_rate": pnl["win_rate"],
            "avg_trade_pnl": pnl["realized_pnl"] / max(pnl["trades_count"], 1),
        }
    
    async def HealthCheck(self, request, context):
        """Return service health status."""
        positions = self.backend.get_positions()
        
        return {
            "status": "OK",
            "mode": EXECUTION_MODE.upper(),
            "open_positions": sum(1 for p in positions if p.status == "OPEN"),
            "cash_balance": self.backend.get_cash(),
            "uptime_seconds": int(time.time() - self._start_time),
        }


class ExecutionServer:
    """
    Main Execution server.
    
    Orchestrates:
    - gRPC server for client connections
    - Order bus for signal processing
    - Execution backend (paper or live)
    """
    
    def __init__(self) -> None:
        self.order_bus = get_order_bus()
        
        # Select backend based on mode
        if EXECUTION_MODE == "live":
            # Would import live backend here
            print("⚠️ [Execution] Live mode not implemented, using paper")
            self.backend = get_paper_backend()
        else:
            self.backend = get_paper_backend()
        
        # Wire backend to order bus
        self.order_bus.set_executor(self.backend.execute)
        
        self._running = False
    
    async def start(self) -> None:
        """Start the Execution server."""
        print(f"💹 [Execution] Starting server on {EXECUTION_HOST}:{EXECUTION_PORT}")
        print(f"📊 [Execution] Mode: {EXECUTION_MODE.upper()}")
        print(f"💰 [Execution] Initial cash: ${self.backend.get_cash():.2f}")
        
        self._running = True
        
        # Start order bus processing
        await self.order_bus.start()
        
        print(f"✅ [Execution] gRPC server ready on :{EXECUTION_PORT}")
        
        # Keep running
        try:
            while self._running:
                await asyncio.sleep(1)
                
                # Log stats periodically
                if int(time.time()) % 60 == 0:
                    stats = self.order_bus.get_stats()
                    print(f"📋 [Execution] Stats: {stats}")
                    
        except asyncio.CancelledError:
            pass
    
    async def stop(self) -> None:
        """Stop the Execution server."""
        print("🛑 [Execution] Shutting down...")
        self._running = False
        await self.order_bus.stop()
        print("✅ [Execution] Shutdown complete")
    
    def get_servicer(self) -> ExecutionServicer:
        """Get the gRPC servicer instance."""
        return ExecutionServicer(self.order_bus, self.backend)


# --- Entry Point ---

async def serve() -> None:
    """Main server entry point."""
    server = ExecutionServer()
    
    try:
        await server.start()
    except KeyboardInterrupt:
        pass
    finally:
        await server.stop()


def main() -> None:
    """CLI entry point."""
    print("=" * 50)
    print("  PHANTOM EXECUTION ENGINE")
    print("  Second-Layer Trade Execution")
    print("=" * 50)
    
    asyncio.run(serve())


if __name__ == "__main__":
    main()
