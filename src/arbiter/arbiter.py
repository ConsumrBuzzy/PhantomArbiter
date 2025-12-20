"""
PhantomArbiter - Core Arbitrage Orchestrator
=============================================
Unified orchestrator that composes existing components:
- SpreadDetector for opportunity scanning
- ArbitrageExecutor for trade execution
- WalletManager for live mode
- PaperWallet for paper mode

This replaces the standalone run_arbiter.py with proper src/ integration.
"""

import asyncio
import time
import json
import queue
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any, Tuple

from config.settings import Settings
from src.shared.system.logging import Logger
from src.arbiter.core.spread_detector import SpreadDetector, SpreadOpportunity
from src.arbiter.core.executor import ArbitrageExecutor, ExecutionMode
from src.arbiter.core.adaptive_scanner import AdaptiveScanner
from src.arbiter.core.near_miss_analyzer import NearMissAnalyzer
from src.speed.jito_adapter import JitoAdapter
from src.arbiter.core.trade_engine import TradeEngine
from src.arbiter.core.reporter import ArbiterReporter


# ═══════════════════════════════════════════════════════════════════
# CONSTANTS & POD ENGINE
# ═══════════════════════════════════════════════════════════════════
from src.arbiter.core.pod_engine import (
    USDC_MINT, SOL_MINT,
    CORE_PAIRS, TRENDING_PAIRS,
    ALL_PODS, pod_manager,
    _build_pairs_from_pods
)


@dataclass
class ArbiterConfig:
    """Configuration for the arbiter."""
    budget: float = 50.0
    gas_budget: float = 5.0  # USD worth of SOL for gas
    min_spread: float = 0.20
    max_trade: float = 0.0
    live_mode: bool = False
    full_wallet: bool = False
    pairs: List[tuple] = field(default_factory=lambda: CORE_PAIRS)
    # V88.0 Precision Striker: Raised threshold to absorb ~$0.45 decay
    fast_path_threshold: float = 0.75  # Must show 75 cents PROFIT at scan
    # V88.0: Fixed decay buffer based on observed HFT front-running
    decay_buffer: float = 0.45  # Expected quote loss from latency
    # V88.0: Minimum liquidity = trade_size * this multiplier
    liquidity_multiplier: float = 50.0  # Min $1250 liq for $25 trades
    # Use unified engine for direct Meteora/Orca atomic execution (bypasses Jupiter)
    use_unified_engine: bool = False


# Bootstrap defaults based on observed data (used until ML has enough samples)
# These protect against wasted gas on pairs with known issues
BOOTSTRAP_MIN_SPREADS = {
    "PIPPIN": 4.0,   # Observed extreme slippage: +$0.21 scan → -$0.34 quote
    "PNUT": 1.8,     # Observed 1.2% → reverts with -$0.13
    "ACT": 2.5,      # High LIQ failure rate
    "GOAT": 2.0,     # V88.0: Observed consistent ~$0.44 quote loss
    "FWOG": 2.0,     # V88.0: Similar decay pattern
}


def get_pair_threshold(pair: str, default: float = 0.12) -> float:
    """
    Get ML-informed fast-path threshold for a specific pair (Option B).
    
    Uses historical profit_delta from fast_path_attempts table to calculate
    the required buffer for each pair.
    
    Returns: minimum scan profit required for fast-path execution
    """
    try:
        from src.shared.system.db_manager import db_manager
        
        with db_manager.cursor() as c:
            # Get average profit_delta for this pair (last 24 hours)
            c.execute("""
            SELECT 
                AVG(profit_delta) as avg_delta,
                COUNT(*) as attempts
            FROM fast_path_attempts 
            WHERE pair LIKE ? AND timestamp > ?
            """, (f"{pair.split('/')[0]}%", time.time() - 86400))
            
            row = c.fetchone()
            if row and row['attempts'] and row['attempts'] >= 3:
                avg_delta = row['avg_delta'] or 0
                # Required threshold = enough to absorb average decay + safety margin
                # If avg_delta is -0.10, we need at least +0.12 at scan time
                required = abs(avg_delta) + 0.02  # 2 cent safety margin
                
                # Sanity Check: Cap at $0.50
                # If we need >$0.50 buffer, the pair is too volatile for fast path
                final = max(required, default)
                return min(final, 0.50)
        
        return default
        
    except Exception:
        return default


def get_bootstrap_min_spread(pair: str) -> float:
    """
    Get bootstrap minimum spread for a pair based on observations.
    Returns 0.0 if no bootstrap default (allows all spreads).
    """
    base_token = pair.split('/')[0]
    return BOOTSTRAP_MIN_SPREADS.get(base_token, 0.0)


class PhantomArbiter:
    """
    Main arbitrage orchestrator.
    
    Composes existing components to provide unified scanning and execution.
    Supports both paper and live trading modes.
    """
    
    def __init__(self, config: ArbiterConfig):
        self.config = config
        
        # Balance tracking
        self.starting_balance = config.budget
        self.current_balance = config.budget
        self.gas_balance = config.gas_budget  # Gas in USD (SOL equivalent)
        
        # Statistics via TurnoverTracker
        from src.arbiter.core.turnover_tracker import TurnoverTracker
        self.tracker = TurnoverTracker(budget=config.budget)
        self.total_trades = 0
        self.total_profit = 0.0
        self.total_gas_spent = 0.0
        self.trades: List[Dict] = []
        
        # Components (lazy-loaded)
        self._detector: Optional[SpreadDetector] = None
        self._executor: Optional[ArbitrageExecutor] = None
        
        # Telegram Manager
        from src.shared.notification.telegram_manager import TelegramManager
        self.command_queue = queue.Queue()
        self.telegram = TelegramManager(command_queue=self.command_queue)
        self.telegram.start()
        self.reporter = ArbiterReporter(self.telegram)
        
        # Scraper/Signal Coordinator
        self._coordinator = None
        self._connected = False
        
        # Initialize based on mode
        if config.live_mode:
            self._setup_live_mode()
        else:
            self._setup_paper_mode()
    
    def _setup_paper_mode(self) -> None:
        """Initialize paper trading components."""
        mode = ExecutionMode.PAPER
        self._executor = ArbitrageExecutor(mode=mode)
        # Initialize TradeEngine with executor only (no unified adapter for paper)
        self.trade_engine = TradeEngine(executor=self._executor)
        Logger.info("📄 Paper mode initialized")
    
    def _setup_live_mode(self) -> None:
        """Initialize live trading components."""
        import os
        private_key = os.getenv("PHANTOM_PRIVATE_KEY") or os.getenv("SOLANA_PRIVATE_KEY")
        
        if not private_key:
            print("   ❌ LIVE MODE FAILED: No private key found in .env!")
            Logger.error("❌ LIVE MODE FAILED: No private key found!")
            self.config.live_mode = False
            self._setup_paper_mode()
            return
        
        try:
            Settings.ENABLE_TRADING = True
            
            from src.shared.execution.wallet import WalletManager
            from src.shared.execution.swapper import JupiterSwapper
            
            self._wallet = WalletManager()
            if not self._wallet.keypair:
                raise ValueError("WalletManager failed to load keypair")
            
            self._swapper = JupiterSwapper(self._wallet)
            self._jito = JitoAdapter()
            self._executor = ArbitrageExecutor(
                wallet=self._wallet,
                swapper=self._swapper,
                jito_adapter=self._jito,
                mode=ExecutionMode.LIVE
            )
            self._connected = True
            
            # Initialize unified engine adapter if enabled
            self._unified_adapter = None
            if self.config.use_unified_engine:
                from src.shared.execution.unified_adapter import UnifiedEngineAdapter
                self._unified_adapter = UnifiedEngineAdapter()
                if self._unified_adapter.is_available():
                    Logger.info("⚡ Unified Engine: ENABLED (Meteora + Orca atomic)")
                    print(f"   ⚡ Unified Engine: ENABLED")
                else:
                    Logger.warning("⚡ Unified Engine: NOT AVAILABLE (run: cd bridges && npm run build)")
                    self._unified_adapter = None
            
            # Sync balance if full wallet mode
            if self.config.full_wallet:
                usdc_bal = self._wallet.get_balance(USDC_MINT)
                self.starting_balance = usdc_bal
                self.current_balance = usdc_bal
                
                # Also sync SOL balance as gas
                sol_balance = self._wallet.get_sol_balance()
                sol_price = None
                
                # Try cache first (5 minute max age for SOL price)
                try:
                    from src.core.shared_cache import get_cached_price
                    sol_price, _ = get_cached_price("SOL", max_age=300.0)
                except:
                    pass
                
                # If cache stale, fetch fresh from Jupiter
                if not sol_price:
                    try:
                        import httpx
                        resp = httpx.get(
                            "https://api.jup.ag/price/v2?ids=So11111111111111111111111111111111111111112",
                            timeout=5.0
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            sol_price = float(data.get("data", {}).get("So11111111111111111111111111111111111111112", {}).get("price", 0))
                            Logger.debug(f"Fresh SOL price: ${sol_price:.2f}")
                            
                            # Write back to cache for other processes
                            if sol_price > 0:
                                from src.core.shared_cache import SharedPriceCache
                                SharedPriceCache.write_price("SOL", sol_price, source="ARBITER")
                    except Exception as e:
                        Logger.debug(f"SOL price fetch failed: {e}")
                
                # Final fallback (should rarely hit)
                if not sol_price:
                    sol_price = 130.0  # More realistic fallback
                    Logger.warning(f"Using fallback SOL price: ${sol_price}")
                    
                self.gas_balance = sol_balance * sol_price
            
            print(f"   ✅ LIVE MODE ENABLED - Wallet: {self._wallet.get_public_key()[:8]}...")
            print(f"   💰 USDC: ${self.current_balance:.2f} | SOL (Gas): ${self.gas_balance:.2f}")
            Logger.info(f"✅ LIVE MODE ENABLED - Wallet: {self._wallet.get_public_key()[:8]}...")
            
            # Initialize TradeEngine
            self.trade_engine = TradeEngine(
                executor=self._executor,
                unified_adapter=self._unified_adapter,
                use_unified=self.config.use_unified_engine and (self._unified_adapter is not None)
            )
            
        except Exception as e:
            print(f"   ❌ LIVE MODE FAILED: {e}")
            Logger.error(f"❌ LIVE MODE FAILED: {e}")
            self.config.live_mode = False
            self._setup_paper_mode()
    
    def _get_detector(self) -> SpreadDetector:
        """Lazy-load spread detector with DEX feeds."""
        if self._detector is None:
            from src.shared.feeds.jupiter_feed import JupiterFeed
            from src.shared.feeds.raydium_feed import RaydiumFeed
            from src.shared.feeds.orca_feed import OrcaFeed
            from src.shared.feeds.meteora_feed import MeteoraFeed
            
            self._detector = SpreadDetector(feeds=[
                JupiterFeed(),
                RaydiumFeed(),
                OrcaFeed(use_on_chain=False),
                MeteoraFeed(),  # NEW: Meteora DLMM pools
            ])
        return self._detector
    
    async def scan_opportunities(
        self, 
        verbose: bool = True, 
        scanner: Optional[AdaptiveScanner] = None
    ) -> Tuple[List[SpreadOpportunity], List[SpreadOpportunity]]:
        """
        Scan for spatial arbitrage opportunities.
        
        Args:
            verbose: Print debug output
            scanner: Optional AdaptiveScanner for per-pair filtering
            
        Returns: (profitable_opportunities, all_spreads)
        """
        detector = self._get_detector()
        
        # Calculate trade size (Budget vs Max Trade)
        limit = self.config.max_trade if self.config.max_trade > 0 else float('inf')
        trade_size = min(self.current_balance, limit)
        
        # Filter pairs if scanner provided (skip stale/low-spread pairs)
        pairs_to_scan = self.config.pairs
        skipped_count = 0
        if scanner:
            pairs_to_scan = scanner.filter_pairs(self.config.pairs)
            # Fallback: if scanner removes EVERYTHING, just scan original pairs
            # This prevents blank dashboard updates
            if not pairs_to_scan:
                pairs_to_scan = self.config.pairs
            skipped_count = len(self.config.pairs) - len(pairs_to_scan)
        
        spreads = detector.scan_all_pairs(pairs_to_scan, trade_size=trade_size)
        
        # Filter profitable using SpreadOpportunity's own calculations
        profitable = [opp for opp in spreads if opp.is_profitable]
        
        # Log all spreads to DB for training data
        try:
            from src.shared.system.db_manager import db_manager
            for opp in spreads:
                db_manager.log_spread({
                    'timestamp': opp.timestamp,
                    'pair': opp.pair,
                    'spread_pct': opp.spread_pct,
                    'net_profit_usd': opp.net_profit_usd,
                    'buy_dex': opp.buy_dex,
                    'sell_dex': opp.sell_dex,
                    'buy_price': opp.buy_price,
                    'sell_price': opp.sell_price,
                    'fees_usd': opp.estimated_fees_usd,
                    'trade_size_usd': opp.max_size_usd,
                    'was_profitable': opp.is_profitable,
                    'was_executed': False  # Updated in execute_trade
                })
        except Exception as e:
            Logger.debug(f"Spread logging error: {e}")
        
        return profitable, spreads
    
    async def execute_trade(self, opportunity: SpreadOpportunity, trade_size: float = None) -> Dict[str, Any]:
        """Execute a trade delegates to TradeEngine."""
        if trade_size is None:
            trade_size = min(
                self.current_balance,
                self.config.max_trade if self.config.max_trade > 0 else float('inf')
            )
        
        if trade_size < 1.0:
            return {"success": False, "error": "Insufficient balance"}
        
        if not getattr(self, 'trade_engine', None):
             Logger.error("❌ TradeEngine not initialized")
             return {"success": False, "error": "No Engine"}

        # Delegate execution to the engine
        result = await self.trade_engine.execute(opportunity, trade_size)
        
        if result.success:
            # Update Arbiter State
            self.current_balance += result.net_profit
            self.total_profit += result.net_profit
            self.total_trades += 1
            
            # Record in tracker
            self.tracker.record_trade(
                volume_usd=trade_size,
                profit_usd=result.net_profit,
                strategy="SPATIAL",
                pair=opportunity.pair
            )
            
            # Log successful trade
            trade_record = {
                "pair": opportunity.pair,
                "profit": result.net_profit,
                "fees": result.fees,
                "timestamp": time.time(),
                "mode": "LIVE" if self.config.live_mode else "PAPER",
                "engine": result.engine_used
            }
            self.trades.append(trade_record)
            
            return {
                "success": True,
                "trade": {
                    "pair": opportunity.pair,
                    "net_profit": result.net_profit,
                    "spread_pct": opportunity.spread_pct,
                    "fees": result.fees,
                    "mode": "LIVE" if self.config.live_mode else "PAPER",
                    "engine": result.engine_used
                },
                "error": None
            }
        
        return {"success": False, "trade": None, "error": result.error}
    
    def _check_signals(self):
        """Poll Scraper signals for high-trust tokens."""
        try:
            from src.core.shared_cache import SharedPriceCache
            # Get tokens with Trust Score >= 0.8 (Smart Money Conviction)
            hot_tokens = SharedPriceCache.get_all_trust_scores(min_score=0.8)
            
            if not hot_tokens: return
            
            current_pairs = {p[0] for p in self.config.pairs}
            added_count = 0
            
            from config.settings import Settings
            # Inverted asset map for lookup (Symbol -> Mint)
            # Settings.ASSETS is {Symbol: Mint} usually? Let's verify.
            # Assuming Settings.ASSETS = {"SOL": "..."}
            
            for symbol, score in hot_tokens.items():
                if symbol in current_pairs: continue
                
                # Resolve Mint
                mint = Settings.ASSETS.get(symbol)
                if not mint: continue
                
                # Add to scan list
                # Assuming USDC quote for all
                new_pair = (f"{symbol}/USDC", mint, USDC_MINT)
                self.config.pairs.append(new_pair)
                current_pairs.add(symbol)
                added_count += 1
                
                Logger.info(f"   🧠 SIGNAL: Added {symbol} (Trust: {score:.1f}) to Arbiter scan list")
                
            if added_count > 0:
                print(f"   🧠 Scraper Signal: Added {added_count} hot tokens to scan list.")
                
        except Exception as e:
            Logger.debug(f"Signal check error: {e}")

    async def run(self, duration_minutes: int = 10, scan_interval: int = 5, smart_pods: bool = False, landlord=None) -> None:
        """Main trading loop."""
        mode_str = "🔴 LIVE" if self.config.live_mode else "📄 PAPER"
        
        # Landlord strategy for yield farming
        self._landlord = landlord
        
        # Adaptive mode when interval = 0
        adaptive_mode = scan_interval == 0
        monitor = AdaptiveScanner() if adaptive_mode else None
        current_interval = monitor.base_interval if adaptive_mode else scan_interval
        
        # Smart pod rotation
        self._smart_pods_enabled = smart_pods
        
        # Load saved pod priorities (if available)
        if smart_pods:
            loaded = pod_manager.load_from_db()
            if loaded:
                print("   📂 Restored pod priorities from previous session")
            else:
                print("   🆕 Fresh pod priorities (no saved state)")
        
        # WSS Integration handled by SignalCoordinator later
        
        print("\n" + "="*70)
        
        print("\n" + "="*70)
        print(f"   PHANTOM ARBITER - {mode_str} TRADER")
        print("="*70)
        print(f"   Budget:     ${self.starting_balance:.2f} USDC | ${self.gas_balance:.2f} Gas")
        print(f"   Min Spread: {self.config.min_spread}% | Max Trade: ${self.config.max_trade:.2f}")
        scan_mode = "ADAPTIVE" if adaptive_mode else f"{scan_interval}s"
        pods_str = " | Pods: SMART" if smart_pods else ""
        print(f"   Pairs:      {len(self.config.pairs)} | Duration: {duration_minutes} min | Scan: {scan_mode}{pods_str}")
        print("="*70)
        print("\n   Running... (Ctrl+C to stop)\n")
        
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60) if duration_minutes > 0 else float('inf')
        
        last_trade_time: Dict[str, float] = {}
        cooldown = 5
        wake_event = asyncio.Event()

        # ═══════════════════════════════════════════════════════════════════
        # SIGNAL COORDINATOR (External Triggers)
        # ═══════════════════════════════════════════════════════════════════
        from src.arbiter.core.signal_coordinator import SignalCoordinator, CoordinatorConfig
        
        # Callback for WSS triggers:
        # 1. Notify scanner to boost rate for this pair
        # 2. Wake up main loop instantly
        def on_activity(symbol):
            if adaptive_mode and monitor:
                # Map symbol to pair key if needed? 
                # monitor.trigger_activity expects pair key (e.g. "SOL/USDC")
                # We can construct it or pass symbol if monitor is smart.
                # Simplest: "SYMBOL/USDC"
                monitor.trigger_activity(f"{symbol}/USDC")
                wake_event.set()

        signal_config = CoordinatorConfig(
            wss_enabled=adaptive_mode, # Only use WSS in adaptive mode
            pairs=self.config.pairs,
            scraper_poll_interval=60
        )
        
        coordinator = SignalCoordinator(signal_config, on_activity)
        await coordinator.start()

        try:
            while time.time() < end_time:
                now = datetime.now().strftime("%H:%M:%S")
                wake_event.clear()
                
                # 0. Check Remote Commands (Timeout / Stop)
                while not self.command_queue.empty():
                    cmd = self.command_queue.get_nowait()
                    if cmd == "STOP_ENGINE":
                        print(f"   [{now}] 🛑 RECEIVED REMOTE STOP COMMAND")
                        return # Exit run loop
                    elif cmd == "STATUS_REPORT":
                        # Handled by reporter normally (implicit) or we can trigger print
                        pass

                # 1. Poll Scraper Signals
                new_pairs = coordinator.poll_signals()
                if new_pairs:
                    self.config.pairs.extend(new_pairs)
                    await coordinator.register_new_pairs(new_pairs)
                    print(f"   [{now}] 🧠 Added {len(new_pairs)} hot tokens from Scraper")
                
                # V90.0: Periodic Discovery Refresh (every 30 min)
                if not hasattr(self, '_discovery_engine'):
                    from src.tools.discovery import TokenDiscovery
                    self._discovery_engine = TokenDiscovery()
                    self._last_discovery_time = 0
                
                if time.time() - self._last_discovery_time > 1800:  # 30 minutes
                    try:
                        known_mints = set(Settings.ASSETS.values())
                        discovered = self._discovery_engine.discover_and_validate(known_mints)
                        
                        if discovered:
                            # Convert to pair format and inject
                            USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
                            new_discovered = []
                            for token in discovered:
                                pair = (f"{token['symbol']}/USDC", token['mint'], USDC)
                                if pair not in self.config.pairs:
                                    new_discovered.append(pair)
                            
                            if new_discovered:
                                self.config.pairs.extend(new_discovered)
                                print(f"   [{now}] 🔭 Discovery: +{len(new_discovered)} trending tokens")
                        
                        self._last_discovery_time = time.time()
                    except Exception as e:
                        Logger.debug(f"Discovery failed: {e}")
                
                # V90.0: Smart Pair Cycling - evict low performers when list grows too large
                MAX_ACTIVE_PAIRS = 60
                if len(self.config.pairs) > MAX_ACTIVE_PAIRS:
                    try:
                        from src.shared.system.db_manager import db_manager
                        
                        # Get performance scores for all pairs
                        pair_scores = {}
                        for pair_tuple in self.config.pairs:
                            pair_name = pair_tuple[0]
                            # Score = success_rate + spread_avg - quote_loss_rate
                            stats = db_manager.get_pair_performance(pair_name) if hasattr(db_manager, 'get_pair_performance') else None
                            if stats:
                                pair_scores[pair_name] = stats.get('score', 0)
                            else:
                                # Default score for new pairs (give them a chance)
                                pair_scores[pair_name] = 0.5
                        
                        # Keep top performers + all discovered in last hour
                        one_hour_ago = time.time() - 3600
                        keep_pairs = []
                        evict_pairs = []
                        
                        sorted_pairs = sorted(self.config.pairs, key=lambda p: pair_scores.get(p[0], 0), reverse=True)
                        
                        for pair_tuple in sorted_pairs:
                            if len(keep_pairs) < MAX_ACTIVE_PAIRS:
                                keep_pairs.append(pair_tuple)
                            else:
                                evict_pairs.append(pair_tuple[0])
                        
                        if evict_pairs:
                            self.config.pairs = keep_pairs
                            print(f"   [{now}] 🔄 Cycled: -{len(evict_pairs)} stale pairs, keeping {len(keep_pairs)}")
                            
                    except Exception as e:
                        Logger.debug(f"Pair cycling error: {e}")
                
                # Live mode maintenance
                if self.config.live_mode and self._wallet:
                    await self._wallet.check_and_replenish_gas(self._swapper)
                    if self.config.full_wallet:
                        new_bal = self._wallet.get_balance(USDC_MINT)
                        # Protect against RPC failure returning 0
                        if new_bal == 0 and self.current_balance > 10:
                             Logger.warning(f"⚠️ RPC Balance Glitch? Read $0, keeping ${self.current_balance:.2f}")
                        else:
                             self.current_balance = new_bal
                
                # V91.0: Print Throttling (Log scan every 3 cycles unless opportunity found)
                if not hasattr(self, '_scan_counter'): self._scan_counter = 0
                self._scan_counter += 1
                should_print = (self._scan_counter % 3 == 0)

                # Scan (prioritize hot pairs in adaptive mode)
                try:
                    # Smart pod rotation: focus on diversified pods (STABLE + MEME + META)
                    active_pod_names = []
                    if self._smart_pods_enabled:
                        active_pod_names = pod_manager.get_active_pods()
                        scan_pairs = pod_manager.get_pairs_for_pods(active_pod_names)
                        
                        # V91.0: Optimization - Skip SOL pairs initially for speed (50% reduction)
                        # We only add SOL pairs if USDC side is profitable later
                        scan_pairs = [p for p in scan_pairs if p[2] == USDC_MINT]
                        
                        # Add watch pairs (always included)
                        watch_pairs = pod_manager.get_watch_pairs()
                        if watch_pairs:
                            # Find tuples for watched pairs from all pods
                            all_pod_pairs = _build_pairs_from_pods([p for p in ALL_PODS.values()])
                            for wp in watch_pairs:
                                for pair_tuple in all_pod_pairs:
                                    if pair_tuple[0] == wp and pair_tuple not in scan_pairs:
                                        # Only add USDC variant for speed
                                        if pair_tuple[2] == USDC_MINT:
                                            scan_pairs.append(pair_tuple)
                        
                        # V91.0: Smart Priority Sorting (Best 15 pairs)
                        # Sort by: Success rate (high) + Cooldown (low) + Spread Potential
                        try:
                            from src.shared.system.db_manager import db_manager
                            ranked_pairs = []
                            for p in scan_pairs:
                                stats = db_manager.get_pair_performance(p[0])
                                score = stats.get('score', 0.5)
                                # Bonus for fresh pairs (low attempts)
                                if stats.get('attempts', 0) < 5:
                                    score += 0.2
                                ranked_pairs.append((p, score))
                            
                            # Sort by score descending
                            ranked_pairs.sort(key=lambda x: x[1], reverse=True)
                            
                            # V91.1: Guard Watcher Pairs (Force Include)
                            final_pairs = []
                            watch_set = set(watch_pairs) if watch_pairs else set()
                            
                            # 1. Add Watchers first
                            included_indices = set()
                            for i, (p, score) in enumerate(ranked_pairs):
                                if p[0] in watch_set:
                                    final_pairs.append(p)
                                    included_indices.add(i)
                            
                            # V92.0: Adaptive Batch Sizing (Target 2000ms cycle)
                            if not hasattr(self, '_batch_size'): 
                                self._batch_size = 5
                                self._last_duration = 0
                            
                            # Adjust based on previous cycle (if available)
                            if hasattr(self, '_last_duration') and self._last_duration > 0:
                                target_ms = 2000
                                if self._last_duration < target_ms * 0.7:  # < 1400ms
                                    self._batch_size = min(12, self._batch_size + 1)
                                elif self._last_duration > target_ms * 1.3:  # > 2600ms
                                    self._batch_size = max(2, self._batch_size - 1)
                            
                            # 2. Fill to adaptive limit with best remaining
                            # V92.1: Fix Starvation - Ensure at least 2 rotating pairs
                            # even if watchers consume the whole batch budget.
                            
                            target_limit = self._batch_size
                            slots_active = len(final_pairs)
                            slots_remaining = target_limit - slots_active
                            
                            # Force at least 2 rotating pairs to keep discovery alive
                            if slots_remaining < 2:
                                slots_remaining = 2
                                
                            added_rotating = 0
                            for i, (p, score) in enumerate(ranked_pairs):
                                if added_rotating >= slots_remaining:
                                    break
                                if i not in included_indices:
                                    final_pairs.append(p)
                                    added_rotating += 1
                                    
                            self.config.pairs = final_pairs
                            
                        except Exception as e:
                             Logger.debug(f"Ranking error: {e}")
                             self.config.pairs = scan_pairs[:5] # Fallback to 5
                        
                    
                        # ML FILTER: Skip tokens with >80% LIQ failure rate
                        # Cache blacklist to avoid repeated DB queries (refresh every 5 min)
                        if not hasattr(self, '_blacklist_cache') or time.time() - self._blacklist_cache_ts > 300:

                            try:
                                from src.shared.system.db_manager import db_manager
                                liq_rates = db_manager.get_liq_failure_rate(hours=2)
                                self._blacklist_cache = [p for p, rate in liq_rates.items() if rate > 0.8]
                                self._blacklist_cache_ts = time.time()
                            except Exception:
                                self._blacklist_cache = []
                                self._blacklist_cache_ts = time.time()
                        
                        # Force-disable blacklist to recover OG_B
                        # blacklisted = self._blacklist_cache
                        blacklisted = [] 
                        if blacklisted:
                            before_count = len(self.config.pairs)
                            self.config.pairs = [p for p in self.config.pairs if p[0] not in blacklisted]
                            skip_count = before_count - len(self.config.pairs)
                            if skip_count > 0:
                                print(f"   🚫 ML Skip: {skip_count} blacklisted pairs ({', '.join(blacklisted[:2])}...)")
                            
                            # If ALL pairs blacklisted, try next pod
                            if len(self.config.pairs) == 0 and len(active_pod_names) == 1:
                                # Get next pod that's not this one
                                alt_pods = [n for n in pod_manager.state.keys() if n != active_pod_names[0]]
                                if alt_pods:
                                    active_pod_names = [alt_pods[0]]
                                    scan_pairs = pod_manager.get_pairs_for_pods(active_pod_names)
                                    self.config.pairs = [p for p in scan_pairs if p[0] not in blacklisted]
                                    print(f"   ⏭️ Pod skip: trying {active_pod_names[0]} instead")
                        
                        watch_str = f" +{len(watch_pairs)} watch" if watch_pairs else ""
                        print(f"   🔀 [POD] {', '.join(active_pod_names)} ({len(self.config.pairs)} pairs{watch_str})")
                        if not self.config.pairs:
                             print(f"   ⚠️ WARNING: All pairs in {active_pod_names} likely blacklisted too!")
                    elif adaptive_mode and monitor:
                        self.config.pairs = monitor.get_priority_pairs(self.config.pairs)
                    
                    # Calculate trade size for this iteration
                    limit = self.config.max_trade if self.config.max_trade > 0 else float('inf')
                    trade_size = min(self.current_balance, limit)

                    # Single scan with per-pair filtering (skips stale/low-spread pairs)
                    scan_start = time.time()
                    Logger.info(f"DEBUG: Calling scan with {len(self.config.pairs)} pairs...")
                    opportunities, all_spreads = await self.scan_opportunities(
                        verbose=should_print, 
                        scanner=monitor if adaptive_mode else None
                    )
                    Logger.info(f"DEBUG: Scan returned {len(opportunities)} opps, {len(all_spreads)} spreads.")
                    scan_duration_ms = (time.time() - scan_start) * 1000
                    self._last_duration = scan_duration_ms  # V92.0: Feed into adaptive sizing
                    
                    if should_print:
                        print(f"   ⏱️ Scan: {scan_duration_ms:.0f}ms | Batch: {self._batch_size} pairs")
                    
                    # Log cycle timing for ML optimization
                    if self._smart_pods_enabled and active_pod_names:
                        try:
                            from src.shared.system.db_manager import db_manager
                            for pod_name in active_pod_names:
                                db_manager.log_cycle(pod_name, len(self.config.pairs), scan_duration_ms / len(active_pod_names))
                        except Exception:
                            pass  # Non-critical
                    
                    # Log spread decay for ML learning (compare to previous scan)
                    if hasattr(self, '_last_spreads') and all_spreads:
                        try:
                            from src.shared.system.db_manager import db_manager
                            current_time = time.time()
                            for opp in all_spreads:
                                if opp.pair in self._last_spreads:
                                    prev_spread, prev_time = self._last_spreads[opp.pair]
                                    time_delta = current_time - prev_time
                                    if time_delta > 0 and time_delta < 120:  # Only log if < 2 min apart
                                        db_manager.log_spread_decay(opp.pair, prev_spread, opp.spread_pct, time_delta)
                        except Exception:
                            pass
                    
                    # Store current spreads for next comparison
                    self._last_spreads = {opp.pair: (opp.spread_pct, time.time()) for opp in all_spreads} if all_spreads else {}
                    
                    # Update adaptive interval based on results (no redundant RPC call)
                    if adaptive_mode and monitor:
                        current_interval = monitor.update(all_spreads)
                    
                    # Reporting moved to after verification to filter out LIQ/SLIP failures
                        
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    Logger.error(f"Scan error: {e}")
                    opportunities = []
                
                # Execute best opportunity not on cooldown
                verified_opps = []
                
                # Sort opportunities for verification
                
                # Sort by NET PROFIT (descending) - prioritize actually profitable opportunities
                raw_opps = sorted(opportunities, key=lambda x: x.net_profit_usd, reverse=True)
                
                # Check Top Candidates for Real Liquidity
                # V12.2: Parallel DSM Pre-Check (Local/API) -> Then Parallel RPC Verification
                
                # 1. Select Candidates (Top 8 to allow for filtering)
                candidates = []
                for opp in raw_opps[:8]:
                    if time.time() - last_trade_time.get(opp.pair, 0) >= cooldown:
                        candidates.append(opp)
                
                if candidates:
                    # 2. Pre-Check all candidates in parallel using DSM (Liquidity + Slippage)
                    # This prevents wasting RPC calls on bad pairs
                    from src.shared.system.data_source_manager import DataSourceManager
                    dsm = DataSourceManager()
                    
                    pre_checked = []
                    
                    # We can run these synchronously as they are fast (cached or HTTP API)
                    # or use ThreadPool if needed, but local cache is instant
                    for opp in candidates:
                         # A. Liquidity Check
                         liq = dsm.get_liquidity(opp.base_mint)
                         if liq > 0 and liq < 5000:
                             opp.verification_status = f"❌ LIQ (${liq/1000:.1f}k)"
                             continue
                             
                         # B. Slippage Check
                         passes, slip, _ = dsm.check_slippage_filter(opp.base_mint)
                         if not passes:
                             opp.verification_status = f"❌ SLIP ({slip:.1f}%)"
                             continue
                             
                         pre_checked.append(opp)
                    
                    # 3. Verify survivors with RPC (Top 4)
                    valid_candidates = pre_checked[:4]
                    
                    if valid_candidates:
                        
                        async def verify_one(opp):
                            try:
                                is_valid, real_net, status_msg = await self._executor.verify_liquidity(opp, trade_size)
                                opp.verification_status = status_msg
                                opp.net_profit_usd = real_net
                                return opp
                            except Exception as e:
                                opp.verification_status = f"ERR: {e}"
                                return opp
                        
                        verified_opps = await asyncio.gather(*[verify_one(c) for c in valid_candidates])
                        
                    # Add back the failed pre-checks so they show in dashboard
                    verified_opps.extend([c for c in candidates if c not in valid_candidates])
                    
                # PRINT DASHBOARD (with verification status)
                # We pass 'all_spreads' (all scan results) + 'verified_opps' (updated top 3)
                # PRINT DASHBOARD (with verification status)
                # We pass 'all_spreads' (all scan results) + 'verified_opps' (updated top 3)
                self.reporter.print_dashboard(
                    spreads=all_spreads if 'all_spreads' in locals() else raw_opps,
                    verified_opps=verified_opps,
                    pod_names=active_pod_names if self._smart_pods_enabled else None,
                    balance=self.current_balance,
                    gas=self.gas_balance,
                    daily_profit=self.tracker.daily_profit
                )
                
                # Report verified/actionable results to PodManager
                # This prevents pods from being promoted for finding "LIQ" or "SLIP" failed opportunities
                if self._smart_pods_enabled and active_pod_names:
                    is_actionable = False
                    if verified_opps:
                        for op in verified_opps:
                            status = str(op.verification_status or "LIVE")
                            if "LIVE" in status or "SCALED" in status:
                                is_actionable = True
                                break
                            # Actionable near-miss: > -$0.20 and NOT a structural failure (LIQ/SLIP/ERR)
                            if op.net_profit_usd > -0.20 and not any(x in status for x in ["LIQ", "SLIP", "ERR"]):
                                is_actionable = True
                                break
                    
                    for pod_name in active_pod_names:
                        pod_manager.report_result(pod_name, found_opportunity=is_actionable, executed=False, success=False)
                
                # Sticky Watch Logic: Automatically track "Warm" opportunities (Net Profit > -$0.20)
                # This ensures we don't rotate away from a pair that is about to become profitable
                if self._smart_pods_enabled:
                     # Check all scanned spreads
                     candidates_to_check = all_spreads if 'all_spreads' in locals() else raw_opps
                     for op in candidates_to_check:
                         metrics = NearMissAnalyzer.calculate_metrics(op)
                         if metrics.status in ["NEAR_MISS", "WARM"]:
                             # Don't track if it failed verification (LIQ/SLIP)
                             status = str(op.verification_status or "")
                             if "LIQ" in status or "SLIP" in status or "ERR" in status:
                                 continue
                             
                             if op.pair not in pod_manager.watch_list:
                                 pod_manager.add_to_watch(op.pair, reason=metrics.status)
                                 # Logger.info(f"[WATCH] 👀 Locked onto {op.pair} ({metrics.status})")
                
                # ═══════════════════════════════════════════════════════════════
                # FAST-PATH EXECUTION: Skip verification for near-miss opportunities
                # Uses per-pair ML thresholds based on historical profit decay
                # Also checks minimum spread requirement from success history
                # Risk is limited to gas cost (~$0.02) due to atomic revert
                # ═══════════════════════════════════════════════════════════════
                
                # Check for fast-path candidates using per-pair thresholds
                fast_path_candidates = []
                from src.shared.system.db_manager import db_manager
                
                for op in raw_opps:
                    # Skip if on cooldown
                    if time.time() - last_trade_time.get(op.pair, 0) < cooldown:
                        continue
                    
                    # A. Optimistic Unified Path (New)
                    # If Unified Engine is active and Dexes are compatible, we trust atomic revert
                    # This bypasses verification latency for "Scan to Act" speed
                    if self.trade_engine.use_unified:
                        if op.buy_dex in ["METEORA", "ORCA"] and op.sell_dex in ["METEORA", "ORCA"]:
                             # Low threshold for atomic speed
                             if op.net_profit_usd > 0.02: 
                                 op.verification_status = "✨ OPTIMISTIC" 
                                 fast_path_candidates.append(op)
                                 continue

                    # B. Standard ML Fast Path
                    # Check 1: Net profit threshold (per-pair ML) with V88.0 decay buffer
                    pair_threshold = get_pair_threshold(op.pair, self.config.fast_path_threshold)
                    # V88.0: Subtract expected decay to get realistic profit
                    expected_net = op.net_profit_usd - self.config.decay_buffer
                    if expected_net < 0.10:  # Must still be profitable after decay
                        continue
                    if op.net_profit_usd < pair_threshold:
                        continue
                    
                    # Check 2: V88.0 Liquidity Filter
                    # Skip if pool liquidity < trade_size * multiplier
                    min_liquidity = trade_size * self.config.liquidity_multiplier
                    op_liquidity = getattr(op, 'liquidity_usd', 0) or 0
                    if op_liquidity > 0 and op_liquidity < min_liquidity:
                        continue
                    
                    # Check 3: Minimum spread from success history (ML-learned)
                    min_spread_ml = db_manager.get_minimum_profitable_spread(op.pair, hours=24)
                    if min_spread_ml > 0 and op.spread_pct < min_spread_ml * 0.9:
                        continue
                    
                    # Check 4: Bootstrap minimum spread (observed defaults)
                    # Used until ML has enough data
                    min_spread_bootstrap = get_bootstrap_min_spread(op.pair)
                    if min_spread_bootstrap > 0 and op.spread_pct < min_spread_bootstrap:
                        continue
                    
                    op.verification_status = "⚡ FAST ML"
                    fast_path_candidates.append(op)
                
                if fast_path_candidates:
                    # Pick best by net profit (closest to positive)
                    best_fast = sorted(fast_path_candidates, key=lambda x: x.net_profit_usd, reverse=True)[0]
                    pair_threshold = get_pair_threshold(best_fast.pair, self.config.fast_path_threshold)
                    
                    print(f"   [{now}] ⚡ FAST-PATH: {best_fast.pair} @ ${best_fast.net_profit_usd:+.3f} (threshold: ${pair_threshold:+.3f})")
                    
                    # Execute immediately - atomic revert protects us
                    fast_start = time.time()
                    result = await self.execute_trade(best_fast, trade_size=trade_size)
                    fast_latency_ms = (time.time() - fast_start) * 1000
                    
                    # Log for ML training data
                    from src.shared.system.db_manager import db_manager
                    
                    if result.get("success"):
                        trade = result["trade"]
                        last_trade_time[best_fast.pair] = time.time()
                        
                        # Log successful fast-path
                        db_manager.log_fast_path({
                            'pair': best_fast.pair,
                            'scan_profit_usd': best_fast.net_profit_usd,
                            'execution_profit_usd': trade.get('net_profit', 0),
                            'profit_delta': trade.get('net_profit', 0) - best_fast.net_profit_usd,
                            'spread_pct': best_fast.spread_pct,
                            'trade_size_usd': trade_size,
                            'gas_cost_usd': 0.02,  # Estimate
                            'latency_ms': fast_latency_ms,
                            'success': True,
                            'revert_reason': None,
                            'buy_dex': best_fast.buy_dex,
                            'sell_dex': best_fast.sell_dex,
                        })
                        
                        emoji = "💰" if trade["net_profit"] > 0 else "📉"
                        print(f"   [{now}] {emoji} FAST #{self.total_trades}: {trade['pair']}")
                        print(f"            Spread: +{trade['spread_pct']:.2f}% → Net: ${trade['net_profit']:+.4f}")
                        print(f"            Balance: ${self.current_balance:.4f}")
                        print()
                    else:
                        revert_reason = result.get('error', 'atomic revert')
                        
                        # Extract execution profit from revert message if available
                        exec_profit = 0.0
                        import re
                        match = re.search(r'\$([+-]?\d+\.?\d*)', revert_reason)
                        if match:
                            exec_profit = float(match.group(1))
                        
                        # Log reverted fast-path for ML
                        db_manager.log_fast_path({
                            'pair': best_fast.pair,
                            'scan_profit_usd': best_fast.net_profit_usd,
                            'execution_profit_usd': exec_profit,
                            'profit_delta': exec_profit - best_fast.net_profit_usd,
                            'spread_pct': best_fast.spread_pct,
                            'trade_size_usd': trade_size,
                            'gas_cost_usd': 0.02,
                            'latency_ms': fast_latency_ms,
                            'success': False,
                            'revert_reason': revert_reason,
                            'buy_dex': best_fast.buy_dex,
                            'sell_dex': best_fast.sell_dex,
                        })
                        
                        print(f"   [{now}] ❌ FAST REVERTED: {revert_reason}")
                    
                    continue  # Skip normal execution path
                
                # ═══════════════════════════════════════════════════════════════
                # NORMAL EXECUTION: Verified opportunities only
                # ═══════════════════════════════════════════════════════════════
                
                # Execute Best Valid Opportunity
                # Look for "LIVE" or "SCALED" (Default to LIVE if status is None/Empty, consistent with Reporter)
                valid_opps = [op for op in verified_opps if "LIVE" in str(op.verification_status or "LIVE") or "SCALED" in str(op.verification_status or "")]
                
                # DEBUG: Show what we found
                if verified_opps:
                    for op in verified_opps:
                        Logger.debug(f"   Verified: {op.pair} -> {op.verification_status} @ ${op.net_profit_usd:+.3f}")
                if valid_opps:
                    print(f"   🎯 {len(valid_opps)} LIVE opportunities ready for execution")
                    # Pick best by Real Net Profit
                    best_opp = sorted(valid_opps, key=lambda x: x.net_profit_usd, reverse=True)[0]
                    
                    # Check for scaled size
                    exec_size = trade_size
                    status_str = str(best_opp.verification_status or "")
                    if "SCALED" in status_str:
                        import re
                        match = re.search(r'\$(\d+)', status_str)
                        if match:
                            exec_size = float(match.group(1))
                            # Skip if liquidity is too thin (< $10)
                            if exec_size < 10:
                                print(f"   ⏭️ Skipping {best_opp.pair} - liquidity too thin (${exec_size:.0f} < $10)")
                                continue
                    
                    result = await self.execute_trade(best_opp, trade_size=exec_size)
                    
                    if result.get("success"):
                        trade = result["trade"]
                        last_trade_time[best_opp.pair] = time.time()
                        
                        emoji = "💰" if trade["net_profit"] > 0 else "📉"
                        print(f"   [{now}] {emoji} {trade['mode']} #{self.total_trades}: {trade['pair']}")
                        print(f"            Spread: +{trade['spread_pct']:.2f}% → Net: ${trade['net_profit']:+.4f}")
                        print(f"            Balance: ${self.current_balance:.4f}")
                        print()
                        
                    else:
                        print(f"   [{now}] ❌ TRADE FAILED: {result.get('error')}")
                        
                elif raw_opps and not valid_opps:
                     # Dashboard showed failures, no extra print needed usually, 
                     # but maybe a small summary if spread was high?
                     pass
                
                # ═══════════════════════════════════════════════════════════════
                # LANDLORD: Delta-neutral yield farming on idle capital
                # If no execution happened this cycle, tick the Landlord
                # ═══════════════════════════════════════════════════════════════
                if self._landlord and self.config.live_mode:
                    try:
                        # Determine if we had an arb opportunity (to close hedge for)
                        has_arb = bool(valid_opps and len(valid_opps) > 0)
                        
                        # Calculate spot inventory value
                        inventory_usd = self.current_balance
                        
                        # Tick the Landlord (will open/close/monitor hedges)
                        landlord_result = await self._landlord.tick(inventory_usd, arb_opportunity=has_arb)
                        
                        if landlord_result.get("action") == "OPEN_HEDGE":
                            Logger.info(f"[LANDLORD] 🏠 Opened hedge: {landlord_result}")
                        elif landlord_result.get("action") == "CLOSE_FOR_ARB":
                            Logger.info(f"[LANDLORD] 📉 Closed hedge for arb opportunity")
                    except Exception as e:
                        Logger.debug(f"[LANDLORD] Tick error: {e}")
                # Smart Sleep: Wait for interval OR WSS trigger
                try:
                    await asyncio.wait_for(wake_event.wait(), timeout=current_interval)
                except asyncio.TimeoutError:
                    pass  # Timeout reached, loop normally
                except asyncio.CancelledError:
                    raise # Propagate cancellation
                
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\n   Stopping...")
        finally:
            if 'coordinator' in locals() and coordinator:
                await coordinator.stop()
        
        self.reporter.print_summary(start_time, self.starting_balance, self.current_balance, self.trades, mode_str)
        self.reporter.save_session(self.trades, self.starting_balance, self.current_balance, start_time, self.tracker)
    
# CLI ENTRY (for direct module execution)
# ═══════════════════════════════════════════════════════════════════

async def run_arbiter(
    budget: float = 50.0,
    live: bool = False,
    duration: int = 10,
    interval: int = 5,
    min_spread: float = 0.50,
    max_trade: float = 10.0,
    full_wallet: bool = False
) -> None:
    """Run the arbiter with given configuration."""
    config = ArbiterConfig(
        budget=budget,
        min_spread=min_spread,
        max_trade=max_trade,
        live_mode=live,
        full_wallet=full_wallet
    )
    
    arbiter = PhantomArbiter(config)
    await arbiter.run(duration_minutes=duration, scan_interval=interval)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Phantom Arbiter")
    parser.add_argument("--live", action="store_true", help="Enable LIVE trading")
    parser.add_argument("--budget", type=float, default=50.0, help="Starting budget")
    parser.add_argument("--duration", type=int, default=10, help="Duration in minutes")
    parser.add_argument("--interval", type=int, default=5, help="Scan interval in seconds")
    parser.add_argument("--min-spread", type=float, default=0.50, help="Minimum spread percent")
    parser.add_argument("--max-trade", type=float, default=10.0, help="Maximum trade size")
    parser.add_argument("--full-wallet", action="store_true", help="Use entire wallet balance")
    
    args = parser.parse_args()
    
    if args.live:
        print("\n" + "⚠️ "*20)
        print("   WARNING: LIVE MODE ENABLED!")
        print("⚠️ "*20)
        confirm = input("\n   Type 'I UNDERSTAND' to proceed: ")
        if confirm.strip() != "I UNDERSTAND":
            print("   Cancelled.")
            exit(0)
    
    asyncio.run(run_arbiter(
        budget=args.budget,
        live=args.live,
        duration=args.duration,
        interval=args.interval,
        min_spread=args.min_spread,
        max_trade=args.max_trade,
        full_wallet=args.full_wallet
    ))
