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
from src.shared.execution.pool_index import get_pool_index
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
    ray = RaydiumFeed()
    met = MeteoraFeed()
    
    print("\nPre-warming Pool Index (Discovery)...")
    idx = get_pool_index()
    # Force discovery for SOL/USDC
    pools = idx.get_pools("SOL", "USDC")
    print(f"Pool Discovery Result: {pools}")
    if pools:
        print(f"  Meteora: {pools.meteora_pool}")
        print(f"  Raydium: {pools.raydium_clmm_pool}")

    # Inspect Raydium Bridge Cache
    print("Bridge connection test:")
    if ray._bridge:
        print(f"  Bridge Loaded: {ray._bridge}")
    else:
        print("  Bridge Not Loaded (Lazy)")
    
    SOL_MINT = "So11111111111111111111111111111111111111112"
    USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

    print("\n--- Testing Raydium Daemon Scan (SOL/USDC) ---")
    start = time.time()
    q = ray.get_spot_price(SOL_MINT, USDC_MINT)
    lat = (time.time() - start) * 1000
    if q:
        source = getattr(q, 'source', 'Unknown')
        # RaydiumFeed doesn't explicitly set source in SpotPrice (oops), but logs it.
        # Wait, I checked code, only MeteoraFeed sets source="METEORA".
        # Raydium sets dex="RAYDIUM".
        print(f"Price: ${q.price:.4f} | Source: {q.dex} | Latency: {lat:.2f}ms")
    else:
        print("Failed to get Raydium price")

    print("\n--- Testing Meteora Daemon Scan (SOL/USDC) ---")
    start = time.time()
    q = met.get_spot_price(SOL_MINT, USDC_MINT)
    lat = (time.time() - start) * 1000
    if q:
        source = getattr(q, 'source', 'Unknown')
        print(f"Price: ${q.price:.4f} | Source: {source} | Latency: {lat:.2f}ms")
    else:
        print("Failed to get Meteora price")

    print("\nCheck logs for [RAYDIUM] 🟢 Daemon price... or [METEORA] 🟢 Daemon price...")

if __name__ == "__main__":
    test()
