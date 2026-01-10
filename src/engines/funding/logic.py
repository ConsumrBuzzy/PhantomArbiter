"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                     DNEM AUTO-REBALANCER                                     ║
║                  Phase 4.1: Autonomous Delta Correction                      ║
╚══════════════════════════════════════════════════════════════════════════════╝

Automatically corrects delta drift when it exceeds tolerance thresholds.

Features:
- 1% drift tolerance band
- 30-minute cooldown between trades
- Taker price limit safety (prevents toxic flow execution)
- Integrates with DriftOrderBuilder for execution

Usage:
    python -m src.engine.auto_rebalancer           # Single check
    python -m src.engine.auto_rebalancer --loop    # Continuous monitoring
"""

import asyncio
import os
import time
import struct
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

import base58
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solana.rpc.types import TxOpts

from src.delta_neutral.drift_order_builder import DriftOrderBuilder
from src.shared.system.logging import Logger

# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class RebalanceConfig:
    """Configuration for auto-rebalancer."""
    
    # Delta tolerance (1% = 0.01)
    drift_tolerance_pct: float = 1.0
    
    # Minimum seconds between rebalances
    cooldown_seconds: int = 1800  # 30 minutes
    
    # Maximum slippage allowed (in basis points)
    max_slippage_bps: int = 50  # 0.5%
    
    # Minimum trade size (SOL) - prevents dust trades
    min_trade_size: float = 0.005
    
    # Reserved SOL for gas
    reserved_sol: float = 0.017
    
    # Loop interval for continuous monitoring
    loop_interval_seconds: int = 60


# =============================================================================
# CONSTANTS
# =============================================================================

DRIFT_PROGRAM_ID = Pubkey.from_string("dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH")
SOL_DECIMALS = 9
USDC_DECIMALS = 6

# State file for cooldown tracking
STATE_FILE = Path("data/rebalancer_state.json")


# =============================================================================
# HELPERS
# =============================================================================


def derive_user_account(wallet: Pubkey) -> Pubkey:
    pda, _ = Pubkey.find_program_address(
        [b"user", bytes(wallet), (0).to_bytes(2, 'little')],
        DRIFT_PROGRAM_ID
    )
    return pda


def parse_perp_position(data: bytes, market_index: int = 0) -> Optional[dict]:
    """Parse perp position from Drift User account."""
    PERP_POSITIONS_OFFSET = 8 + 32 + 32 + 32 + (8 * 40)
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
            }
    return None


def load_last_rebalance_time() -> Optional[datetime]:
    """Load last rebalance timestamp from state file."""
    try:
        if STATE_FILE.exists():
            import json
            with open(STATE_FILE) as f:
                state = json.load(f)
                return datetime.fromisoformat(state.get("last_rebalance", ""))
    except:
        pass
    return None


def save_last_rebalance_time():
    """Save current timestamp as last rebalance time."""
    import json
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump({"last_rebalance": datetime.now().isoformat()}, f)


# =============================================================================
# AUTO-REBALANCER
# =============================================================================


class AutoRebalancer:
    """
    Autonomous delta-drift correction engine.
    
    Monitors the delta between spot SOL and perp short position.
    When drift exceeds tolerance, executes corrective trades.
    """
    
    def __init__(self, config: Optional[RebalanceConfig] = None):
        self.config = config or RebalanceConfig()
        self.last_rebalance = load_last_rebalance_time()
        
    async def check_and_rebalance(self, simulate: bool = True) -> dict:
        """
        Check delta drift and rebalance if needed.
        
        Returns:
            dict with status, drift_pct, action_taken, etc.
        """
        load_dotenv()
        
        # Load wallet
        private_key = os.getenv("SOLANA_PRIVATE_KEY") or os.getenv("PHANTOM_PRIVATE_KEY")
        if not private_key:
            return {"status": "error", "message": "No private key found"}
        
        secret_bytes = base58.b58decode(private_key)
        keypair = Keypair.from_bytes(secret_bytes)
        wallet_pk = keypair.pubkey()
        user_pda = derive_user_account(wallet_pk)
        
        rpc_url = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
        
        async with AsyncClient(rpc_url) as client:
            # Fetch current positions
            sol_balance = await client.get_balance(wallet_pk)
            spot_sol = sol_balance.value / (10 ** SOL_DECIMALS)
            
            user_info = await client.get_account_info(user_pda)
            if not user_info.value:
                return {"status": "error", "message": "Drift user account not found"}
            
            data = bytes(user_info.value.data)
            position = parse_perp_position(data, market_index=0)
            
            if not position:
                return {"status": "error", "message": "No perp position found"}
            
            perp_sol = position["base_asset_amount"] / (10 ** SOL_DECIMALS)
            quote_amount = position["quote_asset_amount"] / (10 ** USDC_DECIMALS)
            
            # Calculate delta
            hedgeable_spot = max(0, spot_sol - self.config.reserved_sol)
            net_delta = hedgeable_spot + perp_sol  # perp_sol is negative for shorts
            
            if hedgeable_spot == 0:
                return {"status": "error", "message": "No hedgeable spot balance"}
            
            drift_pct = (net_delta / hedgeable_spot) * 100
            abs_drift = abs(drift_pct)
            
            # Estimate SOL price
            sol_price = abs(quote_amount / perp_sol) if perp_sol != 0 else 150.0
            
            result = {
                "timestamp": datetime.now().isoformat(),
                "spot_sol": spot_sol,
                "perp_sol": perp_sol,
                "net_delta": net_delta,
                "drift_pct": drift_pct,
                "sol_price": sol_price,
                "action_taken": None,
                "tx_signature": None,
            }
            
            # Check if rebalance needed
            if abs_drift <= self.config.drift_tolerance_pct:
                result["status"] = "ok"
                result["message"] = f"Delta within tolerance ({drift_pct:+.2f}%)"
                return result
            
            # Check cooldown
            if self.last_rebalance:
                time_since_last = datetime.now() - self.last_rebalance
                if time_since_last < timedelta(seconds=self.config.cooldown_seconds):
                    remaining = self.config.cooldown_seconds - time_since_last.total_seconds()
                    result["status"] = "cooldown"
                    result["message"] = f"Cooldown active ({remaining:.0f}s remaining)"
                    return result
            
            # Calculate correction trade
            correction_size = abs(net_delta)
            
            if correction_size < self.config.min_trade_size:
                result["status"] = "skip"
                result["message"] = f"Correction too small ({correction_size:.6f} SOL)"
                return result
            
            # Determine trade direction
            if net_delta > 0:
                # Net long - need to increase short
                action = "EXPAND_SHORT"
                Logger.info(f"[REBALANCER] Net delta +{net_delta:.6f} SOL - expanding short by {correction_size:.6f}")
            else:
                # Net short - need to reduce short
                action = "REDUCE_SHORT"
                Logger.info(f"[REBALANCER] Net delta {net_delta:.6f} SOL - reducing short by {correction_size:.6f}")
            
            result["action_taken"] = action
            result["correction_size"] = correction_size
            
            # Execute trade
            if simulate:
                result["status"] = "simulated"
                result["message"] = f"Would {action} by {correction_size:.6f} SOL"
                Logger.info(f"[REBALANCER] SIMULATION: {result['message']}")
            else:
                try:
                    tx_sig = await self._execute_rebalance(
                        client, keypair, wallet_pk, action, correction_size
                    )
                    result["status"] = "executed"
                    result["tx_signature"] = tx_sig
                    result["message"] = f"Executed {action}: {tx_sig}"
                    
                    # Update cooldown
                    save_last_rebalance_time()
                    self.last_rebalance = datetime.now()
                    
                    Logger.success(f"[REBALANCER] ✅ Rebalance complete: {tx_sig}")
                    
                except Exception as e:
                    result["status"] = "error"
                    result["message"] = f"Execution failed: {e}"
                    Logger.error(f"[REBALANCER] ❌ Execution error: {e}")
            
            return result
    
    async def _execute_rebalance(
        self, 
        client: AsyncClient,
        keypair: Keypair,
        wallet_pk: Pubkey,
        action: str,
        size: float,
    ) -> str:
        """Execute the rebalance trade on Drift."""
        
        builder = DriftOrderBuilder(wallet_pk)
        
        if action == "EXPAND_SHORT":
            # Open additional short
            ixs = builder.build_short_order("SOL-PERP", size)
        else:
            # Reduce short (open long to offset)
            ixs = builder.build_long_order("SOL-PERP", size)
        
        # Get blockhash
        bh_resp = await client.get_latest_blockhash()
        blockhash = bh_resp.value.blockhash
        
        msg = MessageV0.try_compile(
            payer=wallet_pk,
            instructions=ixs,
            address_lookup_table_accounts=[],
            recent_blockhash=blockhash,
        )
        
        tx = VersionedTransaction(msg, [keypair])
        
        # Simulate first
        sim_resp = await client.simulate_transaction(tx)
        if sim_resp.value.err:
            raise Exception(f"Simulation failed: {sim_resp.value.err}")
        
        # Execute
        opts = TxOpts(skip_confirmation=False, preflight_commitment=Confirmed)
        resp = await client.send_transaction(tx, opts=opts)
        
        sig = str(resp.value)
        await client.confirm_transaction(resp.value, commitment=Confirmed)
        
        return sig
    
    async def run_loop(self, simulate: bool = True):
        """Run continuous monitoring loop."""
        
        Logger.section("AUTO-REBALANCER LOOP STARTED")
        Logger.info(f"Drift Tolerance: ±{self.config.drift_tolerance_pct}%")
        Logger.info(f"Cooldown: {self.config.cooldown_seconds}s")
        Logger.info(f"Loop Interval: {self.config.loop_interval_seconds}s")
        Logger.info(f"Mode: {'SIMULATION' if simulate else 'LIVE'}")
        
        while True:
            try:
                result = await self.check_and_rebalance(simulate=simulate)
                
                status_icon = {
                    "ok": "🟢",
                    "cooldown": "⏳",
                    "simulated": "🔵",
                    "executed": "✅",
                    "skip": "⏭️",
                    "error": "❌",
                }.get(result["status"], "❓")
                
                Logger.info(
                    f"[{datetime.now().strftime('%H:%M:%S')}] "
                    f"{status_icon} Drift: {result.get('drift_pct', 0):+.2f}% | "
                    f"{result.get('message', '')}"
                )
                
            except Exception as e:
                Logger.error(f"[REBALANCER] Loop error: {e}")
            
            await asyncio.sleep(self.config.loop_interval_seconds)


# =============================================================================
# MAIN
# =============================================================================


async def main():
    import sys
    
    loop_mode = "--loop" in sys.argv
    live_mode = "--live" in sys.argv
    
    config = RebalanceConfig()
    rebalancer = AutoRebalancer(config)
    
    if loop_mode:
        await rebalancer.run_loop(simulate=not live_mode)
    else:
        result = await rebalancer.check_and_rebalance(simulate=not live_mode)
        
        print("\n" + "=" * 50)
        print("  AUTO-REBALANCER CHECK")
        print("=" * 50)
        print(f"  Status:     {result['status'].upper()}")
        print(f"  Drift:      {result.get('drift_pct', 0):+.2f}%")
        print(f"  Net Delta:  {result.get('net_delta', 0):+.6f} SOL")
        print(f"  Message:    {result.get('message', '')}")
        if result.get('action_taken'):
            print(f"  Action:     {result['action_taken']}")
        if result.get('tx_signature'):
            print(f"  Tx:         {result['tx_signature']}")
        print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
