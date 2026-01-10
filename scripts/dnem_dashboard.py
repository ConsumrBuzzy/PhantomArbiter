import asyncio
import os
import sys
import struct
import json
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey

# Rich Imports
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.console import Console
from rich import box
from rich.align import Align

# =============================================================================
# CONSTANTS & HELPERS (Legacy Logic Preserved)
# =============================================================================

DRIFT_PROGRAM_ID = Pubkey.from_string("dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH")
USDC_SPOT_MARKET_INDEX = 0
SOL_PERP_MARKET_INDEX = 0

SOL_DECIMALS = 9
USDC_DECIMALS = 6
QUOTE_PRECISION = 1_000_000

RESERVED_SOL = 0.02

# Thresholds
HEALTHY_THRESHOLD = 2.0  # Drift < 2%
WARNING_THRESHOLD = 5.0  # Drift < 5%
ALERT_THRESHOLD = 5.0

def get_user_account_public_key(program_id: Pubkey, authority: Pubkey, sub_account_id: int = 0) -> Pubkey:
    """Derive Drift User Account PDA."""
    return Pubkey.find_program_address(
        [b"user", bytes(authority), sub_account_id.to_bytes(2, "little")],
        program_id
    )[0]

def parse_perp_position(user_account_data: bytes, market_index: int = 0) -> dict:
    """
    Manually parses the User Account data to find the Perp Position.
    (Simplified from IDL structure)
    """
    # Offset analysis from Phase 1
    # Discriminator: 8 bytes
    # Authority: 32
    # Delegate: 32
    # Name: 32
    # SpotPositions: 8 * 104 (832)
    # PerpPositions: Start approx at 8 + 32 + 32 + 32 + 832 = 936
    # Each PerpPosition is ~108 bytes
    
    PERP_POSITIONS_OFFSET = 936
    PERP_POSITION_SIZE = 108 # Adjusted based on IDL
    
    offset = PERP_POSITIONS_OFFSET
    # Loop through up to 8 positions
    for _ in range(8):
        # Read market index (u16)
        try:
            m_index = struct.unpack_from("<H", user_account_data, offset)[0]
            
            # If this is our market
            if m_index == market_index:
                # Read Base Asset Amount (i64) at offset + 2 (padding) + ?
                # Layout: market_index (2), kind (1), padding (5), base_asset_amount (8), quote_asset_amount (8), ...
                base_amt = struct.unpack_from("<q", user_account_data, offset + 8)[0]
                quote_amt = struct.unpack_from("<q", user_account_data, offset + 16)[0]
                quote_entry = struct.unpack_from("<q", user_account_data, offset + 24)[0] # Approx
                settled_pnl = struct.unpack_from("<q", user_account_data, offset + 56)[0] # Approx check IDL if needed
                
                # Check for "Available" flag? 
                # If market index is 0 and base is 0, might be uninitialized? 
                # Drift usually inits indices to 0. Check base amt.
                return {
                    "base_asset_amount": base_amt,
                    "quote_asset_amount": quote_amt,
                    "quote_entry": quote_entry,
                    "settled_pnl": settled_pnl
                }
        except:
            pass
        offset += PERP_POSITION_SIZE
        
    return None

def get_health_score(maint_margin, equity):
    if maint_margin == 0: return 100.0
    health = 100 * (1 - (maint_margin / equity))
    return max(0, min(100, health))

# =============================================================================
# RICH DASHBOARD CLASS
# =============================================================================

class DNEMDashboard:
    def __init__(self):
        self.layout = Layout()
        self.layout.split(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )
        self.layout["main"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=1)
        )
        self.layout["left"].split_column(
            Layout(name="positions", ratio=1),
            Layout(name="pnl", ratio=1)
        )
        self.layout["right"].split_column(
            Layout(name="risk", ratio=1),
            Layout(name="sim", ratio=1)
        )

    def update(self, data: dict):
        """Update all panels with new data."""
        self.layout["header"].update(self._header(data))
        self.layout["positions"].update(self._positions_panel(data))
        self.layout["pnl"].update(self._pnl_panel(data))
        self.layout["risk"].update(self._risk_panel(data))
        self.layout["sim"].update(self._sim_panel(data))
        self.layout["footer"].update(self._footer(data))

    def _header(self, data: dict):
        now = datetime.now().strftime("%H:%M:%S")
        
        # Engine Heartbeat
        heartbeat = data.get("heartbeat", {})
        hb_mode = heartbeat.get("mode", "STOPPED")
        hb_next = heartbeat.get("next_beat_sec", 0)
        
        if hb_next > 0:
            status = f"🟢 ONLINE | Next Beat: {hb_next}s"
            style = "bold white on green"
        else:
            status = f"🔴 PENDING/OFFLINE"
            style = "bold white on red"
            
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="right", ratio=1)
        
        grid.add_row(
            f"🏛️  PHANTOM ARBITER",
            f"[{style}] {hb_mode} [/]",
            f"CLOCK: {now} UTC"
        )
        
        return Panel(grid, style="white on blue")

    def _positions_panel(self, data: dict):
        table = Table(box=box.SIMPLE)
        table.add_column("Asset", style="cyan")
        table.add_column("Amount", justify="right")
        table.add_column("Value (USD)", justify="right")
        
        spot_sol = data.get("spot_sol", 0)
        perp_sol = data.get("perp_sol", 0)
        price = data.get("sol_price", 0)
        
        table.add_row("Spot SOL", f"{spot_sol:.4f}", f"${spot_sol * price:.2f}")
        table.add_row("Perp SOL", f"{perp_sol:.4f}", f"${perp_sol * price:.2f}")
        
        net_delta = spot_sol + perp_sol
        hedgeable = max(0, spot_sol - RESERVED_SOL)
        drift = (net_delta / hedgeable * 100) if hedgeable > 0 else 0
        
        color = "green" if abs(drift) < 2.0 else "red"
        table.add_row("Net Delta", f"[{color}]{net_delta:+.4f}[/]", f"Drift: [{color}]{drift:+.2f}%[/]")
        
        return Panel(table, title="📊 Positions & Delta", border_style="cyan")

    def _pnl_panel(self, data: dict):
        table = Table(box=box.SIMPLE)
        table.add_column("Metric")
        table.add_column("Value", justify="right", style="green")
        
        u_pnl = data.get("unrealized_pnl", 0)
        s_pnl = data.get("settled_pnl", 0)
        
        # Estimate Funding
        perp_sol = data.get("perp_sol", 0)
        price = data.get("sol_price", 0)
        # Funding rate?
        rate_hr = data.get("funding_rate_hr", 0)
        hr_yield = abs(perp_sol) * price * rate_hr
        
        table.add_row("Unrealized PnL", f"${u_pnl:+.4f}")
        table.add_row("Settled PnL", f"${s_pnl:+.4f}")
        table.add_section()
        
        rate_color = "green" if rate_hr > 0 else "red"
        table.add_row("Funding Rate", f"[{rate_color}]{rate_hr:.6f}/hr[/]")
        table.add_row("Est. Yield/Hr", f"${hr_yield:.4f}")
        table.add_row("Est. Yield/Day", f"${hr_yield*24:.2f}")
        
        return Panel(table, title="💰 PnL & Yield", border_style="green")

    def _risk_panel(self, data: dict):
        health = data.get("health_score", 0)
        liq_buf = data.get("liq_dist_pct", 0)
        perp_sol = data.get("perp_sol", 0)
        
        # Determine Status
        status = "SECURE"
        color = "green"
        if health < 50: 
            status = "DANGER"
            color = "red"
        elif health < 80:
            status = "WARNING"
            color = "yellow"
            
        # Unwind check
        funding = data.get("funding_rate_hr", 0)
        unwind = "NO"
        if funding < -0.0005:
            unwind = "WATCHDOG ACTIVE"
            color = "yellow"
        
        grid = Table.grid(expand=True)
        grid.add_column()
        grid.add_column(justify="right")
        
        prog = int(health / 10)
        bar = "█" * prog + "░" * (10 - prog)
        
        grid.add_row("Health Score", f"[{color}]{health:.1f}% {bar}[/]")
        grid.add_row("Liq Buffer", f"{liq_buf:+.1f}%")
        grid.add_row("Watchdog", f"[{color}]{unwind}[/]")
        
        return Panel(grid, title=f"🛡️ Risk: [{color}]{status}[/]", border_style="red")

    def _sim_panel(self, data: dict):
        # Leverage Simulator
        table = Table(box=box.SIMPLE, show_header=True)
        table.add_column("Lev", width=4)
        table.add_column("Size")
        table.add_column("Health")
        
        base_amt = abs(data.get("perp_sol", 0)) or 0.1
        price = data.get("sol_price", 0)
        equity = data.get("spot_sol", 0) * price 
        
        for lev in [1.0, 2.0, 3.0]:
            size = base_amt * lev # Simplified
            # Crude health calc
            notional = size * price
            maint = notional * 0.10
            h = 100 * (1 - maint/equity) if equity > 0 else 0
            hc = "green" if h > 50 else "red"
            table.add_row(f"{lev}x", f"{size:.1f} S", f"[{hc}]{h:.0f}%[/]")
            
        return Panel(table, title="🎢 Leverage Sim", border_style="magenta")

    def _footer(self, data: dict):
        msg = data.get("log_msg", "System monitoring active.")
        return Panel(Text(msg, style="dim"), style="white on black")


# =============================================================================
# MAIN LOOP
# =============================================================================

async def run_dashboard(log_to_file: bool = False, watch_mode: bool = True):
    load_dotenv()
    
    # RPC Setup
    rpc_url = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
    client = AsyncClient(rpc_url)
    
    # Wallet / User
    private_key = os.getenv("SOLANA_PRIVATE_KEY") or os.getenv("PHANTOM_PRIVATE_KEY")
    if not private_key:
        print("Error: Missing Private Key")
        return

    # Decode Key (Placeholder for actual wallet Manager)
    # Just need Pubkey for queries
    # Assuming user knows how to setup env, skipping strict key decode for brevity if imports missing
    # Re-importing core logic if needed
    import base58
    from solders.keypair import Keypair
    
    keypair = Keypair.from_bytes(base58.b58decode(private_key))
    wallet_pk = keypair.pubkey()
    
    # Derive Drift User
    user_pda = get_user_account_public_key(DRIFT_PROGRAM_ID, wallet_pk, 0)
    
    # Setup TUI
    dashboard = DNEMDashboard()
    
    with Live(dashboard.layout, refresh_per_second=2, screen=True) as live:
        while True:
            try:
                # 1. Fetch Engine State (Heartbeat)
                engine_state = {}
                state_file = Path("data/engine_state.json")
                if state_file.exists():
                    try:
                        with open(state_file) as f:
                            js = json.load(f)
                            # Calc next beat
                            nb = js.get("next_beat", 0)
                            rem = max(0, int(nb - time.time()))
                            engine_state = {
                                "mode": js.get("mode", "UNKNOWN"),
                                "next_beat_sec": rem
                            }
                    except:
                        pass
                
                # 2. Fetch On-Chain Data
                # Balance
                bal_resp = await client.get_balance(wallet_pk)
                spot_sol = bal_resp.value / 1e9
                
                # Position
                acc_resp = await client.get_account_info(user_pda)
                perp_sol = 0.0
                u_pnl = 0.0
                s_pnl = 0.0
                
                if acc_resp.value:
                    pos_data = parse_perp_position(acc_resp.value.data)
                    if pos_data:
                        perp_sol = pos_data["base_asset_amount"] / 1e9
                        u_pnl = 0 # Complex calc, skip for MVP or placeholder
                        s_pnl = pos_data["settled_pnl"] / 1e6
                
                # Fetch Price (Oracle? Or Jupiter?)
                # Quick hack: Use a known oracle or just assuming a price for TUI speed?
                # Let's use the Python request to simple price API if RPC is heavy?
                # No, RPC Oracle read is best.
                # SOL Oracle: 
                oracle = Pubkey.from_string("H6ARHf6YXhGYeQfUzQNGk6rDNnLBQKrenN712K4AQJEG")
                o_resp = await client.get_account_info(oracle)
                sol_price = 0
                if o_resp.value:
                    # Pyth/Switchboard layout... assuming Pyth for now or similar
                    # Pyth price is at offset 208? 
                    # Actually let's just use a hardcoded fallback or simple publicly available API for TUI 
                    # so we don't block on Oracle parsing complexity here.
                    # BETTER: Use valid pyth parsing if possible.
                    pass
                
                # FALLBACK PRICE for MVP TUI
                sol_price = 145.0 # TODO: Real feed
                
                # 3. Construct Data Dict
                data = {
                    "heartbeat": engine_state,
                    "spot_sol": spot_sol,
                    "perp_sol": perp_sol,
                    "sol_price": sol_price,
                    "unrealized_pnl": u_pnl,
                    "settled_pnl": s_pnl,
                    "funding_rate_hr": -0.0017, # TODO: Fetch real
                    "health_score": 95.0, # TODO: Calc
                    "liq_dist_pct": 30.0,
                    "log_msg": f"Last Updated: {datetime.now().strftime('%H:%M:%S')}"
                }
                
                # Update UI
                dashboard.update(data)
                
                await asyncio.sleep(1)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                # Log error to footer
                dashboard.update({"log_msg": f"Error: {e}"})
                await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(run_dashboard())
    except KeyboardInterrupt:
        print("👋 Dashboard Closed.")
