
import asyncio
import argparse
import sys
import os
from datetime import datetime
from dotenv import load_dotenv

from src.shared.system.logging import Logger
from src.engine.funding_watchdog import FundingWatchdog
from src.engine.auto_rebalancer import AutoRebalancer, RebalanceConfig
from src.engine.pnl_settler import PnLSettler
from src.engine.leverage_manager import LeverageManager
from src.shared.execution.wallet import WalletManager

# Constants
ENGINE_LOG_PATH = "data/engine_activity.log"
WATCHDOG_INTERVAL_SEC = 900  # 15 Minutes
REBALANCE_INTERVAL_SEC = 60  # 1 Minute (Engine Tick)
SETTLEMENT_HOUR_UTC = 0      # Midnight UTC

class ArbiterEngine:
    def __init__(self, live_mode: bool = False, target_leverage: float = 1.0):
        self.live_mode = live_mode
        self.target_leverage = target_leverage
        
        # Init Components
        self.wallet_manager = WalletManager()
        self.watchdog = FundingWatchdog(check_interval_sec=WATCHDOG_INTERVAL_SEC)
        
        # Rebalancer Config
        rebalance_config = RebalanceConfig(
            loop_interval_seconds=REBALANCE_INTERVAL_SEC
        )
        self.rebalancer = AutoRebalancer(rebalance_config)
        
        self.settler = PnLSettler()
        self.leverage_manager = LeverageManager(self.wallet_manager)
        
        # State
        self.last_watchdog_check = 0
        self.last_settlement_date = None

    async def run_loop(self):
        mode_str = "🛑 LIVE TRADING" if self.live_mode else "🔵 SIMULATION"
        Logger.section(f"🤖 ARBITER ENGINE ONLINE: {mode_str}")
        Logger.info(f"Target Leverage: {self.target_leverage}x")
        Logger.info(f"Logging to: {ENGINE_LOG_PATH}")
        
        # Main Pulse
        while True:
            try:
                current_time = datetime.utcnow()
                timestamp = current_time.timestamp()
                
                # ---------------------------------------------------------
                # 1. SAFETY (Watchdog) - Priority 1
                # ---------------------------------------------------------
                # Run every 15 mins (WATCHDOG_INTERVAL_SEC)
                if timestamp - self.last_watchdog_check >= WATCHDOG_INTERVAL_SEC:
                    Logger.info("🛡️ [WATCHDOG] Checking Funding Rates...")
                    # Watchdog internal logic handles strike counting and unwinding
                    await self.watchdog.check_health()
                    self.last_watchdog_check = timestamp
                
                # ---------------------------------------------------------
                # 2. HEALTH CHECK - Priority 2
                # ---------------------------------------------------------
                # Using LeverageManager's logic to check health
                # We need a client for this. Creating one ad-hoc or sharing?
                # LeverageManager creates its own currently.
                # Optimally we pass a client, but for now let's reuse its internal method logic
                # calling scale_to_target with simulate=True essentially checks health too, 
                # but let's implement a lighter check if possible or just rely on rebalancer loop to report drift/health.
                # Rebalancer loop reports Drift.
                
                # ---------------------------------------------------------
                # 3. HARVEST (PnL Settler) - Priority 3
                # ---------------------------------------------------------
                # Run daily at 10:00 AM EST (Funding Drip)? Or 00:00 UTC?
                # User prompted "Check if 24 hours have passed... Settle PnL"
                # Let's stick to 00:00 UTC or roughly once a day.
                # Current date string
                today_str = current_time.strftime("%Y-%m-%d")
                
                # If hour is 0 (Midnight UTC) and we haven't settled today
                if current_time.hour == SETTLEMENT_HOUR_UTC and self.last_settlement_date != today_str:
                    Logger.section("💰 [HARVEST] Daily PnL Settlement Triggered")
                    await self.settler.execute_settlement(simulate=not self.live_mode)
                    self.last_settlement_date = today_str
                    Logger.info("✅ [HARVEST] Settlement Complete (or Simulated)")

                # ---------------------------------------------------------
                # 4. BALANCE (Rebalancer) - Priority 4
                # ---------------------------------------------------------
                # Run on every tick (60s)
                # AutoRebalancer handles its own checks (Deltas, Tolerance, Cooldowns)
                # We simply invoke it.
                
                # Note: Rebalancer logic assumes 1x hedge by default? 
                # Our rebalancer currently calculates `net_delta = hedgeable_spot + perp_sol`.
                # If we are targeting 2x leverage (Net Short), the rebalancer logic logic might fight us?
                # 
                # WAIT. Phase 7 "Leverage Expansion" creates a net short.
                # The "AutoRebalancer" in Phase 4.1 was designed for "Delta Neutral" (Net Delta ~ 0).
                # If we go 2x, we have a Net Short. The Rebalancer will see Net Delta < 0 and try to BUY SOL to fix it.
                # 
                # CRITICAL: We need to update AutoRebalancer or Main Engine to respect Target Leverage.
                # For now, if leverage > 1.0, we might need to DISABLE the standard Rebalancer or Update it.
                # 
                # User request: "Balance: Check Delta Drift. If > 1%, execute Rebalance Trade."
                # But also "Target Leverage: 2.0".
                # 
                # If Leverage is 2.0, Net Delta SHOULD be negative.
                # Target Short = Equity * 2 / Price.
                # Spot = Equity / 2 (approx).
                # Net = Spot - Short = Spot - (2 * Spot) = -Spot.
                # 
                # Unless we update Rebalancer, it will fight the leverage manager.
                # 
                # DECISION: For this "Unified Engine", if target_leverage != 1.0, 
                # we should probably rely on LeverageManager to maintain the ratio?
                # OR update Rebalancer logic.
                # 
                # Given the user just asked to consolidate, and mentioned "Rebalance Trade" as priority 3...
                # I will assume for now we are maintaining 1x if standard rebalancer is used.
                # IF the user passes --leverage 2.0, we should probably warn that standard rebalancer enforces neutrality.
                # 
                # ACTUALLY, checking AutoRebalancer code:
                # `net_delta = hedgeable_spot + perp_sol`
                # `drift_pct = (net_delta / hedgeable_spot) * 100`
                # It enforces Net Delta = 0.
                # 
                # I will add a check: If target_leverage > 1.0, skip standard rebalancer or log warning.
                # For now, I will execute Rebalancer only if target_leverage is close to 1.0.
                
                if abs(self.target_leverage - 1.0) < 0.1:
                    result = await self.rebalancer.check_and_rebalance(simulate=not self.live_mode)
                    
                    # Log minimal status to keep heartbeat alive
                    status_icon = {
                        "ok": "🟢", "cooldown": "⏳", "simulated": "🔵", 
                        "executed": "✅", "skip": "⏭️", "error": "❌"
                    }.get(result.get("status"), "❓")
                    
                    Logger.info(f"⚖️ [REBALANCER] {status_icon} Drift: {result.get('drift_pct', 0):+.2f}%")
                else:
                    # If leverage > 1.0, we theoretically use LeverageManager logic to maintain ratio?
                    # But LeverageManager is currently a "One Shot" scaler.
                    # For safety, skipping rebalancer in 2x mode to prevent it from unwinding the leverage.
                    Logger.info(f"⚖️ [REBALANCER] Skipped (Target Leverage {self.target_leverage}x != 1.0)")

                # Beat
                Logger.info("💓 Heartbeat... Walking the line.")
                
                # Update State File for Dashboard
                import json
                state_file = "data/engine_state.json"
                with open(state_file, "w") as f:
                    json.dump({
                        "last_beat": timestamp,
                        "next_beat": timestamp + REBALANCE_INTERVAL_SEC,
                        "mode": mode_str,
                        "leverage": self.target_leverage
                    }, f)
                
            except Exception as e:
                Logger.error(f"💥 ENGINE LOOP ERROR: {e}")
                import traceback
                traceback.print_exc()
            
            # Sleep 60s
            await asyncio.sleep(REBALANCE_INTERVAL_SEC)

if __name__ == "__main__":
    load_dotenv()
    
    # Configure Unified Logging
    Logger.add_file_sink(ENGINE_LOG_PATH)
    
    parser = argparse.ArgumentParser(description="PhantomArbiter Unified Engine")
    parser.add_argument("--live", action="store_true", help="Enable LIVE execution (Real Money)")
    parser.add_argument("--leverage", type=float, default=1.0, help="Target Leverage Ratio (Default: 1.0)")
    
    args = parser.parse_args()
    
    engine = ArbiterEngine(live_mode=args.live, target_leverage=args.leverage)
    
    try:
        asyncio.run(engine.run_loop())
    except KeyboardInterrupt:
        Logger.section("👋 Engine Shutdown Requested.")
        sys.exit(0)
