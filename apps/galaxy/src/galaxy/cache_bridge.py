
import asyncio
import time
import os
import logging
from typing import Dict, Any, List

from galaxy.connection_manager import connection_manager

# Configure Logging
logger = logging.getLogger("GalaxyCacheBridge")

class CacheBridge:
    """
    Bridges the high-speed Rust FlashCache (Shared Memory) to the Galaxy WebSocket stream.
    
    Reads from: data/market_data.shm (via phantom_core.FlashCacheReader)
    Writes to: WebSocket clients (via connection_manager.broadcast)
    """

    def __init__(self, fps: int = 30):
        self._running = False
        self._fps = fps
        self._interval = 1.0 / fps
        self.reader = None
        
        # Initialize Reader
        try:
            import phantom_core
            # Assume data dir is relative to CWD (usually run from root)
            cache_path = os.path.join(os.getcwd(), "data", "market_data.shm")
            
            if os.path.exists(cache_path):
                self.reader = phantom_core.FlashCacheReader(cache_path)
                logger.info(f"🚀 [Bridge] Connected to FlashCache at {cache_path}")
            else:
                logger.warning(f"⚠️ [Bridge] FlashCache not found at {cache_path}")
                
        except ImportError:
            logger.error("❌ [Bridge] phantom_core not found. Acceleration disabled.")
        except Exception as e:
            logger.error(f"❌ [Bridge] Init Error: {e}")

    async def start(self):
        """Start the polling loop."""
        if not self.reader:
            return

        self._running = True
        logger.info(f"⚡ [Bridge] Starting Frame Loop ({self._fps} FPS)")
        
        # We run the polling in a separate thread-like behavior via asyncio.to_thread 
        # or just cooperative multitasking since default Python loop is single threaded.
        # But poll_updates is fast (memory read).
        
        self.trade_buffer = []
        self.last_flush = time.time()
        self.CONVOY_INTERVAL = 0.1 # 100ms Batching
        
        while self._running:
            start_time = time.time()
            
            try:
                # 1. Poll Updates (Sync call to Rust)
                # Returns list of (mint, price, slot, liquidity, trade_flow)
                updates = self.reader.poll_updates()
                
                # 2. Aggregating/Conflating
                if updates:
                    frame_data = {}
                    
                    for mint, price, slot, liquidity, trade_flow in updates:
                        # Price/State Update
                        frame_data[mint] = {
                            "p": price,
                            "s": slot
                        }
                        
                        # Trade Scouting (Kinetic Trigger)
                        if abs(trade_flow) > 0.0001:
                            self.trade_buffer.append({
                                "mint": mint,
                                "p": price,
                                "flow": trade_flow, #Signed: +Buy, -Sell
                                "is_buy": trade_flow > 0,
                                "size": abs(trade_flow),
                                "t": int(start_time * 1000)
                            })
                    
                    # 3. Broadcast Price Frame (Immediate 30FPS)
                    if frame_data:
                        payload = {
                            "type": "PRICE_FRAME",
                            "t": int(start_time * 1000),
                            "updates": frame_data
                        }
                        asyncio.create_task(connection_manager.broadcast(payload))
                
                # 4. Flush Trade Convoy (100ms Interval)
                if (start_time - self.last_flush) >= self.CONVOY_INTERVAL:
                    if self.trade_buffer:
                        convoy_payload = {
                            "type": "TRADE_CONVOY",
                            "t": int(start_time * 1000),
                            "events": list(self.trade_buffer) # Copy
                        }
                        self.trade_buffer.clear()
                        self.last_flush = start_time
                        asyncio.create_task(connection_manager.broadcast(convoy_payload))
                    else:
                        self.last_flush = start_time # Reset even if empty to keep cadence
                    
            except Exception as e:
                logger.error(f"⚠️ [Bridge] Loop Error: {e}")
            
            # 5. Frame Pacing
            elapsed = time.time() - start_time
            sleep_time = max(0, self._interval - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    def stop(self):
        """Stop the polling loop."""
        self._running = False
        logger.info("🛑 [Bridge] Stopping...")

# Global Instance
cache_bridge = CacheBridge()
