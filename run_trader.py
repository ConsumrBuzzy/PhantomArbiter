"""
Phantom Arbiter - Unified Trader (Paper + Live)
=================================================
Switch between paper and live mode with one flag.

Usage:
    # Paper mode (default, safe)
    python run_trader.py --budget 50 --duration 10
    
    # Live mode (REAL MONEY!)
    python run_trader.py --live --budget 5 --duration 10
    
⚠️ LIVE MODE WILL EXECUTE REAL TRADES ⚠️
"""

import asyncio
import os
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

# Load .env file
from dotenv import load_dotenv
load_dotenv()

from config.settings import Settings
from src.system.logging import Logger


class UnifiedTrader:
    """
    Unified trader that works in both paper and live mode.
    
    Paper Mode: Uses real prices, simulates execution
    Live Mode:  Uses real prices, executes real swaps
    """
    
    def __init__(
        self,
        budget: float = 50.0,
        live_mode: bool = False,
        min_spread: float = 0.20,
        max_trade: float = 10.0
    ):
        self.budget = budget
        self.live_mode = live_mode
        self.min_spread = min_spread
        self.max_trade = max_trade
        
        # Wallet tracking
        self.current_balance = budget
        self.starting_balance = budget
        self.total_trades = 0
        self.total_profit = 0.0
        
        # Trade history
        self.trades: List[Dict] = []
        
        # Live mode setup
        self._live_executor = None
        if live_mode:
            self._setup_live_mode()
    
    def _setup_live_mode(self):
        """Setup live trading components."""
        private_key = os.getenv("PHANTOM_PRIVATE_KEY") or os.getenv("SOLANA_PRIVATE_KEY")
        
        if not private_key:
            print("\n❌ LIVE MODE FAILED: No private key found!")
            print("   Add PHANTOM_PRIVATE_KEY to .env")
            self.live_mode = False
            return
        
        try:
            from src.trading.live_executor import SolanaWallet, LiveTrader
            
            wallet = SolanaWallet(private_key)
            self._live_executor = LiveTrader(
                wallet=wallet,
                max_trade_usd=self.max_trade,
                require_confirmation=True
            )
            
            print(f"\n✅ LIVE MODE ENABLED")
            print(f"   Wallet: {wallet.public_key[:8]}...{wallet.public_key[-4:]}")
            print(f"   Max Trade: ${self.max_trade}")
            
        except Exception as e:
            print(f"\n❌ LIVE MODE FAILED: {e}")
            self.live_mode = False
    
    async def scan_opportunities(self, verbose: bool = True) -> List[Dict]:
        """Scan for spatial arbitrage opportunities."""
        opportunities = []
        all_spreads = []
        
        try:
            from src.arbitrage.core.spread_detector import SpreadDetector
            from src.arbitrage.feeds.jupiter_feed import JupiterFeed
            from src.arbitrage.feeds.raydium_feed import RaydiumFeed
            from src.arbitrage.feeds.orca_feed import OrcaFeed
            
            detector = SpreadDetector(feeds=[
                JupiterFeed(),
                RaydiumFeed(),
                OrcaFeed(use_on_chain=False),
            ])
            
            USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            pairs = [
                ("SOL/USDC", "So11111111111111111111111111111111111111112", USDC),
                ("BONK/USDC", "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", USDC),
                ("WIF/USDC", "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", USDC),
                ("JUP/USDC", "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", USDC),
            ]
            
            spreads = detector.scan_all_pairs(pairs)
            
            # Show all spreads
            if verbose:
                now = datetime.now().strftime("%H:%M:%S")
                print(f"\n   [{now}] MARKET SCAN:")
                print(f"   {'Pair':<12} {'Buy DEX':<10} {'Sell DEX':<10} {'Spread':<10} {'Status':<15}")
                print("   " + "-"*55)
            
            for opp in spreads:
                gross = opp.spread_pct
                fees = 0.20
                net = gross - fees
                
                # Determine status
                if net > 0:
                    status = "✅ PROFITABLE"
                elif gross >= self.min_spread:
                    status = "⚠️ Break-even"
                else:
                    status = "❌ Below min"
                
                if verbose:
                    print(f"   {opp.pair:<12} {opp.buy_dex:<10} {opp.sell_dex:<10} +{opp.spread_pct:.2f}%     {status}")
                
                all_spreads.append({
                    "pair": opp.pair,
                    "spread_pct": opp.spread_pct,
                    "status": status
                })
                
                if net > 0:
                    opportunities.append({
                        "pair": opp.pair,
                        "buy_dex": opp.buy_dex,
                        "buy_price": opp.buy_price,
                        "sell_dex": opp.sell_dex,
                        "sell_price": opp.sell_price,
                        "spread_pct": opp.spread_pct,
                        "net_pct": net,
                        "buy_mint": pairs[[p[0] for p in pairs].index(opp.pair)][1] if opp.pair in [p[0] for p in pairs] else None
                    })
            
            if verbose and opportunities:
                print(f"\n   🎯 {len(opportunities)} profitable opportunity found!")
                        
        except Exception as e:
            Logger.debug(f"Scan error: {e}")
            if verbose:
                print(f"   ⚠️ Scan error: {e}")
            
        return opportunities
    
    async def execute_trade(self, opportunity: Dict) -> Dict:
        """Execute a trade (paper or live)."""
        
        amount = min(self.current_balance, self.max_trade)
        
        if self.live_mode and self._live_executor:
            # LIVE EXECUTION
            buy_mint = opportunity.get("buy_mint")
            if not buy_mint:
                return {"success": False, "error": "No mint address"}
            
            result = await self._live_executor.execute_spatial_arb(
                buy_mint=buy_mint,
                sell_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
                amount_usd=amount
            )
            
            if result.get("success"):
                # Update balance (would need to re-check wallet)
                net_profit = amount * (opportunity["net_pct"] / 100)
                self.current_balance += net_profit
                self.total_profit += net_profit
                self.total_trades += 1
                
                trade = {
                    "timestamp": time.time(),
                    "mode": "LIVE",
                    "pair": opportunity["pair"],
                    "amount": amount,
                    "spread_pct": opportunity["spread_pct"],
                    "net_profit": net_profit,
                    "signature": result.get("signature"),
                    "balance_after": self.current_balance
                }
                self.trades.append(trade)
                
                return {"success": True, "trade": trade}
            else:
                return {"success": False, "error": result.get("error")}
        
        else:
            # PAPER EXECUTION
            gross_profit = amount * (opportunity["spread_pct"] / 100)
            fees = amount * 0.002
            net_profit = gross_profit - fees
            
            self.current_balance += net_profit
            self.total_profit += net_profit
            self.total_trades += 1
            
            trade = {
                "timestamp": time.time(),
                "mode": "PAPER",
                "pair": opportunity["pair"],
                "amount": amount,
                "spread_pct": opportunity["spread_pct"],
                "net_profit": net_profit,
                "signature": f"PAPER_{int(time.time())}",
                "balance_after": self.current_balance
            }
            self.trades.append(trade)
            
            return {"success": True, "trade": trade}
    
    async def run(self, duration_minutes: int = 10, scan_interval: int = 5):
        """Run the trader."""
        
        mode_str = "🔴 LIVE" if self.live_mode else "📄 PAPER"
        
        print("\n" + "="*70)
        print(f"   PHANTOM ARBITER - {mode_str} TRADER")
        print("="*70)
        print(f"   Starting Balance: ${self.starting_balance:.2f}")
        print(f"   Min Spread:       {self.min_spread}%")
        print(f"   Max Trade:        ${self.max_trade:.2f}")
        print(f"   Duration:         {duration_minutes} minutes")
        print("="*70)
        print("\n   Running... (Ctrl+C to stop)\n")
        
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60) if duration_minutes > 0 else float('inf')
        
        last_trade_time = {}  # Cooldown tracking
        cooldown = 5  # seconds
        
        try:
            while time.time() < end_time:
                now = datetime.now().strftime("%H:%M:%S")
                
                try:
                    opportunities = await self.scan_opportunities()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    opportunities = []
                
                if opportunities:
                    # Find best opportunity not on cooldown
                    for opp in sorted(opportunities, key=lambda x: x["spread_pct"], reverse=True):
                        pair = opp["pair"]
                        last_time = last_trade_time.get(pair, 0)
                        
                        if time.time() - last_time < cooldown:
                            continue
                        
                        # Execute
                        result = await self.execute_trade(opp)
                        
                        if result.get("success"):
                            trade = result["trade"]
                            last_trade_time[pair] = time.time()
                            
                            emoji = "💰" if trade["net_profit"] > 0 else "📉"
                            print(f"   [{now}] {emoji} {trade['mode']} #{self.total_trades}: {trade['pair']}")
                            print(f"            Spread: +{trade['spread_pct']:.2f}% → Net: ${trade['net_profit']:+.4f}")
                            print(f"            Balance: ${trade['balance_after']:.4f}")
                            print()
                            break
                        else:
                            # Print error
                            error = result.get("error", "Unknown error")
                            print(f"   [{now}] ❌ TRADE FAILED: {error}")
                            break
                else:
                    # Scan already printed all spreads, no action needed
                    pass
                
                await asyncio.sleep(scan_interval)
                
        except KeyboardInterrupt:
            pass
        
        # Final summary
        runtime = (time.time() - start_time) / 60
        roi = ((self.current_balance - self.starting_balance) / self.starting_balance) * 100
        
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
        
        # Save session
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        mode = "live" if self.live_mode else "paper"
        save_path = f"data/trading_sessions/{mode}_session_{timestamp}.json"
        
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, 'w') as f:
            json.dump({
                "mode": mode,
                "starting_balance": self.starting_balance,
                "ending_balance": self.current_balance,
                "total_profit": self.total_profit,
                "total_trades": self.total_trades,
                "roi_pct": roi,
                "runtime_minutes": runtime,
                "trades": self.trades
            }, f, indent=2)
        
        print(f"\n   Session saved: {save_path}")


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Phantom Arbiter Unified Trader")
    parser.add_argument("--live", action="store_true", help="Enable LIVE trading (REAL MONEY!)")
    parser.add_argument("--budget", type=float, default=50.0, help="Starting budget in USD")
    parser.add_argument("--duration", type=int, default=10, help="Duration in minutes")
    parser.add_argument("--interval", type=int, default=5, help="Scan interval in seconds")
    parser.add_argument("--min-spread", type=float, default=0.20, help="Minimum spread percent")
    parser.add_argument("--max-trade", type=float, default=10.0, help="Maximum trade size")
    
    args = parser.parse_args()
    
    if args.live:
        print("\n" + "⚠️ "*20)
        print("   WARNING: LIVE MODE ENABLED!")
        print("   This will execute REAL transactions with REAL money!")
        print("⚠️ "*20)
        confirm = input("\n   Type 'I UNDERSTAND' to proceed: ")
        if confirm.strip() != "I UNDERSTAND":
            print("   Cancelled.")
            exit(0)
    
    trader = UnifiedTrader(
        budget=args.budget,
        live_mode=args.live,
        min_spread=args.min_spread,
        max_trade=args.max_trade
    )
    
    asyncio.run(trader.run(
        duration_minutes=args.duration,
        scan_interval=args.interval
    ))
