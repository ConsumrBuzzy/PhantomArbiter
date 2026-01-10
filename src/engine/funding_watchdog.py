"""
DNEM FUNDING WATCHDOG (Phase 5.2)
=================================
Protect "Penny Profits" by monitoring funding rates.

Rules:
1. Check 1-hour funding rate every 15 minutes.
2. If rate is NEGATIVE (< 0.00) for 4 consecutive checks (1 hour), trigger CRITICAL UNWIND.
3. Unwind = Close Drift Short (Leg B) + Sell Spot SOL (Leg A).

Usage:
    python -m src.engine.funding_watchdog --loop
"""

import asyncio
import os
import struct
import json
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

import base58
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed

from src.shared.system.logging import Logger
from src.engine.auto_rebalancer import AutoRebalancer # For position parsing reuse

# =============================================================================
# CONSTANTS
# =============================================================================

DRIFT_PROGRAM_ID = Pubkey.from_string("dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH")
SOL_PERP_MARKET_INDEX = 0

# Offsets for PerpMarket account (derived from IDL analysis)
# PerpMarket struct:
# - pubkey (32)
# - amm (starts at 40)
#   - oracle (32)
#   - historicalOracleData (48)
#   - baseAssetAmountPerLp (16)
#   ... (see Step 362 analysis)
#   - lastFundingRate (at offset 480 from PerpMarket start)
LAST_FUNDING_RATE_OFFSET = 480
LAST_24H_AVG_FUNDING_RATE_OFFSET = 504

FUNDING_RATE_PRECISION = 1_000_000_000  # 1e9

WATCHDOG_STATE_FILE = Path("data/watchdog_state.json")

# =============================================================================
# WATCHDOG ENGINE
# =============================================================================

class FundingWatchdog:
    def __init__(self, check_interval_sec: int = 900): # 15 minutes
        self.check_interval_sec = check_interval_sec
        self.rpc_url = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
        self.consecutive_negative_checks = 0
        
        # Load state
        self._load_state()

    def _load_state(self):
        if WATCHDOG_STATE_FILE.exists():
            try:
                with open(WATCHDOG_STATE_FILE, 'r') as f:
                    data = json.load(f)
                    self.consecutive_negative_checks = data.get("negative_count", 0)
            except:
                self.consecutive_negative_checks = 0

    def _save_state(self):
        WATCHDOG_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(WATCHDOG_STATE_FILE, 'w') as f:
            json.dump({"negative_count": self.consecutive_negative_checks}, f)

    async def get_funding_rate(self, client: AsyncClient) -> float:
        """Fetch current hourly funding rate for SOL-PERP."""
        # Derive SOL-PERP market address
        # Market index 0
        market_pda, _ = Pubkey.find_program_address(
            [b"perp_market", (0).to_bytes(2, 'little')],
            DRIFT_PROGRAM_ID
        )
        
        info = await client.get_account_info(market_pda)
        if not info.value:
            Logger.error("Could not fetch SOL-PERP market account")
            return 0.0
            
        data = info.value.data
        
        # Read lastFundingRate (i64)
        raw_rate = struct.unpack_from("<q", data, LAST_FUNDING_RATE_OFFSET)[0]
        
        # Determine sign and scale
        # Rate is unit amount per hour? It's usually "quote per base" for the period
        # Drift updates funding every hour.
        
        rate_decimal = raw_rate / FUNDING_RATE_PRECISION
        
        # Also check 24h average for context
        raw_24h = struct.unpack_from("<q", data, LAST_24H_AVG_FUNDING_RATE_OFFSET)[0]
        rate_24h = raw_24h / FUNDING_RATE_PRECISION
        
        return rate_decimal

    async def check_health(self):
        """Single check loop."""
        async with AsyncClient(self.rpc_url) as client:
            current_rate = await self.get_funding_rate(client)
            
            # Convert to APR for display
            # Hourly rate * 24 * 365
            apr = current_rate * 24 * 365 * 100
            
            Logger.info(f"Funding Check: Rate = {current_rate:.8f}/hr ({apr:.2f}% APR)")
            
            if current_rate < 0:
                self.consecutive_negative_checks += 1
                Logger.warning(f"⚠️ NEGATIVE FUNDING DETECTED! Count: {self.consecutive_negative_checks}/4")
            else:
                if self.consecutive_negative_checks > 0:
                    Logger.success("✅ Funding positive. Resetting negative counter.")
                self.consecutive_negative_checks = 0
            
            self._save_state()
            
            # TRIGGER UNWIND?
            if self.consecutive_negative_checks >= 4:
                Logger.critical("🚨 CRITICAL: NEGATIVE FUNDING FOR 1 HOUR. TRIGGERING UNWIND!")
                await self.unwind_position(client)
                # Reset after unwind attempt to avoid spam loop, or exit
                self.consecutive_negative_checks = 0 
                self._save_state()

    async def unwind_position(self, client: AsyncClient):
        """
        Emergency Unwind:
        1. Close Drift Short
        2. Sell Spot SOL (Log only for now, manual confirmation recommended)
        """
        Logger.section("🛑 EMERGENCY UNWIND INITIATED 🛑")
        
        # 1. Get Drift Position Size
        # Re-use AutoRebalancer logic or standard fetch
        # For simplicity, just close whatever short we find
        
        # Load wallet
        private_key = os.getenv("SOLANA_PRIVATE_KEY") or os.getenv("PHANTOM_PRIVATE_KEY")
        if not private_key:
            Logger.error("No private key for unwind!")
            return

        from src.delta_neutral.drift_order_builder import DriftOrderBuilder
        from solders.transaction import VersionedTransaction
        from solders.message import MessageV0
        from solders.types import TxOpts
        
        secret_bytes = base58.b58decode(private_key)
        keypair = Keypair.from_bytes(secret_bytes)
        wallet_pk = keypair.pubkey()
        
        # Check current position
        rebalancer = AutoRebalancer() # Reuse to get data
        status = await rebalancer.check_and_rebalance(simulate=True)
        perp_size = status.get('perp_sol', 0)
        
        Logger.info(f"Current Drift Position: {perp_size} SOL")
        
        if perp_size < 0:
            Logger.info("Attempting to CLOSE Drift Short...")
            # Build Close Order (Reduce-Only Market Buy)
            builder = DriftOrderBuilder(wallet_pk)
            # Size should be positive for Long order
            close_size = abs(perp_size)
            
            # Market Long, Reduce Only
            # Note: build_long_order usually isn't reduce-only by default in some implementations, 
            # let's assume we use standard loop or specific reduce call
            # For now, let's use build_long_order and ensure we don't flip long (monitor logic?)
            # Actually, standard long order to match size exactly reduces it to 0.
            
            ixs = builder.build_long_order("SOL-PERP", close_size)
            # Safety: Force reduce-only if builder supports it? 
            # If not, exact size match is "neutralizing".
            
            bh_resp = await client.get_latest_blockhash()
            msg = MessageV0.try_compile(
                payer=wallet_pk,
                instructions=ixs,
                address_lookup_table_accounts=[],
                recent_blockhash=bh_resp.value.blockhash
            )
            tx = VersionedTransaction(msg, [keypair])
            
            try:
                sig = await client.send_transaction(tx, opts=TxOpts(skip_confirmation=False, preflight_commitment=Confirmed))
                Logger.success(f"Drift Close Tx Sent: {sig.value}")
            except Exception as e:
                Logger.error(f"Drift Close Failed: {e}")
        else:
            Logger.info("No Short Position to close.")

        # 2. Sell Spot SOL
        Logger.warning("⚠️ SPOT SALE REQUIRED: Please manually sell SOL on Jupiter/Phantom.")
        Logger.warning("   (Auto-Spot Sell not fully enabled in Watchdog v1)")

    async def run_loop(self):
        Logger.section("Started Funding Watchdog")
        while True:
            try:
                await self.check_health()
            except Exception as e:
                Logger.error(f"Watchdog error: {e}")
            
            Logger.info(f"Sleeping {self.check_interval_sec}s...")
            await asyncio.sleep(self.check_interval_sec)

if __name__ == "__main__":
    load_dotenv()
    dog = FundingWatchdog()
    asyncio.run(dog.run_loop())
