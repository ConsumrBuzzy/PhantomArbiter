import asyncio
from solana.rpc.async_api import AsyncClient
from driftpy.drift_client import DriftClient
from driftpy.wallet import Wallet
from driftpy.types import OrderParams, OrderType, MarketType, PositionDirection, PostOnlyParam
from solders.keypair import Keypair

async def main():
    # Use public RPC
    connection = AsyncClient("https://api.mainnet-beta.solana.com")
    wallet = Wallet(Keypair())
    client = DriftClient(connection, wallet, "mainnet")
    
    # We must subscribe to load the program ID and other state
    await client.subscribe()
    
    # Generic market order params
    params = OrderParams(
        order_type=OrderType.Market(),
        market_type=MarketType.Perp(),
        direction=PositionDirection.Long(),
        user_order_id=0,
        base_asset_amount=1000000000, # 1 unit
        price=0,
        market_index=0, # SOL-PERP
        reduce_only=False,
        post_only=PostOnlyParam.None_(),
        immediate_or_cancel=False,
        max_ts=None,
        trigger_price=None,
        trigger_condition=None,
        oracle_price_offset=None,
        auction_duration=None,
        auction_start_price=None,
        auction_end_price=None
    )
    
    ix = await client.get_place_perp_order_ix(params)
    
    print("\n--- driftpy place_perp_order Account Sequence ---")
    for i, acc in enumerate(ix.accounts):
        role = "Writable" if acc.is_writable else "ReadOnly"
        signer = "Signer" if acc.is_signer else ""
        print(f"{i}: {acc.pubkey} ({role} {signer})")

    await client.unsubscribe()

if __name__ == "__main__":
    asyncio.run(main())
