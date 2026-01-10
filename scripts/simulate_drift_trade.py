import asyncio
import os
import struct
import base58
from dotenv import load_dotenv

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from solders.transaction import Transaction
from solana.rpc.async_api import AsyncClient

from src.delta_neutral.drift_order_builder import DriftOrderBuilder, PositionDirection, OrderType
from src.shared.system.logging import Logger

async def simulate_drift_trade():
    load_dotenv()
    
    Logger.section("DRIFT ORDER SIMULATION (Attempt #27)")
    
    # 1. Setup Environment
    rpc_url = os.getenv("HELIUS_RPC_URL") or os.getenv("SOLANA_RPC_URL") or "https://api.mainnet-beta.solana.com"
    private_key = os.getenv("SOLANA_PRIVATE_KEY") or os.getenv("PHANTOM_PRIVATE_KEY")
    
    if not private_key:
        Logger.error("No private key found in .env")
        return

    secret_bytes = base58.b58decode(private_key)
    keypair = Keypair.from_bytes(secret_bytes)
    wallet_pk = keypair.pubkey()
    
    Logger.info(f"Wallet: {wallet_pk}")
    Logger.info(f"RPC: {rpc_url[:50]}...")
    
    # 2. Build Instruction
    builder = DriftOrderBuilder(wallet_pk)
    
    # Test Parameters: 0.01 SOL SHORT
    market = "SOL-PERP"
    size = 0.01
    direction = PositionDirection.SHORT
    
    Logger.info(f"Building order: {size} {market} {direction.name}")
    
    try:
        order_ix = builder.build_order_instruction(
            market=market,
            size=size,
            direction=direction
        )
        
        Logger.info(f"Instruction Data (Hex): {order_ix.data.hex()}")
        Logger.info(f"Instruction Data Size: {len(order_ix.data)} bytes")
        
        # 3. Simulate
        async with AsyncClient(rpc_url) as client:
            # Need a recent blockhash
            recent_blockhash_resp = await client.get_latest_blockhash()
            recent_blockhash = recent_blockhash_resp.value.blockhash
            
            # Create transaction
            tx = Transaction.new_signed_with_payer(
                [order_ix],
                wallet_pk,
                [keypair],
                recent_blockhash
            )
            
            Logger.info("Simulating transaction...")
            sim_resp = await client.simulate_transaction(tx)
            
            if sim_resp.value.err:
                Logger.error(f"Simulation FAILED: {sim_resp.value.err}")
                if hasattr(sim_resp.value, 'logs') and sim_resp.value.logs:
                    for log in sim_resp.value.logs:
                        if "Program dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH" in log or "error" in log.lower():
                            Logger.error(f"  > {log}")
            else:
                Logger.success("Simulation SUCCEEDED! The 'Golden Byte' handshake is perfect.")
                Logger.info(f"Units Consumed: {sim_resp.value.units_consumed}")
                
    except Exception as e:
        Logger.error(f"Error during simulation: {str(e)}")
        import traceback
        Logger.debug(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(simulate_drift_trade())
