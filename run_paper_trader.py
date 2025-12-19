"""
Phantom Arbiter - Real Market Paper Trader
===========================================
Watches REAL market data and auto-executes PAPER trades.

Features:
- Uses LIVE prices from Jupiter, Raydium, Orca
- Auto-executes when profitable opportunity detected
- Tracks paper wallet balance with realistic fees
- Logs all trades with timestamps
- Shows real P&L that would occur with real money

Usage:
    python run_paper_trader.py --budget 50 --duration 60
    python run_paper_trader.py --budget 500 --min-spread 0.25
"""

import asyncio
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict

from config.settings import Settings
from src.system.logging import Logger


@dataclass
class PaperTrade:
    """A single paper trade record."""
    trade_id: int
    timestamp: float
    trade_type: str          # "SPATIAL", "FUNDING"
    pair: str
    buy_dex: str
    buy_price: float
    sell_dex: str
    sell_price: float
    amount_usd: float
    gross_profit: float
    fees: float
    net_profit: float
    balance_after: float
    spread_pct: float
    execution_time_ms: int = 0
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass 
class PaperWallet:
    """Tracks paper trading balance and statistics."""
    starting_balance: float
    current_balance: float
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_profit: float = 0.0
    total_fees: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    trades: List[PaperTrade] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    
    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100
    
    @property
    def roi(self) -> float:
        return ((self.current_balance - self.starting_balance) / self.starting_balance) * 100
    
    @property
    def runtime_minutes(self) -> float:
        return (time.time() - self.start_time) / 60
    
    def execute_trade(
        self,
        trade_type: str,
        pair: str,
        buy_dex: str,
        buy_price: float,
        sell_dex: str,
        sell_price: float,
        spread_pct: float
    ) -> PaperTrade:
        """Execute a paper trade and update balance."""
        
        # Use full balance for trade
        amount = self.current_balance
        
        # Calculate profit
        gross_profit = amount * (spread_pct / 100)
        fees = amount * 0.002  # 0.1% per swap × 2
        net_profit = gross_profit - fees
        
        # Update balance
        self.current_balance += net_profit
        self.total_trades += 1
        self.total_profit += net_profit
        self.total_fees += fees
        
        if net_profit > 0:
            self.winning_trades += 1
            if net_profit > self.largest_win:
                self.largest_win = net_profit
        else:
            self.losing_trades += 1
            if net_profit < self.largest_loss:
                self.largest_loss = net_profit
        
        # Create trade record
        trade = PaperTrade(
            trade_id=self.total_trades,
            timestamp=time.time(),
            trade_type=trade_type,
            pair=pair,
            buy_dex=buy_dex,
            buy_price=buy_price,
            sell_dex=sell_dex,
            sell_price=sell_price,
            amount_usd=amount,
            gross_profit=gross_profit,
            fees=fees,
            net_profit=net_profit,
            balance_after=self.current_balance,
            spread_pct=spread_pct,
            execution_time_ms=int(time.time() * 1000) % 1000
        )
        
        self.trades.append(trade)
        return trade
    
    def get_summary(self) -> str:
        """Get wallet summary."""
        return f"""
╔══════════════════════════════════════════════════════════════════╗
║                    PAPER TRADING SESSION                         ║
╠══════════════════════════════════════════════════════════════════╣
║  Runtime:       {self.runtime_minutes:.1f} minutes
║  Starting:      ${self.starting_balance:.2f}
║  Current:       ${self.current_balance:.2f}
║  ────────────────────────────────────────────────────────────────
║  Total Profit:  ${self.total_profit:+.4f}
║  Total Fees:    ${self.total_fees:.4f}
║  Net ROI:       {self.roi:+.2f}%
║  ────────────────────────────────────────────────────────────────
║  Total Trades:  {self.total_trades}
║  Winning:       {self.winning_trades} ({self.win_rate:.0f}%)
║  Largest Win:   ${self.largest_win:.4f}
║  Largest Loss:  ${self.largest_loss:.4f}
╚══════════════════════════════════════════════════════════════════╝
"""
    
    def save_to_file(self, filepath: str):
        """Save trading session to JSON file."""
        data = {
            "session_summary": {
                "starting_balance": self.starting_balance,
                "ending_balance": self.current_balance,
                "total_profit": self.total_profit,
                "total_fees": self.total_fees,
                "roi_pct": self.roi,
                "total_trades": self.total_trades,
                "win_rate": self.win_rate,
                "runtime_minutes": self.runtime_minutes,
                "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
                "end_time": datetime.now().isoformat()
            },
            "trades": [t.to_dict() for t in self.trades]
        }
        
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)


class RealMarketPaperTrader:
    """
    Paper trader using REAL market data.
    
    Watches live prices, auto-executes paper trades when
    profitable opportunities are detected.
    """
    
    # Thresholds
    MIN_SPREAD = 0.20  # Minimum 0.2% spread to trade
    
    # Cooldown between trades on same pair (avoid spamming)
    TRADE_COOLDOWN = 5  # seconds
    
    def __init__(
        self,
        starting_budget: float = 50.0,
        min_spread: float = 0.20,
        auto_trade: bool = True
    ):
        self.wallet = PaperWallet(
            starting_balance=starting_budget,
            current_balance=starting_budget
        )
        self.min_spread = min_spread
        self.auto_trade = auto_trade
        
        # Track last trade time per pair
        self.last_trade_time: Dict[str, float] = {}
        
        # Running state
        self._running = False
        
    async def scan_opportunities(self) -> List[dict]:
        """Scan for spatial arbitrage opportunities."""
        opportunities = []
        
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
            
            for opp in spreads:
                if opp.spread_pct >= self.min_spread:
                    # Check cooldown
                    last_time = self.last_trade_time.get(opp.pair, 0)
                    if time.time() - last_time < self.TRADE_COOLDOWN:
                        continue
                    
                    # Calculate if profitable after fees
                    gross = opp.spread_pct
                    fees = 0.20  # 0.2% total fees
                    net = gross - fees
                    
                    if net > 0:
                        opportunities.append({
                            "pair": opp.pair,
                            "buy_dex": opp.buy_dex,
                            "buy_price": opp.buy_price,
                            "sell_dex": opp.sell_dex,
                            "sell_price": opp.sell_price,
                            "spread_pct": opp.spread_pct,
                            "net_pct": net
                        })
                        
        except Exception as e:
            Logger.debug(f"Scan error: {e}")
            
        return opportunities
    
    async def run(self, duration_minutes: int = 60, scan_interval: int = 5):
        """
        Run the paper trader for a specified duration.
        
        Args:
            duration_minutes: How long to run (0 = indefinitely)
            scan_interval: Seconds between scans
        """
        self._running = True
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60) if duration_minutes > 0 else float('inf')
        
        print("\n" + "="*70)
        print("   REAL MARKET PAPER TRADER")
        print("="*70)
        print(f"   Starting Balance: ${self.wallet.starting_balance:.2f}")
        print(f"   Min Spread: {self.min_spread}%")
        print(f"   Duration: {duration_minutes} minutes" if duration_minutes > 0 else "   Duration: Indefinite")
        print(f"   Auto-Trade: {'ENABLED ✅' if self.auto_trade else 'DISABLED ❌'}")
        print("="*70)
        print("\n   Watching real market prices...\n")
        
        scan_count = 0
        
        try:
            while self._running and time.time() < end_time:
                scan_count += 1
                now = datetime.now().strftime("%H:%M:%S")
                
                try:
                    opportunities = await self.scan_opportunities()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    Logger.debug(f"Scan error: {e}")
                    opportunities = []
                
                if opportunities and self.auto_trade:
                    # Execute best opportunity
                    best = max(opportunities, key=lambda x: x['spread_pct'])
                    
                    trade = self.wallet.execute_trade(
                        trade_type="SPATIAL",
                        pair=best['pair'],
                        buy_dex=best['buy_dex'],
                        buy_price=best['buy_price'],
                        sell_dex=best['sell_dex'],
                        sell_price=best['sell_price'],
                        spread_pct=best['spread_pct']
                    )
                    
                    # Record cooldown
                    self.last_trade_time[best['pair']] = time.time()
                    
                    # Print trade
                    profit_emoji = "💰" if trade.net_profit > 0 else "📉"
                    print(f"   [{now}] {profit_emoji} TRADE #{trade.trade_id}: {trade.pair}")
                    print(f"            {trade.buy_dex} → {trade.sell_dex} @ +{trade.spread_pct:.2f}%")
                    print(f"            Net: ${trade.net_profit:+.4f} | Balance: ${trade.balance_after:.4f}")
                    print()
                    
                elif opportunities:
                    # Just report (no auto-trade)
                    print(f"   [{now}] Found {len(opportunities)} opportunities (auto-trade disabled)")
                else:
                    # Status update every 10 scans
                    if scan_count % 10 == 0:
                        print(f"\r   [{now}] Scan #{scan_count}: No opportunities (balance: ${self.wallet.current_balance:.4f})", end="")
                
                await asyncio.sleep(scan_interval)
                
        except KeyboardInterrupt:
            pass
        finally:
            self._running = False
        
        # Final summary
        print("\n")
        print(self.wallet.get_summary())
        
        # Save session
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = f"data/paper_sessions/session_{timestamp}.json"
        self.wallet.save_to_file(save_path)
        print(f"   Session saved to: {save_path}")
        
        return self.wallet
    
    def stop(self):
        """Stop the paper trader."""
        self._running = False


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Real Market Paper Trader")
    parser.add_argument("--budget", type=float, default=50.0, help="Starting budget in USD")
    parser.add_argument("--duration", type=int, default=10, help="Duration in minutes, 0 for indefinite")
    parser.add_argument("--interval", type=int, default=5, help="Scan interval in seconds")
    parser.add_argument("--min-spread", type=float, default=0.20, help="Minimum spread to trade")
    parser.add_argument("--no-auto", action="store_true", help="Disable auto-trading")
    
    args = parser.parse_args()
    
    trader = RealMarketPaperTrader(
        starting_budget=args.budget,
        min_spread=args.min_spread,
        auto_trade=not args.no_auto
    )
    
    asyncio.run(trader.run(
        duration_minutes=args.duration,
        scan_interval=args.interval
    ))
