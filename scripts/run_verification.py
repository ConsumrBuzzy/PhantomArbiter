import asyncio
import sqlite3
import os
import random
from solders.pubkey import Pubkey

# Import Verifier
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.engine.verifier import verify_target_viability

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "src", "data", "targets.db")

async def run_verification_batch():
    print("="*50)
    print("⚖️ SKIMMER TRUTH MACHINE: BATCH 1 (Top 50)")
    print("="*50)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Fetch Candidates (Using NEW status)
    cursor.execute("SELECT address FROM leads WHERE status='NEW' LIMIT 50")
    rows = cursor.fetchall()
    targets = [r[0] for r in rows]
    
    if not targets:
        print("❌ No NEW targets found in DB.")
        conn.close()
        return

    print(f"🔍 Verifying {len(targets)} Targets...")
    
    verified_count = 0
    total_value = 0.0
    
    for address in targets:
        print(f"   Checking {address}...", end="", flush=True)
        
        # Call Verifier (RPC)
        try:
            # We enforce a small delay to be nice to public RPC
            await asyncio.sleep(0.5) 
            
            viable_accounts = await verify_target_viability(address)
            
            count = len(viable_accounts)
            value = count * 0.00203928
            
            # Print status
            if count > 0:
                print(f" ✅ FOUND {count} Accounts ({value:.4f} SOL)")
                
                # Update DB
                cursor.execute("""
                    UPDATE leads 
                    SET verified_account_count=?, verified_rent_value=?, status='VERIFIED'
                    WHERE address=?
                """, (count, value, address))
                
                verified_count += 1
                total_value += value
            else:
                print(" ❌ Dead")
                cursor.execute("UPDATE leads SET status='DEAD' WHERE address=?", (address,))
                
        except Exception as e:
            print(f" ⚠️ RPC Error: {e}")
            # Mock Fallback for Demonstration if RPC fails drastically
            # (In production we would just log error)
            
    conn.commit()
    conn.close()
    
    print("-" * 50)
    print("📊 TRUTH REPORT")
    print("-" * 50)
    print(f"Targets Scanned:      {len(targets)}")
    print(f"Viable Targets:       {verified_count}")
    print(f"Total Verified Value: {total_value:.4f} SOL")
    print("-" * 50)
    
    if total_value > 0.01:
        print("✅ GROUND TRUTH ESTABLISHED. READY FOR HARVEST.")
    else:
        print("⚠️ NO YIELD FOUND (Or RPC failed).")

if __name__ == "__main__":
    asyncio.run(run_verification_batch())
