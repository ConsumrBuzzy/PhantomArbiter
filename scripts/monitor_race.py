
"""
Monitor Race - "The Pulse"
==========================
Runs the Fast-Path WSS client and visualizes the "Race-to-First" 
competition between RPC providers.
"""

import asyncio
import os
import random
from rich.live import Live
from rich.console import Console
from src.dashboard.race_tracker import RaceSpeedometer
from src.shared.system.fast_client import FastClient

# Dummy endpoints for demonstration if no config
DEFAULT_ENDPOINTS = [
    "wss://api.mainnet-beta.solana.com", # Generic
    "wss://atlas-mainnet.helius-rpc.com?api-key=dummy", # Helius (Mock)
    "wss://mainnet.rpcpool.com", # Triton (Mock)
]

async def run_monitor():
    console = Console()
    tracker = RaceSpeedometer()
    
    # Initialize FastClient (Hot-Path Bridge)
    # in real usage, these would be your premium RPCs
    client = FastClient(DEFAULT_ENDPOINTS)
    
    # We need to simulate traffic for the speedometer if using Mock
    # OR if using Real Rust, we need actual endpoints.
    # Since we can't easily put real API keys here, we relies on FastClient's Mock fallback
    # OR if Rust is active, it handles connection errors gracefully.
    
    # Let's start client
    # Subscribe to Raydium AMI 
    RAYDIUM_AMM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
    client.start([RAYDIUM_AMM])
    
    try:
        with Live(tracker.generate_view(), refresh_per_second=4, console=console) as live:
            async for event in client.events():
                # Update tracker
                tracker.update(event.provider)
                
                # Mock dedupe count (Rust aggregates internally, so we don't see dropped here!)
                # Wait, if Rust drops them, we don't see them.
                # To visualize "Deduped", we might need `client.get_stats()`!
                stats = client.get_stats()
                if stats:
                    # Sync dropped count
                    tracker.total_deduped = stats.messages_dropped
                    
                live.update(tracker.generate_view())
                
    except KeyboardInterrupt:
        print("Stopping Monitor...")
    finally:
        client.stop()

if __name__ == "__main__":
    try:
        asyncio.run(run_monitor())
    except KeyboardInterrupt:
        pass
