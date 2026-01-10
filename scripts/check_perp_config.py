import asyncio
import os
from dotenv import load_dotenv
from solana.rpc.async_api import AsyncClient
from driftpy.drift_client import DriftClient
from driftpy.account_subscription_config import AccountSubscriptionConfig
from driftpy.keypair import load_keypair
import base58

async def inspect_drift_markets():
    load_dotenv()
    rpc_url = os.getenv("HELIUS_RPC_URL") or os.getenv("SOLANA_RPC_URL") or "https://api.mainnet-beta.solana.com"
    
    async with AsyncClient(rpc_url) as connection:
        # We don't need a real wallet just to read accounts
        drift_client = DriftClient(connection, None, "mainnet-beta")
        
        print("\n--- Drift Perp Markets (Index 0-5) ---")
        for i in range(6):
            market = await drift_client.get_perp_market_account(i)
            if market:
                print(f"Index {i}: {bytes(market.name).decode().strip()}")
                print(f"  Oracle: {market.oracle}")
                print(f"  Oracle Source: {market.oracle_source}")
            else:
                print(f"Index {i}: Not Found")

if __name__ == "__main__":
    asyncio.run(inspect_drift_markets())
