
import asyncio
import json
import websockets
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("BITQUERY_API_KEY")
WS_URL = "wss://streaming.bitquery.io/graphql"

# Query for Order Book Updates
# Based on Bitquery V2 EVM/Solana schema. 
# "Solana" -> "DEXTrades" or "OrderBook"?
# Usually it is "Solana" -> "OrderBook" for depth updates.
QUERY = """
subscription {
  Solana {
    OrderBook(
      marketAddress: "8BnEgHoWFysVcuFFX7QztDmzuH8r5ZFvyP3sYwn1XTh6" 
    ) {
      Market {
        MarketAddress
        BaseToken { Symbol }
        QuoteToken { Symbol }
      }
      Bids {
        Price
        Amount
      }
      Asks {
        Price
        Amount
      }
      Block {
        Time
      }
    }
  }
}
"""

async def test_bitquery_depth():
    print(f"🔌 Connecting to Bitquery (Key: {API_KEY[:6]}...)...")
    headers = {"X-API-KEY": API_KEY}
    
    async with websockets.connect(WS_URL, subprotocols=['graphql-transport-ws'], extra_headers=headers) as ws:
        # Handshake
        await ws.send(json.dumps({"type": "connection_init", "payload": {"token": API_KEY}}))
        ack = await ws.recv()
        print(f"🤝 Handshake: {ack}")
        
        # Subscribe
        msg = {
            "id": "1",
            "type": "subscribe",
            "payload": {"query": QUERY}
        }
        await ws.send(json.dumps(msg))
        print("📡 Subscription sent for SOL/USDC OrderBook...")
        
        # Listen for 10 seconds
        print("⏳ Listening for 10 seconds...")
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < 10:
            try:
                res = await asyncio.wait_for(ws.recv(), timeout=2.0)
                data = json.loads(res)
                if data.get("type") == "next":
                    payload = data['payload']['data']['Solana']['OrderBook'][0]
                    print(f"✅ DEPTH RECEIVED!")
                    print(f"   Bids: {len(payload.get('Bids', []))} levels")
                    print(f"   Asks: {len(payload.get('Asks', []))} levels")
                    print(f"   Top Bid: {payload['Bids'][0] if payload.get('Bids') else 'None'}")
                    return
                elif data.get("type") == "error":
                    print(f"❌ Error: {data}")
            except asyncio.TimeoutError:
                print(".")
                
    print("❌ No depth data received in 10s.")

if __name__ == "__main__":
    if not API_KEY:
        print("❌ SKIPPING: No BITQUERY_API_KEY in env")
    else:
        asyncio.run(test_bitquery_depth())
