"""
WebSocketListener - Real-Time DEX Log Parsing V6.1.8
=====================================================
V6.1.8: Uses Helius RPC + exponential backoff on 429.
"""

import os
import json
import threading
import time
import asyncio
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), "../../.env")
load_dotenv(env_path)


RAYDIUM_AMM_PROGRAM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
ORCA_WHIRLPOOLS_PROGRAM = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"

USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

WSS_DEBUG = True


def wss_log(msg: str):
    if WSS_DEBUG:
        print(f"   [WSS] {msg}")


class WebSocketListener:
    """
    V6.1.8: Helius RPC + aggressive throttling to avoid 429s.
    """

    def __init__(self, price_cache, watched_mints: dict):
        self.price_cache = price_cache
        self.watched_mints = watched_mints
        self.symbol_to_mint = {v: k for k, v in watched_mints.items()}
        self.ws = None
        self.running = False
        self.thread = None
        self.reconnect_delay = 5

        self.ws_url = os.getenv("HELIUS_WS_URL", "")

        # V9.0: RPC Failover Manager
        from src.shared.infrastructure.rpc_manager import RpcConnectionManager

        # Load RPCs from Env (Comma separated)
        env_rpcs = os.getenv("RPC_URLS", "")
        base_rpc = os.getenv("RPC_URL", "")

        rpc_list = []
        if env_rpcs:
            rpc_list.extend(env_rpcs.split(","))
        if base_rpc:
            rpc_list.append(base_rpc)

        # Helius fallback logic logic
        if "api-key=" in self.ws_url:
            api_key = self.ws_url.split("api-key=")[-1]
            rpc_list.append(f"https://mainnet.helius-rpc.com/?api-key={api_key}")

        self.rpc_manager = RpcConnectionManager(rpc_list)

        # V6.1.8: Backoff state
        self.rate_limited_until = 0
        self.backoff_seconds = 5

        self.stats = {
            "messages_received": 0,
            "swaps_detected": 0,
            "swaps_queued": 0,
            "swaps_throttled": 0,
            "prices_updated": 0,
            "rpc_fetches": 0,
            "rpc_429s": 0,
            "rpc_errors": 0,
            "rpc_success": 0,
            "reconnects": 0,
            "last_price_update": None,
            "connection_status": "disconnected",
            # V84.0: Mint tracking
            "known_swaps": 0,  # Swaps for tokens we track
            "unknown_swaps": 0,  # Swaps for new/unknown tokens
        }

        # V84.0: Track unknown mints for later resolution (capped set)
        self.unknown_mints: set = set()
        self.MAX_UNKNOWN_MINTS = 500

        if not self.ws_url:
            print("   ⚠️ HELIUS_WS_URL not set. WebSocket disabled.")
        else:
            wss_log(f"Monitoring: {list(watched_mints.values())[:5]}...")
            wss_log(f"RPC: {'Helius' if 'helius' in self.ws_url else 'Public'}")

    def start(self):
        if self.running or not self.ws_url:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self.thread.start()
        print("   🔌 WebSocket Listener started (V6.1.8 Throttled)")

    def stop(self):
        self.running = False
        self.stats["connection_status"] = "stopped"

    def _run_async_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._connect_loop())
        except:
            pass
        finally:
            try:
                loop.close()
            except:
                pass

    async def _connect_loop(self):
        import websockets

        while self.running:
            try:
                self.stats["connection_status"] = "connecting"
                async with websockets.connect(
                    self.ws_url, ping_interval=20, ping_timeout=10, close_timeout=5
                ) as ws:
                    self.ws = ws
                    self.stats["connection_status"] = "connected"
                    print("   ✅ WebSocket connected to Helius")
                    await self._subscribe(ws)

                    async for message in ws:
                        if not self.running:
                            break
                        self._process_message(message)

            except asyncio.CancelledError:
                break
            except Exception:
                if self.running:
                    self.stats["reconnects"] += 1
                    self.stats["connection_status"] = "reconnecting"
                    print("   ⚠️ WSS reconnecting...")
                    await asyncio.sleep(self.reconnect_delay)

    async def _subscribe(self, ws):
        # Subscribe to USDC mentions only (reduces traffic)
        usdc_sub = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": [{"mentions": [USDC_MINT]}, {"commitment": "confirmed"}],
        }
        await ws.send(json.dumps(usdc_sub))
        wss_log("📡 Subscribed to USDC swaps")

    def _process_message(self, message: str):
        self.stats["messages_received"] += 1

        try:
            data = json.loads(message)

            if "result" in data or "params" not in data:
                return

            params = data.get("params", {})
            result = params.get("result", {})
            value = result.get("value", {})

            logs = value.get("logs", [])
            signature = value.get("signature", "")

            if not logs or not signature:
                return

            # Check for swap
            is_swap = any(
                "Swap" in log or "swap" in log or "ray_log" in log for log in logs[:5]
            )
            if not is_swap:
                return

            self.stats["swaps_detected"] += 1

            # V77.0: COUNT-ONLY MODE - Skip expensive transaction fetches
            # Stats still track swap activity for market sentiment
            # Price updates now come from DexScreener/Jupiter (more reliable)

            # Optional: Track which programs are active
            logs_str = " ".join(logs[:10])
            dex = "SOLANA"  # Default to generic Solana swap
            if "ray_log" in logs_str or RAYDIUM_AMM_PROGRAM[:8] in logs_str:
                self.stats["raydium_swaps"] = self.stats.get("raydium_swaps", 0) + 1
                dex = "RAYDIUM"
            elif "Whirlpool" in logs_str or ORCA_WHIRLPOOLS_PROGRAM[:8] in logs_str:
                self.stats["orca_swaps"] = self.stats.get("orca_swaps", 0) + 1
                dex = "ORCA"
            elif "LBUZKhRx" in logs_str or "Meteora" in logs_str:
                self.stats["meteora_swaps"] = self.stats.get("meteora_swaps", 0) + 1
                dex = "METEORA"
            elif "JUP" in logs_str or "jupiter" in logs_str.lower():
                self.stats["jupiter_swaps"] = self.stats.get("jupiter_swaps", 0) + 1
                dex = "JUPITER"
            else:
                self.stats["other_swaps"] = self.stats.get("other_swaps", 0) + 1

            # V84.0: Queue signature for Solscan scraping
            try:
                from src.scraper.discovery.scrape_intelligence import (
                    get_scrape_intelligence,
                )

                scraper = get_scrape_intelligence()
                scraper.add_signature(signature, dex=dex)
            except:
                pass

            # V77.0: Log occasionally for debug (every 5000 swaps)
            if self.stats["swaps_detected"] % 5000 == 0:
                wss_log(
                    f"📊 {self.stats['swaps_detected']} swaps detected (Raydium: {self.stats.get('raydium_swaps', 0)}, Orca: {self.stats.get('orca_swaps', 0)})"
                )

            # ═══ V88.0: RUST FLASH DECRYPTION (PHASE 3: THE WIRE) ═══
            try:
                import phantom_core
                from src.shared.state.app_state import state as app_state

                # Update Core Status if not already
                if not app_state.stats["rust_core_active"]:
                    app_state.update_stat("rust_core_active", True)

                for log_str in logs:
                    # Instant zero-copy decoding in Rust
                    event = phantom_core.parse_raydium_log(log_str)
                    if event:
                        # Proof of Life: Log the flash decode
                        msg = f"⚡ FLASH SWAP: In={event.amount_in} Out={event.amount_out} Buy={event.is_buy}"
                        wss_log(msg)
                        app_state.log(msg)  # Push to TUI
                        app_state.update_stat(
                            "wss_latency_ms", 10
                        )  # Mock metric for now, or measure time
                        
                        # V34.5: Emit Signal for Dashboard ("The Void")
                        # Using signature as 'mint' to create firework effect or a constant for pulsing.
                        # Since we don't know the token mint here (zero-copy), we use a placeholder or derived ID.
                        # 'event' object might not have mint.
                        
                        from src.shared.system.signal_bus import signal_bus, Signal, SignalType
                        
                        # Use a persistent ID for "Flash Feed" to avoid chaos, or random for swarm.
                        # Let's use 'FLASHER_<random>' for fireworks? No, user wants *Tokens*.
                        # But we don't have token. So we use "UNKNOWN_SWAP" but with unique ID to trigger "createNode".
                        # To prevent infinite memory, we rely on the Pruning Logic added to dashboard.html.
                        
                        # Format amount as USD (USDC has 6 decimals)
                        amount_usd = event.amount_in / 1_000_000
                        if amount_usd >= 1000:
                            label_str = f"${amount_usd/1000:.1f}k"
                        elif amount_usd >= 1:
                            label_str = f"${amount_usd:.0f}"
                        else:
                            continue  # Skip dust transactions
                        
                        # Emit as DEX activity event (not a token)
                        # These will appear as transient PULSAR nodes
                        signal_bus.emit(Signal(
                            type=SignalType.MARKET_UPDATE,
                            source="DEX",  # Maps to PULSAR (Green) - transient events
                            data={
                                "mint": f"SWAP_{signature[-8:]}",  # Unique event ID
                                "symbol": f"⚡ {dex}",  # e.g. "⚡ RAYDIUM"
                                "label": label_str,  # "$1.5k"
                                "volume_24h": amount_usd,
                                "liquidity": 1000, 
                                "price": amount_usd,
                                "is_event": True,  # Mark as transient
                                "timestamp": time.time()
                            }
                        ))

            except ImportError:
                pass
            except Exception:
                pass  # Don't crash the listener

        except:
            pass

    def _fetch_tx(self, signature: str):
        """
        V6.2.2: Maximized Polling Window.
        20 retries × 150ms = 3.0 seconds total polling time.
        """
        import requests

        MAX_RETRIES = 20
        DELAY = 0.15  # 150ms constant delay

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                signature,
                {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0},
            ],
        }

        try:
            for attempt in range(MAX_RETRIES):
                self.stats["rpc_fetches"] += 1

                # Proxy through Manager (Auto-switch on connection failure)
                # Note: We catch RequestException inside manager?
                # Actually manager re-raises it after switching. So we need to handle it here or let it retry.
                try:
                    response = self.rpc_manager.post(payload, timeout=self.rpc_timeout)
                except requests.RequestException:
                    # Manager has already switched provider.
                    # We continue to next retry loop, which will use new provider.
                    continue

                if response.status_code == 429:
                    self.stats["rpc_429s"] += 1
                    # Notify manager maybe?
                    self.rate_limited_until = time.time() + self.backoff_seconds
                    self.backoff_seconds = min(self.backoff_seconds * 2, 30)
                    return

                self.backoff_seconds = 5

                if response.status_code != 200:
                    self.stats["rpc_errors"] += 1
                    return

                data = response.json()

                if "error" in data:
                    self.stats["rpc_errors"] += 1
                    return

                # V6.2.2: Check if indexed
                if data.get("result"):
                    self.stats["rpc_success"] += 1
                    # wss_log(f"✅ OK ({signature[:8]}) [{attempt+1}]")

                    price_found = self._process_balances(data["result"])
                    # Price log is in _process_balances
                    return

                # Wait and retry
                if attempt < MAX_RETRIES - 1:
                    time.sleep(DELAY)

            # All retries exhausted
            self.stats["rpc_errors"] += 1
            # V76.0: Silenced - too noisy. Stats track it.
            # wss_log(f"❌ EXPIRED ({signature[:8]}) after 20 tries")

        except requests.Timeout:
            self.stats["rpc_errors"] += 1
        except:
            self.stats["rpc_errors"] += 1
        finally:
            self.pending_signatures.discard(signature)
            self.rpc_semaphore.release()

    def _process_balances(self, tx_data: dict) -> bool:
        try:
            meta = tx_data.get("meta", {})
            pre_balances = meta.get("preTokenBalances", [])
            post_balances = meta.get("postTokenBalances", [])

            if not pre_balances or not post_balances:
                return False

            pre = {}
            post = {}

            for b in pre_balances:
                mint = b.get("mint", "")
                amt = float(b.get("uiTokenAmount", {}).get("uiAmount") or 0)
                if mint:
                    pre[mint] = pre.get(mint, 0) + amt

            for b in post_balances:
                mint = b.get("mint", "")
                amt = float(b.get("uiTokenAmount", {}).get("uiAmount") or 0)
                if mint:
                    post[mint] = post.get(mint, 0) + amt

            usdc_change = post.get(USDC_MINT, 0) - pre.get(USDC_MINT, 0)

            for mint, symbol in self.watched_mints.items():
                if mint == USDC_MINT:
                    continue

                token_change = post.get(mint, 0) - pre.get(mint, 0)

                if abs(usdc_change) > 0.01 and abs(token_change) > 0.0001:
                    price = abs(usdc_change) / abs(token_change)

                    if 0.0001 < price < 10000:
                        self.price_cache.update_price(mint, price)
                        self.stats["prices_updated"] += 1
                        self.stats["last_price_update"] = time.time()
                        wss_log(f"📈 {symbol} = ${price:.6f} (WSS)")

                        from src.shared.system.signal_bus import signal_bus, Signal, SignalType
                        
                        # V31: Emit Real-Time Signal for Visual Bridge
                        signal_bus.emit(Signal(
                            type=SignalType.MARKET_UPDATE,
                            source="WSS_Listener",
                            data={
                                "mint": mint,
                                "symbol": symbol,
                                "price": price,
                                "timestamp": time.time()
                            }
                        ))

                        # V12.2: Push to Dashboard Pulse
                        try:
                            from src.shared.state.app_state import state
                            state.update_pulse(symbol, price)
                        except:
                            pass

                        return True

            return False
        except:
            return False

    def get_stats(self) -> dict:
        return self.stats.copy()

    def is_connected(self) -> bool:
        return self.stats["connection_status"] == "connected"

    def add_mint(self, mint: str, symbol: str):
        self.watched_mints[mint] = symbol
        self.symbol_to_mint[symbol] = mint

    def remove_mint(self, mint: str):
        symbol = self.watched_mints.pop(mint, None)
        if symbol:
            self.symbol_to_mint.pop(symbol, None)


def create_websocket_listener(price_cache, watched_mints: dict) -> WebSocketListener:
    return WebSocketListener(price_cache, watched_mints)
