import sqlite3
import json
import os
import sys

# Define pathes
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "src", "data")
JSON_PATH = os.path.join(DATA_DIR, "targets.json")
DB_PATH = os.path.join(DATA_DIR, "targets.db")

def init_db():
    print(f"🔧 Initializing Database at {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create leads table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS leads (
        address TEXT PRIMARY KEY,
        category TEXT,
        notes TEXT,
        last_active TEXT,
        status TEXT DEFAULT 'NEW',
        potential_sol REAL DEFAULT 0.0,
        zombie_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    conn.commit()
    return conn

def populate_from_json(conn):
    if not os.path.exists(JSON_PATH):
        print(f"❌ targets.json not found at {JSON_PATH}")
        return

    print(f"📂 Reading targets from {JSON_PATH}...")
    with open(JSON_PATH, "r") as f:
        targets = json.load(f)
        
    cursor = conn.cursor()
    count = 0
    for target in targets:
        # Upsert logic (INSERT OR REPLACE would overwrite status, so we use INSERT OR IGNORE or UPDATE)
        # We want to preserve 'status' if it exists.
        # Let's use INSERT OR IGNORE for the base record, or check existence.
        # Simple approach: INSERT OR IGNORE
        
        try:
            cursor.execute("""
            INSERT OR IGNORE INTO leads (address, category, notes, last_active)
            VALUES (?, ?, ?, ?)
            """, (target["address"], target["category"], target["notes"], target["last_active"]))
            
            if cursor.rowcount > 0:
                count += 1
                print(f"   ➕ Added: {target['address']} ({target['category']})")
            else:
                print(f"   Skipped (Exists): {target['address']}")
                
        except sqlite3.Error as e:
            print(f"Error inserting {target['address']}: {e}")

    conn.commit()
    print(f"✅ Import Complete. Added {count} new leads.")

def verify_db(conn):
    print("\n🔍 Verifying Database Content:")
    cursor = conn.cursor()
    cursor.execute("SELECT address, category, status FROM leads")
    rows = cursor.fetchall()
    print(f"Total Records: {len(rows)}")
    for row in rows:
        print(f" - {row[0]}: {row[1]} [{row[2]}]")

if __name__ == "__main__":
    # Ensure data dir exists
    os.makedirs(DATA_DIR, exist_ok=True)
    
    connection = init_db()
    populate_from_json(connection)
    verify_db(connection)
    connection.close()
