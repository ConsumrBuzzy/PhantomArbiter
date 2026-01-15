"""
Base Engine
===========
Abstract base class for all trading engines in the Phantom Arbiter OS.
Standardizes interface for startup, shutdown, mode handling, and reporting.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Callable
from src.shared.system.logging import Logger

from src.shared.feeds.jupiter_feed import JupiterFeed

class BaseEngine(ABC):
    def __init__(self, name: str, live_mode: bool = False):
        self.name = name
        self.live_mode = live_mode
        self.mode = "live" if live_mode else "paper"
        self.running = False
        self._callback: Optional[Callable] = None
        self.driver = None
        self.wallet = None
        self.swapper = None
        self.paper_wallet = None  # Engine-specific paper vault
        self.feed = JupiterFeed()
        
        # Initialize Drivers
        if self.live_mode:
            from src.drivers.wallet_manager import WalletManager
            from src.drivers.jupiter_driver import JupiterSwapper
            self.wallet = WalletManager()
            self.swapper = JupiterSwapper(self.wallet)
        else:
            from src.shared.drivers.virtual_driver import VirtualDriver
            from src.shared.state.paper_wallet import get_engine_wallet
            self.driver = VirtualDriver(self.name)
            # Multi-Vault: Each engine gets isolated paper wallet
            self.paper_wallet = get_engine_wallet(self.name)
            
        Logger.info(f"[{self.name.upper()}] Engine Initialized ({self.mode.upper()})")

    # ... set_callback, start, stop ...

    async def execute_swap(self, direction: str, amount_usd: float, token_mint: str, token_symbol: str) -> Dict[str, Any]:
        """
        Unified swap execution (Live or Paper).
        Returns: {success: bool, price: float, amount: float, txid: str, error: str}
        """
        try:
            if self.live_mode:
                # LIVE EXECUTION
                result = self.swapper.execute_swap(
                    direction=direction.upper(),
                    amount_usd=amount_usd,
                    reason=f"{self.name} Signal",
                    target_mint=token_mint
                )
                if result.get("success"):
                     # Attempt to parse outAmount/price from result if possible
                     # JupiterSwapper returns outAmount.
                     # We might need to fetch decimals to convert atomic to float.
                     # For now, pass basic info.
                     return {
                         "success": True,
                         "txid": result.get("txid"),
                         "price": 0.0, # Hard to know without fetching
                         "amount": float(result.get("outAmount", 0)), # Atomic units?
                         "error": None
                     }
                else:
                    return {"success": False, "error": result.get("error")}
                    
            elif self.driver:
                # PAPER EXECUTION
                # 1. Get Price
                # Use USDC as quote
                quote = self.feed.get_spot_price(token_mint, JupiterFeed.USDC_MINT)
                if not quote:
                    return {"success": False, "error": f"No price for {token_mint}"}
                
                price = quote.price
                if price <= 0: return {"success": False, "error": "Invalid price"}
                
                # 2. Calc Amount
                amount_token = amount_usd / price
                
                # 3. Place Virtual Order
                from src.shared.drivers.virtual_driver import VirtualOrder
                order = VirtualOrder(
                    symbol=f"{token_symbol}",
                    side=direction.lower(),
                    size=amount_token, # VirtualDriver expects Token Amount usually? Or check implementation.
                    # In ScalpEngine I used size=amount_token.
                    order_type="market"
                )
                
                # Update driver feed for fill
                self.driver.set_price_feed({f"{token_symbol}": price})
                
                filled = await self.driver.place_order(order)
                
                if filled.status == "filled":
                    return {
                        "success": True,
                        "price": filled.filled_price,
                        "amount": filled.filled_size,
                        "txid": f"paper_{filled.id}",
                        "error": None
                    }
                else:
                    return {"success": False, "error": "Fill failed"}
                    
            return {"success": False, "error": "No driver available"}
            
        except Exception as e:
            Logger.error(f"[{self.name}] Swap Error: {e}")
            return {"success": False, "error": str(e)}

    def set_callback(self, callback: Callable[[Dict[str, Any]], Any]):
        """Set the callback for broadcasting updates to the dashboard."""
        self._callback = callback

    async def start(self, config: Optional[Dict[str, Any]] = None):
        """
        Start the engine loop with optional configuration overrides.
        Args:
            config: Optional dictionary of runtime parameters (risk, leverage, etc.)
        """
        if self.running:
            Logger.info(f"[{self.name.upper()}] Already running.")
            return

        if config:
            self.config = config # Update internal config if provided
            Logger.info(f"[{self.name.upper()}] Configuration updated: {config}")

        self.running = True
        self.start_time = time.time()
        self.status = "RUNNING"
        Logger.info(f"[{self.name.upper()}] Started (Mode: {self.mode.upper()})")
        
        # Start the monitor loop as a background task
        asyncio.create_task(self._monitor_loop())

    async def stop(self):
        """Stop the engine loop and persist state."""
        if not self.running:
            return
            
        self.running = False
        self.status = "STOPPED"
        Logger.info(f"[{self.name.upper()}] Stopped")
        
        # Optional: Hook for persistence/cleanup
        await self.on_stop()

    async def on_stop(self):
        """Override to perform cleanup or state saving on stop."""
        pass

    def get_status(self) -> Dict[str, Any]:
        """
        Returns standardized JSON operational status.
        Structure: {status, uptime, pnl, mode, config}
        """
        uptime = time.time() - self.start_time if self.running and hasattr(self, 'start_time') else 0
        return {
            "name": self.name,
            "status": self.status, # RUNNING, STOPPED, ERROR
            "uptime": int(uptime),
            "mode": self.mode,
            "live_mode": self.live_mode,
            "pnl": getattr(self, "pnl", 0.0), # Engines should update self.pnl
            "config": getattr(self, "config", {})
        }

    def export_state(self) -> Dict[str, Any]:
        """
        High-frequency State Export for Dashboard UI.
        Subclasses should override this to provide engine-specific real-time data.
        Returns: Dict of metrics/state to be broadcasted.
        """
        return {}

    async def _monitor_loop(self):
        """Internal loop handling errors and intervals."""
        while self.running:
            try:
                # 1. Execute Logic
                await self.tick()
                
                # 2. Export State (Heartbeat)
                # We can auto-broadcast state if desired, or let tick() handle it.
                # For standardization, let's allow tick() to return state upgrades or handle it explicitly.
                # Here we strictly run tick().
                
            except Exception as e:
                Logger.error(f"[{self.name.upper()}] Error: {e}")
                self.status = "ERROR"
                # decided NOT to stop on error immediately to allow retry or recovery, 
                # but valid to consider self.stop() here depending on severity.
            
            await asyncio.sleep(self.get_interval())

    @abstractmethod
    async def tick(self):
        """Single execution logic step. Must be implemented by subclass."""
        pass

    def get_interval(self) -> float:
        """Tick interval in seconds. Can be overridden."""
        return 5.0

    async def broadcast(self, data: Dict[str, Any]):
        """Helper to send data via callback."""
        if self._callback:
            # Wrap in standard envelope if not already? 
            # For now passing raw data as engines might have specific schemas.
            await self._callback(data)
