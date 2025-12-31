"""
Verify Hydration Logic
======================
Tests the Nomad Persistence Bridge (Dehydration/Rehydration).
"""

import sys
import os
import json
import sqlite3

# Add src to path
sys.path.append(os.getcwd())

from src.shared.system.hydration_manager import HydrationManager
from src.shared.system.database.core import DatabaseCore


def test_full_cycle():
    print("💧 Testing Dehydration/Rehydration Cycle...")

    # Setup: Create a clean environment
    db_core = DatabaseCore()
    db_path = db_core.DB_PATH

    # Ensure DB directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # 1. Populate DB with Mock Data
    print("   1. Populating Mock DB...")
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS trades")
        cursor.execute("""
            CREATE TABLE trades (
                id TEXT PRIMARY KEY,
                input_mint TEXT,
                output_mint TEXT,
                profit_amount REAL
            )
        """)
        cursor.execute(
            "INSERT INTO trades VALUES (?, ?, ?, ?)", ("trade_1", "SOL", "USDC", 0.05)
        )
        cursor.execute(
            "INSERT INTO trades VALUES (?, ?, ?, ?)", ("trade_2", "USDC", "SOL", 0.02)
        )
        conn.commit()

    # 2. Dehydrate
    print("   2. Dehydrating...")
    hydration = HydrationManager()
    archive_path = hydration.dehydrate(context={"test": "true"})

    if not archive_path or not os.path.exists(archive_path):
        print("❌ Dehydration returned no file!")
        sys.exit(1)

    print(f"      Archived to: {archive_path}")

    # Verify Archive Content
    with open(archive_path, "r") as f:
        data = json.load(f)
        assert len(data["ledger"]) == 2
        assert data["ledger"][0]["id"] == "trade_1"
        print("      ✅ Archive Content Verified")

    # 3. Nuke DB
    print("   3. Nuking DB (Simulating new station)...")
    conn.close()  # Ensure closed
    if os.path.exists(db_path):
        os.remove(db_path)

    # 4. Rehydrate
    print("   4. Rehydrating...")
    # New DB instance will create file, but table needs to exist
    # HydrationManager rehydrate assumes schema exists usually,
    # but let's see if we need to recreate mock schema

    # In a real scenario, the app initializes the schema on startup.
    # Here we simulate that:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE trades (
                id TEXT PRIMARY KEY,
                input_mint TEXT,
                output_mint TEXT,
                profit_amount REAL
            )
        """)
        conn.commit()

    success = hydration.rehydrate(archive_path)
    if not success:
        print("❌ Rehydration failed!")
        sys.exit(1)

    # 5. Verify Restoration
    print("   5. Verifying Restoration...")
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades")
        rows = cursor.fetchall()
        assert len(rows) == 2, f"Expected 2 rows, got {len(rows)}"
        print(f"      Restored {len(rows)} rows.")

    # Cleanup
    if os.path.exists(archive_path):
        os.remove(archive_path)
    print("✅ Cycle Complete: Nomad Persistence Verified")


if __name__ == "__main__":
    try:
        test_full_cycle()
        print("\n🎉 Hydration Logic Verified")
    except Exception as e:
        print(f"\n❌ VERIFICATION FAILED: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
