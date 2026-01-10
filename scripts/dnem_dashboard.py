"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                     DNEM UNIFIED DASHBOARD                                   ║
║                  Delta-Neutral Execution Module                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

One command to see everything:
- Wallet SOL balance
- Drift perp position  
- Net delta & hedge health
- PnL & funding estimates
- System status

Usage:
    python scripts/dnem_dashboard.py           # Standard view
    python scripts/dnem_dashboard.py --log     # Log to CSV
    python scripts/dnem_dashboard.py --watch   # Refresh every 30s
"""

import asyncio
import os
import csv
import struct
import sys
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
RESERVED_SOL = 0.017  # Reserved for gas fees

# Funding log
FUNDING_LOG = Path("data/funding_harvest.csv")

# Status thresholds
HEALTHY_THRESHOLD = 0.1   # Within 0.1%
WARNING_THRESHOLD = 0.5   # Within 0.5%
ALERT_THRESHOLD = 1.0     # Rebalance alert at 1%


def trigger_alert(drift_pct: float):
    """Trigger audio/visual alert when drift exceeds threshold."""
    import winsound
    print("\n" + "🚨" * 20)
    print(f"   ⚠️  REBALANCE ALERT: Delta Drift = {drift_pct:+.2f}%")
    print(f"   ⚠️  Threshold exceeded! Manual intervention recommended.")
    print("🚨" * 20)
    
    # Windows beep (frequency=1000Hz, duration=500ms)
    try:
        winsound.Beep(1000, 500)
        winsound.Beep(1500, 500)
    except:
        print("\a")  # Fallback terminal beep


# =============================================================================
# HELPERS
# =============================================================================


def derive_user_account(wallet: Pubkey) -> Pubkey:
    pda, _ = Pubkey.find_program_address(
        [b"user", bytes(wallet), (0).to_bytes(2, 'little')],
        DRIFT_PROGRAM_ID
    )
    return pda


def parse_perp_position(data: bytes, market_index: int = 0) -> dict:
    """Parse perp position from Drift User account."""
    PERP_POSITIONS_OFFSET = 8 + 32 + 32 + 32 + (8 * 40)  # 424
    PERP_POSITION_SIZE = 88
    
    if len(data) < PERP_POSITIONS_OFFSET + PERP_POSITION_SIZE:
        return None
    
    for i in range(8):
        offset = PERP_POSITIONS_OFFSET + (i * PERP_POSITION_SIZE)
        if offset + PERP_POSITION_SIZE > len(data):
            break
        
        pos_market_index = struct.unpack_from("<H", data, offset + 92)[0]
        
        if pos_market_index == market_index:
            return {
                "market_index": pos_market_index,
                "base_asset_amount": struct.unpack_from("<q", data, offset + 8)[0],
                "quote_asset_amount": struct.unpack_from("<q", data, offset + 16)[0],
                "quote_break_even": struct.unpack_from("<q", data, offset + 24)[0],
                "quote_entry": struct.unpack_from("<q", data, offset + 32)[0],
                "settled_pnl": struct.unpack_from("<q", data, offset + 56)[0],
            }
    return None


def log_to_csv(data: dict):
    """Log funding record to CSV."""
    FUNDING_LOG.parent.mkdir(parents=True, exist_ok=True)
    file_exists = FUNDING_LOG.exists()
    
    with open(FUNDING_LOG, 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "spot_sol", "perp_sol", "net_delta", "drift_pct", 
                           "unrealized_pnl", "settled_pnl", "total_pnl"])
        writer.writerow([
            data["timestamp"], 
            f"{data['spot_sol']:.6f}",
            f"{data['perp_sol']:.6f}",
            f"{data['net_delta']:.6f}",
            f"{data['drift_pct']:.2f}",
            f"{data['unrealized_pnl']:.6f}",
            f"{data['settled_pnl']:.6f}",
            f"{data['total_pnl']:.6f}",
        ])


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


# =============================================================================
# MAIN DASHBOARD
# =============================================================================


async def run_dashboard(log_to_file: bool = False, watch_mode: bool = False):
    """Run the unified DNEM dashboard."""
    
    load_dotenv()
    
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
    
    while True:
        try:
            async with AsyncClient(rpc_url) as client:
                await display_dashboard(client, wallet_pk, user_pda, log_to_file)
        except Exception as e:
            print(f"\n❌ Error: {e}")
        
        if not watch_mode:
            break
        
        print("\n⏳ Refreshing in 30 seconds... (Ctrl+C to exit)")
        try:
            await asyncio.sleep(30)
            clear_screen()
        except KeyboardInterrupt:
            print("\n👋 Dashboard stopped.")
            break


async def display_dashboard(client: AsyncClient, wallet_pk: Pubkey, user_pda: Pubkey, log_to_file: bool):
    """Display the full dashboard."""
    
    now = datetime.now()
    
    # Header
    print()
    print("╔" + "═" * 62 + "╗")
    print("║" + "   🏛️  DNEM UNIFIED DASHBOARD".center(62) + "║")
    print("║" + f"   {now.strftime('%Y-%m-%d %H:%M:%S')}".center(62) + "║")
    print("╚" + "═" * 62 + "╝")
    
    # -----------------------------------------------------------------
    # Fetch Data
    # -----------------------------------------------------------------
    
    # SOL Balance
    sol_balance = await client.get_balance(wallet_pk)
    spot_sol = sol_balance.value / (10 ** SOL_DECIMALS)
    
    # Drift Position
    user_info = await client.get_account_info(user_pda)
    
    perp_sol = 0.0
    quote_amount = 0.0
    entry_amount = 0.0
    settled_pnl = 0.0
    has_position = False
    
    if user_info.value:
        data = bytes(user_info.value.data)
        position = parse_perp_position(data, market_index=0)
        
        if position and position["base_asset_amount"] != 0:
            has_position = True
            perp_sol = position["base_asset_amount"] / (10 ** SOL_DECIMALS)
            quote_amount = position["quote_asset_amount"] / (10 ** USDC_DECIMALS)
            entry_amount = position["quote_entry"] / (10 ** USDC_DECIMALS)
            settled_pnl = position["settled_pnl"] / (10 ** USDC_DECIMALS)
    
    # Calculations
    hedgeable_spot = max(0, spot_sol - RESERVED_SOL)
    net_delta = hedgeable_spot + perp_sol
    drift_pct = (net_delta / hedgeable_spot * 100) if hedgeable_spot > 0 else 0.0
    abs_drift = abs(drift_pct)
    
    unrealized_pnl = quote_amount - entry_amount if has_position else 0.0
    total_pnl = unrealized_pnl + settled_pnl
    
    # SOL price estimate (from position notional)
    sol_price = abs(quote_amount / perp_sol) if perp_sol != 0 else 150.0
    
    # -----------------------------------------------------------------
    # Display Sections
    # -----------------------------------------------------------------
    
    # Section 1: Positions
    print("\n┌─────────────────────────────────────────────────────────────┐")
    print("│  📊 POSITIONS                                               │")
    print("├─────────────────────────────────────────────────────────────┤")
    print(f"│  Wallet:  {str(wallet_pk)[:20]}...                       │")
    print(f"│                                                             │")
    print(f"│  📈 SPOT (Wallet)       {spot_sol:>+12.6f} SOL              │")
    print(f"│  📉 PERP (Drift)        {perp_sol:>+12.6f} SOL              │")
    print(f"│  ─────────────────────────────────────────                  │")
    print(f"│  ⚖️  NET DELTA           {net_delta:>+12.6f} SOL              │")
    print("└─────────────────────────────────────────────────────────────┘")
    
    # Section 2: Hedge Health
    if abs_drift <= HEALTHY_THRESHOLD:
        status = "🟢 SYSTEM GREEN"
        status_msg = "Perfectly hedged"
    elif abs_drift <= WARNING_THRESHOLD:
        status = "🟡 SYSTEM YELLOW"
        status_msg = "Minor drift, monitoring..."
    else:
        status = "🔴 SYSTEM RED"
        status_msg = "REBALANCE RECOMMENDED"
    
    print("\n┌─────────────────────────────────────────────────────────────┐")
    print("│  🛡️  HEDGE HEALTH                                           │")
    print("├─────────────────────────────────────────────────────────────┤")
    print(f"│  Delta Drift:     {drift_pct:>+8.2f}%                              │")
    print(f"│  Status:          {status:<20}                  │")
    print(f"│  Message:         {status_msg:<30}        │")
    print("└─────────────────────────────────────────────────────────────┘")
    
    # Section 3: PnL & Funding
    hourly_funding = abs(perp_sol) * sol_price * 0.0001  # 0.01% estimate
    
    print("\n┌─────────────────────────────────────────────────────────────┐")
    print("│  💰 PnL & FUNDING                                           │")
    print("├─────────────────────────────────────────────────────────────┤")
    print(f"│  Position Size:   {abs(perp_sol):>8.4f} SOL @ ${sol_price:>7.2f}          │")
    print(f"│  Notional Value:  ${abs(quote_amount):>10.2f}                          │")
    print(f"│                                                             │")
    print(f"│  Unrealized PnL:  ${unrealized_pnl:>+10.4f}                          │")
    print(f"│  Settled PnL:     ${settled_pnl:>+10.4f}                          │")
    print(f"│  ─────────────────────────────────────────                  │")
    print(f"│  TOTAL PnL:       ${total_pnl:>+10.4f}                          │")
    print("└─────────────────────────────────────────────────────────────┘")
    
    # Section 4: Funding Estimates
    print("\n┌─────────────────────────────────────────────────────────────┐")
    print("│  📈 FUNDING ESTIMATES (at 0.01%/hr)                         │")
    print("├─────────────────────────────────────────────────────────────┤")
    print(f"│  Hourly:   ${hourly_funding:>8.4f}                                   │")
    print(f"│  Daily:    ${hourly_funding * 24:>8.4f}                                   │")
    print(f"│  Monthly:  ${hourly_funding * 24 * 30:>8.2f}                                   │")
    print("└─────────────────────────────────────────────────────────────┘")
    
    # Log to CSV if requested
    if log_to_file:
        log_to_csv({
            "timestamp": now.isoformat(),
            "spot_sol": spot_sol,
            "perp_sol": perp_sol,
            "net_delta": net_delta,
            "drift_pct": drift_pct,
            "unrealized_pnl": unrealized_pnl,
            "settled_pnl": settled_pnl,
            "total_pnl": total_pnl,
        })
        print(f"\n✅ Logged to {FUNDING_LOG}")
    
    # Trigger alert if drift exceeds threshold
    if abs_drift > ALERT_THRESHOLD:
        trigger_alert(drift_pct)


if __name__ == "__main__":
    log_flag = "--log" in sys.argv
    watch_flag = "--watch" in sys.argv
    
    asyncio.run(run_dashboard(log_to_file=log_flag, watch_mode=watch_flag))
