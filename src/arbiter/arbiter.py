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


# ═══════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOL_MINT = "So11111111111111111111111111111111111111112"

# ═══════════════════════════════════════════════════════════════════
# TRADING PAIRS BY RISK TIER
# ═══════════════════════════════════════════════════════════════════

# LOW RISK: Blue chips, high liquidity, tight spreads (0.05-0.3%)
LOW_RISK_PAIRS = [
    ("SOL/USDC", SOL_MINT, USDC_MINT),
    ("JUP/USDC", "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", USDC_MINT),
    ("RAY/USDC", "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R", USDC_MINT),
    ("ORCA/USDC", "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE", USDC_MINT),
]

# MID RISK: Established tokens, moderate volatility, wider spreads possible (0.2-0.8%)
MID_RISK_PAIRS = [
    ("WIF/USDC", "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", USDC_MINT),
    ("BONK/USDC", "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", USDC_MINT),
    ("PYTH/USDC", "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3", USDC_MINT),
    ("JITO/USDC", "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn", USDC_MINT),
    ("HNT/USDC", "hntyVP6YFm1Hg25TN9WGLqM12b8TQmcknKrdu1oxWux", USDC_MINT),
    ("RENDER/USDC", "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof", USDC_MINT),
    ("TNSR/USDC", "TNSRxcUxoT9xBG3de7PiJyTDYu7kskLqcpddxnEJAS6", USDC_MINT),
]

# HIGH RISK: Memes and small caps, volatile, wide spreads (0.5-2%+)
HIGH_RISK_PAIRS = [
    ("SAMO/USDC", "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU", USDC_MINT),
    ("MNGO/USDC", "MangoCzJ36AjZyKwVj3VnYU4GTonjfVEnJmvvWaxLac", USDC_MINT),
    ("FIDA/USDC", "EchesyfXePKdLtoiZSL8pBe8Myagyy8ZRqsACNCFGnvp", USDC_MINT),
    ("STEP/USDC", "StepWBPggCzpZJz6XHjZpJZGZgRZSAmDkCdMX4sWsmc", USDC_MINT),
    ("COPE/USDC", "8HGyAAB1yoM1ttS7pXjHMa3dukTFGQggnFFH3hJZgzQh", USDC_MINT),
]

# ═══════════════════════════════════════════════════════════════════
# TRENDING: High-volatility Dec 2025 - Pump.fun graduates with 1.5-5%+ spreads
# Includes BOTH USDC and SOL pairs for deeper liquidity access
# ═══════════════════════════════════════════════════════════════════

# AI & Narrative Tier (High spreads, news-driven)
_AI_TOKENS = [
    ("GOAT", "CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump"),      # Goatseus Maximus
    ("ACT", "GJAFwWjJ3vnTsrQVabjBVK2TYB1YtRCQXRDfDgUnpump"),       # AI Prophecy
    ("AI16Z", "4ptu2LhxRTERJNJWqnYZ681srxquMBumTHD3XQvDRTjt"),     # AI16Z
    ("FARTCOIN", "9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump"), # Meteora bin volatility
]

# Viral Meme Tier (High volume, zero $30 impact)
_MEME_TOKENS = [
    ("PNUT", "2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump"),      # Peanut Squirrel
    ("MOODENG", "ED5nyyWEzpPPiWimP8vYm7sD7TD3LAt3Q3gRTWHzPJBY"),   # Moo Deng
    ("CHILLGUY", "Df6yfrKC8kZE3KNkrHERKzAetSxbrWeniQfyJY4Jpump"),  # TikTok viral
    ("PENGU", "2zMMhcVQEXDtdE6vsFS7S7D5oUodfJHE8vd1gnBouauv"),     # Pudgy Penguins
    ("POPCAT", "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr"),    # Popcat
]

# Heavy-Hitter Tier (Strategic targets)
_HEAVY_TOKENS = [
    ("PIPPIN", "Dfh5DzRgSvvCFDoYc2ciTkMrbDfRKybA4SoFbPmApump"),    # Pippin
    ("TRUMP", "6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN"),     # Official Trump
    ("FWOG", "A8C3xuqscfmyLrte3VmTqrAq8kgMASius9AFNANwpump"),      # Fwog
    ("GIGA", "8v8GSr4p7Gz8xw6nF22m1LSfSgY7T2nBv2nK3y7f3z6A"),      # Gigachad
]

# Build TRENDING_PAIRS with BOTH USDC and SOL quote currencies
TRENDING_PAIRS = []
for symbol, mint in _AI_TOKENS + _MEME_TOKENS + _HEAVY_TOKENS:
    TRENDING_PAIRS.append((f"{symbol}/USDC", mint, USDC_MINT))
    TRENDING_PAIRS.append((f"{symbol}/SOL", mint, SOL_MINT))

# Combined default - all pairs for maximum opportunity scanning
CORE_PAIRS = LOW_RISK_PAIRS + MID_RISK_PAIRS + HIGH_RISK_PAIRS + TRENDING_PAIRS


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
    # Fast-path threshold (Option A: Conservative baseline)
    # Require +$0.12 at scan time to absorb typical ~$0.10 decay
    fast_path_threshold: float = 0.12  # Must show 12 cents PROFIT at scan


# Bootstrap defaults based on observed data (used until ML has enough samples)
# These protect against wasted gas on pairs with known issues
BOOTSTRAP_MIN_SPREADS = {
    "PIPPIN": 2.0,   # Observed 1.2% → reverts with -$0.07 to -$0.14
    "PNUT": 1.8,     # Observed 1.2% → reverts with -$0.13
    "ACT": 2.5,      # High LIQ failure rate
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
                return max(required, default)  # Never below baseline
        
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
        self.telegram = TelegramManager()
        self.telegram.start()
        
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
            self._executor = ArbitrageExecutor(
                wallet=self._wallet,
                swapper=self._swapper,
                mode=ExecutionMode.LIVE
            )
            self._connected = True
            
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
            
            self._detector = SpreadDetector(feeds=[
                JupiterFeed(),
                RaydiumFeed(),
                OrcaFeed(use_on_chain=False),
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
    
    def _print_dashboard(self, spreads: List[SpreadOpportunity], verified_opps: List[SpreadOpportunity] = None):
        """Print the market dashboard with merged verification status."""
        now = datetime.now().strftime("%H:%M:%S")
        
        # Verify map for O(1) lookup
        verified_map = {op.pair: op for op in (verified_opps or [])}
        
        # Clear line and print table header
        print(f"\n   [{now}] MARKET SCAN | Bal: ${self.current_balance:.2f} | Gas: ${self.gas_balance:.2f} | Day P/L: ${self.tracker.daily_profit:+.2f}")
        print(f"   {'Pair':<12} {'Buy':<8} {'Sell':<8} {'Spread':<8} {'Net':<10} {'Status'}")
        print("   " + "-"*60)
        
        profitable_count = 0
        
        # We only show top N spreads to avoid spam, or all? 
        # Original showed all spreads passed to it (which was all scanned pairs).
        # Let's show all spreads, but updated with verification info if available.
        
        for opp in spreads:
            # Check if we have verified data for this opp
            verified = verified_map.get(opp.pair)
            
            if verified:
                # Use verified data (Real Net Profit & Status)
                net_profit = verified.net_profit_usd
                spread_pct = verified.spread_pct # Should match scan usually
                
                # Status: "✅ LIVE" or "❌ LIQ ($...)"
                status = verified.verification_status or "✅ LIVE"
                if "LIVE" in status:
                     status = "✅ READY" # Keep UI consistent for good ones
                elif "LIQ" in status:
                     status = "❌ LIQ" # Shorten for table
                
            else:
                # Use Scan data + NearMissAnalyzer for nuanced status
                net_profit = opp.net_profit_usd
                spread_pct = opp.spread_pct
                
                # Calculate near-miss metrics for rich status display
                metrics = NearMissAnalyzer.calculate_metrics(opp)
                status = metrics.status_icon
            
            if opp.is_profitable:
                profitable_count += 1
                
            # Color/Format based on status
            print(f"   {opp.pair:<12} {opp.buy_dex:<8} {opp.sell_dex:<8} +{spread_pct:.2f}%   ${net_profit:+.3f}    {status}")
        
        print("-" * 60)
        
        if profitable_count > 0:
            print(f"   🎯 {profitable_count} profitable opportunit{'y' if profitable_count == 1 else 'ies'}!")
        
        # Format for Telegram Dashboard (Code Block - SAFE MODE)
        # We wrap everything in a code block to avoid MarkdownV2 400 errors
        
        tg_table = [
            f"[{now}] MARKET SCAN | P/L: ${self.tracker.daily_profit:+.2f}",
            f"{'Pair':<11} {'Spread':<7} {'Net':<8} {'St'}",
            "-" * 33
        ]
        
        # Add ALL rows to TG table
        for i, opp in enumerate(spreads):
            verified = verified_map.get(opp.pair)
            status = "❌"
            net = f"${opp.net_profit_usd:+.3f}"
            spread = f"{opp.spread_pct:+.2f}%"
            
            if verified:
                net = f"${verified.net_profit_usd:+.3f}"
                if "LIVE" in (verified.verification_status or ""):
                    status = "✅"
                elif "SCALED" in (verified.verification_status or ""):
                    status = "⚠️"
                elif "LIQ" in (verified.verification_status or ""):
                    status = "💧"
            else:
                # Use NearMissAnalyzer for better status
                metrics = NearMissAnalyzer.calculate_metrics(opp)
                match metrics.status:
                    case "VIABLE": status = "✅"
                    case "NEAR_MISS": status = "⚡"
                    case "WARM": status = "🔸"
                    case _: status = "❌"
            
            tg_table.append(f"{opp.pair[:10]:<11} {spread:<7} {net:<8} {status}")
            
        if profitable_count:
            tg_table.append(f"\n🎯 {profitable_count} Opportunities!")
            
        # Beam to Telegram (Wrapped in Code Block)
        final_msg = "```\n" + "\n".join(tg_table) + "\n```"
        self.telegram.update_dashboard(final_msg)
        
        if profitable_count:
            print(f"   🎯 {profitable_count} profitable opportunities!")
    
    async def execute_trade(self, opportunity: SpreadOpportunity, trade_size: float = None) -> Dict[str, Any]:
        """Execute a trade using the ArbitrageExecutor."""
        if trade_size is None:
            trade_size = min(
                self.current_balance,
                self.config.max_trade if self.config.max_trade > 0 else float('inf')
            )
        
        if trade_size < 1.0:
            return {"success": False, "error": "Insufficient balance"}
        
        result = await self._executor.execute_spatial_arb(opportunity, trade_size)
        
        if result.success:
            # Use opportunity's calculated net profit (includes accurate fees)
            net_profit = opportunity.net_profit_usd * (trade_size / opportunity.max_size_usd)
            
            self.current_balance += net_profit
            self.total_profit += net_profit
            self.total_trades += 1
            
            # Record in tracker for accurate stats
            self.tracker.record_trade(
                volume_usd=trade_size,
                profit_usd=net_profit,
                strategy="SPATIAL",
                pair=opportunity.pair
            )
            
            self.trades.append({
                "pair": opportunity.pair,
                "profit": net_profit,
                "fees": opportunity.estimated_fees_usd,
                "timestamp": time.time(),
                "mode": "LIVE" if self.config.live_mode else "PAPER"
            })
            
            return {
                "success": True,
                "trade": {
                    "pair": opportunity.pair,
                    "net_profit": net_profit,
                    "spread_pct": opportunity.spread_pct,
                    "fees": opportunity.estimated_fees_usd,
                    "mode": "LIVE" if self.config.live_mode else "PAPER"
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

    async def run(self, duration_minutes: int = 10, scan_interval: int = 5) -> None:
        """Main trading loop."""
        mode_str = "🔴 LIVE" if self.config.live_mode else "📄 PAPER"
        
        # Adaptive mode when interval = 0
        adaptive_mode = scan_interval == 0
        monitor = AdaptiveScanner() if adaptive_mode else None
        current_interval = monitor.base_interval if adaptive_mode else scan_interval
        
        
        # WSS Integration handled by SignalCoordinator later
        
        print("\n" + "="*70)
        
        print("\n" + "="*70)
        print(f"   PHANTOM ARBITER - {mode_str} TRADER")
        print("="*70)
        print(f"   Budget:     ${self.starting_balance:.2f} USDC | ${self.gas_balance:.2f} Gas")
        print(f"   Min Spread: {self.config.min_spread}% | Max Trade: ${self.config.max_trade:.2f}")
        scan_mode = "ADAPTIVE" if adaptive_mode else f"{scan_interval}s"
        print(f"   Pairs:      {len(self.config.pairs)} | Duration: {duration_minutes} min | Scan: {scan_mode}")
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
                
                # 1. Poll Scraper Signals
                new_pairs = coordinator.poll_signals()
                if new_pairs:
                    self.config.pairs.extend(new_pairs)
                    await coordinator.register_new_pairs(new_pairs)
                    print(f"   [{now}] 🧠 Added {len(new_pairs)} hot tokens from Scraper")
                
                # Live mode maintenance
                if self.config.live_mode and self._wallet:
                    await self._wallet.check_and_replenish_gas(self._swapper)
                    if self.config.full_wallet:
                        self.current_balance = self._wallet.get_balance(USDC_MINT)
                
                # Scan (prioritize hot pairs in adaptive mode)
                try:
                    if adaptive_mode and monitor:
                        self.config.pairs = monitor.get_priority_pairs(self.config.pairs)
                    
                    # Calculate trade size for this iteration
                    limit = self.config.max_trade if self.config.max_trade > 0 else float('inf')
                    trade_size = min(self.current_balance, limit)

                    # Single scan with per-pair filtering (skips stale/low-spread pairs)
                    opportunities, all_spreads = await self.scan_opportunities(
                        verbose=False, 
                        scanner=monitor if adaptive_mode else None
                    )
                    
                    # Update adaptive interval based on results (no redundant RPC call)
                    if adaptive_mode and monitor:
                        current_interval = monitor.update(all_spreads)
                        
                except Exception as e:
                    Logger.debug(f"Scan error: {e}")
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
                self._print_dashboard(all_spreads if 'all_spreads' in locals() else raw_opps, verified_opps)
                
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
                    
                    # Check 1: Net profit threshold (per-pair ML)
                    pair_threshold = get_pair_threshold(op.pair, self.config.fast_path_threshold)
                    if op.net_profit_usd < pair_threshold:
                        continue
                    
                    # Check 2: Minimum spread from success history (ML-learned)
                    min_spread_ml = db_manager.get_minimum_profitable_spread(op.pair, hours=24)
                    if min_spread_ml > 0 and op.spread_pct < min_spread_ml * 0.9:
                        continue
                    
                    # Check 3: Bootstrap minimum spread (observed defaults)
                    # Used until ML has enough data
                    min_spread_bootstrap = get_bootstrap_min_spread(op.pair)
                    if min_spread_bootstrap > 0 and op.spread_pct < min_spread_bootstrap:
                        continue
                    
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
                # Look for "LIVE" or "SCALED"
                valid_opps = [op for op in verified_opps if op.verification_status and ("LIVE" in op.verification_status or "SCALED" in op.verification_status)]
                
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
                    if "SCALED" in best_opp.verification_status:
                        import re
                        match = re.search(r'\$(\d+)', best_opp.verification_status)
                        if match:
                            exec_size = float(match.group(1))
                    
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
        
        self._print_summary(start_time, mode_str)
        self._save_session()
    
    def _print_summary(self, start_time: float, mode_str: str) -> None:
        """Print session summary."""
        runtime = (time.time() - start_time) / 60
        denom = self.starting_balance if self.starting_balance > 0 else 1
        roi = ((self.current_balance - self.starting_balance) / denom) * 100
        
        print("\n\n" + "="*70)
        print(f"   SESSION SUMMARY ({mode_str})")
        print("="*70)
        print(f"   Runtime:      {runtime:.1f} minutes")
        print(f"   Starting:     ${self.starting_balance:.2f}")
        print(f"   Ending:       ${self.current_balance:.4f}")
        print(f"   Profit:       ${self.total_profit:+.4f}")
        print(f"   ROI:          {roi:+.2f}%")
        print(f"   Trades:       {self.total_trades}")
        print("="*70)
    
    def _save_session(self) -> None:
        """Save session data to JSON."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        mode = "live" if self.config.live_mode else "paper"
        save_path = f"data/trading_sessions/{mode}_session_{timestamp}.json"
        
        denom = self.starting_balance if self.starting_balance > 0 else 1
        roi = ((self.current_balance - self.starting_balance) / denom) * 100
        
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, 'w') as f:
            json.dump({
                "mode": mode,
                "starting_balance": self.starting_balance,
                "ending_balance": self.current_balance,
                "total_profit": self.total_profit,
                "total_trades": self.total_trades,
                "roi_pct": roi,
                "trades": self.trades
            }, f, indent=2)
        
        print(f"\n   Session saved: {save_path}")


# ═══════════════════════════════════════════════════════════════════
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
