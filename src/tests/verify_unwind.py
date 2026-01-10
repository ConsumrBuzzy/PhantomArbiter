"""
SIMULATION: Unwind Protocol Verification
========================================
Simulates the emergency unwind sequence without executing it.

Checks:
1. Drift Close Order (Reduce-Only Market Long) construction
2. Jupiter Swap (SOL -> USDC) construction
3. Transaction compilation and simulation response

Usage:
    python -m src.tests.verify_unwind
"""

import asyncio
import os
import struct
from dotenv import load_dotenv

import base58
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed

from src.shared.system.logging import Logger
from src.delta_neutral.drift_order_builder import DriftOrderBuilder, PositionDirection
from src.shared.execution.swapper import JupiterSwapper
from src.shared.execution.wallet import WalletManager

async def simulate_unwind():
    load_dotenv()
    Logger.section("SIMULATING UNWIND PROTOCOL")
    
    # 1. Setup
    rpc_url = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
    wallet_manager = WalletManager()
    
    # Mock position size for simulation
    mock_short_size = 0.1
    mock_spot_balance = 0.12
    
    Logger.info(f"Mock State: Short {mock_short_size} SOL-PERP | Spot {mock_spot_balance} SOL")
    
    async with AsyncClient(rpc_url) as client:
        
        # ---------------------------------------------------------
        # 1. DRIFT CLOSE SIMULATION
        # ---------------------------------------------------------
        Logger.info("[SIM] Building Drift Close Order...")
        
        builder = DriftOrderBuilder(wallet_manager.keypair.pubkey())
        ixs = builder.build_order_instruction(
            "SOL-PERP",
            mock_short_size,
            direction=PositionDirection.LONG,
            reduce_only=True
        )
        if not isinstance(ixs, list):
            ixs = [ixs]
            
        bh_resp = await client.get_latest_blockhash()
        
        msg = MessageV0.try_compile(
            payer=wallet_manager.keypair.pubkey(),
            instructions=ixs,
            address_lookup_table_accounts=[],
            recent_blockhash=bh_resp.value.blockhash
        )
        tx = VersionedTransaction(msg, [wallet_manager.keypair])
        
        sim_resp = await client.simulate_transaction(tx)
        
        if sim_resp.value.err:
            Logger.error(f"[SIM] Drift Close Simulation Limit: {sim_resp.value.err}")
            # Expected error: InsufficientCollateral or trivial error since we are mocking size
            # But the BUILDING process is what we care about here
        else:
            Logger.success("[SIM] Drift Close Simulation OK")
            
        # ---------------------------------------------------------
        # 2. JUPITER SWAP SIMULATION
        # ---------------------------------------------------------
        Logger.info("[SIM] Building Jupiter Spot Swap...")
        
        swapper = JupiterSwapper(wallet_manager)
        USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        SOL_MINT = "So11111111111111111111111111111111111111112"
        
        sell_amount = mock_spot_balance - 0.02
        amount_atomic = int(sell_amount * 1_000_000_000)
        
        try:
            # 1. Get Quote
            Logger.info(f"[SIM] Getting Quote for {sell_amount:.4f} SOL...")
            quote = await swapper.get_quote(
                input_mint=SOL_MINT,
                output_mint=USDC_MINT,
                amount=amount_atomic,
                slippage=50
            )
            
            if not quote or "outAmount" not in quote:
                Logger.error(f"[SIM] Quote failed: {quote}")
                return

            Logger.success(f"[SIM] Quote Received: {int(quote['outAmount'])/1e6} USDC")

            # 2. Get Instructions
            ixs = await swapper.get_swap_instructions(quote)
            
            if not ixs:
                Logger.error("[SIM] No instructions returned from Jupiter")
                return

            Logger.success(f"[SIM] Received {len(ixs)} instructions from Jupiter")
            
            # 3. Simulate Transaction
            bh_resp = await client.get_latest_blockhash()
            msg = MessageV0.try_compile(
                payer=wallet_manager.keypair.pubkey(),
                instructions=ixs,
                address_lookup_table_accounts=[],
                recent_blockhash=bh_resp.value.blockhash
            )
            tx = VersionedTransaction(msg, [wallet_manager.keypair])
            
            sim_resp = await client.simulate_transaction(tx)
            
            if sim_resp.value.err:
                Logger.error(f"[SIM] Jupiter Simulation Error: {sim_resp.value.err}")
            else:
                Logger.success(f"[SIM] Jupiter Swap Simulation OK (Consumed {sim_resp.value.units_consumed} CUs)")
                
        except Exception as e:
            Logger.error(f"[SIM] Jupiter Simulation Exception: {e}")

if __name__ == "__main__":
    asyncio.run(simulate_unwind())
