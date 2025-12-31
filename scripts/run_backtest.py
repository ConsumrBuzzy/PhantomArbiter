"""
V29.0 Backtest Runner
Executes Scalper and Longtail strategies on OOS data.
"""

import sys
import os
import pandas as pd
from backtesting import Backtest
from src.backtesting.adapters import (
    PhantomScalper,
    PhantomLongtail,
    PhantomKeltner,
    PhantomVWAP,
)

from src.backtesting.data_fetcher import DexDataFetcher
import argparse

# Known Mints (for testing)
# SOL: So11111111111111111111111111111111111111112
# JUP: JUPyiwrYJFskUPiHa7hkeR8VUtkPHCLkh5FZnPfpdFq
SOL_MINT = "So11111111111111111111111111111111111111112"


def get_data(mint=SOL_MINT, split_date=None):
    """
    Fetch DEX Data and partition.
    """
    print(f"📥 Fetching DEX data for Mint: {mint}...")

    # Try 'hour' - minute might be failing or empty
    df = DexDataFetcher.fetch_ohlcv(mint, timeframe="hour", limit=1000)
    print(f"DEBUG: Fetch result: Empty? {df.empty} | Len: {len(df)}")

    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    print(f"📊 Loaded {len(df)} candles from GeckoTerminal.")

    if split_date:
        # Split logic
        try:
            # Use UTC for split
            split = pd.Timestamp(split_date).tz_localize("UTC")

            # Ensure df index is tz-aware (Gecko returns naive UTC usually)
            # Fetcher code: df.set_index('Time')...
            # Let's force df index to UTC if naive
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")

            in_sample = df[df.index < split]
            out_sample = df[df.index >= split]

            if out_sample.empty:
                print("⚠️  Warning: OOS set empty by date. Falling back to 70/30 split.")
                raise ValueError("Empty OOS")

            return in_sample, out_sample
        except Exception as e:
            print(f"⚠️ Split failed: {e}. Using partitioning by percentage default.")

    # Default 70/30
    cutoff = int(len(df) * 0.7)
    return df.iloc[:cutoff], df.iloc[cutoff:]


def run_scalper(data):
    print("\n🚀 RUNNING BACKTEST: SCALPER (RSI) 🚀")
    bt = Backtest(
        data,
        PhantomScalper,
        cash=1000,
        commission=0.001,  # 0.1% fee (approx Solana swap)
        exclusive_orders=True,
    )

    # Run
    stats = bt.run()
    print(stats)
    print("✅ Scalper test complete.")


def run_longtail(data):
    print("\n🔭 RUNNING BACKTEST: LONGTAIL (MACD) 🔭")
    bt = Backtest(
        data, PhantomLongtail, cash=1000, commission=0.001, exclusive_orders=True
    )

    # Run Initial
    stats = bt.run()
    print("Initial Stats:")
    print(stats)

    # Optimize
    print("\n🔧 OPTIMIZING LONGTAIL...")
    try:
        opt_stats = bt.optimize(
            fast=range(5, 20, 5),
            slow=range(10, 40, 5),
            signal=range(5, 15, 2),
            constraint=lambda p: p.fast < p.slow,
            maximize="Sharpe Ratio",
        )
        print("Optimized Stats:")
        print(opt_stats)
        print("Best Params:", opt_stats._strategy)
    except Exception as e:
        print(f"⚠️ Optimization failed (need more data?): {e}")

    # bt.plot(filename='backtest_longtail.html', open_browser=False)
    print("✅ Longtail test complete.")


def run_strategy(name, strategy_cls, data, optimize=False):
    """Generic runner for a strategy."""
    print(f"\n🧪 TESTING: {name}")
    bt = Backtest(
        data, strategy_cls, cash=1000, commission=0.001, exclusive_orders=True
    )

    stats = bt.run()
    sharpe = stats["Sharpe Ratio"]
    ret = stats["Return [%]"]
    print(
        f"   📊 Res: Sharpe={sharpe:.2f} | Ret={ret:.2f}% | DD={stats['Max. Drawdown [%]']:.2f}%"
    )

    return {"name": name, "sharpe": sharpe, "stats": stats, "strategy": strategy_cls}


if __name__ == "__main__":
    import datetime

    # Arg Parser
    parser = argparse.ArgumentParser(description="V31.0 Strategy Researcher")
    parser.add_argument(
        "--mint", type=str, required=True, help="Token Mint Address (Required)"
    )
    parser.add_argument("--days", type=int, default=14, help="Days for OOS split")
    args = parser.parse_args()

    SPLIT_DATE = (
        datetime.datetime.now() - datetime.timedelta(days=args.days)
    ).strftime("%Y-%m-%d")

    try:
        print(f"✂️  OOS Split Date: {SPLIT_DATE}")

        train_data, test_data = get_data(mint=args.mint, split_date=SPLIT_DATE)

        if train_data.empty:
            print("❌ No data found.")
            sys.exit(1)

        print(f"🔹 In-Sample (Selection): {len(train_data)} candles")
        print(f"🔸 Out-of-Sample (Validation): {len(test_data)} candles")

        # V31.2: Strategy Selection (Competition on In-Sample)
        print("\n🏆 STRATEGY SELECTION (In-Sample Competition)")
        strategies = [
            ("Scalper", PhantomScalper),
            ("Longtail", PhantomLongtail),
            ("Keltner", PhantomKeltner),
            ("VWAP", PhantomVWAP),
        ]

        results = []
        for name, cls in strategies:
            res = run_strategy(name, cls, train_data)
            results.append(res)

        # Pick Winner
        winner = max(results, key=lambda x: x["sharpe"])
        print(f"\n🏅 WINNER: {winner['name']} (Sharpe: {winner['sharpe']:.2f})")

        # Validation
        print(f"\n🚀 FINAL VALIDATION (Out-of-Sample) for {winner['name']}...")
        final_stats = Backtest(
            test_data,
            winner["strategy"],
            cash=1000,
            commission=0.001,
            exclusive_orders=True,
        ).run()
        print(final_stats)

        # V32.0: Save Result to Strategy Map
        # Only save if Sharpe > 0 (Positive Edge)
        final_sharpe = final_stats["Sharpe Ratio"]
        if final_sharpe > 0:
            import json

            map_file = os.path.join(
                os.path.dirname(__file__), "config", "strategy_map.json"
            )

            # Load existing
            try:
                with open(map_file, "r") as f:
                    strategy_map = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                strategy_map = {}

            # Update
            strategy_map[args.mint] = winner[
                "name"
            ].upper()  # SCALPER, KELTNER, LONGTAIL

            # Write
            with open(map_file, "w") as f:
                json.dump(strategy_map, f, indent=4)

            print(f"\n✅ Strategy Map Updated: {args.mint} -> {winner['name'].upper()}")
        else:
            print("\n⚠️ Result not profitable (Sharpe <= 0). Strategy Map NOT updated.")

    except ImportError:
        print("❌ Dependencies missing.")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
