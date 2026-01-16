
import sys
import os
import sqlite3

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.shared.system.persistence import get_db

def check_vaults():
    print("🔍 Checking Engine Vaults in DB...")
    db = get_db()
    conn = db._get_connection()
    
    # Check engine_vaults table
    try:
        rows = conn.execute("SELECT * FROM engine_vaults").fetchall()
        if not rows:
            print("❌ engine_vaults table is EMPTY!")
        else:
            print(f"✅ Found {len(rows)} entries in engine_vaults:")
            for row in rows:
                print(f"   - [{row['engine']}] {row['asset']}: {row['balance']}")
                
        # Check paper_wallet table (Global)
        rows_pw = conn.execute("SELECT * FROM paper_wallet").fetchall()
        if not rows_pw:
            print("\n❌ paper_wallet table is EMPTY (Global paper wallet empty)")
        else:
            print(f"\n✅ Found {len(rows_pw)} entries in paper_wallet:")
            for row in rows_pw:
                print(f"   - {row['asset']}: {row['balance']}")

    except Exception as e:
        print(f"❌ Error querying DB: {e}")

if __name__ == "__main__":
    check_vaults()
