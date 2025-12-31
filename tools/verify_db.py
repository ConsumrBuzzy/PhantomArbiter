import sqlite3
import os

db_path = os.path.join("data", "market_data.db")
if not os.path.exists(db_path):
    print("No DB")
    exit()

conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT COUNT(*) FROM market_data")
print(f"Total Rows: {c.fetchone()[0]}")
c.execute("SELECT token_mint, COUNT(*) FROM market_data GROUP BY token_mint")
print(c.fetchall())
