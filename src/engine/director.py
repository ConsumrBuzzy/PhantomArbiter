import asyncio
import time
from typing import Optional
from src.shared.state.app_state import state
from src.shared.infrastructure.websocket_listener import WebSocketListener
from src.arbiter.arbiter import PhantomArbiter, ArbiterConfig
from src.scalper.engine import ScalperConfig

class PhantomScalperEngine:
    def __init__(self, config):
        self.config = config
        self.watchlist = []
    
    async def run_cycle(self):
        # Logic: Check watchlist -> Execute Strategy
        pass

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
        class MockPriceCache:
            def update_price(self, mint, price): pass
        
        self.price_cache = MockPriceCache()
        self.watched_mints = {"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC"}
        
        self.listener = WebSocketListener(self.price_cache, self.watched_mints)
        
        # V9.0: Chaos Shield (Security)
        from src.shared.system.chaos_shield import chaos_shield
        self.chaos = chaos_shield
        
        # 1. ARBITER (Atomic)
        arb_config = ArbiterConfig(live_mode=live_mode) 
        self.arbiter = PhantomArbiter(arb_config)
        
        # 2. SCALPER (Inventory)
        scalp_config = ScalperConfig(live_mode=live_mode)
        self.scalper = PhantomScalperEngine(scalp_config)
        
        # 3. SCOUT (Discovery)
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
        # We start the arbiter run loop in the background
        self.fast_tasks.append(asyncio.create_task(
            self.arbiter.run(duration_minutes=0, scan_interval=2)
        ))
        
        # 3. THE MERCHANT (Mid Lane) - Scalper
        # The Scalper is integrated into the ArbiterEngine via signals 
        # but we can also run a dedicated scalper loop if needed.
        # For now, we've hooked ArbiterEngine and DataBroker.
        
        # 4. THE SCOUT (Slow Lane)
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
        """Mid Lane: Scalping Strategy."""
        state.log("[Director] Scalper: Active (Interval: 2s)")
        from src.shared.state.app_state import ScalpSignal
        import random
        
        while self.is_running:
            try:
                await asyncio.sleep(2)
                
                # Mock Signal Generation for Dashboard Visualization
                # In prod, this comes from self.scalper.run_cycle()
                if random.random() < 0.3: # 30% chance every 2s
                    sigs = [
                        ("BONK", "RSI Oversold", "High", "BUY"),
                        ("WIF", "Breakout", "Med", "BUY"),
                        ("JUP", "MA Cross", "Low", "WAIT"),
                        ("POPCAT", "Volume Spike", "High", "BUY")
                    ]
                    s = random.choice(sigs)
                    signal = ScalpSignal(token=s[0], signal_type=s[1], confidence=s[2], action=s[3])
                    state.add_signal(signal)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                state.log(f"[Scalper] Error: {e}")

    async def _run_scout_loop(self):
        """Slow Lane: Token Discovery."""
        state.log("[Director] Scout Agent: Active (Interval: 60s)")
        while self.is_running:
            try:
                # 1. Sleep first
                await asyncio.sleep(60)
                
                # 2. Perform Scan (Mock)
                # new_tokens = await self.scout.scan()
                new_tokens = ["MOCK_TOKEN"] # Mock
                
                # 3. Feed Scalper
                if new_tokens:
                    self.scalper.watchlist.extend(new_tokens)
                    state.log(f"[Scout] Found {len(new_tokens)} targets -> Passed to Scalper")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                state.log(f"[Scout] Error: {e}")

    async def _run_whale_loop(self):
        """Slow Lane: Smart Money Tracker."""
        state.log("[Director] Whale Watcher: Active (Interval: 300s)")
        while self.is_running:
            try:
                await asyncio.sleep(300)
                # await self.whale.track()
            except asyncio.CancelledError:
                break
            except Exception as e:
                state.log(f"[Whale] Error: {e}")

    async def _run_state_sync(self):
        """
        Dashboard 2.0: Synchronize Wallet & Inventory State.
        Polls underlying CapitalManager (via PaperWallet adapter) and pushes to AppState.
        """
        from src.shared.state.app_state import WalletData
        
        while self.is_running:
            try:
                await asyncio.sleep(1.0) # 1Hz Refresh
                
                # 1. Fetch from Arbiter's Wallet Adapter (Primary Source)
                # Note: Arbiter uses PaperWallet which wraps CapitalManager
                wallet_adapter = self.arbiter.executor.wallet
                
                # We need a mock price map for value calculation
                # In real V2, we'd use Oracle prices.
                price_map = {'SOL': 150.0} # Mock SOL Price
                
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
