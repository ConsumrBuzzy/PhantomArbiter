from src.shared.execution.pool_index import PoolIndex
import asyncio


async def check():
    index = PoolIndex()
    # Force load from DB

    print(f"Index loaded {len(index._pool_cache)} pairs")

    pairs = ["WIF/USDC", "JUP/USDC", "FARTCOIN/USDC"]
    for p in pairs:
        tA, tB = p.split("/")
        pools = index.get_pools(tA, tB)
        if pools:
            print(
                f"{p}: CLMM={pools.raydium_clmm_pool}, STD={pools.raydium_standard_pool}, ORCA={pools.orca_pool}"
            )
        else:
            print(f"{p}: NOT FOUND")


if __name__ == "__main__":
    asyncio.run(check())
