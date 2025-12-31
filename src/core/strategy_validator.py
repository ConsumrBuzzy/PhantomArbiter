import collections
import pandas as pd
from src.core.shared_cache import SharedPriceCache
from src.core.data import DataFeed  # V9.0: Import DataFeed for on-demand fetching


class StrategyValidator:
    """
    V8.5 Gatekeeper: Validates buy signals by running a mini-backtest
    on recent data to ensure the strategy is performing well.
    """

    # Strategy Params (Must match Engine)
    RSI_PERIOD = 14
    SMA_PERIOD = 50
    RSI_OVERSOLD = 30
    RSI_OVERBOUGHT = 70
    TAKE_PROFIT_PCT = 0.03  # +3%
    STOP_LOSS_PCT = -0.01  # -1%

    def __init__(self):
        pass

    def validate_buy(
        self, symbol: str, mint: str = None, timeframe_hours: int = 24
    ) -> tuple:
        """
        Run a backtest on the last N hours of data.
        V9.0: Accepts 'mint' to fetch data on-demand if missing from cache (Time Machine).

        Args:
            symbol: Token symbol
            mint: Token mint address (Optional, required for new tokens)
            timeframe_hours: How far back to test

        Returns:
            (is_valid: bool, stats: dict)
        """
        # 1. Fetch History from Cache
        raw_prices = SharedPriceCache.get_price_history(symbol)

        # V9.0: If cache miss and mint provided, fetch on-demand
        if (not raw_prices or len(raw_prices) < self.SMA_PERIOD + 20) and mint:
            try:
                # Use DataFeed to fetch/backfill
                # We use is_critical=True to force CoinGecko retries if needed
                feed = DataFeed(mint=mint, symbol=symbol, is_critical=True)
                if feed.raw_prices:
                    raw_prices = list(feed.raw_prices)
            except Exception as e:
                print(f"   ⚠️ StrategyValidator Fetch Error: {e}")

        if not raw_prices or len(raw_prices) < self.SMA_PERIOD + 20:
            return False, {"reason": "Insufficient Data", "win_rate": 0}

        # 2. Simulate Strategy
        # We use the full history available in cache (usually > 24h if backfilled)

        trades = self._run_simulation(symbol, raw_prices)

        # 3. Analyze Results
        if not trades:
            # No trades in period -> Neutral.
            # If no signals generated, we can't say it's "bad", but it's untested.
            # However, if we are calling this, it means we HAVE a signal NOW.
            # So if history had 0 signals, maybe market condition changed?
            return True, {"reason": "No historical trades", "win_rate": 0, "count": 0}

        wins = sum(1 for t in trades if t["pnl"] > 0)
        total = len(trades)
        win_rate = (wins / total) * 100
        avg_pnl = sum(t["pnl"] for t in trades) / total

        stats = {
            "win_rate": win_rate,
            "count": total,
            "avg_pnl": avg_pnl * 100,  # %
            "reason": f"Win Rate: {win_rate:.1f}% ({wins}/{total})",
        }

        # GATEKEEPER RULE: Must have > 40% win rate (allowing for some noise)
        # 50% is strict, 40% allows for breakeven with 3:1 RR, but our RR is 3:1 (3% vs 1%).
        # Actually TP=3%, SL=1% -> 25% win rate is breakeven.
        # So > 40% is actually very safe.
        is_valid = win_rate >= 40.0

        return is_valid, stats

    def _calculate_rsi(self, prices: list, period: int = 14) -> float:
        if len(prices) < period:
            return 50.0

        # Simple/efficient calculation without pandas overhead for every tick?
        # Actually backtester used pandas rolling. Let's stick to simple logic if possible.
        # But for accuracy we should match backtester.
        s = pd.Series(prices)
        delta = s.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs)).iloc[-1]

    def _run_simulation(self, symbol: str, price_history: list) -> list:
        """Run the simulation loop."""
        trades = []
        prices = collections.deque(maxlen=200)

        in_position = False
        entry_price = 0.0

        # We need to process sequentiall
        # Optimization: Don't re-sim EVERYTHING from 0 if list is huge.
        # Just last 1000 points.
        history_subset = (
            price_history[-2000:] if len(price_history) > 2000 else price_history
        )

        for price in history_subset:
            prices.append(price)

            if len(prices) < self.SMA_PERIOD:
                continue

            # Calc Indicators
            curr_prices = list(prices)
            rsi = self._calculate_rsi(curr_prices, self.RSI_PERIOD)
            sma = sum(curr_prices[-self.SMA_PERIOD :]) / self.SMA_PERIOD

            if not in_position:
                # Buy Logic (Same as Engine)
                if rsi < self.RSI_OVERSOLD and price > sma:
                    in_position = True
                    entry_price = price
            else:
                # Exit Logic
                pnl = (price - entry_price) / entry_price

                if pnl >= self.TAKE_PROFIT_PCT or pnl <= self.STOP_LOSS_PCT:
                    trades.append({"pnl": pnl})
                    in_position = False
                elif rsi > self.RSI_OVERBOUGHT and pnl > 0.005:
                    trades.append({"pnl": pnl})
                    in_position = False

        return trades


if __name__ == "__main__":
    # Test Run
    v = StrategyValidator()
    print("Testing StrategyValidator on known assets...")
    assets = ["JUP", "POPCAT", "WIF"]

    for symbol in assets:
        valid, stats = v.validate_buy(symbol)
        status = "✅ PASS" if valid else "⛔ BLOCK"
        print(
            f"{status} {symbol}: Win Rate {stats['win_rate']:.1f}% ({stats['count']} trades) Avg PnL: {stats.get('avg_pnl', 0):.2f}%"
        )
