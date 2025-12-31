import sys
import os
import requests

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from src.core.data import batch_fetch_jupiter_prices


def test_fallback():
    print("🧪 Testing Price Fallback System...")

    # 1. Test Batch Fetch
    # We will simulate a failure by temporarily monkey-patching requests.get
    # actually, easier to just rely on the fact that if we use a fake URL or force error it triggers fallback
    # But we want to confirm fallback works.

    # Let's test by using a known token (SOL)
    mints = ["So11111111111111111111111111111111111111112"]

    print("\n1️⃣  Testing Batch Fetch (Standard)...")
    prices = batch_fetch_jupiter_prices(mints)
    print(f"   Result: {prices}")

    if not prices:
        print("   ⚠️ Standard fetch failed (Network issue?)")
    else:
        print("   ✅ Standard fetch success")

    # 2. Test Fallback (by forcing Jupiter fail)
    print("\n2️⃣  Testing Fallback (Simulated Jupiter Failure)...")

    original_get = requests.get

    def mocked_get(url, *args, **kwargs):
        if "jup.ag" in url:
            raise Exception("Simulated Jupiter Failure")
        return original_get(url, *args, **kwargs)

    requests.get = mocked_get

    try:
        prices = batch_fetch_jupiter_prices(mints)
        print(f"   Fallback Result: {prices}")

        if prices and prices.get(mints[0], 0) > 0:
            print("   ✅ FALLBACK SUCCESS: Retrieved price via DexScreener!")
        else:
            print("   ❌ FALLBACK FAILED: No price retrieved")

    finally:
        requests.get = original_get

    print("\n✅ Test Complete")


if __name__ == "__main__":
    test_fallback()
