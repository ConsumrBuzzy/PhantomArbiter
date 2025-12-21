
import asyncio
import json
import logging
import ssl
import requests
from typing import Callable, Optional, List
import websockets

from config.settings import Settings
from src.shared.system.logging import Logger

class BitqueryAdapter:
    """
    V64.0 / V72.0: Bitquery GraphQL Adapter.
    
    V64.0: WebSocket streaming for real-time market data.
    V72.0: Added REST GraphQL for First 100 Buyers (Flash Audit).
    """
    
    WS_URL = "wss://streaming.bitquery.io/graphql"
    REST_URL = "https://streaming.bitquery.io/graphql"
    
    # V117: Restored PascalCase (V1) schema, works on streaming.bitquery.io for Solana
    QUERY_FIRST_100_BUYERS = """
    query FirstBuyers($mint: String!) {
      Solana {
        DEXTrades(
          where: {
            Trade: {
              Buy: {
                Currency: {
                  MintAddress: { is: $mint }
                }
              }
            }
          }
          limit: { count: 100 }
          orderBy: { ascending: Block_Time }
        ) {
          Trade {
            Buy {
              Amount
              Account {
                Token {
                  Owner
                }
              }
            }
          }
          Block {
            Time
          }
        }
      }
    }
    """
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or Settings.BITQUERY_API_KEY
        self.running = False
        self.ws = None
        self.callbacks = []
        
        # Default Query provided by user
        self.subscription_query = """
        subscription {
          Trading {
            Pairs(
              where: {
                Interval: {Time: {Duration: {eq: 1}}},
                Price: {IsQuotedInUsd: true},
                Market: {
                  Program: {in: ["675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8", "ECvrnhtqTNJoFUW4HUfF4CDRrVRhxoVvdD7b83pY5EcQ", "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"]},
                  Network: {is: "Solana"}
                }
              }
            ) {
              Token { Name Symbol Address }
              Market { Protocol Network Name }
              Volume { Base Quote Usd }
              Price {
                Average { Mean }
                Ohlc { Close High Low Open }
              }
              Block { Timestamp }
            }
          }
        }
        """
    
    # ═══════════════════════════════════════════════════════════════════
    # V72.0: REST GraphQL Methods (for Flash Audit)
    # ═══════════════════════════════════════════════════════════════════
    
    def get_first_100_buyers(self, mint: str) -> List[str]:
        """
        V72.0: Get first 100 buyer wallet addresses for a token.
        
        Used by Scout Flash Audit to check against Smart Money watchlist.
        
        Args:
            mint: Token mint address
            
        Returns:
            List of wallet addresses (up to 100)
        """
        if not self.api_key:
            Logger.warning("⚠️ [BITQUERY] API Key is missing. Check your .env file.")
            return []
            
        try:
            headers = {
                "Content-Type": "application/json",
                "X-API-KEY": self.api_key
            }
            
            payload = {
                "query": self.QUERY_FIRST_100_BUYERS,
                "variables": {"mint": mint}
            }
            
            resp = requests.post(self.REST_URL, json=payload, headers=headers, timeout=15)
            
            if resp.status_code != 200:
                Logger.debug(f"[BITQUERY] REST Query failed: {resp.status_code} - {resp.text}")
                return []
            
            result = resp.json()
            # Handle potential GraphQL errors in 200 response
            if "errors" in result:
                Logger.debug(f"[BITQUERY] GraphQL Errors: {result['errors']}")
                return []
                
            trades = result.get("data", {}).get("Solana", {}).get("DEXTrades", [])
            
            wallets = []
            for trade in trades:
                owner = trade.get("Trade", {}).get("Buy", {}).get("Account", {}).get("Token", {}).get("Owner")
                if owner and owner not in wallets:
                    wallets.append(owner)
            
            if wallets:
                Logger.info(f"🏹 [BITQUERY] Found {len(wallets)} early buyers for {mint[:8]}")
            
            return wallets
            
        except Exception as e:
            Logger.error(f"[BITQUERY] REST Error: {e}")
            return []
    
    # ═══════════════════════════════════════════════════════════════════
    # V64.0: WebSocket Methods (original)
    # ═══════════════════════════════════════════════════════════════════

    def add_callback(self, callback: Callable[[dict], None]):
        """Register a callback for new data frames."""
        self.callbacks.append(callback)

    async def start(self):
        """Start the WebSocket content stream."""
        if not self.api_key:
            Logger.warning("⚠️ [BITQUERY] No API Key provided. Bitquery Adapter disabled.")
            return

        self.running = True
        Logger.info("🔌 [BITQUERY] Connecting to WebSocket stream...")
        
        while self.running:
            try:
                # SSL Context might be needed
                ssl_context = ssl.create_default_context()
                
                # Headers for Auth if supported via URL param or protocol message.
                # Bitquery usually requires 'Sec-WebSocket-Protocol': 'graphql-ws'
                # And payload based auth or header. Use 'X-API-KEY' header or Bearer?
                # V2 streaming usually uses headers.
                
                headers = {
                    "X-API-KEY": self.api_key
                }

                async with websockets.connect(
                    self.WS_URL, 
                    subprotocols=['graphql-transport-ws'],
                    extra_headers=headers
                ) as websocket:
                    self.ws = websocket
                    Logger.success("✅ [BITQUERY] Connected.")
                    
                    # Handshake for graphql-transport-ws
                    await self.ws.send(json.dumps({"type": "connection_init", "payload": {"token": self.api_key}}))
                    
                    # Wait for ack
                    ack = await self.ws.recv()
                    # Logger.debug(f"[BITQUERY] Handshake: {ack}")
                    
                    # Send Subscription
                    payload = {
                        "id": "1",
                        "type": "subscribe",
                        "payload": {
                            "query": self.subscription_query
                        }
                    }
                    await self.ws.send(json.dumps(payload))
                    Logger.info("📡 [BITQUERY] Subscription sent.")
                    
                    # Listen loop
                    async for message in self.ws:
                        if not self.running: break
                        await self._handle_message(message)
                        
            except Exception as e:
                Logger.error(f"❌ [BITQUERY] Connection Error: {e}")
                await asyncio.sleep(5) # Reconnect delay

    async def _handle_message(self, raw_msg):
        """Parse and dispatch message."""
        try:
            data = json.loads(raw_msg)
            msg_type = data.get("type")
            
            if msg_type == "next":
                # Data payload
                payload = data.get("payload", {}).get("data", {})
                trading_data = payload.get("Trading", {}).get("Pairs", [])
                
                for item in trading_data:
                    self._dispatch(item)
                    
            elif msg_type == "ping":
                await self.ws.send(json.dumps({"type": "pong"}))
                
        except Exception as e:
            pass
            
    def _dispatch(self, item):
        """Normalize and emit."""
        # Parsing logic according to schema
        # Token info
        tokens = item.get("Token", {}) # Could be list? Schema says Token { Name... }
        # Actually GraphQL usually aligns with selection.
        # Check introspection or assume schema provided is correct.
        
        # Flatten and dispatch
        for cb in self.callbacks:
            try:
                cb(item)
            except:
                pass

    def stop(self):
        self.running = False
        if self.ws:
            asyncio.create_task(self.ws.close())
