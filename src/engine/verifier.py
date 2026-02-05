import asyncio
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey
from solders.rpc.filter import Memcmp
from typing import List

TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
# Base58 for 32 bytes of 0s (approx representation for memcmp if needed, but 'bytes' expects base58 string of the bytes)
# 0 in base58 is '1'. 32 bytes of 0 is '11111111111111111111111111111111' usually used for System Program or checked. 
# For 'amount' (u64), it's 8 bytes. offset 64.
# 8 bytes of zeros in base58 is '11111111111'
# The user's prompt suggested "11111111111111111111111111111111". That's 32 bytes.
# Amount is u64 (8 bytes). 
# However, let's stick to the User's example if possible, or correct it for u64.
# User code: "bytes": "11111111111111111111111111111111"
# If amount is 0, it is 8 bytes of 0.
# If `memcmp` checks for *owner* equality or similar, maybe 32 bytes.
# But 0 balance check?
# Let's try to interpret the user's intent: "Balance is exactly 0".
# If we filter for amount (offset 64) = 0.
# 8 bytes of 0.
# "1" is the zero byte in Base58? No. Base58 '1' represents value 0? No, '1' is the character for 0 value in Bitcoin Base58, but in Solana Base58, '1' maps to 0x00? Yes.
# valid Base58 for 8 bytes of 0x00 is '11111111111'.
# User provided longer string. 
# I'll use the user's string but comment. 
# Actually, strict `getProgramAccounts` with `memcmp` for amount=0 works best with 8 bytes.
# But for now, I'll use the user's exact provided example logic to match the request "Implement ... using the memcmp filter".
# Note: "memcmp": {"offset": 64, "bytes": "..."} works on the raw data.
# Offset 64 is indeed the 'amount' field in SPL Token Account layout (Mint(32) + Owner(32) + Amount(8) + ...).

async def verify_target_viability(owner_pubkey: str) -> List[Pubkey]:
    """
    Verifies if a target is 'Skimmable'.
    Filters: 
    1. Owned by Token Program
    2. Data length is exactly 165 bytes (Standard SPL)
    3. Balance is exactly 0
    """
    
    # We need a client.
    # Ideally passed in, but for this standalone function we create one or use a context.
    # The user example used context manager.
    
    # Using public RPC might be rate limited for getProgramAccounts.
    async with AsyncClient("https://api.mainnet-beta.solana.com") as client:
        # Filter 1: Data Size = 165 (SPL Token Account)
        # solders/solana-py often accepts int for data size in the list
        filters = [165]
        
        # Filter 2: Amount = 0
        # Amount is at offset 64, length 8.
        # "11111111" is Base58 for 8 bytes of zeros.
        # solders Memcmp bytes arg expects the encoded string or bytes.
        # Signature is (offset, bytes_)
        memcmp_filter_amount = Memcmp(offset=64, bytes_="11111111")
        
        # Filter 3: Owner must be the target
        # Offset 32 is Owner (Pubkey).
        # owner_pubkey is string.
        memcmp_filter_owner = Memcmp(offset=32, bytes_=owner_pubkey)
        
        filters.append(memcmp_filter_amount)
        filters.append(memcmp_filter_owner)
        
        try:
            response = await client.get_program_accounts(
                TOKEN_PROGRAM_ID,
                filters=filters,
                encoding="base64"
            )
            
            # response.value is a list of objects with .pubkey and .account
            return [x.pubkey for x in response.value]
            
        except Exception as e:
            print(f"RPC Error for {owner_pubkey}: {e}")
            return []

if __name__ == "__main__":
    # Test logic
    asyncio.run(verify_target_viability("5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1"))
