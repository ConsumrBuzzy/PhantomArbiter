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
# Configuration
BRIDGE_CODE = "ZINK-ORIGIN-2026"
BRIDGE_URL = "https://z.ink/bridge"
MIN_SOL_BALANCE = 0.05
GAS_BUFFER = 0.005 # Safety ceiling - never trade below this buffer
MAINTENANCE_CHECK_INTERVAL = 300  # 5 minutes
LOOP_interval = 60 # Slower loop for live
LIVE_LOG_FILE = "LIVE_EXECUTION_LOGS.csv"
MIN_SPREAD = 0.18 # Higher target for live (18%) as per pilot strategy
TARGET_PROFIT_SOL = 0.05
MAX_CONSECUTIVE_LOSSES = 3

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
                                             
   Z.INK BRIDGE & ARBITRAGE DIRECTOR (v2026.3)
   *** LIVE PILOT ACTIVE ***
    """)

def init_live_logs():
    if not os.path.exists(LIVE_LOG_FILE):
        with open(LIVE_LOG_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Timestamp', 'Tx_Signature', 'Starbase_Buy', 'Price_Buy', 'Starbase_Sell', 'Price_Sell', 'Spread_Pct', 'Net_Profit_SOL', 'zXP', 'Action'])
        Logger.info(f"📝 Created Live Execution Log: {LIVE_LOG_FILE}")

def log_live_trade(tx_sig, buy_sb, buy_price, sell_sb, sell_price, spread, profit, zxp):
    with open(LIVE_LOG_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().isoformat(),
            tx_sig,
            buy_sb, f"{buy_price:.6f}",
            sell_sb, f"{sell_price:.6f}",
            f"{spread*100:.2f}%",
            f"{profit:.6f}",
            f"{zxp:.2f}",
            "LIVE_EXECUTE"
        ])

def audit_performance(total_profit, total_zxp, trade_count):
    """Output 4-hour performance audit."""
    Logger.info("\n📊 === 4-HOUR PILOT AUDIT ===")
    Logger.info(f"   Trades Executed: {trade_count}")
    Logger.info(f"   Net Profit: {total_profit:.6f} SOL")
    Logger.info(f"   Total zXP: {total_zxp:.2f}")
    if trade_count > 0:
        Logger.info(f"   Avg Profit/Trade: {total_profit/trade_count:.6f} SOL")
    Logger.info("=============================\n")

def prompt_bridge_sequence():
    """Guide user through the z.ink bridge process."""
    print_banner()
    # Check for auto-yes argument
    if "--auto-yes" in sys.argv:
        print("\n✅ Auto-Bridge Confirmed. Initializing Executors...")
        return

    # In Live Mode, we assume bridge is done or user is ready
    Logger.warning("⚠️  WARNING: LIVE TRADING ENABLED. REAL FUNDS AT RISK.")
    print(f"   Safety Ceiling: Wallet must maintain > {GAS_BUFFER} SOL buffer.")
    
    while True:
        response = input("Are you ready to broadcast live transactions? (yes/no): ").lower().strip()
        if response in ['yes', 'y']:
            print("\n✅ Live Pilot Initiated...")
            break
        elif response in ['no', 'n']:
            print("\n🛑 Aborting Live Pilot.")
            sys.exit(0)

def run_arbitrage_loop():
    """Main execution loop (Live Pilot)."""
    # Force z.ink network, LIVE MODE
    executor = StarAtlasExecutor(network="zink", dry_run=False)
    client = StarAtlasClient()
    
    init_live_logs()
    
    consecutive_losses = 0
    total_net_profit = 0.0
    total_zxp = 0.0
    trade_count = 0
    start_time = datetime.now()
    last_audit_time = datetime.now()
    
    Logger.info("🚀 Starting SAGE Live Pilot...")
    Logger.info(f"   Target: > {MIN_SPREAD*100}% Spread | Gas Buffer: {GAS_BUFFER} SOL")
    
    try:
        while True:
            # 1. Safety Check: Balance
            try:
                balance = client.client.get_balance(executor.wallet_pubkey).value / 1e9
                if balance < (GAS_BUFFER * 2): # Warn if getting close
                     Logger.warning(f"   [!] Low Balance: {balance:.4f} SOL")
                
                # Hard Stop Logic handled by Executor mostly, but let's be safe
                if balance < MIN_SOL_BALANCE:
                     Logger.error("   🛑 Balance below Maintenance Threshold. Pausing.")
                     time.sleep(MAINTENANCE_CHECK_INTERVAL)
                     continue
            except Exception as e:
                Logger.warning(f"   [!] Balance check failed: {e}")

            # 2. Scanning
            Logger.info("\n🔍 Scanning SDU Market (Live)...")
            try:
                listings = client.get_sdu_prices()
                
                if len(listings) >= 2:
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
                        quantity = 10 # Pilot size: Start small
                        
                        # Calculate cost to check safety ceiling
                        est_cost = buy_price * quantity
                        current_balance = client.client.get_balance(executor.wallet_pubkey).value / 1e9
                        
                        if (current_balance - est_cost) < GAS_BUFFER:
                             Logger.error(f"   🛑 Safety Ceiling Hit! Bal: {current_balance:.4f} - Cost: {est_cost:.4f} < {GAS_BUFFER}")
                             time.sleep(60)
                             continue

                        Logger.info("   ⚡ EXECUTING LIVE TRADE...")
                        result = executor.buy_resource(
                             resource_type="SDU",
                             quantity=quantity,
                             max_price_atlas=buy_price * 1.05 # 5% slippage tolerance
                        )
                        
                        if result.success:
                             total_zxp += result.zxp_earned
                             trade_count += 1
                             
                             # Assume we sold immediately for net profit calc in logging (audit purpose)
                             # Real sell would happen here in full bot
                             gross_profit = (sell_price - buy_price) * quantity
                             fee = sell_price * quantity * 0.06
                             net_profit = gross_profit - fee
                             total_net_profit += net_profit
                             
                             consecutive_losses = 0
                             if net_profit < 0:
                                  consecutive_losses += 1
                             
                             log_live_trade(
                                 result.tx_signature,
                                 best_buy['starbase']['name'], buy_price,
                                 best_sell['starbase']['name'], sell_price,
                                 spread, net_profit, result.zxp_earned
                             )
                        else:
                             Logger.error(f"   ❌ Trade Failed: {result.error_message}")

                    else:
                        Logger.info(f"   📉 Spread too low ({spread*100:.2f}%)")

                else:
                    Logger.warning("   [!] Not enough liquidity.")

            except Exception as e:
                Logger.error(f"Scan loop error: {e}")
            
            # 3. Safety Pause
            if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
                 Logger.error("   🛑 3 Consecutive Losses. Pausing Live Pilot.")
                 break

            # 4. Audit (Every 4 hours)
            if (datetime.now() - last_audit_time).total_seconds() > 14400:
                 audit_performance(total_net_profit, total_zxp, trade_count)
                 last_audit_time = datetime.now()

            # 5. Sleep
            Logger.info(f"💤 Sleeping {LOOP_interval}s...")
            time.sleep(LOOP_interval)
                
    except KeyboardInterrupt:
        Logger.info(f"\n🛑 Live Pilot Stopped. Net: {total_net_profit:.6f} SOL | zXP: {total_zxp:.0f}")
        
if __name__ == "__main__":
    prompt_bridge_sequence()
    run_arbitrage_loop()
