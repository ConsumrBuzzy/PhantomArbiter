"""
Explore Drift Account Structure
================================

Reads the raw Drift account data and explores different offsets to find the correct balance.
"""

import asyncio
import struct
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from src.drivers.wallet_manager import WalletManager
from src.shared.system.logging import Logger


async def explore_account():
    """Explore Drift account structure."""
    
    Logger.info("=" * 80)
    Logger.info("EXPLORING DRIFT ACCOUNT STRUCTURE")
    Logger.info("=" * 80)
    Logger.info("")
    
    # Get wallet
    wallet_mgr = WalletManager()
    wallet_pubkey_str = wallet_mgr.get_public_key()
    wallet_pubkey = Pubkey.from_string(wallet_pubkey_str)
    
    Logger.info(f"Wallet: {wallet_pubkey_str}")
    Logger.info("")
    
    # RPC client
    rpc_url = "https://api.mainnet-beta.solana.com"
    client = AsyncClient(rpc_url)
    
    # Drift Program ID
    drift_program_id = Pubkey.from_string("dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH")
    
    # Derive User PDA
    seeds = [b"user", bytes(wallet_pubkey), (0).to_bytes(2, 'little')]
    user_pda, _ = Pubkey.find_program_address(seeds, drift_program_id)
    
    Logger.info(f"User PDA: {user_pda}")
    Logger.info("")
    
    # Fetch account data
    response = await client.get_account_info(user_pda)
    
    if not response.value:
        Logger.error("Account not found!")
        await client.close()
        return
    
    data = bytes(response.value.data)
    Logger.info(f"Account data size: {len(data)} bytes")
    Logger.info("")
    
    # Expected value: $31.56 USDC = 31,560,000 in raw (1e6 precision)
    expected_raw = 31_560_000
    Logger.info(f"Looking for value: {expected_raw} (31.56 USDC with 1e6 precision)")
    Logger.info("")
    
    # Also search for values in the $30-35 range
    Logger.info("Also searching for any value in $30-35 range...")
    Logger.info("")
    
    # Search for this value in the account data
    Logger.info("Searching for matching values...")
    Logger.info("")
    
    found_matches = []
    
    # Search as i64 (signed)
    for offset in range(0, len(data) - 8, 1):
        try:
            value = struct.unpack_from("<q", data, offset)[0]
            # Check for exact match
            if abs(value - expected_raw) < 1000:  # Within 0.001 USDC
                found_matches.append((offset, value, "i64"))
                Logger.success(f"✅ Found exact match at offset {offset}: {value} (i64) = ${value/1e6:.2f}")
            # Check for range $30-35
            elif 30_000_000 <= value <= 35_000_000:
                Logger.info(f"   Found in range at offset {offset}: {value} (i64) = ${value/1e6:.2f}")
        except:
            pass
    
    # Search as u64 (unsigned)
    for offset in range(0, len(data) - 8, 1):
        try:
            value = struct.unpack_from("<Q", data, offset)[0]
            if abs(value - expected_raw) < 1000:
                found_matches.append((offset, value, "u64"))
                Logger.success(f"✅ Found at offset {offset}: {value} (u64) = ${value/1e6:.2f}")
        except:
            pass
    
    Logger.info("")
    Logger.info(f"Total matches found: {len(found_matches)}")
    Logger.info("")
    
    # Also check what's at offset 104 (what we're currently reading)
    Logger.info("Current offset (104) reads:")
    try:
        value_104 = struct.unpack_from("<q", data, 104)[0]
        Logger.info(f"  Offset 104 (i64): {value_104} = ${value_104/1e6:.2f}")
    except:
        Logger.error("  Failed to read offset 104")
    
    Logger.info("")
    
    await client.close()


if __name__ == "__main__":
    asyncio.run(explore_account())
