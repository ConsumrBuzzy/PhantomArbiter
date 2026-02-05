import sqlite3
import os

DB_PATH = os.path.join("src", "data", "targets.db")
conn = sqlite3.connect(DB_PATH)
conn.execute("UPDATE leads SET status='NEW'")
conn.commit()
print("Reset leads to NEW.")
