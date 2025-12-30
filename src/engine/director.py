import asyncio
import time
from typing import Optional
from src.shared.state.app_state import state
from src.shared.infrastructure.websocket_listener import WebSocketListener
from src.arbiter.arbiter import PhantomArbiter, ArbiterConfig
from src.strategy.ensemble import MerchantEnsemble
from src.engine.trading_core import TradingCore
from src.shared.system.signal_bus import signal_bus, Signal, SignalType

class Director:
    """
    The Orchestrator.
    Manages the lifecycle of Fast Lane (Arb) and Slow Lane (Scout/Whale) tasks.
    And now: Mid Lane (Scalper).
    """
    
    # V23: Lag Monitor
    from src.shared.system.lag_monitor import LagMonitor
    
    def __init__(self, live_mode: bool = False, lite_mode: bool = False):
        self.is_running = False
        self.lite_mode = lite_mode
        
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
        
        if not self.lite_mode:
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
        else:
            # Mock or Skip
            self.agents["whale"] = None
            self.agents["scout"] = None
            self.agents["landlord"] = None

        # 5. SIGNAL BUS (Unified OS Hub)
        self.signal_bus = signal_bus
        self._setup_signal_routing()

    def _setup_signal_routing(self):
        """Route internal system alerts to the bus."""
        def log_signal(sig: Signal):
            state.log(f"📡 [Bus] {sig.type.value} from {sig.source}")
            # V35: Push to unified audit log
            state.add_system_signal(sig)
        
        self.signal_bus.subscribe(SignalType.SYSTEM_ALERT, log_signal)
        self.signal_bus.subscribe(SignalType.WHALE, log_signal)
        self.signal_bus.subscribe(SignalType.SCOUT, log_signal)
        self.signal_bus.subscribe(SignalType.SCALP_SIGNAL, log_signal)
        self.signal_bus.subscribe(SignalType.ARB_OPP, log_signal)
        self.signal_bus.subscribe(SignalType.MARKET_UPDATE, log_signal)  # V134: Price updates
        
        # V35: Reactive Mode Toggle
        def handle_config_change(sig: Signal):
            key = sig.data.get("key")
            value = sig.data.get("value")
            if key == "MODE":
                self._sync_execution_mode(value)
                
        self.signal_bus.subscribe(SignalType.CONFIG_CHANGE, handle_config_change)

    async def start(self):
        """Ignition: The Supervisor Kernel Start (Non-blocking)."""
        self.is_running = True
        state.status = "STARTING_ENGINES"
        state.log("[Director] Igniting Supervisor Kernel...")
        
        # 1. Launch Initialization Task (Background)
        # We do NOT await this here, so the Dashboard can load instantly.
        # The 'Arbiter_Core' task will wait for init internally if needed,
        # or we rely on the async nature.
        self.tasks["slow"]["init"] = asyncio.create_task(
            self._async_init_sequence(),
            name="System_Init"
        )

        # 2. Launch FAST TIER (Hot Path)
        self.tasks["fast"]["wss"] = asyncio.create_task(self._run_wss(), name="WSS_Listener")
        # Arbiter Run loop handles its own readiness checks
        self.tasks["fast"]["arbiter"] = asyncio.create_task(
            self.agents["arbiter"].run(duration_minutes=0, scan_interval=2),
            name="Arbiter_Core"
        )
        state.update_stat("rust_core_active", True)
        
        # 3. Launch MID TIER (Intelligence)
        self.tasks["mid"]["scalper"] = asyncio.create_task(self._run_scalper_loop(), name="Scalper_Engine")
        
        # Wallet Sync (Robust Loop)
        self.tasks["slow"]["wallet_sync"] = asyncio.create_task(
            self._run_state_sync(),
            name="Wallet_Sync"
        )

        if not self.lite_mode:
            # Whale Watcher (Internal Loop)
            self.agents["whale"].start() 
            
            # 4. Launch SLOW TIER (Maintenance)
            self.agents["scout"].start() 
            
            # Landlord Monitoring
            self.tasks["slow"]["landlord"] = asyncio.create_task(
                self.agents["landlord"].run_monitoring_loop(),
                name="Landlord_Monitor"
            )
            
            # Discovery Service
            from src.services.discovery_service import discovery_monitor_loop
            self.tasks["slow"]["discovery"] = asyncio.create_task(
                discovery_monitor_loop(),
                name="Discovery_Monitor"
            )
            
            # Liquidity Service
            from src.services.liquidity_service import liquidity_cycle_loop
            self.tasks["slow"]["liquidity"] = asyncio.create_task(
                liquidity_cycle_loop(),
                name="Liquidity_Manager"
            )
        else:
            state.log("[Director] ⚡ Lite Mode Active: Skipping non-essential background daemons.")
        
        # 5. Start Supervisor Monitor
        asyncio.create_task(self.monitor_system(), name="Kernel_Monitor")
        
        # 6. Start Loop Lag Monitor
        self.lag_monitor = LagMonitor()
        asyncio.create_task(self.lag_monitor.start(), name="Lag_Monitor")
        
        state.status = "OPERATIONAL"
        state.log("[Director] Supervisor Kernel Online (Background Init).")

    async def _async_init_sequence(self):
        """Heavy initialization sequence running in background."""
        state.log("[Init] Warming up engines...")
        try:
            # Parallel init for maximum speed
            await asyncio.gather(
                self.agents["arbiter"].initialize(),
                self.agents["scalper"].initialize()
            )
            state.log("[Init] Engines Ready.")
        except Exception as e:
            state.log(f"[Init] ❌ Startup Error: {e}")

    async def stop(self):
        """Shutdown."""
        self.is_running = False
        state.log("[Director] Shutting down...")
        
        # Stop Components
        self.listener.stop()
        if hasattr(self, 'lag_monitor'): self.lag_monitor.stop()
        
        # V133: Safe-Stop Iterator - Guard against None agents in lite_mode
        if agent := self.agents.get("scout"): agent.stop()
        if agent := self.agents.get("whale"): agent.stop()
        
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
                signals = await asyncio.to_thread(self.agents["scalper"].scan_signals)
                # V12.6: Push to UI and Execute
                if signals:
                    from src.shared.state.app_state import ScalpSignal
                    for s in signals[:5]: # Limit spam
                        # 1. Update UI
                        state.add_signal(ScalpSignal(
                            token=s['symbol'],
                            signal_type=f"🧠 {s['engine']}",
                            confidence="High" if s['confidence'] > 0.8 else ("Med" if s['confidence'] > 0.5 else "Low"),
                            action=s['action'],
                            price=s.get('price', 0)  # V133: Include price in signal
                        ))
                        
                        # V134: Emit to Global Feed
                        self.signal_bus.emit(Signal(
                            type=SignalType.SCALP_SIGNAL,
                            source="Scalper",
                            data={
                                "symbol": s['symbol'],
                                "action": s['action'],
                                "price": s.get('price', 0),
                                "confidence": s['confidence'],
                                "message": f"{s['action']} {s['symbol']} @ ${s.get('price', 0):.4f}"
                            }
                        ))
                        
                        # 2. Execute (Simulation or Live)
                        # V12.6: We actually call the engine to process the event
                        # This triggers Paper trades in CapitalManager or Live trades via Swapper
                        try:
                            self.agents["scalper"].execute_signal(s)
                        except Exception as e:
                            import traceback
                            tb = traceback.format_exc()
                            print(f"[Director] Signal execution failed: {e}\n{tb}")  # V134: Print to console
                            state.log(f"[Director] Signal execution failed: {e}\n{tb}")
                
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                break
            except Exception as e:
                state.log(f"[Scalper] Error: {e}")

    # Note: _run_scout_loop is removed as ScoutAgent manages its own tasks via .start()
    # But in strict Supervisor mode, we should control it.
    # For this phase, we rely on Scout's internal .start() but monitor it loosely.

    async def _run_state_sync(self):
        """Slow Lane: Wallet Sync for BOTH Live and Paper modes."""
        from src.shared.state.app_state import WalletData, InventoryItem
        from src.core.shared_cache import SharedPriceCache
        
        # Wait for arbiter initialization (tracker must exist)
        arb = self.agents["arbiter"]
        while not hasattr(arb, 'tracker') or not arb.tracker:
            await asyncio.sleep(0.5)
        
        state.log("[WalletSync] Wallet sync loop started.")
            
        while self.is_running:
            try:
                await asyncio.sleep(1.0) # 1Hz Refresh
                
                is_live = arb.config.live_mode
                sol_price, _ = SharedPriceCache.get_price("SOL")
                if not sol_price: sol_price = 150.0
                
                # ═══ LIVE MODE: Real Wallet ═══
                if is_live and hasattr(arb, 'executor') and arb.executor and arb.executor.wallet:
                    wallet_adapter = arb.executor.wallet
                    
                    price_map = {'SOL': sol_price}
                    holdings = wallet_adapter.assets if hasattr(wallet_adapter, 'assets') else {}
                    
                    for symbol in holdings.keys():
                        if symbol not in price_map:
                            p, _ = SharedPriceCache.get_price(symbol)
                            if p: price_map[symbol] = p

                    balance_data = wallet_adapter.get_detailed_balance(price_map)
                    
                    inventory_items = []
                    for symbol, asset in holdings.items():
                        price = price_map.get(symbol, 0.0)
                        inventory_items.append(InventoryItem(
                            symbol=symbol,
                            amount=asset.balance,
                            value_usd=asset.balance * price,
                            price_change_24h=0.0
                        ))

                    live_snapshot = WalletData(
                        balance_usdc = balance_data.get('cash', 0.0),
                        balance_sol = wallet_adapter.sol_balance,
                        gas_sol = wallet_adapter.sol_balance,
                        total_value_usd = balance_data.get('total_equity', 0.0),
                        inventory = inventory_items
                    )
                    state.update_wallet(True, live_snapshot)
                
                # ═══ PAPER MODE: Use TradeTracker balances ═══
                tracker = arb.tracker
                paper_balance = tracker.current_balance
                paper_gas = tracker.gas_balance / sol_price if sol_price > 0 else 0.0
                
                paper_snapshot = WalletData(
                    balance_usdc = paper_balance,
                    balance_sol = paper_gas,
                    gas_sol = paper_gas,
                    total_value_usd = paper_balance + tracker.gas_balance,
                    inventory = []  # Paper mode doesn't track individual tokens
                )
                state.update_wallet(False, paper_snapshot)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                state.log(f"[WalletSync] Error: {e}")
                await asyncio.sleep(5)

    def _sync_execution_mode(self, mode: str):
        """Synchronize LIVE/PAPER mode across all tiered agents."""
        is_live = (mode == "LIVE")
        state.log(f"🔄 [Director] Syncing execution mode to: {mode} (Live: {is_live})")
        
        # 1. Update Arbiter
        if "arbiter" in self.agents:
            # We add this method to PhantomArbiter
            self.agents["arbiter"].set_live_mode(is_live)
            
        # 2. Update Scalper
        if "scalper" in self.agents:
            # We add this method to TradingCore
            self.agents["scalper"].set_live_mode(is_live)
            
        # 3. Update Other Components
        # e.g. Landlord, Discovery (usually informational but good to sync)
        
        state.log(f"✅ [Director] System transformed to {mode} path.")
