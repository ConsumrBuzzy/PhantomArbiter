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
NEGATIVE_THRESHOLD = -0.0005 # Stricter tolerance
POSITIVE_THRESHOLD = 0.0005  # Re-Entry requirement

WATCHDOG_STATE_FILE = Path("data/watchdog_state.json")

# ...

class FundingWatchdog:
    def __init__(self, check_interval_sec: int = 900): # 15 minutes
        self.check_interval_sec = check_interval_sec
        self.rpc_url = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
        self.consecutive_negative_checks = 0
        self.consecutive_positive_checks = 0
        
        # Load state
        self._load_state()

    def _load_state(self):
        if WATCHDOG_STATE_FILE.exists():
            try:
                with open(WATCHDOG_STATE_FILE, 'r') as f:
                    data = json.load(f)
                    self.consecutive_negative_checks = data.get("negative_count", 0)
                    self.consecutive_positive_checks = data.get("positive_count", 0)
            except:
                self.consecutive_negative_checks = 0
                self.consecutive_positive_checks = 0

    def _save_state(self):
        WATCHDOG_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(WATCHDOG_STATE_FILE, 'w') as f:
            json.dump({
                "negative_count": self.consecutive_negative_checks,
                "positive_count": self.consecutive_positive_checks
            }, f)

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
        try:
            raw_24h = struct.unpack_from("<q", data, LAST_24H_AVG_FUNDING_RATE_OFFSET)[0]
            rate_24h = raw_24h / FUNDING_RATE_PRECISION
        except:
             pass 
        
        return rate_decimal

    async def check_health(self, simulate: bool = False) -> bool:
        """
        Single check loop. Returns True if UNWIND TRIGGERED.
        """
        async with AsyncClient(self.rpc_url) as client:
            current_rate = await self.get_funding_rate(client)
            
            # Convert to APR for display
            apr = current_rate * 24 * 365 * 100
            
            Logger.info(f"Funding Check: Rate = {current_rate:.8f}/hr ({apr:.2f}% APR)")
            
            # Logic: If rate < THRESHOLD, increment strike counter
            if current_rate < NEGATIVE_THRESHOLD:
                self.consecutive_negative_checks += 1
                self.consecutive_positive_checks = 0 # Reset positive streak
                Logger.warning(f"⚠️ NEGATIVE FUNDING DETECTED ({current_rate:.6f} < {NEGATIVE_THRESHOLD})! Streak: {self.consecutive_negative_checks}/4")
            else:
                if self.consecutive_negative_checks > 0:
                    Logger.success("✅ Funding ok (above threshold). Resetting negative counter.")
                self.consecutive_negative_checks = 0
                
            # Log positive streak for re-entry context (even if in Active mode)
            if current_rate > POSITIVE_THRESHOLD:
                self.consecutive_positive_checks += 1
            else:
                self.consecutive_positive_checks = 0
            
            self._save_state()
            
            # TRIGGER UNWIND?
            if self.consecutive_negative_checks >= 4:
                Logger.critical("🚨 CRITICAL: NEGATIVE FUNDING PERSISTED FOR 1 HOUR. TRIGGERING UNWIND!")
                await self.unwind_position(client, simulate=simulate)
                self.consecutive_negative_checks = 0 
                self._save_state()
                return True # Signal Unwind
            
            return False

    async def check_re_entry_opportunity(self) -> bool:
        """
        Checks if funding is consistently positive to justify Re-Entry.
        Returns True if RE-ENTRY RECOMMENDED.
        """
        async with AsyncClient(self.rpc_url) as client:
            current_rate = await self.get_funding_rate(client)
            apr = current_rate * 24 * 365 * 100
            
            Logger.info(f"Waitlist Monitor: Funding = {current_rate:.8f}/hr ({apr:.2f}% APR)")
            
            if current_rate > POSITIVE_THRESHOLD:
                self.consecutive_positive_checks += 1
                Logger.success(f"📈 POSITIVE FUNDING DETECTED! Streak: {self.consecutive_positive_checks}/2")
            else:
                if self.consecutive_positive_checks > 0:
                    Logger.info("📉 Funding dropped below threshold. Resetting re-entry counter.")
                self.consecutive_positive_checks = 0
                
            self._save_state()
            
            if self.consecutive_positive_checks >= 2:
                Logger.success("🚀 FUNDING STABLE POSITIVE. RECOMMENDING RE-ENTRY!")
                self.consecutive_positive_checks = 0 # Reset on trigger
                self._save_state()
                return True
                
            return False

    async def unwind_position(self, client: AsyncClient, simulate: bool = False):
        """
        Emergency Unwind Protocol:
        1. Close Drift Short (Reduce-Only)
        2. Sell Spot SOL (Jupiter Swap)
        """
        Logger.section("🛑 EMERGENCY UNWIND INITIATED 🛑")
        
        if simulate:
            Logger.info("[SIMULATION] Would close Drift Perp and Sell Spot SOL.")
            return
        private_key = os.getenv("SOLANA_PRIVATE_KEY") or os.getenv("PHANTOM_PRIVATE_KEY")
        if not private_key:
            Logger.error("No private key for unwind!")
            return

        from src.delta_neutral.drift_order_builder import DriftOrderBuilder, PositionDirection
        from solders.transaction import VersionedTransaction
        from solders.message import MessageV0
        from solders.keypair import Keypair
        from solana.rpc.types import TxOpts
        from solana.rpc.commitment import Confirmed
        from src.shared.execution.swapper import JupiterSwapper
        from src.shared.execution.wallet import WalletManager
        
        secret_bytes = base58.b58decode(private_key)
        keypair = Keypair.from_bytes(secret_bytes)
        wallet_pk = keypair.pubkey()
        
        # -------------------------------------------------------------
        # STEP 1: CLOSE DRIFT SHORT
        # -------------------------------------------------------------
        
        # Check current position
        rebalancer = AutoRebalancer() 
        status = await rebalancer.check_and_rebalance(simulate=True)
        perp_size = status.get('perp_sol', 0)
        
        Logger.info(f"[UNWIND] Current Drift Position: {perp_size} SOL")
        
        if perp_size < 0:
            Logger.info("[UNWIND] Closing Drift Short...")
            builder = DriftOrderBuilder(wallet_pk)
            close_size = abs(perp_size)
            
            # Build LONG order to close SHORT
            # reduce_only=True is CRITICAL
            ixs = builder.build_order_instruction(
                "SOL-PERP", 
                close_size, 
                direction=PositionDirection.LONG, 
                reduce_only=True
            )
            # Make it a list if not already (builder usually returns list)
            if not isinstance(ixs, list):
                ixs = [ixs]
                
            bh_resp = await client.get_latest_blockhash()
            msg = MessageV0.try_compile(
                payer=wallet_pk,
                instructions=ixs,
                address_lookup_table_accounts=[],
                recent_blockhash=bh_resp.value.blockhash
            )
            tx = VersionedTransaction(msg, [keypair])
            
            try:
                # Execute Close
                resp = await client.send_transaction(tx, opts=TxOpts(skip_confirmation=False, preflight_commitment=Confirmed))
                Logger.success(f"[UNWIND] ✅ Drift Close Tx Sent: {resp.value}")
                await client.confirm_transaction(resp.value, commitment=Confirmed)
                
            except Exception as e:
                Logger.error(f"[UNWIND] ❌ Drift Close Failed: {e}")
                return # Abort if Drift fails - we don't want to be naked long spot
        else:
            Logger.info("[UNWIND] No Short Position to close (or already positive/zero).")

        # -------------------------------------------------------------
        # STEP 2: SELL SPOT SOL (Jupiter)
        # -------------------------------------------------------------
        Logger.info("[UNWIND] Selling Spot SOL...")
        
        # Check balance
        sol_balance = await client.get_balance(wallet_pk)
        current_sol = sol_balance.value / 1e9
        reserved_gas = 0.02
        sell_amount = current_sol - reserved_gas
        
        if sell_amount < 0.01:
            Logger.warning(f"[UNWIND] Spot balance ({current_sol}) too low to sell (min 0.01). Skipping.")
            return

        Logger.info(f"[UNWIND] Swapping {sell_amount:.4f} SOL to USDC...")
        
        try:
            # Init Swapper
            wallet_manager = WalletManager() # Should load env keys
            swapper = JupiterSwapper(wallet_manager)
            
            # USDC Mint: EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
            USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            SOL_MINT = "So11111111111111111111111111111111111111112"
            
            # Execute Swap
            # Correct API: execute_swap(direction, amount_usd, reason, target_mint=..., override_atomic_amount=...)
            amount_atomic = int(sell_amount * 1_000_000_000)
            
            sig = swapper.execute_swap(
                direction="SELL",
                amount_usd=0, # Use override
                reason="Emergency Unwind",
                target_mint=SOL_MINT,
                override_atomic_amount=amount_atomic
            )
            
            if sig:
                Logger.success(f"[UNWIND] ✅ Spot Sold: {sig}")
            else:
                Logger.error("[UNWIND] ❌ Spot Sell Failed (No signature)")
                
        except Exception as e:
            Logger.error(f"[UNWIND] ❌ Jupiter Swap Error: {e}")
            
        Logger.section("🛑 UNWIND SEQUENCE COMPLETE 🛑")

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
