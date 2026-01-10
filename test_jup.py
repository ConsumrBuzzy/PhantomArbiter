import httpx
import asyncio

async def test():
    # Try alternate endpoint
    url = "https://public.jupiterapi.com/quote?inputMint=So11111111111111111111111111111111111111112&outputMint=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v&amount=100000000"
    print(f"Testing {url}...")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            print(f"Status: {resp.status_code}")
            print(f"Body: {resp.text[:200]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())
