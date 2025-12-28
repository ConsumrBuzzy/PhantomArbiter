import asyncio
import time
from typing import Optional
from src.shared.state.app_state import state
from src.shared.infrastructure.websocket_listener import WebSocketListener
from src.arbiter.arbiter import PhantomArbiter, ArbiterConfig
from src.engine.trading_core import TradingCore
from src.strategy.ensemble import MerchantEnsemble

class Director:
    """
    The Orchestrator.
    Manages the lifecycle of Fast Lane (Arb) and Slow Lane (Scout/Whale) tasks.
    And now: Mid Lane (Scalper).
    """
    def __init__(self, live_mode: bool = False):
        self.is_running = False
        self.fast_tasks = []
        self.mid_tasks = []
        self.slow_tasks = []
        
        # Components
        # V3.1: Inject dependencies for WebSocketListener
        # V22: Use Real Price Cache
        from src.core.shared_cache import SharedPriceCache
        self.price_cache = SharedPriceCache
        
        self.watched_mints = {"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC"}
        
        self.listener = WebSocketListener(self.price_cache, self.watched_mints)
        
        # V9.0: Chaos Shield (Security)
        from src.shared.system.chaos_shield import chaos_shield
        self.chaos = chaos_shield
        
        # 1. ARBITER (Atomic)
        arb_config = ArbiterConfig(live_mode=live_mode) 
        self.arbiter = PhantomArbiter(arb_config)
        
        # 2. SCALPER (Merchant Mind)
        # V12.8: Unified Merchant Engine (Scalper+Keltner+VWAP)
        self.scalper = TradingCore(strategy_class=MerchantEnsemble, engine_name="SCALPER")
        
        # 3. SCOUT (Discovery)
        from src.scraper.agents.scout_agent import ScoutAgent
        self.scout = ScoutAgent()
        self.scout_active = True

    async def start(self):
        """Ignition."""
        self.is_running = True
        state.status = "STARTING_ENGINES"
        state.log("[Director] Igniting Systems (REAL)...")
        
        # 1. THE WIRE (Fast Lane) - WSS
        self.fast_tasks.append(asyncio.create_task(self._run_wss()))
        state.update_stat("rust_core_active", True)
        
        # 2. THE ARBITER (Fast Lane) - Real Cycle
        # V21: Async Init to prevent startup lag (loading weights/tg/keys)
        await self.arbiter.initialize()
        
        # We start the arbiter run loop in the background
        self.fast_tasks.append(asyncio.create_task(
            self.arbiter.run(duration_minutes=0, scan_interval=2)
        ))
        
        # 3. THE MERCHANT (Mid Lane) - Scalper
        # Real-time scan and signal generation
        # V13.0: Async Init to prevent lag
        await self.scalper.initialize()
        self.mid_tasks.append(asyncio.create_task(self._run_scalper_loop()))
        
        # 4. THE SCOUT (Slow Lane)
        self.scout.start() # Start internal scout tasks
        self.slow_tasks.append(asyncio.create_task(self._run_scout_loop()))
        
        # 5. STATE SYNC (Dashboard 2.1 Refresh)
        self.slow_tasks.append(asyncio.create_task(self._run_state_sync()))
        
        state.status = "OPERATIONAL"
        state.log("[Director] All Systems Nominal (Real Data Active).")

    async def stop(self):
        """Shutdown."""
        self.is_running = False
        state.log("[Director] Shutting down...")
        self.listener.stop()
        self.scout.stop()
        
        for task in self.fast_tasks + self.mid_tasks + self.slow_tasks:
            task.cancel()
        
        state.status = "OFFLINE"

    async def _run_wss(self):
        """Fast Lane: WebSocket Listener."""
        try:
            self.listener.start()
            # Keep the task alive to monitor the thread? 
            # Logic: Just sleep forever while checking is_running
            while self.is_running:
                 await asyncio.sleep(1)
        except Exception as e:
            state.log(f"[Director] ❌ WSS Crash: {e}")

    async def _run_scalper_loop(self):
        """Mid Lane: Real Scalper (Merchant Engine)."""
        state.log("[Director] Scalper: Active (Merchant Engine / 2s)")
        
        while self.is_running:
            try:
                # V12.8: Execute Sync Scan in Thread
                # This triggers MerchantEnsemble.analyze_tick via TradingCore.scan_signals
                await asyncio.to_thread(self.scalper.scan_signals)
                await asyncio.sleep(2)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                state.log(f"[Scalper] Error: {e}")

    async def _run_scout_loop(self):
        """Slow Lane: Token Discovery (Real Scout)."""
        state.log("[Director] Scout Agent: Active (Interval: 60s)")
        while self.is_running:
            try:
                # 1. Sleep first
                await asyncio.sleep(60)
                
                # 2. Trigger Audit (Real)
                # We can trigger an audit on top trading pairs or watchlist items
                # For now, let's keep it alive
                pass 
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                state.log(f"[Scout] Error: {e}")

    async def _run_whale_loop(self):
        """Slow Lane: Smart Money Tracker."""
        pass # Disabled for now

    async def _run_state_sync(self):
        """
        Dashboard 2.0: Synchronize Wallet & Inventory State.
        Polls underlying CapitalManager (via PaperWallet adapter) and pushes to AppState.
        """
        from src.shared.state.app_state import WalletData
        
        # Wait for arbiter initialization (V22 Fix)
        while not hasattr(self.arbiter, 'executor') or not self.arbiter.executor:
            await asyncio.sleep(0.5)
            
        while self.is_running:
            try:
                await asyncio.sleep(1.0) # 1Hz Refresh
                
                # 1. Fetch from Arbiter's Wallet Adapter (Primary Source)
                # Note: Arbiter uses PaperWallet which wraps CapitalManager
                wallet_adapter = self.arbiter.executor.wallet
                if not wallet_adapter:
                   continue

                # We need a mock price map for value calculation
                # In real V2, we'd use Oracle prices or SharedPriceCache
                # V22: Use SharedPriceCache
                from src.core.shared_cache import SharedPriceCache
                sol_price, _ = SharedPriceCache.get_price("SOL")
                if not sol_price: sol_price = 150.0
                
                price_map = {'SOL': sol_price} 
                
                # 2. Get Detailed Balance
                # This returns: {'cash': ..., 'gas_usd': ..., 'assets_usd': ...}
                balance_data = wallet_adapter.get_detailed_balance(price_map)
                
                # 3. Construct WalletData Snapshot
                snapshot = WalletData(
                    balance_usdc = balance_data.get('cash', 0.0),
                    balance_sol = wallet_adapter.sol_balance,
                    gas_sol = wallet_adapter.sol_balance, # Same for now
                    total_value_usd = balance_data.get('total_equity', 0.0),
                    # Construct simple inventory dict {Symbol: Amt}
                    inventory = {s: a.balance for s, a in wallet_adapter.assets.items()}
                )
                
                # 4. Push to State
                # Using arbiter.config.live_mode to determine target slot
                state.update_wallet(self.arbiter.config.live_mode, snapshot)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Silent fail to avoid log spam, but maybe log once?
                pass
