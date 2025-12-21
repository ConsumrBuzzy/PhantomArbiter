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
from src.arbiter.core.triangular_scanner import TriangularScanner
from src.arbiter.core.near_miss_analyzer import NearMissAnalyzer
from src.shared.infrastructure.jito_adapter import JitoAdapter
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
    use_unified_engine: bool = True


# ═══════════════════════════════════════════════════════════════════
# CALIBRATION (ML-informed thresholds)
# ═══════════════════════════════════════════════════════════════════
from src.arbiter.core.calibration import (
    BOOTSTRAP_MIN_SPREADS,
    get_pair_threshold,
    get_bootstrap_min_spread
)


class PhantomArbiter:
    """
    Main arbitrage orchestrator.
    
    Composes existing components to provide unified scanning and execution.
    Supports both paper and live trading modes.
    """
    
    def __init__(self, config: ArbiterConfig):
        self.config = config
        
        # 1. New Core Modular Components
        from src.arbiter.core.trade_tracker import TradeTracker
        self.tracker = TradeTracker(budget=config.budget, gas_budget=config.gas_budget)
        
        # 2. Communication Layer
        from src.shared.notification.telegram_manager import TelegramManager
        from src.arbiter.core.reporter import ArbiterReporter
        self.command_queue = queue.Queue()
        self.telegram = TelegramManager(command_queue=self.command_queue)
        self.telegram.start()
        self.reporter = ArbiterReporter(self.telegram)
        
        # 3. lazy-loaded Components
        self._detector = None
        self._executor = None
        self._triangular_scanner = None
        self._engine = None # ArbiterEngine (Lazy)
        
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
            
            # V120: Initialize StuckTokenGuard for safety net
            from src.arbiter.core.stuck_token_guard import StuckTokenGuard
            self._stuck_guard = StuckTokenGuard()
            
            self._executor = ArbitrageExecutor(
                wallet=self._wallet,
                swapper=self._swapper,
                jito_adapter=self._jito,
                mode=ExecutionMode.LIVE,
                stuck_token_guard=self._stuck_guard
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
            # Shared feeds for triangular scanner
            self._triangular_scanner = TriangularScanner(feeds=self._detector.feeds)
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
        
        # V115: Auto-Inject Bridge Pairs for Triangular Arbitrage (Smart Flop)
        # If we are scanning X/USDC, we MUST also scan X/SOL to see the triangle.
        # This respects the Pods/Scanner logic: we only add bridges for ACTIVE tokens.
        final_pairs = list(pairs_to_scan)
        SOL_MINT = "So11111111111111111111111111111111111111112"
        USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        
        # Ensure we scan SOL/USDC (Anchor)
        if ("SOL/USDC", SOL_MINT, USDC_MINT) not in final_pairs:
             final_pairs.append(("SOL/USDC", SOL_MINT, USDC_MINT))
             
        for p_name, base, quote in pairs_to_scan:
            if quote == USDC_MINT and base != SOL_MINT:
                # Add corresponding Bridge Pair (X/SOL)
                bridge_pair = (f"{p_name.split('/')[0]}/SOL", base, SOL_MINT)
                if bridge_pair not in final_pairs:
                    final_pairs.append(bridge_pair)
        
        spreads = await detector.scan_all_pairs(final_pairs, trade_size=trade_size)
        
        # V115: Update Triangular Graph & Check for Cycles
        if self._triangular_scanner:
            try:
                self._triangular_scanner.update_graph(detector, self.config.pairs)
                cycles = self._triangular_scanner.find_cycles(amount_in=trade_size)
                
                # V120: Reality Check for top candidates (Observation Mode)
                if cycles:
                    top_cycles = sorted(cycles, key=lambda x: x.net_profit_usd, reverse=True)[:2]
                    for cycle in top_cycles:
                        # Call executor in dry_run mode to fetch live quotes
                        await self.executor.execute_triangular_arb(cycle, dry_run=True)
            except Exception as e:
                Logger.debug(f"Triangular scan error: {e}")
        
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

    async def stop(self):
        """Clean shutdown of all components."""
        Logger.info("[ARB] 🛑 Shutting down Arbiter components...")
        self._connected = False
        
        if hasattr(self, '_detector') and self._detector:
            await self._detector.shutdown()
            
        if hasattr(self, '_jito') and self._jito:
            await self._jito.close()
            
        if hasattr(self, 'telegram') and self.telegram:
            self.telegram.stop()
            
        Logger.info("[ARB] ✅ Shutdown complete.")

    async def run(self, duration_minutes: int = 10, scan_interval: int = 5, smart_pods: bool = False, landlord=None) -> None:
        """Main trading loop (Delegated to ArbiterEngine)."""
        from src.arbiter.core.arbiter_engine import ArbiterEngine
        if not self._engine:
            self._engine = ArbiterEngine(self, self.tracker)
            
        try:
            await self._engine.run(
                duration_minutes=duration_minutes,
                scan_interval=scan_interval,
                smart_pods=smart_pods,
                landlord=landlord
            )
        finally:
            await self.stop()

    async def stop(self):
        """Clean shutdown of all components."""
        Logger.info("🛑 Shutting down PhantomArbiter...")
        if self.telegram:
            self.telegram.stop()
        
        # Close other persistent connections if any
        if hasattr(self, '_jito') and self._jito:
            await self._jito.close()
            
        print("   ✅ Shutdown complete. Goodbye!")

    @property
    def current_balance(self):
        return self.tracker.current_balance
        
    @current_balance.setter
    def current_balance(self, value):
        self.tracker.current_balance = value
        
    @property
    def gas_balance(self):
        return self.tracker.gas_balance
        
    @property
    def total_trades(self):
        return self.tracker.total_trades
        
    @property
    def starting_balance(self):
        return self.tracker.starting_balance

    @property
    def trades(self):
        return self.tracker.trades

    @property
    def executor(self):
        return self._executor
    
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
