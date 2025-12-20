import sys
import os
import time

sys.path.append(os.getcwd())

try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

from src.shared.system.logging import Logger
from src.shared.feeds.raydium_feed import RaydiumFeed
from src.shared.feeds.meteora_feed import MeteoraFeed
from src.shared.feeds.orca_feed import OrcaFeed
from src.shared.execution.pool_index import get_pool_index
from src.shared.execution.pool_registry import get_pool_registry
import logging

# Configure logger to stdout
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
logger.handlers = [handler]

# Also patch src.shared.system.logging.Logger if it's a wrapper
from src.shared.system.logging import Logger as SysLogger
SysLogger.info = logger.info
SysLogger.debug = logger.debug
SysLogger.warning = logger.warning
SysLogger.error = logger.error

def test():
    print("=" * 60)
    print("Daemon Scanning Verification")
    print("=" * 60)

    print("Initializing Feeds...")
    raydium = RaydiumFeed()
    meteora = MeteoraFeed()
    orca = OrcaFeed()
    
    print("\nPopulating Pool Registry (Mint -> Symbol)...")
    reg = get_pool_registry()
    SOL_MINT = "So11111111111111111111111111111111111111112"
    USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    
    reg.update_coverage("SOL", SOL_MINT, has_raydium=True, has_meteora=True, has_orca=True)
    reg.update_coverage("USDC", USDC_MINT, has_raydium=True, has_meteora=True, has_orca=True)
    
    print("\nPre-warming Pool Index (Discovery)...")
    idx = get_pool_index()
    
    # CLEAR STALE CACHE to test new discovery logic
    if "SOL/USDC" in idx._pool_cache:
        del idx._pool_cache["SOL/USDC"]
    if "USDC/SOL" in idx._pool_cache:
        del idx._pool_cache["USDC/SOL"]
        
    # Force discovery for SOL/USDC
    pools = idx.get_pools("SOL", "USDC")
    print(f"Pool Discovery Result: {pools}")
    if pools:
        print(f"  Meteora: {pools.meteora_pool}")
        print(f"  Raydium: {pools.raydium_clmm_pool}")
        print(f"  Orca: {pools.orca_whirlpool_pool}")

    # Inspect Bridge Caches
    print("Bridge connection test:")
    if raydium._bridge:
        print(f"  Raydium Bridge Loaded: {raydium._bridge}")
    else:
        print("  Raydium Bridge Not Loaded (Lazy)")
    
    if meteora._bridge:
        print(f"  Meteora Bridge Loaded: {meteora._bridge}")
    else:
        print("  Meteora Bridge Not Loaded (Lazy)")

    if orca._bridge:
        print(f"  Orca Bridge Loaded: {orca._bridge}")
    else:
        print("  Orca Bridge Not Loaded (Lazy)")
    
    SOL_MINT = "So11111111111111111111111111111131111111112"
    USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

    print("\n--- Testing Raydium Daemon Scan (SOL/USDC) ---")
    t0 = time.time()
    price = raydium.get_spot_price(SOL_MINT, USDC_MINT)
    t1 = time.time()
    if price:
        # RaydiumFeed doesn't explicitly set source in SpotPrice (oops), but logs it.
        # Wait, I checked code, only MeteoraFeed sets source="METEORA".
        # Raydium sets dex="RAYDIUM".
        print(f"Price: ${price.price:.4f} | Source: {price.dex} | Latency: {(t1-t0)*1000:.2f}ms")
    else:
        print("Raydium Scan Failed")

    print("\n--- Testing Meteora Daemon Scan (SOL/USDC) ---")
    t0 = time.time()
    price = meteora.get_spot_price(SOL_MINT, USDC_MINT)
    t1 = time.time()
    if price:
        print(f"Price: ${price.price:.4f} | Source: {price.source} | Latency: {(t1-t0)*1000:.2f}ms")
    else:
        print("Meteora Scan Failed")

    print("\n--- Testing Orca Daemon Scan (SOL/USDC) ---")
    t0 = time.time()
    price = orca.get_spot_price(SOL_MINT, USDC_MINT)
    t1 = time.time()
    if price:
        print(f"Price: ${price.price:.4f} | Source: {price.source} | Latency: {(t1-t0)*1000:.2f}ms")
    else:
        print("Orca Scan Failed")

    print("\nCheck logs for [RAYDIUM] 🟢 Daemon price... or [METEORA] 🟢 Daemon price... or [ORCA] 🟢 Daemon price...")

if __name__ == "__main__":
    test()
