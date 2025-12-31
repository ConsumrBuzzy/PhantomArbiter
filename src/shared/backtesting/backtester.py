"""
V9.0 Backtester - "The Time Machine" (Unified Logic)
=====================================================
Replay historical price data using REAL simulation logic.
Uses CapitalManager (V40.0) for accurate Fees, Gas, and Slippage.

Usage:
    python backtester.py                    # All cached tokens
    python backtester.py --symbol JUP       # Single cached token
    python backtester.py --mint <ADDRESS>   # Fetch and test any token
"""

import json
import os
import argparse
import requests
import tempfile
from collections import deque
from dataclasses import dataclass
from typing import List

# V9.0: Import Real Logic Components
from src.shared.system.capital_manager import CapitalManager

# Path to price cache
CACHE_PATH = os.path.join(os.path.dirname(__file__), "../../data/price_cache.json")


class BacktestCapitalManager(CapitalManager):
    """
    Isolated CapitalManager for Backtesting.
    Overrides persistence to use a temporary file.
    """

    def __init__(self, initial_capital: float = 1000.0):
        # Create temp file for isolated state
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.temp_db.close()

        # Override class-level constant for this instance (trick)
        # We need to monkeypatch the instance's access to STATE_FILE
        self.STATE_FILE = self.temp_db.name

        # Reset Singleton for this thread/process context if needed,
        # but since we are inheriting, we just run __init__ logic.
        # CapitalManager is a Singleton, so we must be careful.
        # Ideally, we bypass the Singleton check for testing.
        self._initialized = False
        self.default_capital = initial_capital
        self.mode = "BACKTEST"
        self.state = {}

        # Initialize
        self._load_state()
        self._initialize_defaults_if_missing()
        self._initialized = True

    def cleanup(self):
        """Remove temp file."""
        if os.path.exists(self.STATE_FILE):
            try:
                os.remove(self.STATE_FILE)
            except:
                pass


@dataclass
class TradeResult:
    """Records a single trade outcome."""

    symbol: str
    entry_price: float
    exit_price: float
    entry_ts: float
    exit_ts: float
    pnl_usd: float
    pnl_pct: float
    fees_usd: float
    slippage_usd: float
    exit_reason: str


class Backtester:
    """
    V9.0: Strategy backtester using Real Market Logic.

    Simulates:
    - Mechanics: Gas, Slippage (Dynamic), Fees
    - Strategy: RSI < 30 & Price > SMA-50
    """

    # Strategy Parameters
    RSI_OVERSOLD = 30
    RSI_OVERBOUGHT = 70
    TAKE_PROFIT_PCT = 0.03  # +3%
    STOP_LOSS_PCT = -0.01  # -1%
    SMA_PERIOD = 50
    RSI_PERIOD = 14

    def __init__(self, force_entry: bool = False, capital: float = 1000.0):
        self.cm = BacktestCapitalManager(initial_capital=capital)
        self.engine_name = "BACKTESTER"
        self.trades: List[TradeResult] = []
        self.cache_data = self._load_cache()
        self.force_entry = force_entry
        self.capital = capital

        # Ensure engine exists in CM
        if self.engine_name not in self.cm.state["engines"]:
            self.cm._add_engine(self.engine_name)

        print(
            f"   🧪 Engine Initialized: ${self.cm.get_available_cash(self.engine_name):.2f}"
        )

    def __del__(self):
        if hasattr(self, "cm"):
            self.cm.cleanup()

    def _load_cache(self) -> dict:
        """Load price cache from disk."""
        if not os.path.exists(CACHE_PATH):
            print(f"❌ Cache not found: {CACHE_PATH}")
            return {}
        with open(CACHE_PATH, "r") as f:
            return json.load(f)

    def _calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """Calculate RSI (Wilder)."""
        if len(prices) < period + 1:
            return 50.0
        changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
        gains = [c if c > 0 else 0 for c in changes[:period]]
        losses = [-c if c < 0 else 0 for c in changes[:period]]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        for i in range(period, len(changes)):
            change = changes[i]
            gain = max(0, change)
            loss = max(0, -change)
            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period

        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 1)

    def _calculate_sma(self, prices: List[float], period: int = 50) -> float:
        if len(prices) < period:
            return 0.0
        return sum(prices[-period:]) / period

    def backtest_symbol(self, symbol: str, history: List[dict]) -> List[TradeResult]:
        if len(history) < self.SMA_PERIOD + 10:
            print(f"   ⚠️ {symbol}: Insufficient data ({len(history)} points)")
            return []

        trades = []
        prices = deque(maxlen=200)

        # Reset Engine for clean symbol test
        # (Optional: In reality, we might want portfolio test, but let's do per-symbol isolation)
        # For simplicity, we keep accumulating PnL in the engine to test survival.

        in_position = False
        entry_ts = 0.0

        # Metrics
        buy_signals = 0

        for point in history:
            price = point["price"]
            ts = point["ts"]
            prices.append(price)

            if len(prices) < self.SMA_PERIOD:
                continue

            price_list = list(prices)
            rsi = self._calculate_rsi(price_list, self.RSI_PERIOD)
            sma = self._calculate_sma(price_list, self.SMA_PERIOD)

            # Volatility Penalty (V9.0)
            # Calculate simple volatility (std dev proxy) of last 5 candles
            local_volatility = 0.0
            if len(prices) >= 5:
                recent = list(prices)[-5:]
                avg = sum(recent) / 5
                variance = sum((x - avg) ** 2 for x in recent) / 5
                local_volatility = (variance**0.5) / avg

            # Penalty Multiplier (If vol > 0.2%, assume 0.5% spread penalty)
            penalty_mult = 0.0
            is_volatile = False
            if local_volatility > 0.002:
                penalty_mult = 0.005  # 0.5% Penalty
                is_volatile = True

            if not in_position:
                # BUY CONDITION
                is_oversold = rsi < self.RSI_OVERSOLD
                is_uptrend = price > sma

                if is_oversold or self.force_entry:
                    if is_uptrend or self.force_entry:
                        # EXECUTE BUY VIA CM
                        # Size: $100 fixed or 10% of equity
                        cash = self.cm.get_available_cash(self.engine_name)
                        size = min(cash, 100.0)

                        if size < 10:
                            continue  # Broke

                        # Apply Volatility Penalty to Price (Worse Entry)
                        exec_price = price * (1 + penalty_mult)

                        success, msg = self.cm.execute_buy(
                            engine_name=self.engine_name,
                            symbol=symbol,
                            mint="UNKNOWN",
                            price=exec_price,
                            size_usd=size,
                            liquidity_usd=100000.0,  # Assumed liq
                            is_volatile=is_volatile,  # CM adds extra slippage
                        )

                        if success:
                            in_position = True
                            entry_ts = ts
                            buy_signals += 1
                        else:
                            print(f"   ⚠️ Buy rejected: {msg}")

            else:
                # SELL CONDITION
                # Check position using CM
                pos = self.cm.get_position(self.engine_name, symbol)
                if not pos:
                    in_position = False  # Should not happen unless liquidation
                    continue

                entry_price = pos["avg_price"]  # Inc. slippage
                pnl_pct = (price - entry_price) / entry_price

                exit_reason = None
                if pnl_pct >= self.TAKE_PROFIT_PCT:
                    exit_reason = "TAKE_PROFIT"
                elif pnl_pct <= self.STOP_LOSS_PCT:
                    exit_reason = "STOP_LOSS"
                elif rsi > self.RSI_OVERBOUGHT and pnl_pct > 0.005:
                    exit_reason = "FAST_SCALP"

                if exit_reason:
                    # EXECUTE SELL VIA CM
                    pre_sell_stats = self.cm.get_stats(self.engine_name).copy()

                    # Apply Volatility Penalty to Price (Worse Exit)
                    exec_price = price * (1 - penalty_mult)

                    success, msg, pnl = self.cm.execute_sell(
                        engine_name=self.engine_name,
                        symbol=symbol,
                        price=exec_price,
                        reason=exit_reason,
                        liquidity_usd=100000.0,
                        is_volatile=is_volatile,
                    )

                    if success:
                        # Capture accurate metrics from CM stats delta
                        post_stats = self.cm.get_stats(self.engine_name)
                        fees = post_stats["fees_paid_usd"] - pre_sell_stats.get(
                            "fees_paid_usd", 0
                        )
                        slip = post_stats["slippage_usd"] - pre_sell_stats.get(
                            "slippage_usd", 0
                        )

                        trade = TradeResult(
                            symbol=symbol,
                            entry_price=entry_price,
                            exit_price=price,  # Approx (doesn't account for exit slippage in this var, but PnL does)
                            entry_ts=entry_ts,
                            exit_ts=ts,
                            pnl_usd=pnl,
                            pnl_pct=pnl_pct,  # Gross PnL %, Net PnL is in USD
                            fees_usd=fees,
                            slippage_usd=slip,
                            exit_reason=exit_reason,
                        )
                        trades.append(trade)
                        in_position = False

        # Close open positions
        if in_position:
            self.cm.execute_sell(self.engine_name, symbol, prices[-1], "END_OF_DATA")

        print(f"   {symbol}: {len(history)} pts | {len(trades)} trades")
        return trades

    def fetch_and_backtest_mint(
        self, mint: str, symbol: str = "UNKNOWN"
    ) -> List[TradeResult]:
        """Fetch historical data from CoinGecko."""
        print(f"\n🔍 Fetching history for {mint[:8]}...")
        try:
            # V9.1: Use shared DataFetcher or requests
            url = f"https://api.coingecko.com/api/v3/coins/solana/contract/{mint}/market_chart"
            params = {"vs_currency": "usd", "days": "1"}
            resp = requests.get(url, params=params, timeout=15)

            if resp.status_code != 200:
                print(f"   ⚠️ CoinGecko error: {resp.status_code}")
                return []

            data = resp.json()
            prices = data.get("prices", [])
            if not prices:
                return []

            history = [{"price": p[1], "ts": p[0] / 1000} for p in prices]
            print(f"   ✅ Fetched {len(history)} price points")
            return self.backtest_symbol(symbol, history)

        except Exception as e:
            print(f"   ❌ Fetch failed: {e}")
            return []

    def run(self, symbol: str = None, mint: str = None):
        all_trades = []
        if mint:
            all_trades.extend(self.fetch_and_backtest_mint(mint))
        elif symbol:
            # Load from cache
            data = self.cache_data.get("prices", {}).get(symbol, {})
            if data and "history" in data:
                all_trades.extend(self.backtest_symbol(symbol, data["history"]))
            else:
                print(f"❌ No data for {symbol}")
        else:
            # Test all
            for sym, data in self.cache_data.get("prices", {}).items():
                if "history" in data:
                    all_trades.extend(self.backtest_symbol(sym, data["history"]))

        self.trades = all_trades
        self._print_results()

    def _print_results(self):
        print("\n" + "=" * 80)
        print("📊 V9.0 REAL-LOGIC SIMULATION RESULTS")
        print("=" * 80)

        if not self.trades:
            print("   No trades generated.")
            return

        print(
            f"{'Symbol':<10} | {'P/L $':>8} | {'Fees':>6} | {'Slip':>6} | {'Reason':<12}"
        )
        print("-" * 80)

        total_pnl = 0.0
        total_fees = 0.0
        total_slip = 0.0

        for t in self.trades:
            print(
                f"{t.symbol:<10} | {t.pnl_usd:>+8.2f} | {t.fees_usd:>6.2f} | {t.slippage_usd:>6.2f} | {t.exit_reason:<12}"
            )
            total_pnl += t.pnl_usd
            total_fees += t.fees_usd
            total_slip += t.slippage_usd

        print("-" * 80)
        print(f"TOTAL PnL:  ${total_pnl:.2f}")
        print(f"TOTAL FEES: ${total_fees:.2f}")
        print(f"TOTAL SLIP: ${total_slip:.2f}")
        print(f"NET RESULT: ${(total_pnl - total_fees):.2f}")
        print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="V9.0 Unified Backtester")
    parser.add_argument("--symbol", "-s", type=str, help="Specific symbol")
    parser.add_argument("--mint", "-m", type=str, help="Mint address")
    parser.add_argument("--force", "-f", action="store_true", help="Force entry")
    args = parser.parse_args()

    bt = Backtester(force_entry=args.force)
    bt.run(symbol=args.symbol, mint=args.mint)


if __name__ == "__main__":
    main()
