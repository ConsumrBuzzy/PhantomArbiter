
import time
from dataclasses import dataclass, field
from typing import Dict, Optional
from config.settings import Settings
from src.shared.execution.wallet import WalletManager
from src.shared.execution.swapper import JupiterSwapper
from src.shared.system.priority_queue import priority_queue
from src.strategy.watcher import Watcher
from src.tools.asset_manager import AssetManager
from src.strategy.portfolio import PortfolioManager
from src.shared.infrastructure.validator import TokenValidator
from src.shared.notification.notifications import get_notifier
from src.core.shared_cache import SharedPriceCache
from src.shared.system.logging import Logger


# V10.2 Delegates
from src.engine.data_feed_manager import DataFeedManager
from src.engine.decision_engine import DecisionEngine

# V14.0: Remote Control
import queue
from src.shared.notification.telegram_manager import (
    TelegramManager, CMD_STATUS_REPORT, CMD_STOP_ENGINE,
    CMD_SET_MODE, CMD_SET_SIZE, CMD_SET_BUDGET
)
from src.core.global_state import GlobalState
from src.shared.execution.paper_wallet import PaperWallet

# V40.0: Centralized Capital Management
from src.shared.system.capital_manager import get_capital_manager

# V48.0: Extracted Trade Executor
from src.engine.trade_executor import TradeExecutor

# V48.0: Extracted Heartbeat Reporter
from src.engine.heartbeat_reporter import HeartbeatReporter

# V48.0: Pyth Network Low-Latency Oracle
from src.core.prices.pyth_adapter import PythAdapter

# V48.0: Jito Block Engine for Priority Execution
from src.shared.infrastructure.jito_adapter import JitoAdapter


class TradingCore:
    """
    P0 Orchestrator for the V10.2 SRP Architecture.

    The TradingCore is responsible for the high-frequency event loop (Tick Loop).
    It delegating specialized tasks to sub-components while maintaining
    strict zero-delay execution for the core cycle.

    Priority Level: P0 (Critical execution path, no blocking I/O)

    Attributes:
        wallet (WalletManager): Manages Solana keypairs and balances.
        swapper (JupiterSwapper): Executes trades via Jupiter API.
        portfolio (PortfolioManager): Manages capital allocation and risk state.
        decision_engine (DecisionEngine): Pure logic component for trade analysis.
        data_manager (DataFeedManager): Batched data fetching and injection.
        watchers (dict): Active asset state containers.
    """
    
    def __init__(self, strategy_class=None, engine_name="PRIMARY"):
        """Initialize TradingCore.
        
        Args:
            strategy_class: Optional custom strategy class (e.g., LongtailLogic).
                           Defaults to DecisionEngine if None.
            engine_name: Unique identifier for this engine (e.g. SCALPER, VWAP).
        """
        # priority_queue.add(3, 'LOG', {'level': 'INFO', 'message': "⚡ TRADING CORE INITIALIZING..."})
        
        # 1. Execution Layer
        self.wallet = WalletManager()
        self.swapper = JupiterSwapper(self.wallet)
        
        # 2. Data/Asset Layer
        self.asset_manager = AssetManager()
        
        # V12.8: Live/Mocked Wallet Support
        # V13.0: Async Initialization (Avoids Startup Lag)
        # We start with a default/safe value and update during async initialize()
        initial_capital = 1000.0 if not Settings.ENABLE_TRADING else None
        self.portfolio = PortfolioManager(self.wallet, initial_capital=initial_capital)
        self.validator = TokenValidator()
        
        # 3. Delegates (V10.2 Phase 2)
        self.data_manager = DataFeedManager()
        
        # V11.6: Ensure DB is ready before DecisionEngine queries win rate
        from src.shared.system.db_manager import db_manager
        db_manager.wait_for_connection(timeout=2.0)
        
        # V17.0: Allow custom strategy injection
        if strategy_class:
            self.decision_engine = strategy_class(self.portfolio)
            priority_queue.add(3, 'LOG', {'level': 'INFO', 'message': f"🧠 Strategy: {strategy_class.__name__}"})
        else:
            self.decision_engine = DecisionEngine(self.portfolio)
        
        # 4. Watchers (State)
        self.watchers = {}
        self.scout_watchers = {}
        self.watchlist = []  # V132: Fix for Director / Scout Agent integration
        
        # V11.15: Paper Trade Simulator (Monitor Mode)
        # self.paper_positions removed in V45.0 - using paper_wallet.assets
        self.paper_stats = {'wins': 0, 'losses': 0, 'total_pnl': 0.0}
        
        # V16.0: Paper Wallet (Legacy)
        # V19.0: Engine-isolated (separate wallet per strategy)
        # V45.3: Fund Paper Wallet from Real/Mock State
        # V40.0: Centralized CapitalManager (replaces direct PaperWallet usage)
        self.engine_name = engine_name
        self.capital_mgr = get_capital_manager()
        
        # V45.0: Unified Paper Wallet (Adapter Wrapper)
        # We use the local PaperWallet class (Adapter for CapitalManager)
        # Top-level import handles this.
        self.paper_wallet = PaperWallet(engine_name=engine_name)
        
    async def initialize(self):
        """
        Perform heavy initialization (network/RPC).
        This is called by the Director to prevent blocking the TUI startup.
        """
        if not Settings.ENABLE_TRADING:
            Logger.info(f"🔧 [{self.engine_name}] Initializing Paper Mode Capital...")
            try:
                # This is the blocking call being moved (V13.0)
                initial_capital_data = await asyncio.to_thread(self.wallet.get_current_live_usd_balance)
                initial_capital = initial_capital_data.get('total_usd', 1000.0)
                
                # Update Portfolio
                self.portfolio.initial_capital = initial_capital
                self.portfolio.current_cash = initial_capital
                
                # Sync Paper Wallet
                mock_sol = initial_capital_data.get('breakdown', {}).get('SOL', 1.0)
                self.paper_wallet.init_from_real(initial_capital, mock_sol)
                
                Logger.info(f"✅ [{self.engine_name}] Capital Initialized: ${initial_capital:,.2f}")
            except Exception as e:
                Logger.error(f"❌ [{self.engine_name}] Failed to Init Capital: {e}")
             
        self._last_paper_pnl = 0.0
        
        # V45.0: Tick Counter for scanning heartbeat
        self.tick_count = 0
        
        # V45.6: Track engine start time for uptime display
        self.start_time = time.time()
        
        # V11.10: Force immediate heartbeat on first tick
        self.last_heartbeat = 0
        
        # V40.0: dYdX Adapter (when EXECUTION_MODE == "DYDX" OR DYDX_ENABLED for telemetry)
        
        # V40.0: dYdX Adapter (when EXECUTION_MODE == "DYDX" OR DYDX_ENABLED for telemetry)
        self.execution_mode = getattr(Settings, 'EXECUTION_MODE', 'DEX')
        self.dydx_adapter = None
        dydx_enabled = getattr(Settings, 'DYDX_ENABLED', False)
        
        if self.execution_mode == "DYDX" or dydx_enabled:
            try:
                from src.shared.infrastructure.dydx_adapter import DydxAdapter
                self.dydx_adapter = DydxAdapter(getattr(Settings, 'DYDX_NETWORK', 'testnet'))
                # Only pass mnemonic for full trading; otherwise HTTP-only mode
                mnemonic = getattr(Settings, 'DYDX_MNEMONIC', '') if self.execution_mode == "DYDX" else ''
                self.dydx_adapter.connect_sync(mnemonic if mnemonic else None)
                priority_queue.add(3, 'LOG', {'level': 'INFO', 'message': f"🌐 [{self.engine_name}] dYdX: {self.dydx_adapter}"})
            except Exception as e:
                priority_queue.add(3, 'LOG', {'level': 'WARN', 'message': f"⚠️ [{self.engine_name}] dYdX init failed: {e}"})
        
        # V12.4: Drawdown Protection (Loss Streak Tracking)
        self.consecutive_losses = 0
        
        self.notifier = get_notifier()
        
        # V30.1: System Monitor
        from src.shared.system.monitor import SystemMonitor
        self.monitor = SystemMonitor()
        
        # V36.0: ML Predictive Filter
        self.ml_model = None
        try:
            import os
            import joblib
            model_path = os.path.join(os.path.dirname(__file__), "..", "..", "models", "ml_filter.pkl")
            if os.path.exists(model_path):
                self.ml_model = joblib.load(model_path)
                self._ml_model_mtime = os.path.getmtime(model_path) # V47.0: Track for hot-reload
                priority_queue.add(3, 'LOG', {'level': 'INFO', 'message': "🧠 ML Filter Loaded (V41.0 XGBoost)"})
            else:
                self._ml_model_mtime = 0
                priority_queue.add(3, 'LOG', {'level': 'INFO', 'message': "🧠 ML Filter: No model found (Run train_model.py)"})
        except Exception as e:
            priority_queue.add(3, 'LOG', {'level': 'WARN', 'message': f"⚠️ ML Filter Load Error: {e}"})
        
        # V17.1: Telegram Listener moved to Data Broker
        # Trading Engines sync via GlobalState file
        self.command_queue = queue.Queue()  # Keep for backwards compat (local commands)
        self.telegram_listener = None  # Never start - Data Broker handles this
        
        # Run startup routines
        self._init_watchers()
        
        # V48.0: Initialize TradeExecutor with all dependencies
        self.pyth_adapter = PythAdapter()  # V48.0: Low-latency oracle
        self.jito_adapter = JitoAdapter()  # V48.0: Priority execution
        self.executor = TradeExecutor(
            engine_name=self.engine_name,
            capital_mgr=self.capital_mgr,
            paper_wallet=self.paper_wallet,
            swapper=self.swapper,
            portfolio=self.portfolio,
            ml_model=self.ml_model,
            watchers=self.watchers,
            scout_watchers=self.scout_watchers,
            validator=self.validator,
            pyth_adapter=self.pyth_adapter,
            jito_adapter=self.jito_adapter  # V48.0: Tipped bundle submission
        )
        
        # V48.0: Initialize HeartbeatReporter
        self.reporter = HeartbeatReporter(
            engine_name=self.engine_name,
            paper_wallet=self.paper_wallet,
            portfolio=self.portfolio,
            wallet=self.wallet,
            decision_engine=self.decision_engine,
            dydx_adapter=getattr(self, 'dydx_adapter', None)
        )
        
    def _init_watchers(self):
        """Initialize active watchers from config. V11.4: Scouts deferred to background."""
        active, volatile, watch, scout, all_assets, raw_data, watcher_pairs = Settings.load_assets()
        
        # V32.1: Legacy Strategy Filtering Removed (V45.5 Unified)
        # All Active assets are loaded for the MerchantEnsemble to manage.

        # V11.4: Active tokens ONLY (P0 critical path - must wait for these)
        for symbol, mint in active.items():
            self.watchers[symbol] = Watcher(symbol, mint, validator=self.validator, is_critical=True)
            Logger.info(f"   ✅ Watcher Loaded: {symbol}")
        
    def _process_discovery_watchlist(self):
        """V132: Ingest tokens from discovery watchlist into scout_watchers."""
        if not hasattr(self, 'watchlist') or not self.watchlist:
            return
            
        from src.shared.infrastructure.token_scraper import get_token_scraper
        scraper = get_token_scraper()
        
        # Limit processing to prevent blocking
        to_process = self.watchlist[:5]
        self.watchlist = self.watchlist[5:]
        
        for mint in to_process:
            # Skip if already being watched
            if any(w.mint == mint for w in {**self.watchers, **self.scout_watchers}.values()):
                continue
                
            info = scraper.lookup(mint)
            symbol = info.get("symbol", f"UNK_{mint[:4]}")
            
            # Add to scout watchers (Low priority tracking)
            from src.strategy.watcher import Watcher
            self.scout_watchers[symbol] = Watcher(symbol, mint, validator=self.validator, is_critical=False)
            Logger.info(f"   🔭 [{self.engine_name}] Scout Watcher added: {symbol} ({mint[:8]})")
        # V11.4: Scout tokens deferred to P2 background thread
        # V45.4: Ensure Scouts are initialized even if invoked via DataBroker
        self._pending_scouts = scout  # Dict of {symbol: mint}
        if scout:
            Logger.info(f"⏳ {len(scout)} Scout tokens queued for background init")
            
            def init_scouts_bg():
                import time
                time.sleep(2) # Wait for startup to settle
                for symbol, mint in self._pending_scouts.items():
                    if symbol in self.watchers: continue
                    # Use lighter validation for scouts? Or standard?
                    # V45.4: Scouts are full watchers but tracked separately
                    self.scout_watchers[symbol] = Watcher(symbol, mint, validator=self.validator, is_critical=False)
                    # Don't spam logs for every scout, do batch
                    time.sleep(0.1)
                
                priority_queue.add(3, 'LOG', {'level': 'INFO', 'message': f"✅ {len(self.scout_watchers)} Scouts Initialized"})

            import threading
            t = threading.Thread(target=init_scouts_bg, daemon=True, name=f"ScoutInit-{getattr(self, 'engine_name', 'CORE')}")
            t.start()
        
        # V47.6: Reconcile positions after watchers are created
        self._reconcile_open_positions()
    
    def _reconcile_open_positions(self):
        """
        V47.6: Position Reconciliation on Startup.
        
        Syncs CapitalManager.positions with Watcher.in_position to prevent zombie bags.
        For any position in CapitalManager that doesn't have a matching watcher with 
        in_position=True, we either:
        1. Find the watcher and set in_position=True
        2. Create a temporary watcher for the orphaned position
        """
        try:
            positions = self.capital_mgr.get_all_positions(self.engine_name)
            
            if not positions:
                return
            
            reconciled_count = 0
            orphan_count = 0
            
            for symbol, pos_data in positions.items():
                if pos_data.get('balance', 0) <= 0:
                    continue
                    
                # Try to find matching watcher
                watcher = self.watchers.get(symbol) or self.scout_watchers.get(symbol)
                
                if watcher:
                    # Watcher exists - ensure it knows about the position
                    if not watcher.in_position:
                        watcher.in_position = True
                        watcher.entry_price = pos_data.get('avg_price', 0.0)
                        watcher.cost_basis = pos_data.get('balance', 0) * watcher.entry_price
                        watcher.entry_time = pos_data.get('entry_time', time.time())
                        watcher.token_balance = pos_data.get('balance', 0)
                        reconciled_count += 1
                        priority_queue.add(3, 'LOG', {'level': 'INFO', 'message': f"[V47.6] Reconciled: {symbol} (Entry: ${watcher.entry_price:.6f})"})
                else:
                    # No watcher found - this is a true orphan
                    # Create a scout watcher for it so it can be monitored and exited
                    mint = pos_data.get('mint', '')
                    if mint:
                        try:
                            new_watcher = Watcher(symbol, mint, validator=self.validator, is_critical=False, lazy_init=True)
                            new_watcher.in_position = True
                            new_watcher.entry_price = pos_data.get('avg_price', 0.0)
                            new_watcher.cost_basis = pos_data.get('balance', 0) * new_watcher.entry_price
                            new_watcher.entry_time = pos_data.get('entry_time', time.time())
                            new_watcher.token_balance = pos_data.get('balance', 0)
                            self.scout_watchers[symbol] = new_watcher
                            orphan_count += 1
                            priority_queue.add(3, 'LOG', {'level': 'WARN', 'message': f"[V47.6] Orphan Position Found: {symbol} - Created Scout Watcher"})
                        except Exception as e:
                            priority_queue.add(3, 'LOG', {'level': 'ERROR', 'message': f"[V47.6] Failed to create watcher for orphan {symbol}: {e}"})
            
            if reconciled_count > 0 or orphan_count > 0:
                priority_queue.add(3, 'LOG', {'level': 'SUCCESS', 'message': f"[V47.6] Reconciliation Complete: {reconciled_count} synced, {orphan_count} orphans recovered"})
                
        except Exception as e:
            priority_queue.add(3, 'LOG', {'level': 'ERROR', 'message': f"[V47.6] Reconciliation Error: {e}"})
            

    def _sync_active_positions(self):
        """V12.5: Share active position state with Data Broker."""
        active_list = []
        
        # Check all watchers (Primary + Scout)
        # Note: Iterating values() is safe-ish in thread, but this is main thread anyway.
        for watcher in list(self.watchers.values()) + list(self.scout_watchers.values()):
            if watcher.in_position:
                curr_price = watcher.get_price()
                if watcher.entry_price > 0:
                    pnl_pct = ((curr_price - watcher.entry_price) / watcher.entry_price) * 100
                    pnl_usd = (curr_price * watcher.token_balance) - watcher.cost_basis
                else:
                    pnl_pct = 0.0
                    pnl_usd = 0.0
                    
                active_list.append({
                    "symbol": watcher.symbol,
                    "entry": watcher.entry_price,
                    "current": curr_price,
                    "pnl_pct": pnl_pct,
                    "pnl_usd": pnl_usd,
                    "size_usd": watcher.cost_basis,
                    "timestamp": time.time()
                })
        
        # Write to shared cache
        SharedPriceCache.write_active_positions(active_list)
        
    def reload_ml_model(self):
        """V47.0: Hot-reload ML model if newer version exists."""
        import os
        import joblib
        
        try:
            model_path = os.path.join(os.path.dirname(__file__), "..", "..", "models", "ml_filter.pkl")
            if not os.path.exists(model_path):
                return False
            
            new_mtime = os.path.getmtime(model_path)
            # Reload if newer (or if we have no model yet)
            if not hasattr(self, '_ml_model_mtime') or new_mtime > self._ml_model_mtime:
                self.ml_model = joblib.load(model_path)
                self._ml_model_mtime = new_mtime
                # V48.0: Sync to TradeExecutor
                if hasattr(self, 'executor'):
                    self.executor.update_ml_model(self.ml_model)
                priority_queue.add(3, 'LOG', {'level': 'SUCCESS', 'message': f"[{self.engine_name}] ML Model Hot-Reloaded (V47.0)"})
                return True
        except Exception as e:
            priority_queue.add(3, 'LOG', {'level': 'WARN', 'message': f"[{self.engine_name}] ML reload failed: {e}"})
        return False
            
    # ═══════════════════════════════════════════════════════════════════
    # V14.0 Remote Control Methods
    # ═══════════════════════════════════════════════════════════════════
    # run_live() and run_tick() removed (Legacy V1.0-V40.0)
    # Replaced by scan_signals() and DataBroker loop.

    def set_trading_mode(self, is_live: bool):
        """V14.1: Switch between Monitor and Live mode."""
        from config.settings import Settings
        old_mode = "LIVE" if Settings.ENABLE_TRADING else "MONITOR"
        Settings.ENABLE_TRADING = is_live
        
        # Log and Notify
        mode_str = "LIVE REAL MONEY" if is_live else "MONITOR (PAPER)"
        icon = "🔴" if is_live else "🔧"
        msg = f"{icon} TRADING MODE SWITCHED: {old_mode} -> {mode_str}"
        priority_queue.add(3, 'LOG', {'level': 'WARNING', 'message': f"[{self.engine_name}] {msg}"})
        
        # V15.0: Sync happens automatically next tick via _sync_global_state
        # But for command feedback we notify here.
        
        from src.shared.system.comms_daemon import send_telegram
        send_telegram(msg, source=self.engine_name, priority="HIGH")

    def _sync_global_state(self):
        """V15.0: Read shared global state and update internal settings."""
        state = GlobalState.read_state()
        
        # 1. Sync Mode (V39.9: Check LIVE_ENGINE_TARGET)
        global_mode = state.get("MODE", "MONITOR")
        live_target = state.get("LIVE_ENGINE_TARGET", None)
        
        # V39.9: Only enable live trading if I'm the targeted engine
        if global_mode == "LIVE" and live_target:
            should_be_live = (live_target == self.engine_name)
        else:
            should_be_live = False  # MONITOR mode or no target = paper trading
        
        if Settings.ENABLE_TRADING != should_be_live:
             # State mismatch! Update local state
             Settings.ENABLE_TRADING = should_be_live
             if should_be_live:
                 mode_str = f"🔴 LIVE (I am the target: {live_target})"
             else:
                 mode_str = f"🟢 MONITOR"
             priority_queue.add(3, 'LOG', {'level': 'WARNING', 'message': f"🔄 SYNC: {mode_str}"})
             
        # 2. Sync Size
        global_size = state.get("BASE_SIZE_USD", 50.0)
        if Settings.POSITION_SIZE_USD != global_size:
            Settings.POSITION_SIZE_USD = global_size
            priority_queue.add(4, 'LOG', {'level': 'INFO', 'message': f"🔄 SYNC: Size -> ${global_size}"})
            
        # 3. Sync Budget
        global_budget = state.get("MAX_EXPOSURE_USD", 1000.0)
        if getattr(Settings, 'MAX_TOTAL_EXPOSURE_USD', 0) != global_budget:
            Settings.MAX_TOTAL_EXPOSURE_USD = global_budget
            self.portfolio.set_max_exposure(global_budget)

    # ═══════════════════════════════════════════════════════════════════
    # V45.0: Unified Merchant Methods (Data Broker Integration)
    # ═══════════════════════════════════════════════════════════════════

    def scan_signals(self) -> list:
        """
        V45.0: Generate signals without executing them.
        Used by DataBroker to collect and resolve conflicts.
        """
        # V132: Ingest new tokens from Discovery before scanning
        self._process_discovery_watchlist()

        signals = []
        combined_watchers = {**self.watchers, **self.scout_watchers}
        
        # Sync logic from run_tick
        self.tick_count += 1
        
        # V45.0: Ensure Heartbeat Logs Visualization
        self._perform_maintenance_and_heartbeat()
        
        self.portfolio.update_cash(self.watchers)
        self.data_manager.update_prices(self.watchers, self.scout_watchers)
        
        for symbol, watcher in combined_watchers.items():
            price = watcher.data_feed.get_last_price()
            if price <= 0: continue
            
            # V45.6: Check exits for Paper Wallet assets (source of truth for paper holdings)
            if not Settings.ENABLE_TRADING and symbol in self.paper_wallet.assets:
                asset = self.paper_wallet.assets[symbol]
                entry_price = asset.avg_price
                if entry_price > 0:
                    current_pnl_pct = (price - entry_price) / entry_price
                    
                    # Check Stop Loss
                    if current_pnl_pct <= Settings.STOP_LOSS_PCT:
                        signals.append({
                            "engine": self.engine_name,
                            "symbol": symbol,
                            "action": "SELL",
                            "reason": f"🚨 SCALPER CRITICAL EXIT: TSL HIT (${price:.4f}) (Net: {current_pnl_pct*100:.1f}%)",
                            "size_usd": 0,
                            "price": price,
                            "confidence": 1.0,
                            "watcher": watcher
                        })
                        continue  # Don't check for buy signals
                    
                    # Check Take Profit
                    if current_pnl_pct >= Settings.TAKE_PROFIT_PCT:
                        signals.append({
                            "engine": self.engine_name,
                            "symbol": symbol,
                            "action": "SELL",
                            "reason": f"💰 TAKE PROFIT (+{current_pnl_pct*100:.2f}%)",
                            "size_usd": 0,
                            "price": price,
                            "confidence": 1.0,
                            "watcher": watcher
                        })
                        continue
            
            # Analyze
            action, reason, size_usd = self.decision_engine.analyze_tick(watcher, price)
            
            if action in ['BUY', 'SELL']:
                # Calculate ML Confidence
                confidence = 0.5 # Default neutral
                if self.ml_model:
                    try:
                        import numpy as np
                        rsi = watcher.get_rsi()
                        atr = watcher.data_feed.get_atr() if hasattr(watcher.data_feed, 'get_atr') else 0.0
                        volatility_pct = (atr / price * 100) if price > 0 else 0.0
                        log_liq = np.log1p(watcher.get_liquidity())
                        latency = 50 
                        features = np.array([[rsi, volatility_pct, log_liq, latency]])
                        confidence = self.ml_model.predict_proba(features)[0][1]
                    except:
                        pass
                
                # V85.1: Apply Whale Vouch Bonus
                try:
                    from src.shared.infrastructure.smart_scraper import get_scrape_intelligence
                    scrape = get_scrape_intelligence()
                    if hasattr(watcher, 'mint') and scrape.has_whale_vouch(watcher.mint):
                        bonus = getattr(Settings, 'WHALE_VOUCH_BONUS', 0.15)
                        confidence += bonus
                        reason = f"🐋 WHALE VOUCHED (+{bonus*100:.0f}%) | {reason}"
                except:
                    pass
                
                signals.append({
                    "engine": self.engine_name,
                    "symbol": symbol,
                    "action": action,
                    "reason": reason,
                    "size_usd": size_usd,
                    "price": price,
                    "confidence": confidence,
                    "watcher": watcher
                })
        
        # V89.0: Cache results for status reporting
        self._last_scan_results = {
            "tracked": len(combined_watchers),
            "signals": len(signals),
            "best_play": None
        }

        # V90.0: Live Dashboard Feed (Price Watch)
        # We assume 'state' is available globally
        from src.shared.state.app_state import state
        # Batch update pulse
        pulse_data = {}
        for s, w in combined_watchers.items():
            price = w.get_price()
            rsi = w.get_rsi()
            pulse_data[s] = {"price": price, "rsi": rsi, "conf": 0.0}
            
            # Enrich with signal info if available
            # (Matches are expensive, we do it in dashboard usually, but we can hint here)
        
        # Merge signal confidences
        for s in signals:
            if s['symbol'] in pulse_data:
                pulse_data[s['symbol']]['conf'] = s['confidence']
                pulse_data[s['symbol']]['action'] = s['action']

        state.update_pulse_batch(pulse_data)

        # Find best candidate (even if not a signal yet, or just the best signal)
        best_conf = 0
        best_sym = None
        
        for s in signals:
            if s['confidence'] > best_conf:
                best_conf = s['confidence']
                best_sym = s['symbol']
                
        if best_sym:
            self._last_scan_results['best_play'] = {"symbol": best_sym, "conf": best_conf}
        
        return signals

    def get_status_summary(self) -> str:
        """V89.0: Return a human-readable status pulse."""
        if not hasattr(self, '_last_scan_results'):
            return "Warming up..."
            
        res = self._last_scan_results
        tracked = res.get('tracked', 0)
        best = res.get('best_play')
        
        pulse = f"Tracking {tracked} assets."
        if best:
            pulse += f" Top Play: {best['symbol']} ({best['conf']*100:.0f}% Conf)."
        else:
            pulse += " Waiting for setup..."
            
        return pulse

    def _perform_maintenance_and_heartbeat(self):
        """V45.0: Shared maintenance and logging logic for run_tick and scan_signals."""
        # 1. Maintenance (Every 10 ticks)
        if self.tick_count % 10 == 0:
            self.wallet.check_and_replenish_gas(self.swapper)
        
        # V12.5: Sync active positions (Every 5 seconds)
        import time
        now = time.time()
        if not hasattr(self, 'last_sync_active'):
             self.last_sync_active = 0
             
        if now - self.last_sync_active >= 5:
             self.last_sync_active = now
             self._sync_active_positions()
        
        # V11.10: Heartbeat logging (every 60 seconds)
        if not hasattr(self, 'last_heartbeat'):
            self.last_heartbeat = now
        
        if now - self.last_heartbeat >= 60:
            self.last_heartbeat = now
            active_positions = sum(1 for w in self.watchers.values() if w.in_position)
            scout_positions = sum(1 for w in self.scout_watchers.values() if w.in_position)
            total_watchers = len(self.watchers) + len(self.scout_watchers)
            
            # V11.14: Enhanced heartbeat with more detail
            engine = getattr(self, 'engine_name', 'PRIMARY')
            uptime_min = int((now - getattr(self, 'start_time', now)) / 60) if hasattr(self, 'start_time') else 0
            dsa_mode = getattr(self.decision_engine, 'mode', 'NORMAL')
            
            # V13.0: Wallet Visibility
            usdc_bal = self.portfolio.cash_available
            sol_bal = 0.0
            # V13.2: Full Wallet Visibility (Cached)
            wallet_state = self.wallet.get_current_live_usd_balance()
            usdc_bal = wallet_state.get('breakdown', {}).get('USDC', 0.0)
            sol_bal = wallet_state.get('breakdown', {}).get('SOL', 0.0)
            bags = wallet_state.get('assets', [])
            
            # Identify Top 3 Bags
            top_bags_str = ""
            if bags:
                top_bags = bags[:3]
                bag_list = [f"{b['symbol']} (${b['usd_value']:.0f})" for b in top_bags]
                top_bags_str = f"\n• Bags: {', '.join(bag_list)}"
                if len(bags) > 3: top_bags_str += f" +{len(bags)-3}"

            # V16.0: Paper Wallet Stats
            paper_section = ""
            if not Settings.ENABLE_TRADING and self.paper_wallet.initialized:
                # Calc paper value
                price_map = {}
                for s, w in self.watchers.items(): price_map[s] = w.get_price()
                for s, w in self.scout_watchers.items(): price_map[s] = w.get_price()
                
                paper_val = self.paper_wallet.get_total_value(price_map)
                real_val = wallet_state.get('total_usd', usdc_bal)
                
                # Comparison
                diff = paper_val - self.paper_wallet.initial_capital
                pct = (diff / self.paper_wallet.initial_capital) * 100 if self.paper_wallet.initial_capital > 0 else 0
                emoji = "📈" if diff >= 0 else "📉"
                
                # V19.3: Paper Bags (Held Assets)
                paper_bags_str = ""
                if self.paper_wallet.assets:
                    paper_bags = []
                    for sym, asset in list(self.paper_wallet.assets.items())[:5]:
                        asset_price = price_map.get(sym, asset.avg_price)
                        asset_val = asset.balance * asset_price
                        
                        # V45.4: Show PnL% per trade
                        pnl_pct = ((asset_price - asset.avg_price) / asset.avg_price * 100) if asset.avg_price > 0 else 0.0
                        emoji_bag = "🟢" if pnl_pct > 0 else "🔴" if pnl_pct < 0 else "⚪"
                        
                        qty_str = f"{asset.balance:.0f}" if asset.balance > 100 else f"{asset.balance:.3f}"
                        paper_bags.append(f"{emoji_bag} {sym}: {qty_str} (${asset_val:.2f}) {pnl_pct:+.1f}%")
                    paper_bags_str = f"\n• 📦 Bags: {', '.join(paper_bags)}"
                    if len(self.paper_wallet.assets) > 5:
                        paper_bags_str += f" +{len(self.paper_wallet.assets)-5}"
                
                # V45.4: Detailed Breakdown
                details = self.paper_wallet.get_detailed_balance(price_map)
                
                paper_section = (
                    f"\n🎰 **PAPER {self.paper_wallet.engine_name}**\n"
                    f"• Value: ${details['total_equity']:.2f} ({emoji} {pct:+.2f}%)\n"
                    f"• 💵 ${details['cash']:.2f} | ⛽ ${details['gas_usd']:.2f} | 📦 ${details['assets_usd']:.2f}\n"
                    f"• W/L: {self.paper_wallet.stats['wins']}/{self.paper_wallet.stats['losses']} | Fees: ${self.paper_wallet.stats['fees_paid_usd']:.2f}"
                    f"{paper_bags_str}"
                )
                
                # Console log update
                bag_count = len(self.paper_wallet.assets)
                gas_usd = self.paper_wallet.stats['fees_paid_usd']
                gas_bal = self.paper_wallet.sol_balance
                priority_queue.add(4, 'LOG', {'level': 'INFO', 'message': f"[{engine}] 🎰 PAPER: ${paper_val:.2f} ({pct:+.2f}%) | Bags: {bag_count} | Gas: {gas_bal:.3f} SOL | REAL: ${real_val:.2f}"})

            # V40.0: Get CEX prices for dual-market visibility
            cex_section = ""
            if hasattr(self, '  ') and self.dydx_adapter and self.dydx_adapter.is_connected:
                try:
                    eth = self.dydx_adapter.get_ticker_sync("ETH-USD")
                    btc = self.dydx_adapter.get_ticker_sync("BTC-USD")
                    sol = self.dydx_adapter.get_ticker_sync("SOL-USD")
                    if eth or btc or sol:
                        cex_prices = []
                        if eth: cex_prices.append(f"ETH ${eth['price']:,.0f}")
                        if btc: cex_prices.append(f"BTC ${btc['price']:,.0f}")
                        if sol: cex_prices.append(f"SOL ${sol['price']:.2f}")
                        cex_section = f"\n🌐 CEX: {' | '.join(cex_prices)}"
                except:
                    pass
            
            heartbeat_msg = (
                f"💓 Heartbeat\n"
                f"• Ticks: {self.tick_count} | Watchers: {total_watchers}\n"
                f"• Positions: {active_positions}A / {scout_positions}S\n"
                f"• DSA: {dsa_mode} | Cash: ${usdc_bal:.2f}\n"
                f"• Wallet: ${usdc_bal:.2f} (USDC) | {sol_bal:.3f} SOL{top_bags_str}"
                f"{cex_section}\n"
                f"• Uptime: {uptime_min}m"
                f"{paper_section}"
            )
            
            if not paper_section:
                 priority_queue.add(4, 'LOG', {'level': 'INFO', 'message': f"[{engine}] 💓 {self.tick_count}t | {active_positions}A/{scout_positions}S | ${usdc_bal:.0f} | {sol_bal:.2f} SOL"})
            
            # V45.4: Console Heartbeat (User Request)
            # V78.0: DISABLED - Dashboard now handles heartbeat display
            pass  # Old heartbeat code removed - see dashboard_service.py

    def execute_signal(self, signal: dict):
        """V45.0: Execute a resolved signal (called by DataBroker).
        V48.0: Delegates to TradeExecutor.
        V79.0: Confidence-based position sizing.
        """
        action = signal.get("action")
        watcher = signal.get("watcher")
        price = signal.get("price")
        reason = signal.get("reason")
        size_usd = signal.get("size_usd")
        confidence = signal.get("confidence", 0.5)  # V79.0: Get confidence
        
        # V85.1: Enforce Dynamic Confidence Thresholds
        is_live = Settings.ENABLE_TRADING
        min_conf = getattr(Settings, 'LIVE_MIN_CONFIDENCE', 0.85) if is_live else getattr(Settings, 'PAPER_MIN_CONFIDENCE', 0.45)
        
        if action == "BUY" and confidence < min_conf:
            from src.shared.system.logging import Logger
            Logger.debug(f"🛑 REJECTED: Low Confidence {confidence:.2f} < {min_conf:.2f} (Paper: {'OFF' if is_live else 'ON'})")
            return
            
        # V79.0: Apply confidence-based position sizing
        size_usd = self._confidence_to_size(confidence, size_usd)
        
        # V48.0: Sync watchers to executor (in case of changes)
        self.executor.update_watchers(self.watchers, self.scout_watchers)
        
        if action == "BUY":
            self.executor.execute_buy(watcher, price, reason, size_usd, self.decision_engine)
        elif action == "SELL":
            result = self.executor.execute_sell(watcher, price, reason)
            # V48.0: Sync consecutive losses back from executor
            self.consecutive_losses = self.executor.consecutive_losses
    
    def _confidence_to_size(self, confidence: float, base_size: float) -> float:
        """
        V79.0: Map confidence to position size.
        
        Tiers:
        - HIGH (>0.75): 30% of cash
        - MEDIUM (0.5-0.75): 10% of cash
        - LOW (<0.5): 5% of cash
        
        Returns:
            Position size in USD
        """
        from src.shared.system.capital_manager import get_capital_manager
        
        try:
            cm = get_capital_manager()
            engine = cm.get_engine_state(self.engine_name)
            if not engine:
                return base_size
                
            cash = engine.get("cash_balance", 0)
            
            # Determine tier
            if confidence >= 0.75:
                # HIGH confidence
                pct = Settings.POSITION_SIZE_HIGH_PCT
                tier = "HIGH"
            elif confidence >= 0.50:
                # MEDIUM confidence
                pct = Settings.POSITION_SIZE_MED_PCT
                tier = "MED"
            else:
                # LOW confidence
                pct = Settings.POSITION_SIZE_LOW_PCT
                tier = "LOW"
            
            # Calculate size
            tier_size = cash * pct
            
            # Cap at base_size (which may already be capped by settings)
            final_size = min(tier_size, base_size, Settings.POSITION_SIZE_USD)
            
            Logger.debug(f"[V79.0] Confidence {confidence:.2f} → {tier} tier → ${final_size:.2f} (was ${base_size:.2f})")
            
            return final_size
            
        except Exception as e:
            Logger.debug(f"[V79.0] Confidence sizing error: {e}")
            return base_size
    
    def _paper_buy(self, symbol: str, price: float, reason: str, size_usd: float):
        """V11.15: Log paper position entry (Logic handled by CapitalManager)."""
        
        # V39.2: Integrity Check - Ensure Watcher exists to get mint
        watcher = self.watchers.get(symbol) or self.scout_watchers.get(symbol)
        
        # V45.0 Cleaned up PaperPosition creation - utilizing PaperWallet logic in execute_buy
        # This method is now purely for LOGGING side-effects
         
        # V12.2: Get volatility for log
        from src.system.data_source_manager import DataSourceManager
        dsm = DataSourceManager()
        volatility = dsm.get_volatility(symbol)
        
        # V12.6: Update Watcher Timestamp
        if watcher: watcher.last_signal_time = time.time()
        
        # V51.0: Use Template
        from src.system.telegram_templates import TradeTemplates
        msg = TradeTemplates.entry(
            symbol=symbol,
            action="BUY",
            amount=size_usd,
            price=price,
            engine="PAPER (Legacy)",
            reason=f"{reason} (Vol: {volatility:.1f}%)"
        )
        send_telegram(msg, source="PAPER", priority="LOW")
        
        # V51.0: Rich Console Log
        Logger.info(f"[PAPER] 📝 BUY {symbol} @ ${price:.6f} ({reason})")
        send_telegram(msg, source="PAPER", priority="LOW")
    
    def get_held_mints(self) -> dict:
        """V45.4: Get mints for all held positions (Real + Paper) to ensure data feed continuity."""
        held = {}
        # Real
        for s, w in self.watchers.items():
            if w.in_position: held[s] = w.mint
            
        # Paper (Source of Truth: PaperWallet)
        for s in self.paper_wallet.assets.keys():
            # Try to find mint in watchers
            w = self.watchers.get(s) or self.scout_watchers.get(s)
            if w: held[s] = w.mint
            
        return held
    
    # ═══════════════════════════════════════════════════════════════════
    # V48.0: _execute_buy and _execute_sell removed
    # These methods have been extracted to TradeExecutor (trade_executor.py)
    # Execution now delegated via self.executor in execute_signal()
