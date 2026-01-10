import asyncio
import os
from dotenv import load_dotenv
from solana.rpc.async_api import AsyncClient
from driftpy.drift_client import DriftClient
from anchorpy import Wallet
from solders.keypair import Keypair

async def inspect_drift_markets():
    rpc_url = "https://api.mainnet-beta.solana.com"
    print(f"Using RPC: {rpc_url}")
    
    async with AsyncClient(rpc_url) as connection:
        wallet = Wallet(Keypair())
        drift_client = DriftClient(connection, wallet, "mainnet")
        
        await drift_client.subscribe()
        
        print("\n--- Drift Perp Markets ---")
        for i in range(5):
            try:
                market = drift_client.get_perp_market_account(i)
                if market:
                    name = bytes(market.name).decode().strip()
                    print(f"Index {i}: {name}")
                    # In driftpy, oracle and oracle_source are in AMM
                    print(f"  Oracle: {market.amm.oracle}")
                    print(f"  Oracle Source: {market.amm.oracle_source}")
                else:
                    print(f"Index {i}: Not cached")
            except Exception as e:
                print(f"Index {i}: Error: {e}")
        
        await drift_client.unsubscribe()

if __name__ == "__main__":
    asyncio.run(inspect_drift_markets())
