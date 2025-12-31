import sys
import os
import numpy as np

# Ensure src is in path
sys.path.append(os.getcwd())

from src.analysis.regime_detector import RegimeDetector


def generate_random_candles(n=100, trend_type="random"):
    """Generate dummy candles."""
    candles = []
    price = 100.0

    for i in range(n):
        if trend_type == "up":
            change = np.random.normal(0.5, 0.5)  # Drift up
        elif trend_type == "down":
            change = np.random.normal(-0.5, 0.5)  # Drift down
        else:
            change = np.random.normal(0, 2.0)  # High vol random

        price += change
        high = price + abs(np.random.normal(0, 1))
        low = price - abs(np.random.normal(0, 1))

        candles.append(
            {"open": price, "high": high, "low": low, "close": price, "volume": 1000}
        )

    return candles


def test_regime():
    print("🧪 Testing RegimeDetector...")

    # 1. Test Quiet/Ranging
    print("\n[Test 1] Generating Random Walk (Ranging)...")
    candles = generate_random_candles(100, "random")
    regime = RegimeDetector.detect(candles, "TEST")
    print(
        f"Result: Vol={regime.volatility}, Trend={regime.trend}, score={regime.quality_score}"
    )

    # 2. Test Trending Up
    print("\n[Test 2] Generating Uptrend...")
    candles = generate_random_candles(100, "up")
    regime = RegimeDetector.detect(candles, "TEST")
    print(
        f"Result: Vol={regime.volatility}, Trend={regime.trend}, score={regime.quality_score}"
    )

    # 3. Test Trending Down
    print("\n[Test 3] Generating Downtrend...")
    candles = generate_random_candles(100, "down")
    regime = RegimeDetector.detect(candles, "TEST")
    print(
        f"Result: Vol={regime.volatility}, Trend={regime.trend}, score={regime.quality_score}"
    )

    print("\n✅ Test Complete")


if __name__ == "__main__":
    test_regime()
