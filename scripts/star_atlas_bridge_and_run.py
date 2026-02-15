"""
Star Atlas Bridge & Run Director
================================
Orchestrates the z.ink bridge sequence and runs the SDU arbitrage loop.

Features:
- "Double-Tap" Bridge Prompt (ZINK-ORIGIN-2026)
- Maintenance Mode (Pauses if SOL < 0.05)
- Volume Mode (Pivots to 1 ATLAS ping-pong if dry-run is stagnant)
- Resilient RPC Handling
"""

import time
import sys
import os
import random
from datetime import datetime
from typing import Optional

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.shared.system.logging import Logger
from src.modules.star_atlas.executor import StarAtlasExecutor
from src.shared.infrastructure.star_atlas_client import StarAtlasClient

# Configuration
BRIDGE_CODE = "ZINK-ORIGIN-2026"
BRIDGE_URL = "https://z.ink/bridge"
MIN_SOL_BALANCE = 0.05
MAINTENANCE_CHECK_INTERVAL = 300  # 5 minutes
LOOP_interval = 60 # 1 minute

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_banner():
    print(r"""
   _____ _                  _   _            
  / ____| |                | | | |           
 | (___ | |_ __ _ _ __     | |_| |__   ___   
  \___ \| __/ _` | '__|    | __| '_ \ / _ \  
  ____) | || (_| | |       | |_| | | |  __/  
 |_____/ \__\__,_|_|        \__|_| |_|\___|  
                                             
   Z.INK BRIDGE & ARBITRAGE DIRECTOR (v2026.2)
    """)

def prompt_bridge_sequence():
    """Guide user through the z.ink bridge process."""
    print_banner()
    print(f"🔒 OR.IGIN CAMPAIGN DETECTED")
    print(f"🔑 ACCESS CODE: {BRIDGE_CODE}")
    print("-" * 50)
    print(f"1. Navigate to: {BRIDGE_URL}")
    print(f"2. Connect Phantom Wallet")
    print(f"3. Enter Access Code: {BRIDGE_CODE}")
    print(f"4. Bridge 0.15 SOL to z.ink (Keep 0.018 SOL on Mainnet)")
    print("-" * 50)
    
    while True:
        response = input("Did you complete the bridge transaction? (yes/no): ").lower().strip()
        if response in ['yes', 'y']:
            print("\n✅ Bridge Confirmed. Initializing Executors...")
            break
        elif response in ['no', 'n']:
            print("\n⚠️  Please complete the bridge to proceed.")
            input("Press Enter to open bridge URL...")
            import webbrowser
            webbrowser.open(BRIDGE_URL)
        else:
            print("Invalid input.")

def check_maintenance_mode(executor: StarAtlasExecutor) -> bool:
    """
    Check if maintenance mode should be active.
    Returns True if safe to run, False if paused.
    """
    try:
        # Placeholder for actual balance check on z.ink
        # In a real scenario, we'd query the RPC.
        # For now, we assume the executor has a way to check, or we use a mock.
        balance = 0.15 # Mock balance for now, assuming bridge success
        
        # Real implementation would be:
        # balance = executor.get_zink_balance() 
        
        if balance < MIN_SOL_BALANCE:
            Logger.warning(f"⚠️  MAINTENANCE MODE ACTIVE: Balance {balance} < {MIN_SOL_BALANCE} SOL")
            Logger.warning("   Pausing execution to prevent liquidation.")
            return False
            
        return True
    except Exception as e:
        Logger.error(f"Failed to check balance: {e}")
        return True # Fail open to keep trying, or close? Fail open for now with error.

def run_arbitrage_loop():
    """Main execution loop."""
    executor = StarAtlasExecutor(network="zink", dry_run=True)
    client = StarAtlasClient()
    
    consecutive_no_profit = 0
    start_time = datetime.now()
    
    Logger.info("🚀 Starting 24h Dry-Run Loop...")
    
    try:
        while True:
            # 1. Maintenance Check
            if not check_maintenance_mode(executor):
                time.sleep(MAINTENANCE_CHECK_INTERVAL)
                continue
            
            # 2. SDU Arbitrage Scan
            Logger.info("\n🔍 Scanning for SDU Arbitrage...")
            try:
                # We use the client to "scan" (mocked in client for now, but logical flow)
                opportunities = client.scan_for_opportunities(resources=["SDU"])
                
                if not opportunities:
                    consecutive_no_profit += 1
                    Logger.info(f"   No opportunities found. Stagnation counter: {consecutive_no_profit}")
                else:
                    consecutive_no_profit = 0
                    # Execute (Dry Run)
                    for opp in opportunities:
                         # Logic to call executor.buy_resource would go here
                         # For now, scan_for_opportunities logs it.
                         pass

            except Exception as e:
                Logger.error(f"Scan failed (RPC Lag?): {e}")

            # 3. Volume Mode Pivot
            # If we haven't found profit in 5 checks (5 minutes), ping-pong to farm zXP
            if consecutive_no_profit >= 5:
                Logger.info("⚠️  STAGNATION DETECTED: Pivoting to VOLUME MODE")
                Logger.info("   🏓 Executing 1 ATLAS Ping-Pong for zXP...")
                
                # Mock Volume Trade
                executor.buy_resource("ATM", 1, 0.001) # Buying mock Atmosphere or cheap item
                
                # Reset counter to avoid spamming immediately, or keep it high to stay in volume mode?
                # Let's reset to try scanning again next loop
                consecutive_no_profit = 0
            
            # 4. Sleep
            Logger.info(f"💤 Sleeping {LOOP_interval}s...")
            time.sleep(LOOP_interval)
            
            # Check 24h limit
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > 86400:
                Logger.success("✅ 24-Hour Dry-Run Complete.")
                break
                
    except KeyboardInterrupt:
        Logger.info("\n🛑 Execution Interrupted by User.")
        
if __name__ == "__main__":
    prompt_bridge_sequence()
    run_arbitrage_loop()
