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
        
        # V23: Supervisor Registry (Tiered)
        self.tasks = {
            "fast": {},  # Hot Path (Rust)
            "mid": {},   # Intelligence (Yielding)
            "slow": {}   # Maintenance (Heavy I/O)
        }
        
        # Components Registry
        self.agents = {} 
        
        # 1. CORE INFRA
        # V22: Use Real Price Cache
        from src.core.shared_cache import SharedPriceCache
        self.price_cache = SharedPriceCache
        self.watched_mints = {"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC"}
        self.listener = WebSocketListener(self.price_cache, self.watched_mints)
        
        # V9.0: Chaos Shield (Security)
        from src.shared.system.chaos_shield import chaos_shield
        self.chaos = chaos_shield
        
        # 2. FAST TIER AGENTS
        arb_config = ArbiterConfig(live_mode=live_mode) 
        self.agents["arbiter"] = PhantomArbiter(arb_config)
        
        # 3. MID TIER AGENTS
        # Scalper
        self.agents["scalper"] = TradingCore(strategy_class=MerchantEnsemble, engine_name="SCALPER")
        
        # Whale Watcher (V23)
        from src.scraper.agents.whale_watcher_agent import WhaleWatcherAgent
        self.agents["whale"] = WhaleWatcherAgent()
        
        # 4. SLOW TIER AGENTS
        # Scout
        from src.scraper.agents.scout_agent import ScoutAgent
        self.agents["scout"] = ScoutAgent()
        
        # Landlord (V23)
        from src.engine.landlord_core import get_landlord
        self.agents["landlord"] = get_landlord()

    async def start(self):
        """Ignition: The Supervisor Kernel Start."""
        self.is_running = True
        state.status = "STARTING_ENGINES"
        state.log("[Director] Igniting Supervisor Kernel...")
        
        # 1. Initialize Core (Async)
        await self.agents["arbiter"].initialize()
        await self.agents["scalper"].initialize()
        
        # 2. Launch FAST TIER (Hot Path)
        self.tasks["fast"]["wss"] = asyncio.create_task(self._run_wss(), name="WSS_Listener")
        self.tasks["fast"]["arbiter"] = asyncio.create_task(
            self.agents["arbiter"].run(duration_minutes=0, scan_interval=2),
            name="Arbiter_Core"
        )
        state.update_stat("rust_core_active", True)
        
        # 3. Launch MID TIER (Intelligence)
        self.tasks["mid"]["scalper"] = asyncio.create_task(self._run_scalper_loop(), name="Scalper_Engine")
        
        self.agents["whale"].start() # Internal loop
        # We assume agent.start() spawns internal tasks, but to be safe under Supervisor,
        # we ideally manage the loop here. 
        # WhaleWatcher currently spawns its own task in start().
        # For V23 integration, we let it spawn but track it if possible, 
        # or we just assume it runs.
        # Ideally: self.tasks["mid"]["whale"] = asyncio.create_task(self.agents["whale"].run_loop())
        
        # 4. Launch SLOW TIER (Maintenance)
        self.agents["scout"].start() # Internal
        # self.tasks["slow"]["scout"] = ... (Scout manages own tasks)
        
        # Landlord Monitoring (V23)
        self.tasks["slow"]["landlord"] = asyncio.create_task(
            self.agents["landlord"].run_monitoring_loop(),
            name="Landlord_Monitor"
        )
        
        # Wallet Sync (V23: Moved to Slow)
        self.tasks["slow"]["wallet_sync"] = asyncio.create_task(
            self._run_state_sync(),
            name="Wallet_Sync"
        )
        
        # Discovery Service (V23: Adapted Loop)
        from src.services.discovery_service import discovery_monitor_loop
        self.tasks["slow"]["discovery"] = asyncio.create_task(
            discovery_monitor_loop(),
            name="Discovery_Monitor"
        )
        
        # Liquidity Service (V23: Adapted Loop)
        from src.services.liquidity_service import liquidity_cycle_loop
        self.tasks["slow"]["liquidity"] = asyncio.create_task(
            liquidity_cycle_loop(),
            name="Liquidity_Manager"
        )
        
        # 5. Start Supervisor Monitor
        asyncio.create_task(self.monitor_system(), name="Kernel_Monitor")
        
        # 6. Start Loop Lag Monitor (V23)
        self.lag_monitor = LagMonitor()
        asyncio.create_task(self.lag_monitor.start(), name="Lag_Monitor")
        
        state.status = "OPERATIONAL"
        state.log("[Director] All Systems Nominal (Tiered Execution Active).")

    async def stop(self):
        """Shutdown."""
        self.is_running = False
        state.log("[Director] Shutting down...")
        
        # Stop Components
        self.listener.stop()
        if hasattr(self, 'lag_monitor'): self.lag_monitor.stop()
        self.agents["scout"].stop()
        self.agents["whale"].stop()
        
        # Cancel All Tasks
        for tier in self.tasks.values():
            for name, task in tier.items():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        state.status = "OFFLINE"

    async def monitor_system(self):
        """V23: Supervisor Heartbeat & Health Check."""
        while self.is_running:
            await asyncio.sleep(1.0)
            
            # 1. Update AppState for Dashboard
            # In V2 Dashboard, we might have a 'system_health' map
            # state.update_system_health(self.tasks)
            
            # 2. Check Task Liveness
            for tier, tasks in self.tasks.items():
                for name, task in tasks.items():
                    if task.done():
                        exc = task.exception()
                        if exc:
                            state.log(f"[Director] ⚠️ Task Failed: {name} ({tier}) - {exc}")
                            # Restart logic could go here
                        # else:
                        #     state.log(f"[Director] ℹ️ Task Finished: {name}")

    async def _run_wss(self):
        """Fast Lane: WebSocket Listener."""
        try:
            self.listener.start()
            while self.is_running:
                 await asyncio.sleep(1)
        except Exception as e:
            state.log(f"[Director] ❌ WSS Crash: {e}")

    async def _run_scalper_loop(self):
        """Mid Lane: Real Scalper."""
        state.log("[Director] Scalper: Active (Merchant Engine / 2s)")
        while self.is_running:
            try:
                await asyncio.to_thread(self.agents["scalper"].scan_signals)
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                break
            except Exception as e:
                state.log(f"[Scalper] Error: {e}")

    # Note: _run_scout_loop is removed as ScoutAgent manages its own tasks via .start()
    # But in strict Supervisor mode, we should control it.
    # For this phase, we rely on Scout's internal .start() but monitor it loosely.

    async def _run_state_sync(self):
        """Slow Lane: Wallet Sync."""
        from src.shared.state.app_state import WalletData
        
        # Wait for arbiter initialization
        while not hasattr(self.agents["arbiter"], 'executor') or not self.agents["arbiter"].executor:
            await asyncio.sleep(0.5)
            
        while self.is_running:
            try:
                await asyncio.sleep(1.0) # 1Hz Refresh
                
                wallet_adapter = self.agents["arbiter"].executor.wallet
                if not wallet_adapter: continue

                from src.core.shared_cache import SharedPriceCache
                sol_price, _ = SharedPriceCache.get_price("SOL")
                if not sol_price: sol_price = 150.0
                
                price_map = {'SOL': sol_price} 
                balance_data = wallet_adapter.get_detailed_balance(price_map)
                
                snapshot = WalletData(
                    balance_usdc = balance_data.get('cash', 0.0),
                    balance_sol = wallet_adapter.sol_balance,
                    gas_sol = wallet_adapter.sol_balance,
                    total_value_usd = balance_data.get('total_equity', 0.0),
                    inventory = {s: a.balance for s, a in wallet_adapter.assets.items()}
                )
                
                state.update_wallet(self.agents["arbiter"].config.live_mode, snapshot)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                pass

