import asyncio
import os
import json
import time
from typing import Dict, List, Optional
from src.shared.infrastructure.rpc_balancer import get_rpc_balancer
from src.shared.system.logging import Logger
from src.shared.system.signal_bus import signal_bus, Signal, SignalType

class WhaleSensor:
    """
    V140: Whale Activity Sensor
    
    Centralized I/O component for monitoring 'Alpha Wallets'.
    Polls RPC for new transactions and emits WHALE_ACTIVITY signals.
    """

    def __init__(self, poll_interval: float = 15.0):
        self.rpc = get_rpc_balancer()
        self.poll_interval = poll_interval
        self.running = False
        self.watchlist_file = os.path.join(
            os.path.dirname(__file__), "../../../data/smart_money_watchlist.json"
        )
        self.last_signatures: Dict[str, str] = {}
        self.watchlist = {}

    async def start(self):
        """Start the polling loop."""
        self.running = True
        Logger.info("[WHALE_SENSOR] Opening the eye for Alpha Wallets...")
        
        while self.running:
            try:
                # 1. Reload Watchlist
                self.watchlist = self._load_watchlist()
                
                # 2. Get Top 5 Wallets
                candidates = sorted(
                    self.watchlist.items(),
                    key=lambda item: item[1].get("score", {}).get("win_rate", 0),
                    reverse=True,
                )[:5]
                
                if not candidates:
                    await asyncio.sleep(self.poll_interval)
                    continue
                
                # 3. Poll each
                for wallet, _ in candidates:
                    await self._poll_wallet(wallet)
                    await asyncio.sleep(1.0) # Rate limit
                
                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                Logger.error(f"[WHALE_SENSOR] Loop Error: {e}")
                await asyncio.sleep(5)

    def stop(self):
        self.running = False
        Logger.info("[WHALE_SENSOR] Eye closed.")

    async def _poll_wallet(self, wallet: str):
        """Check for new transactions for a specific wallet."""
        try:
            resp, err = self.rpc.call("getSignaturesForAddress", [wallet, {"limit": 1}])
            if err or not resp:
                return

            latest_sig = resp[0]["signature"]

            if wallet not in self.last_signatures:
                self.last_signatures[wallet] = latest_sig
                return

            if latest_sig != self.last_signatures[wallet]:
                Logger.info(f"[WHALE_SENSOR] 🐋 Movement detected: {wallet[:8]}...")
                self.last_signatures[wallet] = latest_sig
                
                # Fetch full transaction
                tx, tx_err = self.rpc.call(
                    "getTransaction",
                    [latest_sig, {"encoding": "json", "maxSupportedTransactionVersion": 0}],
                )
                
                if not tx_err and tx:
                    # Emit Raw Activity Signal
                    signal_bus.emit(Signal(
                        type=SignalType.WHALE_ACTIVITY,
                        source="WHALE_SENSOR",
                        data={
                            "wallet": wallet,
                            "signature": latest_sig,
                            "tx_data": tx
                        }
                    ))
                    
        except Exception as e:
            Logger.debug(f"[WHALE_SENSOR] Poll failed for {wallet[:8]}: {e}")

    def _load_watchlist(self) -> Dict:
        if not os.path.exists(self.watchlist_file):
            return {}
        try:
            with open(self.watchlist_file, "r") as f:
                return json.load(f)
        except Exception:
            return {}
