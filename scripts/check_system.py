import sys
import os
import sqlite3
import importlib
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())


def check_import(module_name):
    try:
        importlib.import_module(module_name)
        print(f"✅ Import: {module_name}")
        return True
    except Exception as e:
        print(f"❌ Import Failed: {module_name} - {e}")
        return False


def check_db(db_path):
    if not os.path.exists(db_path):
        print(f"⚠️ DB Missing: {db_path}")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        print(f"\n📂 Database: {os.path.basename(db_path)}")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()

        for table in tables:
            t_name = table[0]
            cursor.execute(f"SELECT COUNT(*) FROM {t_name}")
            count = cursor.fetchone()[0]
            print(f"   ├─ {t_name}: {count} records")

        conn.close()
    except Exception as e:
        print(f"❌ DB Error {db_path}: {e}")


def check_json(json_path):
    if not os.path.exists(json_path):
        print(f"⚠️ JSON Missing: {json_path}")
        return

    try:
        import json

        with open(json_path, "r") as f:
            data = json.load(f)

        print(f"\n📄 JSON: {os.path.basename(json_path)}")
        if isinstance(data, list):
            print(f"   └─ Items: {len(data)}")
        elif isinstance(data, dict):
            print(f"   └─ Keys: {len(data)}")
    except Exception as e:
        print(f"❌ JSON Error {json_path}: {e}")


print("=== PHANTOM SYSTEM CHECK ===\n")

# 1. Component Integrity
print("--- Components ---")
check_import("src.arbiter.arbiter")
check_import("src.arbiter.core.executor")
check_import("src.scraper.discovery.discovery_engine")
check_import("src.shared.system.db_manager")
check_import("src.shared.infrastructure.solana_wss")

# 2. Data Integrity
print("\n--- Data ---")
data_dir = Path("data")
check_db(data_dir / "trading_journal.db")
check_db(data_dir / "market_data.db")
check_json(data_dir / "smart_money_watchlist.json")
check_json(
    data_dir / "trading_sessions" / "latest_session.json"
)  # Just checking if dir exists really

print("\n=== CHECK COMPLETE ===")
