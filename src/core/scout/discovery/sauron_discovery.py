import asyncio
import json
import websockets
import os
from typing import Dict
from src.shared.system.logging import Logger
from src.shared.system.signal_bus import signal_bus, Signal, SignalType


class SauronDiscovery:
    """
    V67.0 / V69.0: Sauron Discovery (The All-Seeing Eye)

    Multi-Launchpad WebSocket listener for new token launches.
    Uses Helius 'logsSubscribe' to monitor multiple platforms.

    V69.0: Added BONKfun, Moonshot + Trigger→Fetch→Score flow.
    """

    # ═══════════════════════════════════════════════════════════════════════
    # PROGRAM IDs (2025 Free Stack)
    # ═══════════════════════════════════════════════════════════════════════
    PROGRAMS = {
        "PUMPFUN": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
        "RAYDIUM": "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
        "BONKFUN": "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj",  # LetsBonk.fun (from Bitquery docs)
        "MOONSHOT": "MoonCVVNZFSYkqNXP6bxHLPL6QQJiMagDL3qcqUQTrG",  # Moonshot bonding curve
        "ORCA_WHIRLPOOL": "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
    }

    # Event Signatures (Log patterns to match)
    EVENT_PATTERNS = {
        "PUMPFUN": "Instruction: Create",
        "RAYDIUM": "Instruction: Initialize2",
        "BONKFUN": "initialize_v2",  # LetsBonk.fun uses initialize_v2
        "MOONSHOT": "Instruction: Initialize",
        "ORCA_WHIRLPOOL": "Instruction: InitPool",
    }

    # Helius WSS
    HELIUS_WS_URL = "wss://mainnet.helius-rpc.com/?api-key={}"

    # V69.0: Jupiter API for migration check
    JUPITER_QUOTE_URL = "https://quote-api.jup.ag/v6/quote?inputMint={}&outputMint=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v&amount=1000000"

    def __init__(self):
        self.api_key = os.getenv("HELIUS_API_KEY")
        self.running = False
        self.ws = None
        self.reconnect_delay = 5
        self.callbacks = []

        if not self.api_key:
            Logger.warning("⚠️ [SAURON] No HELIUS_API_KEY found. Eye is blind.")

        # V68.0: Sniper callback
        self.sniper_callback = None

        # V70.0: Discovery rate limiting (reduce Telegram spam)
        self.discovery_count = 0
        self.last_discovery_log = 0
        self.discovery_log_interval = (
            60  # Log summary every 60 seconds instead of per-event
        )

        # V75.0: Per-platform unnamed discovery counter for lumped reporting
        self.unnamed_by_platform: Dict[str, int] = {}
        self.last_lump_report = 0
        self.lump_report_interval = 120  # Report lumped unnamed every 2 minutes

    def set_sniper_callback(self, callback):
        """V68.0: Set callback for when new pools are detected."""
        self.sniper_callback = callback

    def check_jupiter_graduated(self, mint: str) -> dict:
        """
        V69.0: Check if token has "graduated" to Jupiter.

        A token is "graduated" if Jupiter can route it (has liquidity on a DEX).
        This is part of the Trigger → Fetch → Score flow.

        Returns:
            {'graduated': True/False, 'price': float, 'route_count': int}
        """
        import requests

        try:
            url = self.JUPITER_QUOTE_URL.format(mint)
            resp = requests.get(url, timeout=5)

            if resp.status_code == 200:
                data = resp.json()
                routes = data.get("routePlan", [])
                out_amount = (
                    float(data.get("outAmount", 0)) / 1_000_000
                )  # USDC has 6 decimals

                if routes:
                    Logger.info(
                        f"🎓 [SAURON] Token {mint[:8]} GRADUATED! Routes: {len(routes)}, Price: ${out_amount:.6f}"
                    )
                    return {
                        "graduated": True,
                        "price": out_amount,
                        "route_count": len(routes),
                    }

            return {"graduated": False, "price": 0, "route_count": 0}

        except Exception as e:
            Logger.debug(f"[SAURON] Jupiter check failed: {e}")
            return {"graduated": False, "price": 0, "route_count": 0}

    async def start(self):
        """Start as a Signal Consumer (V140 Unification)."""
        self.running = True
        
        # Subscribe to signals from central WebSocketListener
        signal_bus.subscribe(SignalType.MARKET_UPDATE, self._handle_market_signal)
        
        Logger.info("👁️ [SAURON] The Eye is monitoring signals... (Unified Mode)")

    def _handle_market_signal(self, sig: Signal):
        """Process incoming logs from SignalBus."""
        if sig.data.get("type") == "RAW_LOG":
            logs = sig.data.get("logs", [])
            signature = sig.data.get("signature", "unknown")
            self._process_logs_sync(logs, signature)

    def _process_logs_sync(self, logs: list, signature: str):
        """Synchronous version of log parsing."""
        if not logs: return
        log_str = " ".join(logs)
        
        event_type = None
        source = "UNKNOWN"
        for name, pid in self.PROGRAMS.items():
            if pid in log_str:
                pattern = self.EVENT_PATTERNS.get(name, "Initialize")
                if pattern in log_str:
                    source = name
                    event_type = "LAUNCH" if name == "PUMPFUN" else "NEW_POOL"
                    break
        
        if event_type:
            self._handle_discovery(log_str, source, event_type, signature)

    async def _subscribe(self, ws):
        """Send logsSubscribe requests for all monitored programs."""
        sub_id = 1
        for name, pid in self.PROGRAMS.items():
            if pid.startswith("..."):
                continue  # Skip unverified PIDs

            sub_request = {
                "jsonrpc": "2.0",
                "id": sub_id,
                "method": "logsSubscribe",
                "params": [{"mentions": [pid]}, {"commitment": "processed"}],
            }
            await ws.send(json.dumps(sub_request))
            sub_id += 1

        Logger.info(
            f"📡 [SAURON] Watching {len([p for p in self.PROGRAMS.values() if not p.startswith('...')])} launchpads..."
        )

    def _handle_discovery(self, log_str, source, event_type, signature):
        """V69.0: Parse logs and trigger discovery events."""
        try:
            # V67.8: Try to extract mint and resolve symbol
            token_info = None
            try:
                import re
                mint_match = re.search(r"([1-9A-HJ-NP-Za-km-z]{32,44})", log_str)
                if mint_match:
                    mint = mint_match.group(1)
                    from src.infrastructure.token_scraper import get_token_scraper
                    token_info = get_token_scraper().lookup(mint)
                else:
                    return # No mint, no discovery
            except:
                return

            if (
                token_info
                and token_info.get("symbol")
                and not token_info.get("symbol", "").startswith("UNK_")
            ):
                symbol = token_info.get("symbol", "???")
                name = token_info.get("name", "")
                liquidity = token_info.get("liquidity", 0)

                if liquidity > 500:
                    Logger.info(
                        f"🚨 [SAURON] {event_type} on {source}! {symbol} ({name}) | Liq: ${liquidity:,.0f}"
                    )

                if hasattr(self, "sniper_callback") and self.sniper_callback:
                    self.sniper_callback(mint, source)

                signal_bus.emit(
                    Signal(
                        type=SignalType.NEW_TOKEN,
                        source=f"SAURON_{source}",
                        data={"mint": mint, "platform": source},
                    )
                )
            else:
                self.discovery_count += 1
                if source not in self.unnamed_by_platform:
                    self.unnamed_by_platform[source] = 0
                self.unnamed_by_platform[source] += 1

                # V77.0: Queue for delayed metadata resolution
                try:
                    from src.core.scout.discovery.metadata_resolver import (
                        get_metadata_resolver,
                    )
                    get_metadata_resolver().queue_token(mint, source)
                except:
                    pass

                if time.time() - self.last_lump_report > self.lump_report_interval:
                    if self.unnamed_by_platform:
                        lump_parts = [f"{plat}: {cnt}" for plat, cnt in self.unnamed_by_platform.items() if cnt > 0]
                        if lump_parts:
                            Logger.info(f"📊 [SAURON] Unnamed discoveries: {' | '.join(lump_parts)}")
                        self.unnamed_by_platform = {}
                    self.last_lump_report = time.time()

                if hasattr(self, "sniper_callback") and self.sniper_callback:
                    self.sniper_callback(mint, source)

        except Exception:
            pass

    def stop(self):
        self.running = False
        Logger.info("[SAURON] The Eye closes.")


if __name__ == "__main__":
    # Test runner
    try:
        sauron = SauronDiscovery()
        asyncio.run(sauron.start())
    except KeyboardInterrupt:
        pass
