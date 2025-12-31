"""
Launch Visual Bridge
====================
Phase 25: Real-Time Visualization

Starts the Visual Bridge WebSocket server to stream Market Graph updates.
"""

import sys
import os
import asyncio
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.arbiter.visual_bridge import VisualBridge
from src.shared.system.logging import Logger

def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

async def main():
    configure_logging()
    print("🌉 Starting Visual Bridge...")
    
    bridge = VisualBridge(host="localhost", port=8765, update_interval=2.0)
    
    try:
        await bridge.start()
    except KeyboardInterrupt:
        print("\n🛑 Bridge Stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
