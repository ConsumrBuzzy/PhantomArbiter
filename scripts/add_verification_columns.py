import sqlite3
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "src", "data", "targets.db")

def migrate():
    print(f"🔧 Migrating Database at {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Add verified_account_count
    try:
        cursor.execute("ALTER TABLE leads ADD COLUMN verified_account_count INTEGER DEFAULT 0")
        print("   ➕ Added column: verified_account_count")
    except sqlite3.OperationalError:
        print("   verified_account_count already exists.")
        
    # Add verified_rent_value
    try:
        cursor.execute("ALTER TABLE leads ADD COLUMN verified_rent_value REAL DEFAULT 0.0")
        print("   ➕ Added column: verified_rent_value")
    except sqlite3.OperationalError:
        print("   verified_rent_value already exists.")
        
    conn.commit()
    conn.close()
    print("✅ Migration Complete.")

if __name__ == "__main__":
    migrate()
