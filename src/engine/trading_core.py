
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
from src.shared.system.logging import Logger
from src.shared.system.signal_bus import signal_bus, SignalType, Signal


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

# V133: SharedPriceCache for position sync
from src.core.shared_cache import SharedPriceCache

# V133: Notification service
from src.shared.notification.notifications import get_notifier

# V133: WatcherManager (SRP Refactor)
from src.engine.watcher_manager import WatcherManager

# V133: SignalScanner (SRP Refactor)
from src.engine.signal_scanner import SignalScanner

# V67.0: Phase 5 - Institutional Realism
from src.engine.shadow_manager import ShadowManager
from src.engine.slippage_calibrator import SlippageCalibrator
from src.engine.congestion_monitor import CongestionMonitor

# V133: MaintenanceService (SRP Refactor)
from src.engine.maintenance_service import MaintenanceService

# V133: ConfigSyncService (SRP Refactor)
from src.engine.config_sync_service import ConfigSyncService

# V133: PositionSizer (SRP Refactor)
from src.engine.position_sizer import PositionSizer


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
    
    def __init__(self, strategy_class=None, engine_name="PRIMARY", registry: Dict = None):
        """Initialize TradingCore.
        
        Args:
            strategy_class: Optional custom strategy class (e.g., LongtailLogic).
                           Defaults to DecisionEngine if None.
            engine_name: Unique identifier for this engine (e.g. SCALPER, VWAP).
        """
        # priority_queue.add(3, 'LOG', {'level': 'INFO', 'message': "⚡ TRADING CORE INITIALIZING..."})
        
        # Store engine name for later use
        self.engine_name = engine_name
        self.registry = registry or {}
        
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
        
        # 4. Watchers (State) - V133: Delegated to WatcherManager
        self.watcher_mgr = WatcherManager(validator=self.validator, engine_name=engine_name)
        # Legacy accessors for backward compatibility
        self.watchers = self.watcher_mgr.watchers
        self.scout_watchers = self.watcher_mgr.scout_watchers
        self.watchlist = self.watcher_mgr.watchlist
        
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
        
        # V49.0: Unified Execution Backend (Paper = Live parity)
        from src.shared.execution.execution_backend import PaperBackend, LiveBackend
        if Settings.ENABLE_TRADING:
            self.execution_backend = LiveBackend(swapper=self.swapper, engine_name=self.engine_name)
        else:
            self.execution_backend = PaperBackend(capital_manager=self.capital_mgr, engine_name=self.engine_name)
        
        # V67.0: Phase 5 - Shadow Manager for Paper/Live Audit
        self.shadow_manager = ShadowManager()
        
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
            jito_adapter=self.jito_adapter,  # V48.0: Tipped bundle submission
            execution_backend=self.execution_backend,  # V49.0: Unified backend
            shadow_manager=self.shadow_manager # V67.0: Audit Hook
        )
        
        # V67.0: Phase 5 - Shadow Manager moved up
        # self.shadow_manager = ShadowManager()
        
            # V67.0: Phase 5C - Auto-Slippage Calibrator
        # Wire calibrator to executor for drift-reactive slippage adjustment
        try:
            try:
                from phantom_core import ScorerConfig
            except ImportError:
                # Fallback to Python implementation
                from src.shared.models.scorer_config import ScorerConfig
                Logger.info("⚠️ [CORE] phantom_core not found, using Python ScorerConfig fallback")

            scorer_config = ScorerConfig(
                min_profit_usd=getattr(Settings, 'MIN_PROFIT_USD', 0.10),
                max_slippage_bps=getattr(Settings, 'SLIPPAGE_MAX_BPS', 300),
                gas_fee_usd=getattr(Settings, 'GAS_FEE_USD', 0.02),
                jito_tip_usd=getattr(Settings, 'JITO_TIP_USD', 0.001),
                dex_fee_bps=getattr(Settings, 'DEX_FEE_BPS', 30),
                default_trade_size_usd=getattr(Settings, 'MAX_POSITION_SIZE_USD', 15.0)
            )
            self.slippage_calibrator = SlippageCalibrator(
                scorer_config=scorer_config,
                shadow_manager=self.shadow_manager
            )
            self.executor.slippage_calibrator = self.slippage_calibrator
            Logger.info("⚙️ [CORE] SlippageCalibrator wired to TradeExecutor")
        except Exception as e:
            Logger.warn(f"⚙️ [CORE] SlippageCalibrator init skipped: {e}")
            self.slippage_calibrator = None
            
        # V67.0: Phase 5D - Congestion Multiplier
        # Wire monitor to executor for dynamic Jito tipping
        try:
            self.congestion_monitor = CongestionMonitor(
                shadow_manager=self.shadow_manager,
                jito_adapter=self.jito_adapter,
                base_tip_lamports=getattr(Settings, 'JITO_TIP_LAMPORTS', 10000)
            )
            self.executor.congestion_monitor = self.congestion_monitor
            Logger.info("🔥 [CORE] CongestionMonitor wired to TradeExecutor")
        except Exception as e:
            Logger.warn(f"🔥 [CORE] CongestionMonitor init skipped: {e}")
            self.congestion_monitor = None
        
        # V48.0: Initialize HeartbeatReporter
        self.heartbeat = HeartbeatReporter(
            engine_name=self.engine_name,
            paper_wallet=self.paper_wallet,
            portfolio=self.portfolio,
            wallet=self.wallet,
            decision_engine=self.decision_engine,
            dydx_adapter=getattr(self, 'dydx_adapter', None)
        )
        
        # V133: SignalScanner (SRP Refactor)
        self.signal_scanner = SignalScanner(
            engine_name=self.engine_name,
            decision_engine=self.decision_engine,
            paper_wallet=self.paper_wallet,
            ml_model=self.ml_model,
            registry=self.registry
        )
        
        # V133: MaintenanceService (SRP Refactor)
        self.maintenance = MaintenanceService(engine_name=self.engine_name)
        
        # V133: ConfigSyncService (SRP Refactor)
        self.config_sync = ConfigSyncService(
            engine_name=self.engine_name,
            portfolio=self.portfolio
        )
        
        # V133: PositionSizer (SRP Refactor)
        self.position_sizer = PositionSizer(engine_name=self.engine_name)
        
        # Phase 33: SignalBus Subscription (Scout-Fed Scalping)
        def handle_scout_signal(sig: Signal):
            token = sig.data.get("symbol")
            mint = sig.data.get("mint") or sig.data.get("symbol") # In case symbol is used as mint
            if mint:
                Logger.info(f"🔭 [Scalper] Feeding Scout signal: {token} ({mint[:8]})")
                # Add to watchlist for next scan
                if mint not in self.watchlist:
                    self.watchlist.append(mint)
        
        signal_bus.subscribe(SignalType.SCOUT, handle_scout_signal)
        
    def set_live_mode(self, live: bool):
        """Dynamically switch between LIVE and PAPER modes."""
        Logger.info(f"🔄 [{self.engine_name}] Switching to {'LIVE' if live else 'PAPER'} mode...")
        self.executor.live_mode = live
        
        # Sync Settings (Legacy compat for other components that haven't been refactored yet)
        # Settings.ENABLE_TRADING = live 
        # Note: We avoid changing global Settings if possible to keep isolation,
        # but some legacy path might still need it. 
        # For now, we rely on the refactored Executor.
        
        # update portfolio state if needed
        if live:
            self.portfolio.initial_capital = None # Using real wallet balance
        else:
            if not self.portfolio.initial_capital:
                self.portfolio.initial_capital = 1000.0
        
    def _init_watchers(self):
        """Initialize active watchers from config. V133: Delegates to WatcherManager."""
        self.watcher_mgr.init_watchers()
        # Keep legacy references in sync
        self.watchers = self.watcher_mgr.watchers
        self.scout_watchers = self.watcher_mgr.scout_watchers
        
    def _process_discovery_watchlist(self):
        """V133: Delegates to WatcherManager."""
        self.watcher_mgr.process_discovery_watchlist()
        # Sync legacy refs and trigger reconciliation
        self.scout_watchers = self.watcher_mgr.scout_watchers
        self._reconcile_open_positions()
    
    def _reconcile_open_positions(self):
        """V133: Delegates to WatcherManager."""
        self.watcher_mgr.reconcile_open_positions()
        # Sync scout_watchers in case orphans were added
        self.scout_watchers = self.watcher_mgr.scout_watchers

    def _sync_active_positions(self):
        """V133: Delegates to WatcherManager."""
        self.watcher_mgr.sync_active_positions()
        
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
        """V133: Delegates to ConfigSyncService."""
        self.config_sync.sync()

    # ═══════════════════════════════════════════════════════════════════
    # V45.0: Unified Merchant Methods (Data Broker Integration)
    # ═══════════════════════════════════════════════════════════════════

    def scan_signals(self) -> list:
        """V133: Delegates to SignalScanner."""
        # V132: Ingest new tokens from Discovery before scanning
        self._process_discovery_watchlist()
        
        # Sync logic
        self.tick_count += 1
        self._perform_maintenance_and_heartbeat()
        
        # V134: Safety check - signal_scanner may not be initialized yet
        if not hasattr(self, 'signal_scanner') or self.signal_scanner is None:
            return []
        
        # Delegate to SignalScanner
        return self.signal_scanner.scan_signals(
            watchers=self.watchers,
            scout_watchers=self.scout_watchers,
            data_manager=self.data_manager,
            portfolio=self.portfolio,
            tick_count=self.tick_count
        )

    def get_status_summary(self) -> str:
        """V133: Delegates to SignalScanner."""
        if not hasattr(self, 'signal_scanner') or self.signal_scanner is None:
            return "Initializing..."
        return self.signal_scanner.get_status_summary()


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
        V134: Added null safety checks.
        """
        action = signal.get("action")
        watcher = signal.get("watcher")
        price = signal.get("price")
        reason = signal.get("reason")
        size_usd = signal.get("size_usd") or Settings.POSITION_SIZE_USD  # V133: Default if None
        confidence = signal.get("confidence", 0.5)  # V79.0: Get confidence
        
        # V134: Null safety - skip if critical values are missing
        if not watcher:
            from src.shared.system.logging import Logger
            Logger.debug(f"🛑 REJECTED: No watcher in signal")
            return
        if price is None or price <= 0:
            # Try to get price from watcher
            price = watcher.get_price() if hasattr(watcher, 'get_price') else 0.0
            if price is None or price <= 0:
                from src.shared.system.logging import Logger
                Logger.debug(f"🛑 REJECTED: No valid price for {getattr(watcher, 'symbol', 'unknown')}")
                return
        
        # V134: Ensure executor is initialized
        if not hasattr(self, 'executor') or self.executor is None:
            from src.shared.system.logging import Logger
            Logger.debug(f"🛑 REJECTED: Executor not initialized")
            return
        
        # V85.1: Enforce Dynamic Confidence Thresholds
        is_live = Settings.ENABLE_TRADING
        min_conf = getattr(Settings, 'LIVE_MIN_CONFIDENCE', 0.85) if is_live else getattr(Settings, 'PAPER_MIN_CONFIDENCE', 0.45)
        
        # V134: Null safety for confidence
        if confidence is None:
            confidence = 0.5
        
        if action == "BUY" and confidence < min_conf:
            from src.shared.system.logging import Logger
            Logger.debug(f"🛑 REJECTED: Low Confidence {confidence:.2f} < {min_conf:.2f} (Paper: {'OFF' if is_live else 'ON'})")
            return
        
        # V134: Null safety for size_usd before calculation
        if size_usd is None or size_usd <= 0:
            size_usd = Settings.POSITION_SIZE_USD
            
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
        """V133: Delegates to PositionSizer."""
        return self.position_sizer.calculate_size(confidence, base_size)
    
    def _paper_buy(self, symbol: str, price: float, reason: str, size_usd: float):
        """V11.15: Log paper position entry (Logic handled by CapitalManager)."""
        
        # V39.2: Integrity Check - Ensure Watcher exists to get mint
        watcher = self.watchers.get(symbol) or self.scout_watchers.get(symbol)
        
        # V45.0 Cleaned up PaperPosition creation - utilizing PaperWallet logic in execute_buy
        # This method is now purely for LOGGING side-effects
         
        # V12.2: Get volatility for log
        from src.shared.system.data_source_manager import DataSourceManager
        dsm = DataSourceManager()
        volatility = dsm.get_volatility(symbol)
        
        # V12.6: Update Watcher Timestamp
        if watcher: watcher.last_signal_time = time.time()
        
        # V51.0: Use Template
        from src.shared.system.telegram_templates import TradeTemplates
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
