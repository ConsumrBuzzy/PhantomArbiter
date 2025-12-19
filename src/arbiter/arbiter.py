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
from typing import Optional, Dict, List, Any

from config.settings import Settings
from src.shared.system.logging import Logger
from src.arbiter.core.spread_detector import SpreadDetector, SpreadOpportunity
from src.arbiter.core.executor import ArbitrageExecutor, ExecutionMode


# ═══════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# Core profitable pairs (high liquidity, tight spreads)
CORE_PAIRS = [
    ("SOL/USDC", "So11111111111111111111111111111111111111112", USDC_MINT),
    ("BONK/USDC", "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", USDC_MINT),
    ("WIF/USDC", "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", USDC_MINT),
    ("JUP/USDC", "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", USDC_MINT),
]


@dataclass
class ArbiterConfig:
    """Configuration for the arbiter."""
    budget: float = 50.0
    gas_budget: float = 5.0  # USD worth of SOL for gas
    min_spread: float = 0.20
    max_trade: float = 10.0
    live_mode: bool = False
    full_wallet: bool = False
    pairs: List[tuple] = field(default_factory=lambda: CORE_PAIRS)


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
        self._wallet = None
        self._swapper = None
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
            
            Logger.info(f"✅ LIVE MODE ENABLED - Wallet: {self._wallet.get_public_key()[:8]}...")
            
        except Exception as e:
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
    
    async def scan_opportunities(self, verbose: bool = True) -> List[SpreadOpportunity]:
        """Scan for spatial arbitrage opportunities."""
        detector = self._get_detector()
        spreads = detector.scan_all_pairs(self.config.pairs)
        
        # Filter profitable using SpreadOpportunity's own calculations
        profitable = [opp for opp in spreads if opp.is_profitable]
        
        if verbose and spreads:
            now = datetime.now().strftime("%H:%M:%S")
            
            # Clear line and print table header
            print(f"\n   [{now}] MARKET SCAN | Bal: ${self.current_balance:.2f} | Gas: ${self.gas_balance:.2f} | Day P/L: ${self.tracker.daily_profit:+.2f}")
            print(f"   {'Pair':<12} {'Buy':<8} {'Sell':<8} {'Spread':<8} {'Net':<10} {'Status'}")
            print("   " + "-"*60)
            
            for opp in spreads:
                status = "✅ READY" if opp.is_profitable else "❌"
                print(f"   {opp.pair:<12} {opp.buy_dex:<8} {opp.sell_dex:<8} +{opp.spread_pct:.2f}%   ${opp.net_profit_usd:+.3f}    {status}")
            
            print("   " + "-"*60)
            if profitable:
                print(f"   🎯 {len(profitable)} profitable opportunities!")
        
        return profitable
    
    async def execute_trade(self, opportunity: SpreadOpportunity) -> Dict[str, Any]:
        """Execute a trade using the ArbitrageExecutor."""
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
    
    async def run(self, duration_minutes: int = 10, scan_interval: int = 5) -> None:
        """Main trading loop."""
        mode_str = "🔴 LIVE" if self.config.live_mode else "📄 PAPER"
        
        print("\n" + "="*70)
        print(f"   PHANTOM ARBITER - {mode_str} TRADER")
        print("="*70)
        print(f"   Budget:     ${self.starting_balance:.2f} USDC | ${self.gas_balance:.2f} Gas")
        print(f"   Min Spread: {self.config.min_spread}% | Max Trade: ${self.config.max_trade:.2f}")
        print(f"   Pairs:      {len(self.config.pairs)} | Duration: {duration_minutes} min")
        print("="*70)
        print("\n   Running... (Ctrl+C to stop)\n")
        
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60) if duration_minutes > 0 else float('inf')
        
        last_trade_time: Dict[str, float] = {}
        cooldown = 5
        
        try:
            while time.time() < end_time:
                now = datetime.now().strftime("%H:%M:%S")
                
                # Live mode maintenance
                if self.config.live_mode and self._wallet:
                    await self._wallet.check_and_replenish_gas(self._swapper)
                    if self.config.full_wallet:
                        self.current_balance = self._wallet.get_balance(USDC_MINT)
                
                # Scan
                try:
                    opportunities = await self.scan_opportunities()
                except Exception as e:
                    Logger.debug(f"Scan error: {e}")
                    opportunities = []
                
                # Execute best opportunity not on cooldown
                for opp in sorted(opportunities, key=lambda x: x.spread_pct, reverse=True):
                    if time.time() - last_trade_time.get(opp.pair, 0) < cooldown:
                        continue
                    
                    result = await self.execute_trade(opp)
                    
                    if result.get("success"):
                        trade = result["trade"]
                        last_trade_time[opp.pair] = time.time()
                        
                        emoji = "💰" if trade["net_profit"] > 0 else "📉"
                        print(f"   [{now}] {emoji} {trade['mode']} #{self.total_trades}: {trade['pair']}")
                        print(f"            Spread: +{trade['spread_pct']:.2f}% → Net: ${trade['net_profit']:+.4f}")
                        print(f"            Balance: ${self.current_balance:.4f}")
                        print()
                        break
                    else:
                        print(f"   [{now}] ❌ TRADE FAILED: {result.get('error')}")
                        break
                
                await asyncio.sleep(scan_interval)
                
        except KeyboardInterrupt:
            pass
        
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
