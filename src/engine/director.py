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
        
        # V40.0: Shared Token Metadata Layer (Rust-Powered)
        try:
            from phantom_core import SharedTokenMetadata, SignalScanner
            self.signal_scanner = SignalScanner()
            self.token_registry = {} # Dict[str, SharedTokenMetadata]
        except ImportError:
            print("⚠️ Rust Extension (phantom_core) not found or outdated. Shared Metadata disabled.")
            self.signal_scanner = None
            self.token_registry = {}
            
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
        
        # V40.0: Metadata Sync
        def handle_metadata(sig: Signal):
            meta = sig.data.get("metadata")
            mint = sig.data.get("mint")
            if meta and mint:
                # Update Registry (Zero-Copy Ref)
                self.token_registry[mint] = meta
                
                # If Rug Safe flipped to True, notify Scalper
                if meta.is_rug_safe:
                    state.log(f"🔓 [Director] Metadata Validated: {meta.symbol}")
                    
        self.signal_bus.subscribe(SignalType.METADATA, handle_metadata)
        
        # V41.0: Strategy Bridge (Cross-Strategy Signal Bus)
        def handle_scalp_routing(sig: Signal):
            # Only route High Confidence signals to Arbiter to avoid noise
            # Data format from Scalper: {'symbol': 'SOL', 'confidence': 0.9, ...}
            confidence = sig.data.get("confidence", 0.0)
            symbol = sig.data.get("symbol")
            
            if symbol and confidence > 0.8:
                arb = self.agents.get("arbiter")
                if arb:
                    # Direct "Tip" Injection
                    state.log(f"🚌 [Bus] Routing Scalp Tip for {symbol} to Arbiter (Conf: {confidence:.2f})")
                    arb.handle_strategy_tip(symbol)
                    
        self.signal_bus.subscribe(SignalType.SCALP_SIGNAL, handle_scalp_routing)

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
        """
        Slow Lane: Wallet Sync for BOTH Live and Paper modes.
        Aggregates state from Arbiter and Scalper.
        """
        from src.shared.state.app_state import WalletData, InventoryItem
        from src.core.shared_cache import SharedPriceCache
        
        # Wait for engines to be ready
        state.log("[WalletSync] Waiting for engines...")
        await asyncio.sleep(2.0)
        
        state.log("[WalletSync] Wallet sync loop started.")
            
        while self.is_running:
            try:
                await asyncio.sleep(1.0) # 1Hz Refresh
                
                # Determine Primary Source (Prefer Real Wallet if Live, else Paper)
                # We check Arbiter config for "Live Mode" flag as master switch
                arb = self.agents.get("arbiter")
                scalper = self.agents.get("scalper")
                
                is_live = False
                if arb and hasattr(arb, 'config'):
                    is_live = arb.config.live_mode
                elif scalper and hasattr(scalper, 'executor'):
                    is_live = scalper.executor.live_mode
                
                sol_price, _ = SharedPriceCache.get_price("SOL")
                if not sol_price: sol_price = 150.0
                
                # ═══ LIVE MODE: Real Wallet ═══
                wallet_adapter = None
                
                # Try to get wallet adapter from ANY agent
                if arb and hasattr(arb, 'executor') and arb.executor and arb.executor.wallet:
                    wallet_adapter = arb.executor.wallet
                elif scalper and hasattr(scalper, 'wallet'):
                    wallet_adapter = scalper.wallet
                    
                if is_live and wallet_adapter:
                    price_map = {'SOL': sol_price}
                    holdings = wallet_adapter.assets if hasattr(wallet_adapter, 'assets') else {}
                    
                    # If wallet_adapter doesn't have 'assets' property exposed directly (depending on version),
                    # we might need to fetch live balance.
                    # WalletManager.get_current_live_usd_balance() is the robust way.
                    live_data = wallet_adapter.get_current_live_usd_balance()
                    
                    balance_usdc = live_data.get('breakdown', {}).get('USDC', 0.0)
                    balance_sol = live_data.get('breakdown', {}).get('SOL', 0.0)
                    total_value = live_data.get('total_usd', 0.0)
                    
                    inventory_items = []
                    for asset in live_data.get('assets', []):
                        inventory_items.append(InventoryItem(
                            symbol=asset['symbol'],
                            amount=asset['amount'],
                            value_usd=asset['usd_value'],
                            price_change_24h=0.0
                        ))

                    live_snapshot = WalletData(
                        balance_usdc = balance_usdc,
                        balance_sol = balance_sol,
                        gas_sol = balance_sol,
                        total_value_usd = total_value,
                        inventory = inventory_items
                    )
                    state.update_wallet(True, live_snapshot)
                
                # ═══ PAPER MODE: Aggregate Paper Wallets ═══
                # We prioritize Scalper's PaperWallet if active, as it tracks positions more granularly
                else:
                    paper_balance = 0.0
                    paper_gas = 0.0
                    paper_equity = 0.0
                    inventory_items = []
                    
                    # 1. Scalper (TradingCore) Paper Wallet
                    if scalper and hasattr(scalper, 'paper_wallet'):
                        # Calculate total value
                        # Need current prices for assets
                        pw = scalper.paper_wallet
                        price_map = {}
                        for sym in pw.assets.keys():
                             p, _ = SharedPriceCache.get_price(sym)
                             if p: price_map[sym] = p
                        
                        pw_details = pw.get_detailed_balance(price_map)
                        paper_balance += pw_details['cash']
                        paper_equity += pw_details['total_equity']
                        # Gas is tracked in SOL locally in paper wallet? 
                        # PaperWallet.sol_balance is reliable
                        paper_gas += pw.sol_balance
                        
                        # Add stats to inventory
                        for sym, asset in pw.assets.items():
                            p = price_map.get(sym, asset.avg_price)
                            inventory_items.append(InventoryItem(
                                symbol=sym,
                                amount=asset.balance,
                                value_usd=asset.balance * p,
                                price_change_24h=0.0
                            ))
                            
                    # 2. Arbiter (PaperWallet V2)
                    elif arb and hasattr(arb, 'paper_wallet') and arb.paper_wallet:
                        pw = arb.paper_wallet
                        paper_balance = pw.cash
                        paper_gas = pw.sol_balance
                        paper_equity = pw.equity
                        
                        # Add Arbiter assets if any (usually empty for pure spatial arb)
                        # But if we did hold positions, add them
                        price_map = {sym: SharedPriceCache.get_price(sym)[0] or 0.0 for sym in pw.assets.keys()}
                        for sym, asset in pw.assets.items():
                             p = price_map.get(sym, asset.avg_price)
                             inventory_items.append(InventoryItem(
                                symbol=sym,
                                amount=asset.balance,
                                value_usd=asset.balance * p,
                                price_change_24h=0.0
                            ))
                    
                    paper_snapshot = WalletData(
                        balance_usdc = paper_balance,
                        balance_sol = paper_gas,
                        gas_sol = paper_gas,
                        total_value_usd = paper_equity,
                        inventory = inventory_items
                    )
                    state.update_wallet(False, paper_snapshot)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                # state.log(f"[WalletSync] Error: {e}")
                # Don't spam logs
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
