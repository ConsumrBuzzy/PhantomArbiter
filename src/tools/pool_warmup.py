"""
Pool Warmup CLI
================
Warms up pool routes for specific tokens using existing SmartRouter.

Usage:
    python -m src.tools.pool_warmup SYMBOL1 SYMBOL2 ...
    python -m src.tools.pool_warmup --all  # Warm all watchlist tokens
"""

import os
import sys
import json
import time
from typing import Dict, List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env'))

from src.shared.system.logging import Logger
from src.shared.system.db_manager import db_manager
from src.shared.system.smart_router import SmartRouter
from config.settings import Settings

USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def check_route(router: SmartRouter, token_mint: str, symbol: str) -> Dict[str, bool]:
    """Check if Jupiter has routes for a token using existing SmartRouter."""
    routes = {
        "jupiter": False,
        "raydium": False,
        "orca": False,
        "meteora": False
    }
    
    try:
        # Use existing SmartRouter to get quote
        quote = router.get_jupiter_quote(
            USDC_MINT,
            token_mint,
            1_000_000,  # 1 USDC
            slippage_bps=100
        )
        
        if quote:
            routes["jupiter"] = True
            
            # Check which DEXes are in the route
            route_plan = quote.get("routePlan", [])
            for step in route_plan:
                swap_info = step.get("swapInfo", {})
                label = swap_info.get("label", "").lower()
                
                if "raydium" in label:
                    routes["raydium"] = True
                elif "orca" in label or "whirlpool" in label:
                    routes["orca"] = True
                elif "meteora" in label:
                    routes["meteora"] = True
            
            print(f"  ✅ {symbol}: Jupiter route found - Raydium:{routes['raydium']} Orca:{routes['orca']} Meteora:{routes['meteora']}")
        else:
            print(f"  ❌ {symbol}: No Jupiter route found")
            
    except Exception as e:
        print(f"  ❌ {symbol}: Error checking route - {e}")
    
    return routes


def update_pool_registry(symbol: str, mint: str, routes: Dict[str, bool]):
    """Update pool_registry table with route info."""
    with db_manager.cursor(commit=True) as c:
        c.execute("""
            INSERT INTO pool_registry (mint, symbol, has_jupiter, has_raydium, has_orca, has_meteora, last_checked)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(mint) DO UPDATE SET
                symbol = excluded.symbol,
                has_jupiter = excluded.has_jupiter,
                has_raydium = excluded.has_raydium,
                has_orca = excluded.has_orca,
                has_meteora = excluded.has_meteora,
                last_checked = excluded.last_checked
        """, (mint, symbol, routes["jupiter"], routes["raydium"], routes["orca"], routes["meteora"], time.time()))


def warm_token(router: SmartRouter, symbol: str, mint: str) -> bool:
    """Warm a single token's pool routes."""
    routes = check_route(router, mint, symbol)
    
    # Fallback: If Jupiter fails, try DexScreener to verify token exists
    if not routes["jupiter"]:
        routes = check_dexscreener(mint, symbol)
    
    if routes["jupiter"] or routes.get("dexscreener"):
        update_pool_registry(symbol, mint, routes)
        return True
    return False


def check_dexscreener(token_mint: str, symbol: str) -> Dict[str, bool]:
    """Fallback: Check DexScreener for token info."""
    import requests
    
    routes = {
        "jupiter": False,
        "raydium": False,
        "orca": False,
        "meteora": False,
        "dexscreener": False
    }
    
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token_mint}"
        resp = requests.get(url, timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            pairs = data.get("pairs", [])
            
            if pairs:
                routes["dexscreener"] = True
                
                # Check which DEXes the token has pairs on
                for pair in pairs:
                    dex_id = pair.get("dexId", "").lower()
                    
                    if "raydium" in dex_id:
                        routes["raydium"] = True
                    elif "orca" in dex_id:
                        routes["orca"] = True
                    elif "meteora" in dex_id:
                        routes["meteora"] = True
                
                print(f"  🔄 {symbol}: DexScreener fallback - Raydium:{routes['raydium']} Orca:{routes['orca']} Meteora:{routes['meteora']}")
            else:
                print(f"  ❌ {symbol}: No pairs on DexScreener")
                
    except Exception as e:
        print(f"  ❌ {symbol}: DexScreener error - {e}")
    
    return routes


def warm_all_watchlist():
    """Warm pools for all tokens in watchlist.json."""
    watchlist_path = os.path.join(Settings.DATA_DIR, "watchlist.json")
    router = SmartRouter()
    
    with open(watchlist_path, 'r') as f:
        data = json.load(f)
    
    assets = data.get("assets", {})
    print(f"\n🔥 Warming pools for {len(assets)} tokens...\n")
    
    success = 0
    failed = 0
    
    for symbol, info in assets.items():
        mint = info.get("mint", "")
        if mint:
            if warm_token(router, symbol.upper(), mint):
                success += 1
            else:
                failed += 1
            time.sleep(0.3)  # Rate limit
    
    print(f"\n📊 Results: {success} routable, {failed} no routes")


def warm_specific_tokens(symbols: List[str]):
    """Warm pools for specific tokens by symbol."""
    watchlist_path = os.path.join(Settings.DATA_DIR, "watchlist.json")
    router = SmartRouter()
    
    with open(watchlist_path, 'r') as f:
        data = json.load(f)
    
    assets = data.get("assets", {})
    
    print(f"\n🔥 Warming pools for {len(symbols)} tokens...\n")
    
    for symbol in symbols:
        # Case-insensitive lookup
        found = None
        for name, info in assets.items():
            if name.upper() == symbol.upper():
                found = (name, info)
                break
        
        if found:
            name, info = found
            mint = info.get("mint", "")
            if mint:
                warm_token(router, symbol.upper(), mint)
            else:
                print(f"  ⚠️ {symbol}: No mint address")
        else:
            print(f"  ⚠️ {symbol}: Not found in watchlist")
        
        time.sleep(0.3)


def main():
    args = sys.argv[1:]
    
    if not args:
        print("""
Pool Warmup CLI
===============
Usage:
  pool_warmup.py --all              Warm all watchlist tokens
  pool_warmup.py SYMBOL1 SYMBOL2    Warm specific tokens

Examples:
  python -m src.tools.pool_warmup --all
  python -m src.tools.pool_warmup MOBILE ONDO IO GRASS
        """)
        return
    
    if args[0] == "--all":
        warm_all_watchlist()
    else:
        warm_specific_tokens(args)


if __name__ == "__main__":
    main()
