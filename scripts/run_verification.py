import sqlite3
import argparse
import time
import sys
import os

# Add project root to sys.path to ensure imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.verifier import verify_target_viability

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "data", "targets.db")

def run_verification_batch(limit=10, dry_run=False):
    print(f"--- Starting Verification Batch (Limit: {limit}) ---")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Select NEW targets
    cursor.execute("SELECT pubkey FROM leads WHERE status='NEW' LIMIT ?", (limit,))
    rows = cursor.fetchall()
    
    if not rows:
        print("No NEW leads found in database.")
        conn.close()
        return

    print(f"Found {len(rows)} targets to verify.")
    
    processed = 0
    total_value = 0.0
    
    for row in rows:
        pubkey = row[0]
        print(f"Verifying {pubkey}...")
        
        if dry_run:
            # Mock
            count, value = 0, 0.0 
            status = 'VERIFIED_MOCK'
        else:
            # Synchronous Call utilizing RPCBalancer
            count, value = verify_target_viability(pubkey)
            status = 'VERIFIED' if count > 0 else 'DEAD'
            if count == 0 and value == 0.0:
                 status = 'DEAD'
        
        print(f"  Result: {count} accounts, {value:.4f} SOL")
        
        # Update DB
        cursor.execute("""
            UPDATE leads 
            SET status=?, verified_account_count=?, verified_rent_value=?, verified_at=CURRENT_TIMESTAMP
            WHERE pubkey=?
        """, (status, count, value, pubkey))
        
        conn.commit()
        processed += 1
        total_value += value
        
        # Pollute delay if not handled by rate limiter (though Balancer handles it)
        time.sleep(0.1) 

    conn.close()
    print(f"\nBatch Complete. Processed: {processed}. Total Potential: {total_value:.4f} SOL")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    run_verification_batch(limit=args.limit, dry_run=args.dry_run)
