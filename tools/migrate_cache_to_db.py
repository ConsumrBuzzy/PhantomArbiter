
import os
import sys
import json
import time

# Add root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.data_storage.db_manager import db_manager
from config.settings import Settings

def migrate():
    """Migrate data from price_cache.json to market_data.db"""
    cache_file = os.path.join(os.path.dirname(__file__), "..", "data", "price_cache.json")
    
    if not os.path.exists(cache_file):
        print(f"❌ Cache file not found: {cache_file}")
        return

    print(f"📂 Loading Cache: {cache_file}")
    with open(cache_file, 'r') as f:
        data = json.load(f)
        
    prices = data.get("prices", {})
    total_ticks = 0
    
    # Pre-map symbols to mints (DB uses Mints)
    # We do a reverse lookup from Settings
    symbol_to_mint = {v: k for k, v in Settings.ASSETS.items()}
    # Also include others? 
    # Settings.ASSETS has all mapping.
    
    print(f"🔍 Found {len(prices)} symbols in cache.")
    
    for symbol, record in prices.items():
        history = record.get("history", [])
        if not history: continue
        
        mint = symbol_to_mint.get(symbol)
        if not mint:
            # Try to infer or skip?
            # Ideally distinct symbols imply a mint.
            # If mapped, good. If not, we might use symbol as mint placeholder (not ideal but safe).
            mint = symbol 
            # print(f"⚠️ Warning: No mint found for {symbol}, using symbol as ID.")
        
        count = 0
        for point in history:
            # Point has {price, ts}
            # We assume Vol/Liq = 0 for historical cache
            try:
                p = float(point.get("price", 0))
                ts = float(point.get("ts", 0))
                if p > 0 and ts > 0:
                    db_manager.insert_tick(mint, p, volume=0.0, liq=0.0, latency=0)
                    count += 1
            except: pass
            
        print(f"   ✅ Processed {symbol}: {count} ticks")
        total_ticks += count
        
    print("="*40)
    print(f"🚀 Migration Complete. Imported {total_ticks} ticks into market_data.db")

if __name__ == "__main__":
    migrate()
