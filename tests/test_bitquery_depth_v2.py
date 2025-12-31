import asyncio
import json
import websockets
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("BITQUERY_API_KEY")
# Try passing token in URL
WS_URL = f"wss://streaming.bitquery.io/graphql?token={API_KEY}"

QUERY = """
subscription {
  Solana {
    OrderBook(
      marketAddress: "8BnEgHoWFysVcuFFX7QztDmzuH8r5ZFvyP3sYwn1XTh6" 
    ) {
      Market {
        MarketAddress
      }
      Bids {
        Price
        Amount
      }
      Asks {
        Price
        Amount
      }
    }
  }
}
"""


async def test_bitquery_depth():
    print("🔌 Connecting to Bitquery (URL Auth)...")

    # Remove header auth, use URL only
    async with websockets.connect(WS_URL, subprotocols=["graphql-transport-ws"]) as ws:
        # Handshake
        await ws.send(json.dumps({"type": "connection_init"}))
        ack = await ws.recv()
        print(f"🤝 Handshake: {ack}")

        # Subscribe
        msg = {"id": "1", "type": "subscribe", "payload": {"query": QUERY}}
        await ws.send(json.dumps(msg))
        print("📡 Subscription sent...")

        # Listen
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < 10:
            try:
                res = await asyncio.wait_for(ws.recv(), timeout=2.0)
                data = json.loads(res)
                if data.get("type") == "next":
                    payload = data["payload"]["data"]["Solana"]["OrderBook"][0]
                    print("✅ DEPTH RECEIVED!")
                    print(f"   Bids: {len(payload.get('Bids', []))} levels")
                    return
                elif data.get("type") == "error":
                    print(f"❌ Error: {data}")
            except asyncio.TimeoutError:
                print(".")

    print("❌ No depth data received in 10s.")


if __name__ == "__main__":
    if not API_KEY:
        print("❌ SKIPPING: No BITQUERY_API_KEY")
    else:
        asyncio.run(test_bitquery_depth())
