
"""
Log Harvester
=============
Relies on 'logsSubscribe' to capture Program-Level events at the speed of the validator.
Bypasses polling for instant detection of 'Graduation' and 'Token Birth' events.
"""

import json
import asyncio
import threading
from typing import Callable, Dict, Optional
import websockets

from src.shared.system.logging import Logger
from src.shared.system.signal_bus import signal_bus, Signal, SignalType
from config.settings import Settings

# Program IDs
RAYDIUM_V4_ID = "675kPX9MCyJsD5ippTu671dKKkCtSE5v4RBmZJtHNv9v"
PUMPFUN_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

class LogHarvester:
    """
    Asynchronous Log Scanner.
    Connects to WSS and filters for key instruction logs.
    """
    
    def __init__(self):
        self.ws_url = Settings.HELIUS_WS_URL or "wss://api.mainnet-beta.solana.com"
        self.is_running = False
        self.reconnect_delay = 5
        self._thread = None
        
        # Stats
        self.stats = {
            "processed": 0,
            "graduations": 0,
            "launches": 0
        }

    def start(self):
        """Start the harvester loop in a dedicated thread."""
        if self.is_running: return
        self.is_running = True
        self._thread = threading.Thread(target=self._run_forever, daemon=True, name="LogHarvester")
        self._thread.start()
        Logger.info("👁️ [HARVESTER] Started. Watching the Matrix.")

    def stop(self):
        self.is_running = False
        Logger.info("👁️ [HARVESTER] Stopped.")

    def _run_forever(self):
        """Thread wrapper for the async loop."""
        asyncio.run(self._connect_and_listen())

    async def _connect_and_listen(self):
        """Main WebSocket Loop."""
        while self.is_running:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    Logger.info(f"👁️ [HARVESTER] Connected to {self.ws_url}")
                    
                    # Subscribe to Raydium (Graduation Events)
                    await self._subscribe(ws, RAYDIUM_V4_ID)
                    # Subscribe to PumpFun (New Launches)
                    # await self._subscribe(ws, PUMPFUN_ID) # Optional: Enable if bandwidth allows
                    
                    while self.is_running:
                        msg = await ws.recv()
                        await self._process_message(json.loads(msg))
                        
            except Exception as e:
                Logger.warning(f"👁️ [HARVESTER] Connection Lost: {e}. Reconnecting in {self.reconnect_delay}s...")
                await asyncio.sleep(self.reconnect_delay)

    async def _subscribe(self, ws, program_id: str):
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": [
                {"mentions": [program_id]},
                {"commitment": "processed"} # Fastest possible commitment
            ]
        }
        await ws.send(json.dumps(payload))

    async def _process_message(self, data: dict):
        """Parse the raw log notification."""
        self.stats["processed"] += 1
        
        # Filter noise
        if "method" not in data or data["method"] != "logsNotification":
            return
            
        params = data.get("params", {})
        result = params.get("result", {})
        value = result.get("value", {})
        logs = value.get("logs", [])
        signature = value.get("signature", "unknown")
        
        # Analyze Logs
        is_raydium = False
        is_initialize2 = False
        
        for log in logs:
            if "Program 675kPX9MCyJsD5ippTu671dKKkCtSE5v4RBmZJtHNv9v invoke" in log:
                is_raydium = True
            
            # Key Indicator: "initialize2" -> Pool Creation
            if is_raydium and "initialize2" in log:
                is_initialize2 = True
                
            # If we see "success", fire signal
            if is_initialize2 and "Program 675kPX9MCyJsD5ippTu671dKKkCtSE5v4RBmZJtHNv9v success" in log:
                # We found a valid pool creation!
                # Problem: The logs don't always contain the Mint Address directly in plain text.
                # It requires parsing "invoke [1]" or fetching tx. 
                # HOWEVER, for a fast signal, determining "Something happened" is step 1.
                # To get the Mint, we usually need to Parse the Transaction or look closer at log data provided.
                # Helius logs often include more data? No, standard solana logs are just strings.
                
                # Fast Path: Signal that "A Pool was Created" with the Signature.
                # The SniperAgent can then fetch the TX (or use gRPC later for full data).
                
                Logger.info(f"👁️ [HARVESTER] 🎓 GRADUATION: {signature}")
                self.stats["graduations"] += 1
                
                # Emit Signal
                signal_bus.emit(Signal(
                    type=SignalType.NEW_TOKEN, # Or specific GRADUATION type?
                    source="HARVESTER",
                    data={
                        "event": "GRADUATION",
                        "signature": signature,
                        "program": "RAYDIUM"
                    }
                ))
                break # Once per tx
