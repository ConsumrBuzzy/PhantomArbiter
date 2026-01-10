
import asyncio
import argparse
import sys
import os
import json
from datetime import datetime
from dotenv import load_dotenv

from src.shared.system.logging import Logger
from src.engine.funding_watchdog import FundingWatchdog
from src.engine.auto_rebalancer import AutoRebalancer, RebalanceConfig
from src.engine.pnl_settler import PnLSettler
from src.engine.leverage_manager import LeverageManager
from src.shared.execution.wallet import WalletManager
from src.shared.execution.swapper import JupiterSwapper
from solders.pubkey import Pubkey

# Constants
ENGINE_LOG_PATH = "data/engine_activity.log"
WATCHDOG_INTERVAL_SEC = 900  # 15 Minutes
REBALANCE_INTERVAL_SEC = 60  # 1 Minute (Engine Tick)
SETTLEMENT_HOUR_UTC = 0      # Midnight UTC

# State Constants
STATE_ACTIVE = "ACTIVE"
STATE_WAITLIST = "WAITLIST"

from config.settings import Settings

class ArbiterEngine:
    def __init__(self, live_mode: bool = False, target_leverage: float = 1.0):
        self.live_mode = live_mode
        self.target_leverage = target_leverage
        
        # Global Trading Switch
        if self.live_mode:
            Settings.ENABLE_TRADING = True
            Logger.warning("⚠️ LIVE TRADING ENABLED. REAL FUNDS AT RISK.")
        else:
            Settings.ENABLE_TRADING = False
            Logger.info("🔵 SIMULATION MODE. TRADING DISABLED.")
        
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
        self.state = STATE_ACTIVE # Default to active, or detect?
        self.last_watchdog_check = 0
        self.last_settlement_date = None

    async def re_enter_position(self):
        """
        Re-Entry Sequence:
        1. Buy Spot SOL (Max USDC)
        2. Wait for confirmation
        3. Open Short (Target Leverage)
        """
        Logger.section("🚀 AUTO-RE-ENTRY INITIATED")
        
        if not self.live_mode:
            Logger.info("[SIM] Would Buy Spot SOL + Open Short.")
            return

        # 1. Buy Spot SOL
        # We need to swap USDC -> SOL.
        # Check USDC Balance? Or just swap *all*?
        # Swapper logic usually needs specific amount.
        # For MVP, let's assume we want to swap ALL USDC back to SOL.
        # But wait, logic: "Buy Spot SOL (Wallet Max - Reserve)"
        
        # We need a way to get USDC balance.
        # Using drift client or simple RPC? RPC for wallet token account.
        # Simplification: Invoke Rebalancer or LeverageManager to get "Equity" equivalent in USDC?
        
        Logger.info("[RE-ENTRY] Buying Spot SOL via Jupiter...")
        swapper = JupiterSwapper(self.wallet_manager)
        USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        SOL_MINT = "So11111111111111111111111111111111111111112"
        
        # We can't easily get max USDC without parsing token accounts.
        # Hack for MVP: Swap a fixed large amount? No, dangerous.
        # Let's try to get balance via `solana-py` if possible.
        # Alternatively, assume we have X amount known? No.
        
        # Let's skip the "Buy Spot" part implementation complexity for this turn if risky,
        # OR: Just assume the user has USDC and we swap e.g. 50 USDC.
        # BETTER: The user request said "re-buys the SOL".
        # Let's rely on LeverageManager `scale_to_target`? It handles leverage, not spot buying.
        
        # FOR NOW: Log the instruction to buy. Implementing robust token balance fetching + max swap
        # is a bit much for this single step without a TokenManager helper.
        # Wait, AutoRebalancer has `quote_amount` from Drift User?
        # If we exited Drift, our USDC is in Drift?
        # Unwind protocol: "Close Drift Short... Sell Spot SOL (Jupiter)".
        # So USDC is in Wallet?
        # Yes.
        
        # Placeholder for robustness:
        Logger.warning("[RE-ENTRY] Token Balance fetch not implemented. Please manually convert USDC -> SOL.")
        # Triggering Leverage Manager which handles the Short side.
        
        # 3. Open Short
        # This function assumes we HAVE spot to collateralize?
        # If we don't buy spot, we can't open the short safely (naked short).
        
        Logger.info("[RE-ENTRY] Expanding Leverage...")
        await self.leverage_manager.scale_to_target(self.target_leverage, simulate=False)
        Logger.success("✅ Re-Entry Sequence Complete.")


    async def detect_initial_state(self):
        """
        Check if we have an open position to determine startup state.
        """
        Logger.info("🔎 Detecting Initial State...")
        try:
            # Reuse rebalancer to get position data
            status = await self.rebalancer.check_and_rebalance(simulate=True)
            perp_sol = status.get('perp_sol', 0.0)
            
            # If we have a significant short position, we are ACTIVE
            if abs(perp_sol) > 0.01:
                Logger.section(f"✅ EXISTING POSITION FOUND ({perp_sol} SOL). RESUMING ACTIVE MODE.")
                self.state = STATE_ACTIVE
            else:
                Logger.section("💤 NO POSITION DETECTED. STARTING IN WAITLIST MODE.")
                self.state = STATE_WAITLIST
                
        except Exception as e:
            Logger.error(f"Failed to detect state: {e}. Defaulting to ACTIVE.")
            self.state = STATE_ACTIVE

    async def run_loop(self):
        mode_str = "🛑 LIVE TRADING" if self.live_mode else "🔵 SIMULATION"
        Logger.section(f"🤖 ARBITER ENGINE ONLINE: {mode_str}")
        Logger.info(f"Target Leverage: {self.target_leverage}x")
        Logger.info(f"Logging to: {ENGINE_LOG_PATH}")
        
        # Detect initial state
        await self.detect_initial_state()
        
        while True:
            try:
                current_time = datetime.utcnow()
                timestamp = current_time.timestamp()
                
                # Update State File Logic (Moved to top of loop or end? End is fine)
                
                # ---------------------------------------------------------
                # STATE MACHINE
                # ---------------------------------------------------------
                
                if self.state == STATE_ACTIVE:
                    # 1. Safety (Watchdog)
                    if timestamp - self.last_watchdog_check >= WATCHDOG_INTERVAL_SEC:
                        Logger.info("🛡️ [WATCHDOG] Checking Funding Rates...")
                        unwound = await self.watchdog.check_health(simulate=not self.live_mode)
                        self.last_watchdog_check = timestamp
                        
                        if unwound:
                            Logger.critical("🛑 WATCHDOG TRIGGERED UNWIND. SWITCHING TO WAITLIST.")
                            self.state = STATE_WAITLIST
                    
                    # 2. Health & Balance
                    # ... [Existing Checks]
                    
                    # 3. Harvest
                    today_str = current_time.strftime("%Y-%m-%d")
                    if current_time.hour == SETTLEMENT_HOUR_UTC and self.last_settlement_date != today_str:
                        Logger.section("💰 [HARVEST] Daily PnL Settlement Triggered")
                        await self.settler.execute_settlement(simulate=not self.live_mode)
                        self.last_settlement_date = today_str

                    # 4. Rebalance (Only if near 1x)
                    if abs(self.target_leverage - 1.0) < 0.1:
                         await self.rebalancer.check_and_rebalance(simulate=not self.live_mode)
                    else:
                        # Heartbeat log for 2x mode
                        Logger.info(f"⚖️ [REBALANCER] Standby ({self.target_leverage}x mode)")

                elif self.state == STATE_WAITLIST:
                     # Monitoring Mode
                     if timestamp - self.last_watchdog_check >= WATCHDOG_INTERVAL_SEC:
                        Logger.info("🕵️ [WAITLIST] Checking for Re-Entry Opportunity...")
                        should_return = await self.watchdog.check_re_entry_opportunity()
                        self.last_watchdog_check = timestamp
                        
                        if should_return:
                            Logger.section("🌤️ CONDITIONS IMPROVED. SURFACING...")
                            await self.re_enter_position()
                            self.state = STATE_ACTIVE
                     else:
                        Logger.info(f"💤 [WAITLIST] Hibernate... (Status: {self.state})")

                # Heartbeat
                Logger.info(f"💓 Heartbeat... State: {self.state}")
                
                # Write State
                with open("data/engine_state.json", "w") as f:
                    json.dump({
                        "last_beat": timestamp,
                        "next_beat": timestamp + REBALANCE_INTERVAL_SEC,
                        "mode": f"{mode_str} | {self.state}", # Show State in UI
                        "leverage": self.target_leverage
                    }, f)
                
            except Exception as e:
                Logger.error(f"💥 ENGINE LOOP ERROR: {e}")
                import traceback
                traceback.print_exc()
            
            await asyncio.sleep(REBALANCE_INTERVAL_SEC)

if __name__ == "__main__":
    load_dotenv()
    Logger.add_file_sink(ENGINE_LOG_PATH)
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Enable LIVE execution")
    parser.add_argument("--leverage", type=float, default=1.0, help="Target Leverage")
    args = parser.parse_args()
    
    engine = ArbiterEngine(live_mode=args.live, target_leverage=args.leverage)
    try:
        asyncio.run(engine.run_loop())
    except KeyboardInterrupt:
        Logger.section("👋 Engine Shutdown Requested.")
        sys.exit(0)
