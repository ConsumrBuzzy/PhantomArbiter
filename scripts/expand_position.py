"""
DNEM Position Expansion Script (Short Only)
============================================
Expands the perp short from -0.01 SOL to -0.10 SOL.

Since you already have ~$5 USDC in Drift, we'll just expand the short.
If margin is insufficient, Drift will reject.
"""

import asyncio
import os
import base58
from dotenv import load_dotenv

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solana.rpc.types import TxOpts

from src.delta_neutral.drift_order_builder import DriftOrderBuilder, PositionDirection
from src.shared.system.logging import Logger


async def main():
    load_dotenv()
    
    Logger.section("POSITION EXPANSION: Increase Short to -0.10 SOL")
    
    # Load wallet
    private_key = os.getenv("SOLANA_PRIVATE_KEY") or os.getenv("PHANTOM_PRIVATE_KEY")
    if not private_key:
        Logger.error("No private key found")
        return
    
    secret_bytes = base58.b58decode(private_key)
    keypair = Keypair.from_bytes(secret_bytes)
    wallet_pk = keypair.pubkey()
    
    Logger.info(f"Wallet: {wallet_pk}")
    
    rpc_url = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
    
    async with AsyncClient(rpc_url) as client:
        # -----------------------------------------------------------------
        # Expand Short by 0.09 SOL (current: -0.01, target: -0.10)
        # -----------------------------------------------------------------
        Logger.info("Current Position: -0.01 SOL-PERP")
        Logger.info("Expansion Size:   -0.09 SOL-PERP")
        Logger.info("Target Position:  -0.10 SOL-PERP")
        Logger.info("")
        
        builder = DriftOrderBuilder(wallet_pk)
        expansion_size = 0.09  # Additional 0.09 SOL short
        
        # Build short order instruction
        short_ixs = builder.build_short_order("SOL-PERP", expansion_size)
        
        Logger.info(f"Instruction Data: {short_ixs[0].data.hex()}")
        Logger.info(f"Accounts: {len(short_ixs[0].accounts)}")
        
        # Get blockhash
        bh_resp = await client.get_latest_blockhash()
        blockhash = bh_resp.value.blockhash
        
        msg = MessageV0.try_compile(
            payer=wallet_pk,
            instructions=short_ixs,
            address_lookup_table_accounts=[],
            recent_blockhash=blockhash,
        )
        
        tx = VersionedTransaction(msg, [keypair])
        
        # First simulate to check margin
        Logger.info("Simulating expansion...")
        sim_resp = await client.simulate_transaction(tx)
        
        if sim_resp.value.err:
            Logger.error(f"Simulation failed: {sim_resp.value.err}")
            if sim_resp.value.logs:
                for log in sim_resp.value.logs:
                    if "Error" in log or "error" in log.lower():
                        Logger.error(f"  > {log}")
            Logger.warning("")
            Logger.warning("This likely means insufficient margin in Drift account.")
            Logger.warning("You may need to deposit more USDC to Drift first.")
            return
        
        Logger.success(f"Simulation OK! Units: {sim_resp.value.units_consumed}")
        
        # Execute for real
        Logger.info("Sending expansion transaction...")
        opts = TxOpts(skip_confirmation=False, preflight_commitment=Confirmed)
        resp = await client.send_transaction(tx, opts=opts)
        
        short_sig = resp.value
        Logger.info(f"Tx: {short_sig}")
        
        await client.confirm_transaction(short_sig, commitment=Confirmed)
        Logger.success("✅ Expansion CONFIRMED!")
        
        # -----------------------------------------------------------------
        # Summary
        # -----------------------------------------------------------------
        Logger.section("EXPANSION COMPLETE")
        Logger.info("Previous Position: -0.01 SOL-PERP")
        Logger.info("New Position:      -0.10 SOL-PERP (~$15)")
        Logger.info("")
        Logger.info("Run 'python scripts/check_hedge_health.py' to verify!")


if __name__ == "__main__":
    asyncio.run(main())
