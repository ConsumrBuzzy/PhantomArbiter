import asyncio
import sqlite3
import os
import argparse
import random
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient

# Constants
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "data", "targets.db")

# A known 'Dead' or High-Volume token for testing if none provided?
# Can't guess one.
DEFAULT_MOCK_MINT = "DeadTokenMintAddressPlaceHolder11111111"

async def ingest_holders(mint_address: str, mock_count: int = 0):
    print("="*50)
    print(f"📥 LEADS INGESTION: {mint_address}")
    print("="*50)
    
    holders = []
    
    if mock_count > 0:
        print(f"⚠️ MOCK MODE: Generating {mock_count} synthetic leads...")
        for i in range(mock_count):
            from solders.keypair import Keypair
            holders.append(str(Keypair().pubkey()))
    else:
        print(f"📡 Scanning Chain for holders of {mint_address}...")
        async with AsyncClient("https://api.mainnet-beta.solana.com") as client:
            try:
                # 1. SPL Token Account layout: Mint (0-32), Owner (32-64), Amount (64-72)
                # Filter: Mint == mint_address
                mint_filter = {
                    "memcmp": {
                        "offset": 0,
                        "bytes": mint_address
                    }
                }
                # Filter: Data Size 165
                size_filter = {"dataSize": 165}
                
                # We want *holders* who are likely to be zombies.
                # Only finding checks for Mint.
                # If we filter for Amount=0 here, we find people who have 0 balance of THIS token.
                # Which is exactly what we want (Dead Token account).
                amount_filter = {
                    "memcmp": {
                        "offset": 64,
                        "bytes": "11111111" # 8 bytes of 0x00
                    }
                }
                
                filters = [size_filter, mint_filter, amount_filter]
                
                response = await client.get_program_accounts(
                    TOKEN_PROGRAM_ID,
                    filters=filters,
                    encoding="base64"
                )
                
                print(f"   RPC Response: {len(response.value)} accounts found.")
                
                for account_info in response.value:
                    data = account_info.account.data
                    # Extract Owner (Offset 32, 32 bytes)
                    owner_bytes = data[32:64]
                    owner = str(Pubkey(owner_bytes))
                    holders.append(owner)
                    
            except Exception as e:
                print(f"❌ RPC Error: {e}")
                print("   (Use --mock to simulate if RPC fails)")
                return

    # De-duplicate
    unique_holders = list(set(holders))
    print(f"✅ Found {len(unique_holders)} Unique Owners.")
    
    if not unique_holders:
        return

    # Insert into DB
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    new_count = 0
    for owner in unique_holders:
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO leads (address, category, notes, status)
                VALUES (?, ?, ?, 'NEW')
            """, (owner, "Dead-Token-Holder", f"Auto-Ingest: {mint_address}",))
            if cursor.rowcount > 0:
                new_count += 1
        except Exception as e:
            pass
            
    conn.commit()
    conn.close()
    
    print(f"💾 Database Updated: {new_count} NEW leads added.")
    print("="*50)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mint", type=str, default=DEFAULT_MOCK_MINT, help="Token Mint Address")
    parser.add_argument("--mock", type=int, default=0, help="Generate N mock leads")
    args = parser.parse_args()
    
    asyncio.run(ingest_holders(args.mint, args.mock))
