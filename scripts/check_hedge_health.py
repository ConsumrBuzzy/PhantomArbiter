"""
DNEM Hedge Health Dashboard
============================
Real-time status check for Delta-Neutral position.

Displays:
- Spot SOL balance (wallet)
- Perp SOL-PERP position (Drift)
- Net Delta calculation
- System health status

Usage:
    python scripts/check_hedge_health.py
"""

import asyncio
import os
import struct
from datetime import datetime
from dotenv import load_dotenv

import base58
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient

# =============================================================================
# CONSTANTS
# =============================================================================

DRIFT_PROGRAM_ID = Pubkey.from_string("dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH")
USDC_MINT = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
SOL_DECIMALS = 9
USDC_DECIMALS = 6

# Pyth SOL/USD price feed (for reference)
PYTH_SOL_USD = Pubkey.from_string("H6ARHf6YXhGYeQfUzQNGk6rDNnLBQKrenN712K4AQJEG")

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
    
    User account layout:
    - 8 bytes: Anchor discriminator
    - 32 bytes: authority
    - 32 bytes: delegate  
    - 32 bytes: name
    - 8 * 40 bytes = 320 bytes: spotPositions (8 SpotPosition structs)
    - 8 * 88 bytes = 704 bytes: perpPositions (8 PerpPosition structs)
    
    PerpPosition struct (88 bytes):
    - lastCumulativeFundingRate: i64 (8 bytes) - offset 0
    - baseAssetAmount: i64 (8 bytes) - offset 8  <-- POSITION SIZE
    - quoteAssetAmount: i64 (8 bytes) - offset 16
    - quoteBreakEvenAmount: i64 - offset 24
    - quoteEntryAmount: i64 - offset 32
    - openBids: i64 - offset 40
    - openAsks: i64 - offset 48
    - settledPnl: i64 - offset 56
    - lpShares: u64 - offset 64
    - lastBaseAssetAmountPerLp: i64 - offset 72
    - lastQuoteAssetAmountPerLp: i64 - offset 80
    - padding: [u8; 2] - offset 88
    - maxMarginRatio: u16 - offset 90
    - marketIndex: u16 - offset 92
    """
    # Calculate offsets
    DISCRIMINATOR = 8
    AUTHORITY = 32
    DELEGATE = 32
    NAME = 32
    SPOT_POSITIONS = 8 * 40  # 8 SpotPosition(40 bytes each)
    
    PERP_POSITIONS_OFFSET = DISCRIMINATOR + AUTHORITY + DELEGATE + NAME + SPOT_POSITIONS  # = 424
    PERP_POSITION_SIZE = 88
    
    if len(data) < PERP_POSITIONS_OFFSET + PERP_POSITION_SIZE:
        return {"base_asset_amount": 0, "quote_asset_amount": 0, "market_index": -1}
    
    # Find position for market_index
    for i in range(8):  # Max 8 perp positions
        offset = PERP_POSITIONS_OFFSET + (i * PERP_POSITION_SIZE)
        if offset + PERP_POSITION_SIZE > len(data):
            break
        
        # marketIndex is at offset 92 within the PerpPosition struct
        pos_market_index = struct.unpack_from("<H", data, offset + 92)[0]
        
        if pos_market_index == market_index:
            # baseAssetAmount is at offset 8 within PerpPosition
            base_asset_amount = struct.unpack_from("<q", data, offset + 8)[0]
            quote_asset_amount = struct.unpack_from("<q", data, offset + 16)[0]
            
            return {
                "base_asset_amount": base_asset_amount,
                "quote_asset_amount": quote_asset_amount,
                "market_index": pos_market_index,
            }
    
    return {"base_asset_amount": 0, "quote_asset_amount": 0, "market_index": -1}


# =============================================================================
# MAIN
# =============================================================================


async def check_hedge_health():
    """Check the health of the delta-neutral hedge."""
    
    load_dotenv()
    
    print("=" * 60)
    print("   DNEM HEDGE HEALTH DASHBOARD")
    print("   " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)
    
    # Load wallet
    private_key = os.getenv("SOLANA_PRIVATE_KEY") or os.getenv("PHANTOM_PRIVATE_KEY")
    if not private_key:
        print("❌ No private key found in .env")
        return
    
    from solders.keypair import Keypair
    secret_bytes = base58.b58decode(private_key)
    keypair = Keypair.from_bytes(secret_bytes)
    wallet_pk = keypair.pubkey()
    
    print(f"\n📍 Wallet: {wallet_pk}")
    
    rpc_url = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
    
    async with AsyncClient(rpc_url) as client:
        # -----------------------------------------------------------------
        # 1. Get SOL Balance (Spot)
        # -----------------------------------------------------------------
        sol_balance = await client.get_balance(wallet_pk)
        spot_sol = sol_balance.value / (10 ** SOL_DECIMALS)
        
        print(f"\n{'─' * 40}")
        print("📈 SPOT POSITION (Wallet)")
        print(f"   SOL Balance: {spot_sol:.6f} SOL")
        
        # -----------------------------------------------------------------
        # 2. Get Drift User Account (Perp)
        # -----------------------------------------------------------------
        user_pda = derive_user_account(wallet_pk)
        print(f"\n{'─' * 40}")
        print("📉 PERP POSITION (Drift)")
        print(f"   User PDA: {user_pda}")
        
        user_info = await client.get_account_info(user_pda)
        
        if not user_info.value:
            print("   ❌ Drift user account not found")
            perp_sol = 0.0
        else:
            data = user_info.value.data
            position = parse_perp_position(bytes(data), market_index=0)
            
            # base_asset_amount is in BASE_PRECISION (1e9)
            perp_sol = position["base_asset_amount"] / (10 ** SOL_DECIMALS)
            quote_usd = position["quote_asset_amount"] / (10 ** USDC_DECIMALS)
            
            print(f"   SOL-PERP Size: {perp_sol:+.6f} SOL")
            print(f"   Quote (USDC): ${quote_usd:,.2f}")
            
            if perp_sol < 0:
                print("   Direction: 🔴 SHORT")
            elif perp_sol > 0:
                print("   Direction: 🟢 LONG")
            else:
                print("   Direction: ⚪ FLAT")
        
        # -----------------------------------------------------------------
        # 3. Calculate Net Delta
        # -----------------------------------------------------------------
        print(f"\n{'─' * 40}")
        print("⚖️  DELTA ANALYSIS")
        
        # Assume we're hedging against a "base" spot position
        # For delta-neutral: spot_sol + perp_sol should = 0
        # Reserve only minimal SOL for fees (~0.017 SOL = ~$2.50)
        reserved_sol = 0.017
        hedgeable_spot = max(0, spot_sol - reserved_sol)
        
        # Net delta = spot exposure + perp exposure
        # If perp_sol is negative (short), it offsets spot
        net_delta = hedgeable_spot + perp_sol
        
        # Target: matched sizes (opposite signs)
        # e.g., spot = 0.01, perp = -0.01 -> net_delta = 0
        if hedgeable_spot == 0:
            drift_pct = 0.0
        else:
            drift_pct = (net_delta / hedgeable_spot) * 100 if hedgeable_spot != 0 else 0.0
        
        print(f"   Hedgeable Spot: {hedgeable_spot:.6f} SOL")
        print(f"   Perp Position:  {perp_sol:+.6f} SOL")
        print(f"   Net Delta:      {net_delta:+.6f} SOL")
        print(f"   Delta Drift:    {drift_pct:+.2f}%")
        
        # -----------------------------------------------------------------
        # 4. System Health Status
        # -----------------------------------------------------------------
        print(f"\n{'─' * 40}")
        print("🏥 SYSTEM STATUS")
        
        # Define health thresholds
        HEALTHY_THRESHOLD = 0.1  # Within 0.1%
        WARNING_THRESHOLD = 0.5  # Within 0.5%
        
        abs_drift = abs(drift_pct)
        
        if abs_drift <= HEALTHY_THRESHOLD:
            status = "🟢 SYSTEM GREEN"
            status_msg = "Delta-Neutral within tolerance"
        elif abs_drift <= WARNING_THRESHOLD:
            status = "🟡 SYSTEM YELLOW"
            status_msg = "Minor drift detected, monitoring..."
        else:
            status = "🔴 SYSTEM RED"
            status_msg = "REBALANCE RECOMMENDED"
        
        print(f"   {status}")
        print(f"   {status_msg}")
        
        # -----------------------------------------------------------------
        # Summary Table
        # -----------------------------------------------------------------
        print(f"\n{'═' * 60}")
        print("   HEDGE SUMMARY")
        print(f"{'═' * 60}")
        print(f"   │ {'Leg':<12} │ {'Instrument':<15} │ {'Size':>12} │")
        print(f"   ├{'─' * 14}┼{'─' * 17}┼{'─' * 14}┤")
        print(f"   │ {'Spot':<12} │ {'SOL (Wallet)':<15} │ {spot_sol:>+12.6f} │")
        print(f"   │ {'Perp':<12} │ {'SOL-PERP':<15} │ {perp_sol:>+12.6f} │")
        print(f"   ├{'─' * 14}┼{'─' * 17}┼{'─' * 14}┤")
        print(f"   │ {'NET DELTA':<12} │ {'':<15} │ {net_delta:>+12.6f} │")
        print(f"   └{'─' * 14}┴{'─' * 17}┴{'─' * 14}┘")
        print()


if __name__ == "__main__":
    asyncio.run(check_hedge_health())
