import sqlite3
import os

DB_PATH = "src/data/targets.db"

def reinit_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH) # Brute force reset
        print(f"Removed {DB_PATH}")
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE leads (
            pubkey TEXT PRIMARY KEY,
            source TEXT,
            status TEXT DEFAULT 'NEW',
            found_at DATETIME,
            verified_at DATETIME,
            verified_account_count INTEGER,
            verified_rent_value REAL
        )
    """)
    conn.commit()
    conn.close()
    print("Database re-initialized with correct schema.")

if __name__ == "__main__":
    reinit_db()
