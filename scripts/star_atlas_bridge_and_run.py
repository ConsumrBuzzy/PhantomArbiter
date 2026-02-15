"""
Star Atlas Bridge & Run Director (Simulation Protocol)
======================================================
Orchestrates the z.ink bridge sequence and runs the SDU arbitrage loop.
Simulation Mode: Uses Mock Data to stress-test logic and accumulate "Theoretical Profit".

Features:
- "Double-Tap" Bridge Prompt (ZINK-ORIGIN-2026)
- Maintenance Mode (Pauses if SOL < 0.05)
- Volume Mode (Pivots to 1 ATLAS ping-pong if dry-run isn't hitting)
- SIMULATION LOGGING: Tracks theoretical trades in SAGE_SIM_LOGS.csv
"""

import time
import sys
import os
import csv
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
LOOP_interval = 20 # Faster loop for simulation
SIM_LOG_FILE = "SAGE_SIM_LOGS.csv"
MIN_SPREAD = 0.075 # 7.5% (6% fee + 1.5% buffer)
TARGET_PROFIT_SOL = 0.05

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
   *** SIMULATION MODE ACTIVE ***
    """)

def init_sim_logs():
    if not os.path.exists(SIM_LOG_FILE):
        with open(SIM_LOG_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Timestamp', 'Starbase_Buy', 'Price_Buy', 'Starbase_Sell', 'Price_Sell', 'Spread_Pct', 'Theoretical_Profit_SOL', 'Theoretical_zXP', 'Action'])
        Logger.info(f"📝 Created Simulation Log: {SIM_LOG_FILE}")

def log_sim_trade(buy_sb, buy_price, sell_sb, sell_price, spread, profit, zxp):
    with open(SIM_LOG_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().isoformat(),
            buy_sb, f"{buy_price:.6f}",
            sell_sb, f"{sell_price:.6f}",
            f"{spread*100:.2f}%",
            f"{profit:.6f}",
            f"{zxp:.2f}",
            "VOLUME_EXECUTE"
        ])

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
    
    # Check for auto-yes argument
    if "--auto-yes" in sys.argv:
        print("\n✅ Auto-Bridge Confirmed. Initializing Executors...")
        return

    while True:
        response = input("Did you complete the bridge transaction? (yes/no): ").lower().strip()
        if response in ['yes', 'y']:
            print("\n✅ Bridge Confirmed. Initializing Executors...")
            break
        elif response in ['no', 'n']:
            print("\n⚠️  Please complete the bridge to proceed.")
            # input("Press Enter to open bridge URL...")
        else:
            print("Invalid input.")

def check_maintenance_mode(executor: StarAtlasExecutor) -> bool:
    """Mock balance check for simulation."""
    return True

def run_arbitrage_loop():
    """Main execution loop (Volume Mode Enhanced)."""
    # Force z.ink network
    executor = StarAtlasExecutor(network="zink", dry_run=True)
    client = StarAtlasClient()
    
    init_sim_logs()
    
    consecutive_no_profit = 0
    total_theoretical_profit = 0.0
    total_zxp = 0.0
    start_time = datetime.now()
    
    Logger.info("🚀 Starting 24h Simulation Loop (VOLUME MODE | zXP Optimized)...")
    Logger.info(f"   Target: > {MIN_SPREAD*100}% Spread | Principal Buffer: $14.00")
    
    try:
        while True:
            # 1. Scanning
            Logger.info("\n🔍 Scanning SDU Market (Simulation)...")
            try:
                listings = client.get_sdu_prices()
                
                if len(listings) >= 2:
                    # Sort by price
                    sorted_listings = sorted(listings, key=lambda x: float(x['pricePerUnit']))
                    best_buy = sorted_listings[0]
                    best_sell = sorted_listings[-1]
                    
                    buy_price = float(best_buy['pricePerUnit'])
                    sell_price = float(best_sell['pricePerUnit'])
                    
                    spread = (sell_price - buy_price) / buy_price
                    
                    Logger.info(f"   Market: Buy @ {best_buy['starbase']['name']} ({buy_price:.5f}) | Sell @ {best_sell['starbase']['name']} ({sell_price:.5f})")
                    Logger.info(f"   Spread: {spread*100:.2f}% (Threshold: {MIN_SPREAD*100}%)")
                    
                    if spread > MIN_SPREAD:
                        # "Execute" Trade
                        profit_per_unit = sell_price - buy_price - (sell_price * 0.06) # Simplified fee
                        trade_size = 1000
                        trade_profit = profit_per_unit * trade_size
                        
                        # zXP Calculation (Simulated: Volume * Multiplier)
                        # Multiplier 1.5x for Origin Season
                        trade_zxp = (trade_size * buy_price * 150) * 1.5 
                        
                        total_theoretical_profit += trade_profit
                        total_zxp += trade_zxp
                        
                        Logger.success(f"   ✅ [VOLUME] EXECUTED! Profit: {trade_profit:.6f} SOL | zXP: +{trade_zxp:.0f}")
                        log_sim_trade(
                            best_buy['starbase']['name'], buy_price,
                            best_sell['starbase']['name'], sell_price,
                            spread, trade_profit, trade_zxp
                        )
                        consecutive_no_profit = 0
                        
                        Logger.info(f"   📊 Session Total: {total_theoretical_profit:.4f} SOL | {total_zxp:.0f} zXP")

                        if total_theoretical_profit > TARGET_PROFIT_SOL:
                            Logger.success(f"   🎉 TARGET PROFIT ACHIEVED: {total_theoretical_profit:.4f} SOL")
                            # Continue for zXP accumulation
                            # Logger.info("   🚩 FLAGGING FOR LIVE TRANSITION (Pending RPC)")
                    else:
                        Logger.warning(f"   📉 Liquidity Drift: Spread too low ({spread*100:.2f}%)")
                        consecutive_no_profit += 1

                else:
                    Logger.warning("   [!] Not enough data for arbitrage.")
                    consecutive_no_profit += 1

            except Exception as e:
                Logger.error(f"Scan failed: {e}")

            # 3. Volume Mode Pivot (Simulation)
            if consecutive_no_profit >= 5:
                Logger.info("⚠️  STAGNATION DETECTED: Pivoting to VOLUME MODE (Simulated)")
                Logger.info("   🏓 Executing 1 ATLAS Ping-Pong for zXP...")
                # In sim, we just log it
                consecutive_no_profit = 0
            
            # 4. Sleep
            Logger.info(f"💤 Sleeping {LOOP_interval}s...")
            time.sleep(LOOP_interval)
            
            # Check 24h limit
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > 86400:
                Logger.success("✅ 24-Hour Simulation Complete.")
                break
                
    except KeyboardInterrupt:
        Logger.info(f"\n🛑 Execution Interrupted by User. Final zXP: {total_zxp:.0f}")
        
if __name__ == "__main__":
    prompt_bridge_sequence()
    run_arbitrage_loop()
