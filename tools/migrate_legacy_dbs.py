import os
import sys
import sqlite3

# Add root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.data_storage.db_manager import db_manager
from config.settings import Settings


def migrate_legacy():
    # Helper to map symbol -> mint
    symbol_to_mint = {v: k for k, v in Settings.ASSETS.items()}

    # 1. Trading Journal (asset_snapshots)
    tj_path = os.path.join("data", "trading_journal.db")
    if os.path.exists(tj_path):
        print(f"📂 Scanning {tj_path}...")
        try:
            conn = sqlite3.connect(tj_path)
            # Try to infer schema: symbol, price, timestamp
            # inspect_legacy_db output showed columns: symbol (TEXT), price (REAL), timestamp (REAL) usually
            # We try blind select based on index
            try:
                cursor = conn.execute(
                    "SELECT symbol, price, timestamp FROM asset_snapshots"
                )
                count = 0
                for row in cursor:
                    sym, price, ts = row
                    mint = symbol_to_mint.get(sym, sym)
                    db_manager.insert_tick(mint, price, volume=0, liq=0, latency=0)
                    count += 1
                print(f"   ✅ Imported {count} snapshots from trading_journal")
            except Exception as e:
                print(f"   ⚠️ Could not read asset_snapshots: {e}")
            conn.close()
        except Exception as e:
            print(f"   ⚠️ DB Error: {e}")

    # 2. Phantom DB (market_snapshots)
    ph_path = os.path.join("data", "phantom.db")
    if os.path.exists(ph_path):
        print(f"📂 Scanning {ph_path}...")
        try:
            conn = sqlite3.connect(ph_path)
            try:
                cursor = conn.execute(
                    "SELECT symbol, price, timestamp FROM market_snapshots"
                )
                count = 0
                for row in cursor:
                    sym, price, ts = row
                    mint = symbol_to_mint.get(sym, sym)
                    db_manager.insert_tick(mint, price, volume=0, liq=0, latency=0)
                    count += 1
                print(f"   ✅ Imported {count} snapshots from phantom.db")
            except Exception as e:
                print(f"   ⚠️ Could not read market_snapshots: {e}")
            conn.close()
        except Exception as e:
            print(f"   ⚠️ DB Error: {e}")

    print("🚀 Legacy Migration Done")


if __name__ == "__main__":
    migrate_legacy()
