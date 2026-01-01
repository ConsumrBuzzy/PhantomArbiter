#!/usr/bin/env python3
"""
PHANTOM TRADER V7.1 - Data Broker
=================================
Centralized data fetcher for dual-engine architecture.
Handles all WSS/RPC calls and writes to shared cache.

Usage:
  python data_broker.py
"""

import os
import sys
import time
import threading
import signal

from src.shared.system.logging import Logger
from src.shared.system.smart_router import SmartRouter

# V48.0: Universal Watcher
from src.core.prices.dexscreener import DexScreenerProvider

# V17.1: Centralized Command Queue
import queue
from src.shared.notification.telegram_manager import TelegramManager
from src.shared.state.app_state import state as app_state
from src.data_storage.db_manager import db_manager  # V35.0

# V40.0: MarketAggregator for unified status

# V45.0: Unified Merchant Execution
from src.shared.system.capital_manager import get_capital_manager

# V133: SignalResolver (SRP Refactor)
from src.core.signal_resolver import SignalResolver

# V133: AlertPolicyChecker (SRP Refactor)
from src.core.alert_policy_checker import AlertPolicyChecker

# V133: BackgroundWorkerManager (SRP Refactor)
from src.core.background_worker_manager import BackgroundWorkerManager

# V133: EngineManager (SRP Refactor)
from src.core.engine_manager import EngineManager
from src.core.websocket_listener import create_websocket_listener
from src.core.shared_cache import SharedPriceCache
from src.scraper.scout.manager import ScoutManager
from src.scraper.scout.auditor import ActiveCoinAuditor


class DataBroker:
    """
    Centralized data acquisition for dual-engine trading.

    Responsibilities:
    - WebSocket connection to Helius for real-time prices
    - HTTP batch fetching via DSM (Jupiter/DexScreener)
    - Token hunting via ScoutManager
    - Wallet state caching for engines
    """

    def __init__(self):
        Logger.section("PHANTOM TRADER - DATA BROKER")

        # Register broker
        SharedPriceCache.set_broker_info(os.getpid())
        Logger.info(f"[BROKER] PID: {os.getpid()}")
        
        # V19.1: Pool Registry for WSS Wiring
        self.known_pools = {}  # pool_addr -> (base, quote)

        # Watchlist Monitor
        self.watchlist_file = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../data/watchlist.json")
        )
        self.last_config_mtime = 0
        try:
            self.last_config_mtime = os.path.getmtime(self.watchlist_file)
        except OSError:
            pass

        self._load_watchlist_config()

        # Initialize Hunter
        self.hunter = ScoutManager()

        # Initialize Auditor
        self.auditor = ActiveCoinAuditor()

        # Smart Router (used by DSM internally)
        self.router = SmartRouter()

        # V10.13: Data Source Manager (Tiered Reliability)
        from src.shared.system.data_source_manager import DataSourceManager

        self.dsm = DataSourceManager()

        # V48.0: Universal Watcher for rich market data
        self.universal_watcher = DexScreenerProvider()

        # Initialize execution for wallet scanning
        from src.shared.execution.wallet import WalletManager

        self.wallet = WalletManager()
        self.wallet_scan_interval = 6

        # Create price cache bridge for WSS
        self.price_cache = BrokerPriceCache()

        # V19.0: Wire WSS to HopGraphEngine (The Connective Tissue)
        # We lazily import to avoid circular dep issues during init
        self.hop_engine = None 
        try:
             from src.arbiter.core.hop_engine import get_hop_engine
             self.hop_engine = get_hop_engine()
        except ImportError:
             pass

        def _handle_wss_update(event):
            """Relay WSS event to Graph Engine."""
            if self.hop_engine:
                pool = event.get("pool")
                if not pool:
                    return

                # V19.1: Resolve via Registry
                tokens = self.known_pools.get(pool)
                if not tokens:
                    # Optional: Queue for metadata fetch?
                    # For now, just skip until Universal Watcher picks it up.
                    return

                base_mint, quote_mint = tokens
                
                update = {
                    "pool_address": pool,
                    "price": event.get("price"),
                    "dex": event.get("dex"),
                    "slot": 0,  # Rust parser doesn't pass slot yet via SwapEvent, defaults to 0
                    "base_mint": base_mint,
                    "quote_mint": quote_mint,
                    "liquidity_usd": 0, # WSS event doesn't carry liquidity
                    "fee_bps": 25 # Default
                }
                
                # Check for "revert" logic or weird prices
                if update["price"] > 0:
                     self.hop_engine.update_pool(update)

        # Create WSS listener with callback
        self.ws_listener = create_websocket_listener(
            self.price_cache, self.watched_mints, on_price_update=_handle_wss_update
        )

        # Stats
        self.batch_count = 0
        self.wss_updates = 0
        self.last_batch_time = 0

        print("=" * 60)
        print("   ✅ Data Broker initialized")
        print("=" * 60)

        # V7.1.2: Initial wallet scan
        self._scan_and_cache_wallet()

        # V17.1: Centralized Command Queue
        self.command_queue = queue.Queue()
        self.telegram_listener = TelegramManager(self.command_queue)
        print("   📡 Telegram Listener initialized (Central Hub)")

        # V9.7: Detect held bags and prioritize them
        self.held_symbols = self._get_held_symbols()
        if self.held_symbols:
            print(f"   🎯 PRIORITY BAGS: {self.held_symbols}")

        # V40.0: Market Aggregator for unified status
        self._init_market_aggregator()

        # V45.0: Unified Merchant Logic
        self._init_merchant_engines()

        # V133: SignalResolver (SRP Refactor)
        self.signal_resolver = SignalResolver()

        # V133: AlertPolicyChecker (SRP Refactor) (Instantiated after market_aggregator)
        self.alert_checker = AlertPolicyChecker(
            market_aggregator=getattr(self, "market_aggregator", None)
        )

        # V133: BackgroundWorkerManager (SRP Refactor)
        self.worker_mgr = BackgroundWorkerManager(self)

        # V133: EngineManager (SRP Refactor)
        self.engine_mgr = EngineManager()
        self.engine_mgr.initialize_all()

        # Connect Bitquery callback if enabled
        if self.engine_mgr.bitquery_adapter:
            self.engine_mgr.bitquery_adapter.add_callback(self._handle_bitquery_update)

        # V11.5: Defer blocking calls to run() for instant launch
        # _backfill_history() and _validate_tokens() moved to background thread

        # V45.2: Command Processor
        from src.shared.system.command_processor import CommandProcessor

        self.command_processor = CommandProcessor(self)
        self.forced_report_pending = False

        # V133: Agents and Bitquery moved to EngineManager
        pass

    # ═══════════════════════════════════════════════════════════════════
    # V133: SRP Refactor Properties (Bridging to EngineManager)
    # ═══════════════════════════════════════════════════════════════════
    @property
    def merchant_engines(self):
        return self.engine_mgr.merchant_engines

    @property
    def scout_agent(self):
        return self.engine_mgr.scout_agent

    @property
    def whale_watcher(self):
        return self.engine_mgr.whale_watcher

    @property
    def sauron(self):
        return self.engine_mgr.sauron

    @property
    def sniper(self):
        return self.engine_mgr.sniper

    @property
    def bitquery_adapter(self):
        return self.engine_mgr.bitquery_adapter

    def stop(self):
        """V45.2: Graceful shutdown."""
        self.running = False
        Logger.info("[BROKER] Stop signal received.")

    def _init_market_aggregator(self):
        """
        V40.0: Initialize MarketAggregator with available adapters.
        V45.1: Initialize MarketReporter.
        """
        try:
            from src.shared.system.market_aggregator import MarketAggregator

            # 1. Init dYdX if enabled
            dydx_adapter = None
            if Settings.DYDX_ENABLED:
                from src.infrastructure.dydx_adapter import DydxAdapter

                # Fix: V45.0 Adapter expects 'network' str, not 'use_testnet' bool
                network = getattr(Settings, "DYDX_NETWORK", "testnet")
                dydx_adapter = DydxAdapter(network=network)

            # 2. Init Aggregator
            self.market_aggregator = MarketAggregator(dydx_adapter=dydx_adapter)

            # 3. Init Reporter (V45.1)
            from src.shared.system.reporter import MarketReporter

            self.reporter = MarketReporter(self.dsm, self.market_aggregator)
            self.reporter.set_watched_mints(self.watched_mints)

            print("   🌐 Market Aggregator & Reporter Initialized")

        except Exception as e:
            Logger.error(f"Failed to init components: {e}")
            self.market_aggregator = None
            # Fallback reporter
            from src.shared.system.reporter import MarketReporter

            self.reporter = MarketReporter(self.dsm, None)

    # ═══════════════════════════════════════════════════════════════════
    # ORCHESTRATION & LOGIC
    # ═══════════════════════════════════════════════════════════════════

    # Engine initialization moved to EngineManager.initialize_all()

    def _resolve_signals(self, signals: list) -> list:
        """V133: Delegates to SignalResolver."""
        return self.signal_resolver.resolve(signals)

    def _get_unified_status(self) -> str:
        """V40.0: Get unified dual-market status for Telegram."""
        import asyncio

        status = "⚠️ Status Unknown"

        # Run async aggregator in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Run the coroutine
            if self.market_aggregator:
                status = loop.run_until_complete(
                    self.market_aggregator.get_unified_status()
                )
            else:
                status = "⚠️ Market Aggregator Not Initialized"

        except Exception as e:
            Logger.warning(f"[BROKER] Status aggregation failed: {e}")
            status = f"📊 Status Error: {e}"

        finally:
            loop.close()

        # Append engine mode (Safety check for AppState truth)
        try:
            mode = app_state.mode
            status += f"\n\n⚙️ Engine Mode: **{mode}**"
        except Exception:
            pass

        return status

    # Alert methods removed - see AlertPolicyChecker in alert_policy_checker.py

    def _handle_bitquery_update(self, data: dict):
        """
        V64.0: Process real-time update from Bitquery.
        Data format: { "Token": {...}, "Market": {...}, "Price": {...}, "Volume": {...} }
        """
        try:
            # Extract info
            token_info = data.get("Token", {})
            price_info = data.get("Price", {})
            market_info = data.get("Market", {})
            volume_info = data.get("Volume", {})

            # Normalize
            symbol = token_info.get("Symbol")
            mint = token_info.get("Address")  # Check if this is Mint or Market Address?
            # In Raydium DEX trades, Token is usually the base token.

            if not symbol or not mint:
                return

            # Filter: Only process if we are watching this token
            # Optimisation: Bitquery stream is filtered by us?
            # No, subscription gets all pairs in the list of programs.
            # We must filter client-side if we only want 'watched' tokens.
            # To discover new tokens, we might process all.

            is_watched = mint in self.watched_mints

            price = float(price_info.get("Ohlc", {}).get("Close", 0.0))
            if price <= 0:
                return

            # Update Shared Cache
            # We map mint -> symbol
            # If not in watched, perhabs we learn it?
            if not is_watched:
                # Optional: "Scout" logic here to discover high volume
                pass
            else:
                # Update Price Cache (Fast Path)
                # We use specific source tag "BITQUERY"

                # TODO: Volume/Liquidity integration
                # Bitquery gives "Volume" { "Usd": ... } for the interval (1m)

                # Write to shared cache (Simple Price Update)
                # Note: SharedPriceCache.write_batch expects dict {symbol: price}
                # But here we have single update.
                # Maybe add write_single to SharedPriceCache or us batch of 1
                SharedPriceCache.write_batch({symbol: price}, source="BITQUERY")

                # Update Universal Watcher/Aggregator?
                # Currently they poll. Pushing this data requires them to listen or poll cache.
                # Since they read from SharedPriceCache, this is sufficient.

                # Log occasional heartbeat for debug
                # Logger.debug(f"[BQ] {symbol} ${price:.4f}")
                pass

        except Exception:
            pass

    def _update_market_regime(self):
        """V60.0: Fetch latest regime and write to shared cache."""
        import asyncio
        from dataclasses import asdict

        if not self.market_aggregator:
            return

        try:
            # Sync bridge to async method
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Use SOL as the bellwether for regime detection
                telemetry = loop.run_until_complete(
                    self.market_aggregator.get_dex_telemetry("SOL")
                )
            finally:
                loop.close()

            if telemetry:
                # Convert to dict and write to cache
                regime_data = asdict(telemetry)
                SharedPriceCache.write_market_regime(regime_data)

                # Optional: Log change
                # Logger.info(f"🌤️ Market Regime: {telemetry.volatility} / {telemetry.trend} (Q: {telemetry.quality})")

        except Exception as e:
            Logger.debug(f"[BROKER] Regime update failed: {e}")

    def _get_held_symbols(self):
        """V9.7: Get list of currently held token symbols."""
        wallet_state = SharedPriceCache.get_wallet_state(max_age=120)
        held_assets = wallet_state.get("held_assets", {})
        return list(held_assets.keys())

    def _load_watchlist_config(self):
        """Rebuild watched_mints map from Settings (reloaded from disk)."""
        # Reload Settings from file
        try:
            from config.settings import Settings

            a, v, w, s, all_a, meta, wp = Settings.load_assets()
            Settings.ACTIVE_ASSETS = a
            Settings.SCOUT_ASSETS = s
            Settings.VOLATILE_ASSETS = v
            Settings.WATCH_ASSETS = w
            Settings.ASSETS = all_a

            # Rebuild map
            self.watched_mints = {}
            for symbol, mint in a.items():
                self.watched_mints[mint] = symbol
            for symbol, mint in s.items():
                self.watched_mints[mint] = symbol
            for symbol, mint in v.items():
                self.watched_mints[mint] = symbol
            for symbol, mint in w.items():
                self.watched_mints[mint] = symbol

            print(
                f"   📋 Config Loaded: {len(self.watched_mints)} tokens (Active={len(a)}, Scout={len(s)})"
            )

            # V45.4: Persistence of Held Assets (Real & Paper)
            # If we hold a position, we MUST keep watching it even if config removed it.
            if hasattr(self, "merchant_engines") and self.merchant_engines:
                for name, engine in self.merchant_engines.items():
                    # Get held mints from engine (TradingCore has this method?)
                    # If not, access watchers directly carefully
                    if hasattr(engine, "get_held_mints"):
                        held_mints = engine.get_held_mints()
                        for sym, mint in held_mints.items():
                            if mint not in self.watched_mints:
                                self.watched_mints[mint] = sym
                                print(
                                    f"   🛡️ Keeping {sym} in Data Feed (Held in {name})"
                                )
        except Exception as e:
            Logger.warning(f"[BROKER] Config Load Error: {e}")

    def run(self):
        """Main broker loop."""
        # V11.5: Start WSS and go LIVE immediately (P0)
        self.ws_listener.start()

        # V17.1: Start Telegram Listener (Daemon)
        if hasattr(self, "telegram_listener"):
            self.telegram_listener.start()

        Logger.success("[BROKER] DATA BROKER IS LIVE")

        # V11.12: Send Broker init to Telegram via CommsDaemon
        from src.shared.system.comms_daemon import send_telegram

        send_telegram("🔴 Data Broker is LIVE", source="BROKER", priority="HIGH")

        # V133: Background Workers Management (Delegated to BackgroundWorkerManager)
        self.worker_mgr.start_all()

        # Start Hunter Thread (V9.0) - DELAYED START (V10.6)
        # V88.0: Reduce delay from 45s to 5s
        def delayed_hunter_start():
            time.sleep(5)
            print("   🏹 Hunter Daemon Starting...")

        hunter_thread = threading.Thread(
            target=delayed_hunter_start, daemon=True, name="Hunter"
        )
        hunter_thread.start()
        print("   ⏳ Hunter Daemon Scheduled (T+5s)")

        # V10.10: Immediate Wallet Scan to warm cache for Scalper
        print("   ⏳ Warming Wallet Cache...")
        self._scan_and_cache_wallet()

        # V65.0: Start Scout Agent

        # V66.0: Start Whale Watcher

        # V67.0: Start Sauron Discovery

        # V68.0: Start Sniper and wire to Sauron

        # V77.0: Start Glass Cockpit Dashboard
        from src.shared.system.dashboard_service import get_dashboard_service

        self.dashboard = get_dashboard_service()
        self.dashboard.set_broker(self)
        self.dashboard.start()

        # V77.0: Start Metadata Background Resolver
        from src.scraper.discovery.metadata_resolver import get_metadata_resolver

        self.metadata_resolver = get_metadata_resolver()
        self.metadata_resolver.start()

        # V84.0: Start Swap Intelligence (Solscan scraper)
        from src.shared.infrastructure.smart_scraper import get_scrape_intelligence

        self.scrape_intel = get_scrape_intelligence()
        self.scrape_intel.start()
        print("   🔍 Swap Intelligence (Solscan Scraper) Started")

        # Enter main loop
        self.run_loop()

    def run_loop(self):
        """The main loop for data collection and processing."""
        self.running = True
        try:
            while self.running:
                # V18.0: Check if engines are halted (AppState Truth)
                engines_halted = app_state.stats.get("engines_halted", False)

                self._run_tick()

                # V9.1: Periodic Active Coin Audit (Skip in Sentinel Mode)
                if not engines_halted and self.auditor.should_run_audit():
                    self.auditor.run_audit()
                    self._load_watchlist_config()  # Reload after demotions

                # V133: Periodic Alert Policy Check (Delegated to AlertPolicyChecker)
                self.alert_checker.check()

                # V60.0: Update Market Regime (Every 60 seconds)
                if self.batch_count % 120 == 0:  # Approx 60s at 0.5s/tick
                    self._update_market_regime()

                # V18.0: Conditional Loop Speed
                if engines_halted:
                    # SENTINEL MODE: Low CPU, but still listening
                    time.sleep(5.0)  # 5 second loop
                else:
                    # ACTIVE MODE: Fast loop for trading
                    time.sleep(0.5)  # 500ms loop (was 15s, now faster)
        except KeyboardInterrupt:
            Logger.info("[BROKER] STOPPED BY USER")
        finally:
            self.ws_listener.stop()

    def _run_tick(self):
        """Run one data collection tick."""
        self.batch_count += 1

        # V17.1: Process Command Queue (Central Hub)
        self._process_commands()

        # V9.0: Check for watchlist updates
        try:
            mtime = os.path.getmtime(self.watchlist_file)
            if mtime > self.last_config_mtime:
                print("   🔄 Watchlist changed! Reloading...")
                self.last_config_mtime = mtime
                self._load_watchlist_config()
        except OSError:
            pass

        # Get all mints to fetch
        all_mints = list(self.watched_mints.keys())

        # V10.13: Use DSM instead of raw batch fetch
        # V10.13: Use DSM instead of raw batch fetch
        try:
            prices = self.dsm.get_prices(all_mints)
            # data.batch_fetch_jupiter_prices IS DEPRECATED in V10.13

            if prices:
                # V35.3 Fix: Get WSS stats early for DB logging
                wss_stats = self.ws_listener.get_stats()

                # Write to shared cache
                batch_prices = {}
                for mint, price in prices.items():
                    symbol = self.watched_mints.get(mint, mint[:8])
                    batch_prices[symbol] = price

                    # V35.0: Persist to DB
                    # We need volume/liquidity if possible.
                    # DSM might have cached it, or we pass 0 for now if not available in this simple dict.
                    # DSM.get_liquidity fetches from cache.
                    liq = self.dsm.get_liquidity(mint)
                    vol = 0  # No volume in simple batch_fetch yet, would need DSM upgrade or just 0
                    latency = int(wss_stats.get("avg_latency_ms", 0))

                    db_manager.insert_tick(mint, price, vol, liq, latency)

                SharedPriceCache.write_batch(batch_prices, "BROKER")

                # ═══ V12.7: Push to TUI AppState Pulse ═══
                try:
                    from src.shared.state.app_state import state as app_state

                    for sym, price in batch_prices.items():
                        app_state.update_pulse(sym, price)
                except:
                    pass

                # Display
                timestamp = time.strftime("%H:%M:%S")
                # wss_stats cached above

                # V10.13: Show Source (JUP vs DEX)
                source_tag = "DEX" if self.dsm.use_fallback else "JUP"

                msg = f"[BROKER] Batch #{self.batch_count} | Scout:✓{len(self.scout_agent.watchlist)} | Whale:LISTEN | Sniper:🎯{self.sniper.get_stats()['sniped_count']} | Px:{len(batch_prices)}"
                Logger.info(msg)

                # V45.1: Delegated Reporting (SRP Fix)
                # Check for forced status priority
                priority = "HIGH" if self.forced_report_pending else "LOW"
                if self.forced_report_pending:
                    self.forced_report_pending = False

                self.reporter.send_market_snapshot(
                    batch_prices, wss_stats, priority=priority
                )

                # V48.0: Universal Watcher - Fetch rich market data every 10 batches
                if self.batch_count % 10 == 0:
                    try:
                        symbol_map = {v: k for k, v in self.watched_mints.items()}
                        rich_data = self.universal_watcher.fetch_market_data_batch(
                            all_mints, symbol_map
                        )

                        if rich_data:
                            # V89.10: Use TokenRegistry for symbol resolution
                            from src.shared.infrastructure.token_registry import (
                                get_registry,
                            )

                            registry = get_registry()

                            # Convert MarketData objects to dicts for cache
                            cache_batch = {}
                            for mint, mkt_data in rich_data.items():
                                sym = registry.get_symbol(mint)
                                cache_batch[mint] = {  # Key by mint
                                    "symbol": sym,
                                    "dex_id": mkt_data.dex_id,
                                    "liquidity_usd": mkt_data.liquidity_usd,
                                    "volume_24h_usd": mkt_data.volume_24h_usd,
                                    "price_change_1h": mkt_data.price_change_1h,
                                    "price_change_24h": mkt_data.price_change_24h,
                                    "txns_buys_24h": mkt_data.txns_buys_24h,
                                    "txns_sells_24h": mkt_data.txns_sells_24h,
                                    "buy_sell_ratio": mkt_data.buy_sell_ratio,
                                    "fdv": mkt_data.fdv,
                                }

                            # V61.0: Check for Mooners (>300%)
                            for mint, mkt_data in rich_data.items():
                                if (
                                    mkt_data.price_change_1h
                                    and mkt_data.price_change_1h > 300
                                ):
                                    self._fire_discovery_trigger(mint)

                                # V65.0: Feed Scout Agent (OFI/Regime)
                                # Note: We pass minimal data here. Real OFI needs Depth.
                                self.scout_agent.on_tick(
                                    {
                                        "symbol": symbol_map.get(mint, "UNKNOWN"),
                                        "price": mkt_data.price_change_1h,  # Wrong field, just passing placeholder
                                        "bids": [],
                                        "asks": [],
                                    }
                                )

                            SharedPriceCache.write_market_data_batch(cache_batch)
                            
                            # V19.1: Populate Pool Registry for WSS Wiring
                            for mint, mkt_data in rich_data.items():
                                # DexScreener data usually has pair_address.
                                # Check if mkt_data has pair_address, base_mint, quote_mint
                                if hasattr(mkt_data, "pair_address") and hasattr(mkt_data, "base_mint") and hasattr(mkt_data, "quote_mint"):
                                     self.known_pools[mkt_data.pair_address] = (mkt_data.base_mint, mkt_data.quote_mint)
                            # Logger.info(f"[WATCHER] Cached rich data for {len(cache_batch)} tokens")
                    except Exception as e:
                        Logger.debug(f"[WATCHER] Rich data fetch failed: {e}")

        except Exception as e:
            print(f"   ⚠️ Batch error: {str(e)[:40]}")

        # V45.0: Execute Unified Merchant Strategy (Every 5 ticks)
        if hasattr(self, "merchant_engines") and self.merchant_engines:
            # V86.3: Merchant Heartbeat (logging only, every 60s approx)
            if self.batch_count % 120 == 0:
                Logger.info(
                    f"🧠 [MERCHANT] Scanning {len(all_mints)} markets... (Mode: {app_state.mode})"
                )

            # V89.0: Merchant Pulse (Every 30s)
            if self.batch_count % 60 == 0:
                for name, engine in self.merchant_engines.items():
                    if hasattr(engine, "get_status_summary"):
                        summary = engine.get_status_summary()
                        Logger.info(f"💭 [{name}] {summary}")

            if self.batch_count % 5 == 0:
                all_signals = []

                # V67.5: Collect Agent Signals
                agent_signals = []

                # Scout Agent (OFI / Smart Money)
                scout_sig = self.scout_agent.on_tick(
                    {
                        "symbol": "GLOBAL",  # Placeholder
                        "bids": [],
                        "asks": [],
                    }
                )
                if scout_sig:
                    agent_signals.append(scout_sig)

                # Whale Watcher (Copy-Trade)
                whale_sig = self.whale_watcher.on_tick({})
                if whale_sig:
                    agent_signals.append(whale_sig)

                # V68.0: Sniper Agent (Fast-Entry)
                sniper_sig = self.sniper.on_tick({})
                if sniper_sig:
                    agent_signals.append(sniper_sig)

                for name, engine in self.merchant_engines.items():
                    try:
                        # V67.5: Inject Agent Signals into Ensemble
                        if hasattr(engine.decision_engine, "inject_agent_signal"):
                            for sig in agent_signals:
                                engine.decision_engine.inject_agent_signal(sig)

                        # Scan signals (non-executing)
                        sigs = engine.scan_signals()
                        all_signals.extend(sigs)

                    except Exception as e:
                        # Log error but don't crash broker
                        Logger.error(f"🛑 [MERCHANT] Engine Error: {e}")
                        import traceback

                        traceback.print_exc()

                # Resolve & Execute
                winning_signals = self._resolve_signals(all_signals)

                # V89.14: Diagnostic logging disabled
                is_paper_diagnostic = False

                if is_paper_diagnostic and (all_signals or winning_signals):
                    print(
                        f"\n📊 [BROKER] Signals: {len(all_signals)} generated → {len(winning_signals)} winning"
                    )
                    for sig in winning_signals:
                        print(
                            f"   🎯 {sig.get('symbol')} {sig.get('action')} (engine: {sig.get('engine')})"
                        )

                for signal in winning_signals:
                    engine = self.merchant_engines.get(signal["engine"])
                    if engine:
                        if is_paper_diagnostic:
                            print(
                                f"   🚀 Executing {signal.get('symbol')} {signal.get('action')}..."
                            )
                        engine.execute_signal(signal)
                    elif is_paper_diagnostic:
                        print(f"   ❌ Engine '{signal.get('engine')}' not found!")

        # V10.9: Explicit Heartbeat (Even if fetch fails)
        SharedPriceCache.set_broker_info(os.getpid())

        self.last_batch_time = time.time()

        # V7.1.2: Periodic wallet scan
        if self.batch_count % self.wallet_scan_interval == 0:
            self._scan_and_cache_wallet()

    def _scan_and_cache_wallet(self):
        """V7.1.2: Scan wallet and cache state for engines."""
        try:
            # Get USDC balance
            usdc_balance = self.wallet.get_balance(Settings.USDC_MINT)
            sol_balance = self.wallet.get_sol_balance()

            # Get all token accounts
            all_tokens = self.wallet.get_all_token_accounts()

            # Build held assets dict
            held_assets = {}
            mint_to_symbol = {v: k for k, v in Settings.ASSETS.items()}

            for mint, balance in all_tokens.items():
                if balance > 0.01:  # Ignore dust
                    symbol = mint_to_symbol.get(mint)
                    if symbol:
                        # Get price for value calculation
                        price, _ = SharedPriceCache.get_price(symbol, max_age=60)
                        value_usd = balance * (price or 0)
                        held_assets[symbol] = {
                            "balance": balance,
                            "value_usd": value_usd,
                            "mint": mint,
                        }

            # Write to cache
            SharedPriceCache.write_wallet_state(usdc_balance, held_assets, sol_balance)

            # V48.1: Seed Paper Wallet from Real Wallet (First Run Only)
            if getattr(Settings, "CLONE_WALLET_ON_FIRST_RUN", False):
                get_capital_manager().seed_from_real_wallet(usdc_balance, sol_balance)

            if held_assets:
                print(
                    f"   💼 Wallet: ${usdc_balance:.2f} USDC | Bags: {list(held_assets.keys())}"
                )
        except Exception as e:
            print(f"   ⚠️ Wallet scan error: {str(e)[:40]}")

    def _process_commands(self):
        """
        V17.1: Process Telegram commands from queue.
        V45.2: Delegated to CommandProcessor to fix SRP.
        """
        try:
            queue_item = self.telegram_listener.command_queue.get_nowait()

            # Parse command
            if ":" in queue_item:
                cmd_type, cmd_value = queue_item.split(":", 1)
            else:
                cmd_type = queue_item
                cmd_value = None

            # V47.0: Manual Retraining Override
            if cmd_type == CMD_RETRAIN_ML:
                Logger.info("🧠 [BROKER] Manual ML Retraining Triggered")

                def train_bg():
                    from trainer_supervisor import run_retraining_pipeline

                    success = run_retraining_pipeline(force=True)
                    if success:
                        from src.shared.system.comms_daemon import send_telegram

                        send_telegram(
                            "✅ ML Retraining Complete! Reloading models...",
                            source="ML",
                            priority="HIGH",
                        )
                        # Force Reload
                        if hasattr(self, "merchant_engines"):
                            for engine in self.merchant_engines.values():
                                if hasattr(engine, "reload_ml_model"):
                                    engine.reload_ml_model()

                t = threading.Thread(target=train_bg, daemon=True, name="ManualMLTrain")
                t.start()
                return

            # V48.0: Performance Reporting
            if cmd_type == CMD_PERFORMANCE:
                Logger.info("📊 [BROKER] Generating Performance Report...")
                from src.analysis.performance_reporter import get_performance_reporter
                from src.shared.system.comms_daemon import send_telegram

                try:
                    reporter = get_performance_reporter()
                    report = reporter.generate_report()
                    send_telegram(report, source="PERF", priority="INFO")
                    Logger.info("📊 Performance Report Sent")
                except Exception as e:
                    Logger.error(f"Failed to generate report: {e}")
                    send_telegram(
                        f"❌ Report Error: {e}", source="PERF", priority="HIGH"
                    )
                return

            # Delegate
            self.command_processor.process(cmd_type, cmd_value)

        except ImportError:  # queue.Empty is arguably ImportError if not imported? No, usually queue.Empty
            pass
        except Exception as e:
            # Check for queue.Empty (via string to avoid import dependency)
            if "Empty" in str(e):
                return
            Logger.debug(f"[BROKER] Command Queue Empty or Error: {e}")

    def _validate_tokens(self):
        """V7.3: Run safety validation on all tokens and cache results."""
        from src.shared.infrastructure.validator import TokenValidator

        symbols = list(self.watched_mints.values())
        # print(f"\n🛡️ V7.3: Validating safety for {len(symbols)} tokens...")

        # Check cache freshness first
        tokens_to_validate = []
        cached_safe = 0
        cached_unsafe = 0

        for symbol in symbols:
            cached = SharedPriceCache.get_safety(symbol, max_age=3600)  # 1 hour
            if cached:
                if cached.get("safe"):
                    cached_safe += 1
                else:
                    cached_unsafe += 1
                    # Optional: Print unsafe for awareness? Or minimal?
                    # keeping it clean per user request
            else:
                tokens_to_validate.append(symbol)

        # print(f"   🛡️ Cache Check: {cached_safe} Safe | {cached_unsafe} Unsafe (Cached)")

        if not tokens_to_validate:
            # print("   📦 All tokens have fresh safety cache - skipping validation!")
            return

        print(f"\n   🔍 Validating {len(tokens_to_validate)} tokens...")
        validator = TokenValidator()

        count_safe = 0
        count_unsafe = 0

        for symbol in tokens_to_validate:
            mint = Settings.ASSETS.get(symbol)
            if not mint:
                continue

            try:
                result = validator.validate(mint, symbol)

                # V5.7 Fix: ValidationResult is a dataclass, not a dict
                is_safe = result.is_safe
                liquidity = result.liquidity_usd
                reason = result.reason

                # Write to cache
                SharedPriceCache.write_safety(symbol, is_safe, liquidity, reason)

                if is_safe:
                    count_safe += 1
                else:
                    count_unsafe += 1
                    # V89.1: Suppress Low Liquidity warnings (spam reduction)
                    # User request: "Success Low Liquidity Alerts"
                    # Logic: If Low Liquidity is the ONLY reason, suppress.
                    # If mixed with others (e.g. Honeypot), show others but hide Liquidity.

                    if "Low Liquidity" in reason:
                        parts = reason.split("; ")
                        # Filter out the liquidity warning
                        filtered_parts = [p for p in parts if "Low Liquidity" not in p]

                        if not filtered_parts:
                            continue  # Nothing else to report, skip log

                        # Reconstruct reason without liquidity
                        display_reason = "; ".join(filtered_parts)
                        print(f"   ⚠️ {symbol}: {display_reason}")
                    else:
                        print(f"   ⚠️ {symbol}: {reason}")

            except Exception as e:
                print(f"   ⚠️ {symbol}: Validation error - {str(e)[:30]}")
                SharedPriceCache.write_safety(symbol, False, 0.0, str(e)[:50])
                count_unsafe += 1

        print(f"   🛡️ Validation Complete: {count_safe} Safe | {count_unsafe} Unsafe")

    def _backfill_history(self):
        """V7.2: Backfill price history from CoinGecko at startup."""

        # CoinGecko ID mapping for our tokens
        COINGECKO_IDS = {
            "WIF": "dogwifcoin",
            "POPCAT": "popcat",
            "JUP": "jupiter-exchange-solana",
            "BONK": "bonk",
            "RAY": "raydium",
            "JTO": "jito-governance-token",
            "PYTH": "pyth-network",
            "JELLYJELLY": "jelly-my-jelly",
        }

        symbols = list(self.watched_mints.values())
        held_set = set()

        # V9.7: Sort symbols to prioritize held bags
        if hasattr(self, "held_symbols") and self.held_symbols:
            held_set = set(self.held_symbols)
            # Partition symbols into held and others
            held = [s for s in symbols if s in held_set]
            others = [s for s in symbols if s not in held_set]
            symbols = held + others
            print(
                f"   📊 Backfill Order: {len(held)} Priority + {len(others)} Standard"
            )

        print(f"\n📊 V7.2: Checking cache freshness for {len(symbols)} tokens...")

        # Check which tokens need backfill based on:
        # 1. Insufficient data (<50 points)
        # 2. Stale data (newest point >30 minutes old)
        tokens_to_backfill = []
        stale_threshold = 30 * 60  # 30 minutes

        tokens_to_backfill = []
        stale_threshold = 30 * 60  # 30 minutes

        # Helper to check if backfill needed
        def check_backfill(sym):
            # ... identical logic ...
            lock = SharedPriceCache._get_lock()
            with lock:
                c_data = SharedPriceCache._read_raw()
            entry = c_data.get("prices", {}).get(sym, {})
            hist = entry.get("history", [])
            if len(hist) < 50:
                return True, f"insufficient ({len(hist)} points)"
            if hist:
                age = time.time() - max(h.get("ts", 0) for h in hist)
                if age > stale_threshold:
                    return True, f"stale ({int(age / 60)}m old)"
            return False, ""

        for symbol in symbols:
            needed, reason = check_backfill(symbol)
            if needed:
                is_held = (symbol in held_set) if held_set else False
                tokens_to_backfill.append((symbol, reason, is_held))
            else:
                # print(f"   ✅ {symbol}: Fresh") # Too verbose
                pass

        if not tokens_to_backfill:
            print("   📦 All tokens have fresh cache - skipping CoinGecko!")
            return

        # Separate into urgent (held) and background
        urgent = [t for t in tokens_to_backfill if t[2]]
        background = [t for t in tokens_to_backfill if not t[2]]

        # 1. Process Urgent Synchronously
        if urgent:
            print(f"   🔥 Processing {len(urgent)} URGENT held bags...")
            for symbol, reason, _ in urgent:
                print(f"   ⚠️ {symbol}: Backfilling ({reason})...")
                self._backfill_single_token(symbol, COINGECKO_IDS)
                time.sleep(1.5)  # Fast but safe

        # 2. Process Background in Thread
        if background:
            print(f"   ⏳ Scheduling {len(background)} tokens for background backfill")

            def run_bg_backfill():
                for i, (symbol, reason, _) in enumerate(background):
                    # V45.7: Check if allowed to continue
                    if not getattr(self, "running", True):
                        print("   🛑 [BG] Backfill halted by shutdown.")
                        break

                    # Check if we should stop? No mechanism yet.
                    if i > 0:
                        time.sleep(10)  # Slow pace for background
                    print(f"   📡 [BG] Backfilling {symbol} ({reason})...")
                    self._backfill_single_token(symbol, COINGECKO_IDS)
                print("   ✅ [BG] Background backfill complete")

            t = threading.Thread(target=run_bg_backfill, daemon=True, name="Backfill")
            t.start()

        print("=" * 60)
        print("✅ CACHE WARM - Safe to start engines!")
        print("=" * 60)

    def _backfill_single_token(self, symbol: str, cg_ids: dict) -> bool:
        """Backfill a single token from CoinGecko. Returns True on success."""
        import requests

        # V87.0: Suppress recurring "No ID" warnings
        if not hasattr(self, "_ignored_tokens"):
            self._ignored_tokens = set()

        if symbol in self._ignored_tokens:
            return True  # Silently skip

        cg_id = cg_ids.get(symbol)
        if not cg_id:
            # Check if we should ignore (one-time warning)
            if symbol not in self._ignored_tokens:
                print(f"   ⚠️ {symbol}: No CoinGecko ID mapped (Suppressed for session)")
                self._ignored_tokens.add(symbol)
            return True  # Not a failure, just unmapped

        try:
            url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart"
            params = {"vs_currency": "usd", "days": "1"}

            resp = requests.get(url, params=params, timeout=10)

            if resp.status_code == 429:
                print(f"   ⚠️ {symbol}: CoinGecko rate limit")
                return False  # Mark for retry

            if resp.status_code == 200:
                data = resp.json()
                prices = data.get("prices", [])

                if prices:
                    price_list = [p[1] for p in prices]

                    lock = SharedPriceCache._get_lock()
                    with lock:
                        cache_data = SharedPriceCache._read_raw()

                        if symbol not in cache_data["prices"]:
                            cache_data["prices"][symbol] = {
                                "price": 0,
                                "source": "",
                                "timestamp": 0,
                                "history": [],
                            }

                        history = []
                        for i, (ts, price) in enumerate(prices[-200:]):
                            history.append({"price": price, "ts": ts / 1000})

                        cache_data["prices"][symbol]["history"] = history
                        cache_data["prices"][symbol]["price"] = price_list[-1]
                        cache_data["prices"][symbol]["source"] = "CG"
                        cache_data["prices"][symbol]["timestamp"] = time.time()

                        SharedPriceCache._write_raw(cache_data)

                    print(f"   ✅ {symbol}: Backfilled {len(history)} points")
                    return True
                else:
                    print(f"   ⚠️ {symbol}: No data from CoinGecko")
                    return True  # Empty data, not rate limited
            else:
                print(f"   ⚠️ {symbol}: CoinGecko error {resp.status_code}")
                return True  # Other error, don't retry

        except Exception as e:
            print(f"   ⚠️ {symbol}: Backfill error - {str(e)[:30]}")
            return True  # Exception, don't retry


class BrokerPriceCache:
    """
    Bridge class that writes WSS prices to SharedPriceCache.
    Mimics the interface expected by WebSocketListener.
    """

    def update_price(self, mint: str, price: float):
        """Called by WSS listener when price is decoded."""
        # Get symbol from mint
        symbol = None
        for m, s in Settings.ASSETS.items():
            if m == mint:
                symbol = s
                break

        # Reverse lookup
        for s, m in Settings.ASSETS.items():
            if m == mint:
                symbol = s
                break

        if symbol:
            SharedPriceCache.write_price(symbol, price, "WSS")
            print(f"   [WSS] 📈 {symbol} = ${price:.6f}")

    def get_price(self, mint: str) -> float:
        """Get cached price for a mint."""
        for symbol, m in Settings.ASSETS.items():
            if m == mint:
                price, _ = SharedPriceCache.get_price(symbol)
                return price or 0.0
        return 0.0

    def _fire_discovery_trigger(self, mint: str):
        """Helper to fire async trigger from sync context."""

        def run_trigger():
            import asyncio

            try:
                # We need a new loop here because it's a thread
                asyncio.run(self.scout_agent.trigger_audit(mint))
            except Exception as e:
                Logger.debug(f"[DISCOVERY] Trigger failed: {e}")

        t = threading.Thread(
            target=run_trigger, daemon=True, name=f"Trigger-{mint[:4]}"
        )
        t.start()


def main():
    # Handle signals
    def signal_handler(sig, frame):
        print("\n🛑 Shutting down...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    broker = DataBroker()
    broker.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
