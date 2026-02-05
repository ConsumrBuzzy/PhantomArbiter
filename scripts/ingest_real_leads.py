import os
import re
import glob
import sqlite3
import argparse
from datetime import datetime
import secrets
import base58

# Build path to logs relative to this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
DB_PATH = os.path.join(PROJECT_ROOT, "src", "data", "targets.db")

# Solana Pubkey Regex (Base58, 32-44 chars)
PUBKEY_PATTERN = re.compile(r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b')

# Known System Programs to Ignore
IGNORE_LIST = {
    "11111111111111111111111111111111", # System Program
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", # Token Program
    "So11111111111111111111111111111111111111112", # Wrapped SOL
    "Vote111111111111111111111111111111111111111", # Vote
    "SysvarRent111111111111111111111111111111111", 
}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leads (
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
    return conn

def ingest_from_logs(limit_files=5, mock=False):
    print(f"Scanning logs in {LOG_DIR}...")
    log_files = glob.glob(os.path.join(LOG_DIR, "phantom_*.log"))
    
    # Sort files by modification time (newest first)
    log_files.sort(key=os.path.getmtime, reverse=True)
    
    conn = init_db()
    cursor = conn.cursor()
    
    total_found = 0
    new_inserts = 0
    files_processed = 0

    if not log_files and not mock:
        print("No log files found.")
        return

    if mock:
        print("Running in MOCK mode: Generating synthetic leads...")
        for _ in range(5):
            # Generate random pubkey
            random_key = base58.b58encode(secrets.token_bytes(32)).decode()
            try:
                cursor.execute("""
                    INSERT INTO leads (pubkey, source, found_at)
                    VALUES (?, ?, ?)
                """, (random_key, "MOCK_INJECTION", datetime.now()))
                new_inserts += 1
                total_found += 1
            except sqlite3.IntegrityError:
                pass
    else:
        for log_file in log_files:
            if files_processed >= limit_files:
                break
                
            print(f"Reading {os.path.basename(log_file)} (Size: {os.path.getsize(log_file)} bytes)...")
            try:
                with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    matches = PUBKEY_PATTERN.findall(content)
                    
                    print(f"  > Found {len(matches)} pattern matches.")
                    
                    unique_matches = set(matches) - IGNORE_LIST
                    print(f"  > {len(unique_matches)} unique potential pubkeys.")
                    
                    for pubkey in unique_matches:
                        total_found += 1
                        try:
                            cursor.execute("""
                                INSERT INTO leads (pubkey, source, found_at)
                                VALUES (?, ?, ?)
                            """, (pubkey, f"LOG:{os.path.basename(log_file)}", datetime.now()))
                            new_inserts += 1
                        except sqlite3.IntegrityError:
                            pass # Already exists
                            
            except Exception as e:
                print(f"Error reading {log_file}: {e}")
                
            files_processed += 1

    conn.commit()
    conn.close()
    
    print(f"\n--- Ingestion Report ---")
    print(f"Files Scanned: {files_processed}")
    print(f"Total Pubkeys Found: {total_found}")
    print(f"New Leads Inserted: {new_inserts}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Pubkeys from PhantomArbiter Logs")
    parser.add_argument("--limit", type=int, default=10, help="Number of recent log files to scan")
    parser.add_argument("--mock", action="store_true", help="Generate mock leads if logs are empty")
    args = parser.parse_args()
    
    ingest_from_logs(args.limit, args.mock)
