"""
V8.0 Backtester - "The Time Machine"
=====================================
Replay historical price data to prove strategy profitability.

Usage:
    python backtester.py                    # All cached tokens
    python backtester.py --symbol JUP       # Single cached token
    python backtester.py --mint <ADDRESS>   # Fetch and test any token
"""

import json
import os
import argparse
import requests
from collections import deque
from dataclasses import dataclass
from typing import List, Optional

# Path to price cache
CACHE_PATH = os.path.join(os.path.dirname(__file__), "data", "price_cache.json")


@dataclass
class TradeResult:
    """Records a single trade outcome."""
    symbol: str
    entry_price: float
    exit_price: float
    entry_ts: float
    exit_ts: float
    pnl_pct: float
    exit_reason: str


class Backtester:
    """
    V8.0: Strategy backtester using historical price data.
    
    Simulates the trading rules:
    - BUY: RSI < 30 AND price > SMA-50
    - SELL: Take Profit (+3%) OR Stop Loss (-1%) OR RSI > 70
    """
    
    # Strategy Parameters (match live engine)
    RSI_OVERSOLD = 30
    RSI_OVERBOUGHT = 70
    TAKE_PROFIT_PCT = 0.03  # +3%
    STOP_LOSS_PCT = -0.01   # -1%
    SMA_PERIOD = 50
    RSI_PERIOD = 14
    
    def __init__(self, force_entry: bool = False):
        self.trades: List[TradeResult] = []
        self.cache_data = self._load_cache()
        self.force_entry = force_entry
        if self.force_entry:
            print("⚠️ WARNING: Trend filter DISABLED (Force Entry Mode)")
    
    def _load_cache(self) -> dict:
        """Load price cache from disk."""
        if not os.path.exists(CACHE_PATH):
            print(f"❌ Cache not found: {CACHE_PATH}")
            return {}
        
        with open(CACHE_PATH, 'r') as f:
            return json.load(f)
    
    def _calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """
        Calculate RSI using Wilder smoothing (matches live engine).
        """
        if len(prices) < period + 1:
            return 50.0  # Neutral if insufficient data
        
        changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        
        # Initial averages
        gains = [c if c > 0 else 0 for c in changes[:period]]
        losses = [-c if c < 0 else 0 for c in changes[:period]]
        
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        # Wilder smoothing for remaining periods
        for i in range(period, len(changes)):
            change = changes[i]
            gain = change if change > 0 else 0
            loss = -change if change < 0 else 0
            
            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period
        
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(rsi, 1)
    
    def _calculate_sma(self, prices: List[float], period: int = 50) -> float:
        """Calculate Simple Moving Average."""
        if len(prices) < period:
            return 0.0
        return sum(prices[-period:]) / period
    
    def backtest_symbol(self, symbol: str, history: List[dict]) -> List[TradeResult]:
        """
        Run backtest simulation for a single symbol.
        
        Args:
            symbol: Token symbol
            history: List of {"price": float, "ts": float}
            
        Returns:
            List of trade results
        """
        if len(history) < self.SMA_PERIOD + 10:
            print(f"   ⚠️ {symbol}: Insufficient data ({len(history)} points)")
            return []
        
        trades = []
        prices = deque(maxlen=200)  # Rolling window
        
        # Simulation state
        in_position = False
        entry_price = 0.0
        entry_ts = 0.0
        
        # Diagnostics
        min_rsi = 100.0
        max_rsi = 0.0
        buy_signals = 0
        blocked_signals = 0
        
        for point in history:
            price = point["price"]
            ts = point["ts"]
            prices.append(price)
            
            if len(prices) < self.SMA_PERIOD:
                continue
            
            price_list = list(prices)
            rsi = self._calculate_rsi(price_list, self.RSI_PERIOD)
            sma = self._calculate_sma(price_list, self.SMA_PERIOD)
            
            # Track RSI range
            min_rsi = min(min_rsi, rsi)
            max_rsi = max(max_rsi, rsi)
            
            if not in_position:
                # BUY signal: RSI < 30 
                # Safety check: Price > SMA (uptrend) unless forced
                is_oversold = rsi < self.RSI_OVERSOLD
                is_uptrend = price > sma
                
                if is_oversold:
                    if is_uptrend or self.force_entry:
                        in_position = True
                        entry_price = price
                        entry_ts = ts
                        buy_signals += 1
                    else:
                        # Track blocked signals (downtrend)
                        blocked_signals += 1
            else:
                # Check exit conditions
                pnl_pct = (price - entry_price) / entry_price
                exit_reason = None
                
                if pnl_pct >= self.TAKE_PROFIT_PCT:
                    exit_reason = "TAKE_PROFIT"
                elif pnl_pct <= self.STOP_LOSS_PCT:
                    exit_reason = "STOP_LOSS"
                elif rsi > self.RSI_OVERBOUGHT and pnl_pct > 0.005:
                    exit_reason = "FAST_SCALP"
                
                if exit_reason:
                    trade = TradeResult(
                        symbol=symbol,
                        entry_price=entry_price,
                        exit_price=price,
                        entry_ts=entry_ts,
                        exit_ts=ts,
                        pnl_pct=pnl_pct,
                        exit_reason=exit_reason
                    )
                    trades.append(trade)
                    in_position = False
        
        # Close open position at end
        if in_position and len(prices) > 0:
            final_price = prices[-1]
            pnl_pct = (final_price - entry_price) / entry_price
            trade = TradeResult(
                symbol=symbol,
                entry_price=entry_price,
                exit_price=final_price,
                entry_ts=entry_ts,
                exit_ts=history[-1]["ts"],
                pnl_pct=pnl_pct,
                exit_reason="OPEN"
            )
            trades.append(trade)
        
        # Print diagnostic summary
        blocked_str = f" | {blocked_signals} blocked" if blocked_signals > 0 else ""
        print(f"   {symbol}: {len(history)} pts | RSI {min_rsi:.0f}-{max_rsi:.0f} | {len(trades)} trades{blocked_str}")
        
        return trades
    
    def fetch_and_backtest_mint(self, mint: str, symbol: str = "UNKNOWN") -> List[TradeResult]:
        """
        Fetch historical data from CoinGecko for any mint address.
        
        Uses contract endpoint to fetch data for tokens not in our config.
        """
        print(f"\n🔍 Fetching history for {mint[:8]}...")
        
        try:
            url = f"https://api.coingecko.com/api/v3/coins/solana/contract/{mint}/market_chart"
            params = {"vs_currency": "usd", "days": "1"}
            
            resp = requests.get(url, params=params, timeout=15)
            
            if resp.status_code == 429:
                print("   ⚠️ CoinGecko rate limited - try again later")
                return []
            
            if resp.status_code != 200:
                print(f"   ⚠️ CoinGecko error: {resp.status_code}")
                return []
            
            data = resp.json()
            prices = data.get("prices", [])
            
            if not prices:
                print("   ⚠️ No price data returned")
                return []
            
            # Convert to our format
            history = [{"price": p[1], "ts": p[0] / 1000} for p in prices]
            print(f"   ✅ Fetched {len(history)} price points")
            
            return self.backtest_symbol(symbol, history)
            
        except Exception as e:
            print(f"   ❌ Fetch failed: {e}")
            return []
    
    def run(self, symbol: str = None, mint: str = None):
        """
        Run the backtester.
        
        Args:
            symbol: Optional specific symbol from cache
            mint: Optional mint address to fetch and test
        """
        all_trades = []
        
        if mint:
            # Fetch and test external token
            trades = self.fetch_and_backtest_mint(mint)
            all_trades.extend(trades)
        elif symbol:
            # Test specific cached symbol
            prices_data = self.cache_data.get("prices", {}).get(symbol, {})
            history = prices_data.get("history", [])
            if history:
                trades = self.backtest_symbol(symbol, history)
                all_trades.extend(trades)
            else:
                print(f"❌ No data for {symbol}")
        else:
            # Test all cached symbols
            for sym, data in self.cache_data.get("prices", {}).items():
                history = data.get("history", [])
                if history:
                    trades = self.backtest_symbol(sym, history)
                    all_trades.extend(trades)
        
        self.trades = all_trades
        self._print_results()
    
    def _print_results(self):
        """Print backtest results in a formatted table."""
        print("\n" + "=" * 60)
        print("📊 V8.0 BACKTEST RESULTS")
        print("=" * 60)
        
        if not self.trades:
            print("   No trades generated.")
            return
        
        # Group by symbol
        by_symbol = {}
        for trade in self.trades:
            if trade.symbol not in by_symbol:
                by_symbol[trade.symbol] = []
            by_symbol[trade.symbol].append(trade)
        
        print(f"\n{'Symbol':<12} | {'Trades':>6} | {'Win%':>6} | {'Avg P/L':>8} | {'Best':>8} | {'Worst':>8}")
        print("-" * 60)
        
        total_trades = 0
        total_wins = 0
        total_pnl = 0.0
        
        for symbol, trades in sorted(by_symbol.items()):
            wins = sum(1 for t in trades if t.pnl_pct > 0)
            win_rate = (wins / len(trades) * 100) if trades else 0
            avg_pnl = sum(t.pnl_pct for t in trades) / len(trades) if trades else 0
            best = max(t.pnl_pct for t in trades) if trades else 0
            worst = min(t.pnl_pct for t in trades) if trades else 0
            
            print(f"{symbol:<12} | {len(trades):>6} | {win_rate:>5.1f}% | {avg_pnl*100:>+7.2f}% | {best*100:>+7.2f}% | {worst*100:>+7.2f}%")
            
            total_trades += len(trades)
            total_wins += wins
            total_pnl += sum(t.pnl_pct for t in trades)
        
        print("-" * 60)
        
        overall_win_rate = (total_wins / total_trades * 100) if total_trades else 0
        overall_avg_pnl = (total_pnl / total_trades * 100) if total_trades else 0
        
        print(f"{'TOTAL':<12} | {total_trades:>6} | {overall_win_rate:>5.1f}% | {overall_avg_pnl:>+7.2f}%")
        print("=" * 60)
        
        # Show trade breakdown
        print(f"\n📈 Exit Reasons:")
        reasons = {}
        for t in self.trades:
            reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
        for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"   {reason}: {count}")


def main():
    parser = argparse.ArgumentParser(description="V8.0 Backtester - Prove Strategy Profitability")
    parser.add_argument("--symbol", "-s", type=str, help="Specific symbol to test (from cache)")
    parser.add_argument("--mint", "-m", type=str, help="Mint address to fetch and test (any token)")
    parser.add_argument("--force", "-f", action="store_true", help="Force entry during downtrends (disable safety)")
    
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("🕰️  V8.0 BACKTESTER - The Time Machine")
    print("=" * 60)
    
    backtester = Backtester(force_entry=args.force)
    backtester.run(symbol=args.symbol, mint=args.mint)


if __name__ == "__main__":
    main()
