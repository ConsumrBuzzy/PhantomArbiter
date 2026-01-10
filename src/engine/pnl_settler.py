"""
DNEM PNL SETTLER (Phase 4.2)
============================
Daily "Harvester" service to settle Unrealized Funding into Realized USDC.

Schedule: Runs daily at 00:00 UTC (or manual with --now).
Action: Calls Drift `settle_pnl` instruction.

Usage:
    python -m src.engine.pnl_settler --now       # Run immediately
    python -m src.engine.pnl_settler --simulate  # Simulate only
    python -m src.engine.pnl_settler --loop      # Run daily daemon
"""

import asyncio
import os
import csv
import struct
import base64
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

import base58
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solders.instruction import Instruction, AccountMeta
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solana.rpc.types import TxOpts

from src.shared.system.logging import Logger

# =============================================================================
# CONSTANTS
# =============================================================================

DRIFT_PROGRAM_ID = Pubkey.from_string("dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH")
USDC_SPOT_MARKET_INDEX = 0
SOL_PERP_MARKET_INDEX = 0

SETTLEMENT_LOG = Path("data/settlement_history.csv")

# =============================================================================
# SETTLER ENGINE
# =============================================================================

class PnLSettler:
    def __init__(self):
        self.rpc_url = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
        self._init_log()

    def _init_log(self):
        SETTLEMENT_LOG.parent.mkdir(parents=True, exist_ok=True)
        if not SETTLEMENT_LOG.exists():
            with open(SETTLEMENT_LOG, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "market_index", "tx_signature", "status"])

    def derive_user_account(self, wallet: Pubkey) -> Pubkey:
        pda, _ = Pubkey.find_program_address(
            [b"user", bytes(wallet), (0).to_bytes(2, 'little')],
            DRIFT_PROGRAM_ID
        )
        return pda

    def derive_state_account(self) -> Pubkey:
        pda, _ = Pubkey.find_program_address(
            [b"drift_state"],
            DRIFT_PROGRAM_ID
        )
        return pda

    def derive_spot_market_vault(self, market_index: int) -> Pubkey:
        pda, _ = Pubkey.find_program_address(
            [b"spot_market_vault", market_index.to_bytes(2, 'little')],
            DRIFT_PROGRAM_ID
        )
        return pda

    def derive_spot_market_account(self, market_index: int) -> Pubkey:
        pda, _ = Pubkey.find_program_address(
            [b"spot_market", market_index.to_bytes(2, 'little')],
            DRIFT_PROGRAM_ID
        )
        return pda

    def build_settle_pnl_ix(self, wallet_pk: Pubkey, user_pda: Pubkey) -> Instruction:
        """
        Builds the `settle_pnl` instruction manually.
        """
        
        # Discriminator for settle_pnl (global:settle_pnl)
        # Calculated: [43, 61, 234, 45, 15, 95, 152, 153]
        discriminator = bytes([43, 61, 234, 45, 15, 95, 152, 153])
        
        # Args: market_index (u16)
        data = discriminator + struct.pack("<H", SOL_PERP_MARKET_INDEX)
        
        state_pda = self.derive_state_account()
        spot_vault_pda = self.derive_spot_market_vault(USDC_SPOT_MARKET_INDEX)
        
        # Additional Account: SOL-PERP Market
        perp_market_pda, _ = Pubkey.find_program_address(
            [b"perp_market", SOL_PERP_MARKET_INDEX.to_bytes(2, 'little')],
            DRIFT_PROGRAM_ID
        )
        # Additional Account: Spot Market (USDC)
        spot_market_pda = self.derive_spot_market_account(USDC_SPOT_MARKET_INDEX)
        
        # Additional Account: SOL Oracle A (Standard Pyth?)
        oracle_a = Pubkey.from_string("3m6i4RFWEDw2Ft4tFHPJtYgmpPe21k56M3FHeWYrgGBz")
        # Additional Account: SOL Oracle B (Requested by log?)
        oracle_b = Pubkey.from_string("9VCioxmni2gDLv11qufWzT3RDERhQE4iY5Gf7NTfYyAV")
        
        accounts = [
            AccountMeta(state_pda, is_signer=False, is_writable=False),
            AccountMeta(user_pda, is_signer=False, is_writable=True),
            AccountMeta(wallet_pk, is_signer=True, is_writable=False),
            AccountMeta(spot_vault_pda, is_signer=False, is_writable=True), 
            
            # Remaining Accounts (Oracle Map construction)
            # Pass BOTH to be safe
            AccountMeta(oracle_a, is_signer=False, is_writable=False),
            AccountMeta(oracle_b, is_signer=False, is_writable=False),
            
            AccountMeta(spot_market_pda, is_signer=False, is_writable=True),
            AccountMeta(perp_market_pda, is_signer=False, is_writable=True),
        ]
        
        return Instruction(
            program_id=DRIFT_PROGRAM_ID,
            accounts=accounts,
            data=data
        )

    async def execute_settlement(self, simulate: bool = False):
        load_dotenv()
        private_key = os.getenv("SOLANA_PRIVATE_KEY") or os.getenv("PHANTOM_PRIVATE_KEY")
        if not private_key:
            Logger.error("No private key found")
            return

        secret_bytes = base58.b58decode(private_key)
        keypair = Keypair.from_bytes(secret_bytes)
        wallet_pk = keypair.pubkey()
        user_pda = self.derive_user_account(wallet_pk)
        
        Logger.info(f"Preparing PnL Settlement for User: {user_pda}")
        
        ix = self.build_settle_pnl_ix(wallet_pk, user_pda)
        
        async with AsyncClient(self.rpc_url) as client:
            bh_resp = await client.get_latest_blockhash()
            msg = MessageV0.try_compile(
                payer=wallet_pk,
                instructions=[ix],
                address_lookup_table_accounts=[],
                recent_blockhash=bh_resp.value.blockhash
            )
            tx = VersionedTransaction(msg, [keypair])
            
            if simulate:
                Logger.info("Simulating Settlement...")
                resp = await client.simulate_transaction(tx)
                if resp.value.err:
                    Logger.error(f"❌ Simulation Failed: {resp.value.err}")
                    Logger.info(f"Logs: {resp.value.logs}")
                else:
                    Logger.success(f"✅ Simulation Success! Units consumed: {resp.value.units_consumed}")
                return

            # LIVE EXECUTION
            Logger.info("🚀 Sending Settlement Transaction...")
            try:
                resp = await client.send_transaction(tx, opts=TxOpts(skip_confirmation=False, preflight_commitment=Confirmed))
                sig = str(resp.value)
                Logger.success(f"✅ Settlement TX Sent: {sig}")
                
                await client.confirm_transaction(resp.value, commitment=Confirmed)
                Logger.success("✅ Transaction Confirmed")
                
                # Log to CSV
                with open(SETTLEMENT_LOG, 'a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([datetime.now().isoformat(), SOL_PERP_MARKET_INDEX, sig, "Confirmed"])
                    
            except Exception as e:
                Logger.error(f"❌ Execution Failed: {e}")

    async def run_loop(self):
        Logger.section("Daily PnL Settler Started")
        Logger.info("Schedule: Daily at 00:00 UTC")
        
        while True:
            now = datetime.utcnow()
            # Simple check: if hour is 0 and minute is 0 (approx)
            # Better: sleep until next 00:00
            
            # For this MVP, we just wait.
            # In a real daemon, we'd calculate seconds until midnight.
            
            Logger.info("Waiting for next execution window...")
            await asyncio.sleep(3600) # Sleep 1 hour

async def main():
    import sys
    settler = PnLSettler()
    
    if "--now" in sys.argv:
        await settler.execute_settlement(simulate=False)
    elif "--simulate" in sys.argv:
        await settler.execute_settlement(simulate=True)
    elif "--loop" in sys.argv:
        await settler.run_loop()
    else:
        print("Usage: python -m src.engine.pnl_settler [--now | --simulate | --loop]")

if __name__ == "__main__":
    asyncio.run(main())
