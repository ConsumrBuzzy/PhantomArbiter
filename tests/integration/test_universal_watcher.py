#!/usr/bin/env python3
"""
V48.0: Universal Watcher Test Script
Standalone test for fetch_market_data functionality.
ASCII-safe version for Windows console.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.prices.dexscreener import DexScreenerProvider

def main():
    print("=" * 60)
    print("[TEST] UNIVERSAL WATCHER - DexScreener Provider Test")
    print("=" * 60)
    
    provider = DexScreenerProvider()
    
    # Test tokens (known to have multiple DEX pairs)
    TEST_TOKENS = {
        "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
        "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
        "JUP": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    }
    
    print("\n[INFO] Testing Single Token Fetch (fetch_market_data):")
    print("-" * 60)
    
    for symbol, mint in TEST_TOKENS.items():
        print(f"\n[TOKEN] {symbol}:")
        market_data = provider.fetch_market_data(mint, symbol)
        
        if market_data:
            print(f"   [OK] Primary Market: {market_data.dex_id.upper()}")
            print(f"   [OK] Price: ${market_data.price_usd:.8f}")
            print(f"   [OK] Liquidity: ${market_data.liquidity_usd:,.0f}")
            print(f"   [OK] Volume 24h: ${market_data.volume_24h_usd:,.0f}")
            print(f"   [OK] Price Change (1h): {market_data.price_change_1h:+.2f}%")
            print(f"   [OK] Price Change (24h): {market_data.price_change_24h:+.2f}%")
            print(f"   [OK] Buys/Sells 24h: {market_data.txns_buys_24h}/{market_data.txns_sells_24h}")
            print(f"   [OK] Buy/Sell Ratio: {market_data.buy_sell_ratio:.2f}")
            print(f"   [OK] New Pool (<7d): {market_data.is_new_pool}")
            print(f"   [OK] FDV: ${market_data.fdv:,.0f}")
        else:
            print(f"   [FAIL] Failed to fetch market data")
    
    print("\n" + "=" * 60)
    print("[INFO] Testing Batch Fetch (fetch_market_data_batch):")
    print("-" * 60)
    
    mints = list(TEST_TOKENS.values())
    symbol_map = {v: k for k, v in TEST_TOKENS.items()}
    
    batch_results = provider.fetch_market_data_batch(mints, symbol_map)
    
    print(f"\n[OK] Fetched {len(batch_results)} / {len(mints)} tokens")
    
    for mint, data in batch_results.items():
        print(f"   - {data.symbol}: ${data.price_usd:.6f} via {data.dex_id.upper()} (Liq: ${data.liquidity_usd:,.0f})")
    
    print("\n" + "=" * 60)
    print("[SUCCESS] Universal Watcher Test Complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()
