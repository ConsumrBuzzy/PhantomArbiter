"""
DNEM Funding Tracker & Auto-Settler
====================================
Tracks funding payments from your Drift short position.

Features:
- Fetches current unrealized PnL from Drift
- Logs funding payments to CSV
- (Optional) Settles PnL to move profits to available margin

Usage:
    python scripts/track_funding.py          # Check current PnL
    python scripts/track_funding.py --log    # Log to CSV
"""

import asyncio
import os
import csv
import struct
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

import base58
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solana.rpc.async_api import AsyncClient

# =============================================================================
# CONSTANTS
# =============================================================================

DRIFT_PROGRAM_ID = Pubkey.from_string("dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH")
SOL_DECIMALS = 9
USDC_DECIMALS = 6

# Funding log file
FUNDING_LOG = Path("data/funding_harvest.csv")


# =============================================================================
# HELPERS
# =============================================================================


def derive_user_account(wallet: Pubkey) -> Pubkey:
    """Derive Drift user account PDA."""
    pda, _ = Pubkey.find_program_address(
        [b"user", bytes(wallet), (0).to_bytes(2, 'little')],
        DRIFT_PROGRAM_ID
    )
    return pda


def parse_perp_position(data: bytes, market_index: int = 0) -> dict:
    """
    Parse perp position from Drift User account.
    Returns position details including PnL fields.
    """
    DISCRIMINATOR = 8
    AUTHORITY = 32
    DELEGATE = 32
    NAME = 32
    SPOT_POSITIONS = 8 * 40
    
    PERP_POSITIONS_OFFSET = DISCRIMINATOR + AUTHORITY + DELEGATE + NAME + SPOT_POSITIONS
    PERP_POSITION_SIZE = 88
    
    if len(data) < PERP_POSITIONS_OFFSET + PERP_POSITION_SIZE:
        return None
    
    for i in range(8):
        offset = PERP_POSITIONS_OFFSET + (i * PERP_POSITION_SIZE)
        if offset + PERP_POSITION_SIZE > len(data):
            break
        
        pos_market_index = struct.unpack_from("<H", data, offset + 92)[0]
        
        if pos_market_index == market_index:
            # PerpPosition struct fields:
            # - lastCumulativeFundingRate: i64 (offset 0)
            # - baseAssetAmount: i64 (offset 8)
            # - quoteAssetAmount: i64 (offset 16) - Used for PnL calculation
            # - quoteBreakEvenAmount: i64 (offset 24)
            # - quoteEntryAmount: i64 (offset 32)
            # - settledPnl: i64 (offset 56)
            
            return {
                "market_index": pos_market_index,
                "base_asset_amount": struct.unpack_from("<q", data, offset + 8)[0],
                "quote_asset_amount": struct.unpack_from("<q", data, offset + 16)[0],
                "quote_break_even": struct.unpack_from("<q", data, offset + 24)[0],
                "quote_entry": struct.unpack_from("<q", data, offset + 32)[0],
                "settled_pnl": struct.unpack_from("<q", data, offset + 56)[0],
            }
    
    return None


def log_to_csv(timestamp: str, position_size: float, unrealized_pnl: float, settled_pnl: float):
    """Append funding record to CSV."""
    FUNDING_LOG.parent.mkdir(parents=True, exist_ok=True)
    
    file_exists = FUNDING_LOG.exists()
    
    with open(FUNDING_LOG, 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "position_sol", "unrealized_pnl_usd", "settled_pnl_usd", "total_pnl_usd"])
        
        total_pnl = unrealized_pnl + settled_pnl
        writer.writerow([timestamp, f"{position_size:.6f}", f"{unrealized_pnl:.6f}", f"{settled_pnl:.6f}", f"{total_pnl:.6f}"])


# =============================================================================
# MAIN
# =============================================================================


async def track_funding(log_to_file: bool = False):
    """Track funding payments from Drift position."""
    
    load_dotenv()
    
    print("=" * 60)
    print("   DNEM FUNDING TRACKER")
    print("   " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)
    
    # Load wallet
    private_key = os.getenv("SOLANA_PRIVATE_KEY") or os.getenv("PHANTOM_PRIVATE_KEY")
    if not private_key:
        print("❌ No private key found in .env")
        return
    
    secret_bytes = base58.b58decode(private_key)
    keypair = Keypair.from_bytes(secret_bytes)
    wallet_pk = keypair.pubkey()
    
    user_pda = derive_user_account(wallet_pk)
    
    rpc_url = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
    
    async with AsyncClient(rpc_url) as client:
        user_info = await client.get_account_info(user_pda)
        
        if not user_info.value:
            print("❌ Drift user account not found")
            return
        
        data = bytes(user_info.value.data)
        position = parse_perp_position(data, market_index=0)
        
        if not position:
            print("❌ No SOL-PERP position found")
            return
        
        # Calculate values
        position_size = position["base_asset_amount"] / (10 ** SOL_DECIMALS)
        quote_amount = position["quote_asset_amount"] / (10 ** USDC_DECIMALS)
        entry_amount = position["quote_entry"] / (10 ** USDC_DECIMALS)
        break_even = position["quote_break_even"] / (10 ** USDC_DECIMALS)
        settled_pnl = position["settled_pnl"] / (10 ** USDC_DECIMALS)
        
        # Unrealized PnL = quote_asset_amount - quote_entry_amount (simplified)
        # For shorts: profit when price goes down
        unrealized_pnl = quote_amount - entry_amount
        
        print(f"\n📊 SOL-PERP Position")
        print(f"   Size: {position_size:+.6f} SOL")
        print(f"   Entry Value: ${entry_amount:,.2f}")
        print(f"   Current Value: ${quote_amount:,.2f}")
        print(f"   Break-Even: ${break_even:,.2f}")
        
        print(f"\n💰 PnL Summary")
        print(f"   Unrealized PnL: ${unrealized_pnl:+.4f}")
        print(f"   Settled PnL:    ${settled_pnl:+.4f}")
        print(f"   ─────────────────────────")
        print(f"   Total PnL:      ${unrealized_pnl + settled_pnl:+.4f}")
        
        # Funding rate estimate (rough)
        # At 0.01% hourly funding, -0.10 SOL position at $150 = $15 * 0.0001 = $0.0015/hour
        hourly_estimate = abs(position_size) * 150 * 0.0001  # 0.01% hourly
        print(f"\n📈 Funding Estimate (if rate = 0.01%/hr)")
        print(f"   Hourly:  ${hourly_estimate:+.4f}")
        print(f"   Daily:   ${hourly_estimate * 24:+.4f}")
        print(f"   Monthly: ${hourly_estimate * 24 * 30:+.2f}")
        
        if log_to_file:
            timestamp = datetime.now().isoformat()
            log_to_csv(timestamp, position_size, unrealized_pnl, settled_pnl)
            print(f"\n✅ Logged to {FUNDING_LOG}")
        
        print()


if __name__ == "__main__":
    import sys
    log_flag = "--log" in sys.argv
    asyncio.run(track_funding(log_to_file=log_flag))
