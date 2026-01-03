import asyncio
import os
import aiohttp
import websockets
import logging
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Verifier")

async def test_helius():
    """Test Helius WebSocket Connection."""
    logger.info("--- Testing Helius WSS ---")
    api_key = os.getenv("HELIUS_API_KEY")
    if not api_key:
        logger.warning("⚠️ HELIUS_API_KEY not found in .env")
        return False
    
    url = f"wss://mainnet.helius-rpc.com/?api-key={api_key}"
    try:
        async with websockets.connect(url) as ws:
            logger.info("✅ Helius WSS Connected!")
            await ws.ping()
            logger.info("✅ Helius Ping Successful")
            return True
    except Exception as e:
        logger.error(f"❌ Helius Connection Failed: {e}")
        return False

async def test_birdeye():
    """Test Birdeye API."""
    logger.info("\n--- Testing Birdeye API ---")
    api_key = os.getenv("BIRDEYE_API_KEY")
    if not api_key:
        logger.warning("⚠️ BIRDEYE_API_KEY not found in .env")
        return False

    url = "https://public-api.birdeye.so/defi/multi_price?list_address=So11111111111111111111111111111111111111112"
    headers = {"X-API-KEY": api_key, "x-chain": "solana", "accept": "application/json"}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success"):
                        logger.info("✅ Birdeye API Connected & Auth Working")
                        return True
                    else:
                        logger.error(f"❌ Birdeye Logic Error: {data}")
                else:
                    logger.error(f"❌ Birdeye HTTP {resp.status}")
    except Exception as e:
        logger.error(f"❌ Birdeye Attempt Failed: {e}")
    return False

async def test_dexscreener():
    """Test DexScreener (No Key)."""
    logger.info("\n--- Testing DexScreener API ---")
    # Test valid token (SOL)
    url = "https://api.dexscreener.com/latest/dex/tokens/So11111111111111111111111111111111111111112"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("pairs"):
                        logger.info("✅ DexScreener Reachable & Returning Data")
                        return True
                    else:
                        logger.warning("⚠️ DexScreener reachable but no pairs for SOL (Wait, really?)")
                else:
                    logger.error(f"❌ DexScreener HTTP {resp.status}")
    except Exception as e:
        logger.error(f"❌ DexScreener Failed: {e}")
    return False

async def test_chainstack():
    """Test Chainstack WSS (User/Pass)."""
    logger.info("\n--- Testing Chainstack WSS ---")
    user = os.getenv("CHAINSTACK_USERNAME")
    password = os.getenv("CHAINSTACK_PASSWORD")
    ws_url = os.getenv("CHAINSTACK_WS_URL_PASS_PROTECTED")
    
    if not (user and password and ws_url):
        logger.warning("⚠️ Chainstack credentials incomplete (Optional)")
        return None

    # Construct Auth URL
    # Assuming url format wss://host.com, need wss://user:pass@host.com
    # But user might have pasted full url
    
    clean_url = ws_url.replace("wss://", "").replace("https://", "")
    auth_url = f"wss://{user}:{password}@{clean_url}"
    
    try:
        async with websockets.connect(auth_url) as ws:
            logger.info("✅ Chainstack WSS Connected!")
            return True
    except Exception as e:
        logger.error(f"❌ Chainstack Connection Failed: {e}")
        return False

async def main():
    logger.info("🚀 Starting Ingestion Connection Verification...")
    results = {
        "Helius": await test_helius(),
        "Birdeye": await test_birdeye(),
        "DexScreener": await test_dexscreener(),
        "Chainstack": await test_chainstack()
    }
    
    print("\n" + "="*30)
    print("📢 VERIFICATION REPORT")
    print("="*30)
    for service, status in results.items():
        if status is True:
            print(f"✅ {service}: OK")
        elif status is None:
            print(f"⚪ {service}: Skipped")
        else:
            print(f"❌ {service}: FAILED")
    print("="*30)

if __name__ == "__main__":
    asyncio.run(main())
