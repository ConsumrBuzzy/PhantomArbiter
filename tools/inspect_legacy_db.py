
import sqlite3
import os

dbs = ["phantom.db", "trading_journal.db"]

for db_name in dbs:
    db_path = os.path.join("data", db_name)
    if not os.path.exists(db_path):
        continue
        
    print(f"\n--- {db_name} ---")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # List tables
    c.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [t[0] for t in c.fetchall()]
    
    for t in tables:
        if "snapshot" in t or "price" in t or "asset" in t:
            print(f"Table: {t}")
            c.execute(f"PRAGMA table_info({t})")
            cols = c.fetchall()
            for col in cols:
                print(f"  {col[1]} ({col[2]})")
            
            c.execute(f"SELECT * FROM {t} LIMIT 1")
            print(f"  Sample: {c.fetchone()}")
