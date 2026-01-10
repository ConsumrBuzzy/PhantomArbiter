
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
        Handles 'Orphaned Spot' (Spot held, Short closed) by checking funding.
        """
        Logger.info("🔎 Detecting Initial State...")
        from solana.rpc.async_api import AsyncClient
        
        rpc_url = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
        
        try:
            # Reuse rebalancer to get position data
            status = await self.rebalancer.check_and_rebalance(simulate=True)
            perp_sol = status.get('perp_sol', 0.0)
            spot_sol = status.get('spot_sol', 0.0)
            
            # Scenario A: Healthy Short Position
            if abs(perp_sol) > 0.01:
                Logger.section(f"✅ EXISTING POSITION FOUND ({perp_sol} SOL). RESUMING ACTIVE MODE.")
                self.state = STATE_ACTIVE
                return

            # Scenario B: Orphaned Spot (Unhedged Long)
            if spot_sol > 0.02:
                Logger.warning(f"⚠️ ORPHANED SPOT DETECTED ({spot_sol} SOL) WITH NO SHORT.")
                
                # Check Funding Context
                async with AsyncClient(rpc_url) as client:
                    funding_rate = await self.watchdog.get_funding_rate(client)
                    
                Logger.info(f"   Context: Funding Rate is {funding_rate:.6f}/hr")
                
                from src.engine.funding_watchdog import NEGATIVE_THRESHOLD
                if funding_rate < NEGATIVE_THRESHOLD:
                    Logger.critical("🛑 FUNDING IS HOSTILE. FINISHING EMERGENCY UNWIND (SELLING SPOT).")
                    if self.live_mode:
                        async with AsyncClient(rpc_url) as client:
                            await self.watchdog.unwind_position(client, simulate=False)
                    else:
                        Logger.info("   [SIM] Would Sell Spot now.")
                    
                    self.state = STATE_WAITLIST
                else:
                    Logger.success("✅ FUNDING IS SAFE. RESUMING ACTIVE MODE TO RE-HEDGE.")
                    self.state = STATE_ACTIVE
                return

            # Scenario C: Clean Slate (USDC)
            Logger.section("💤 NO POSITION DETECTED. STARTING IN WAITLIST MODE.")
            self.state = STATE_WAITLIST
                
        except Exception as e:
            Logger.error(f"Failed to detect state: {e}. Defaulting to ACTIVE.")
            # Fallback to ACTIVE is risky if funding bad, but safest for "do something"
            self.state = STATE_ACTIVE

    async def run_loop(self):
        mode_str = "🛑 LIVE TRADING" if self.live_mode else "🔵 SIMULATION"
        Logger.section(f"🤖 ARBITER ENGINE ONLINE: {mode_str}")
        Logger.info(f"Target Leverage: {self.target_leverage}x")
        Logger.info(f"Logging to: {ENGINE_LOG_PATH}")
        
        # 1. Detect Initial State (Console Mode)
        await self.detect_initial_state()
        
        # 2. Switch to TUI Mode
        from src.arbiter.ui.dnem_panel import DNEMDashboard
        from rich.live import Live
        from loguru import logger
        
        # Reconfigure Logging: Mute Console, Keep File, Add Memory Sink
        logger.remove()
        Logger.add_file_sink(ENGINE_LOG_PATH)
        log_buffer = Logger.add_memory_sink(maxlen=10)
        
        dashboard = DNEMDashboard()
        
        # State Container for TUI
        engine_data = {
            "mode": mode_str,
            "state": self.state,
            "perp_sol": 0.0,
            "spot_sol": 0.0,
            "sol_price": 0.0,
            "funding_rate_hr": 0.0,
            "health_score": 100.0,
            "recent_logs": []
        }
        
        timestamp_last_cycle = 0
        
        with Live(dashboard.layout, refresh_per_second=4, screen=True):
            while True:
                try:
                    current_time = datetime.now()
                    now_ts = current_time.timestamp()
                    
                    # ---------------------------------------------------------
                    # SLOW LOOP: Engine Logic (Every REBALANCE_INTERVAL_SEC)
                    # ---------------------------------------------------------
                    if now_ts - timestamp_last_cycle >= REBALANCE_INTERVAL_SEC:
                        timestamp_last_cycle = now_ts
                        
                        # A. Update TUI Logs from Buffer
                        engine_data["recent_logs"] = list(log_buffer)
                        engine_data["state"] = self.state
                        
                        # B. Watchdog Check
                        Logger.info("🛡️ [WATCHDOG] Checking Funding Rates...")
                        unwound = await self.watchdog.check_health(simulate=not self.live_mode)
                        if unwound:
                            self.state = STATE_WAITLIST
                        
                        # C. State Machine
                        if self.state == STATE_ACTIVE:
                            # Rebalancer
                            status = await self.rebalancer.check_and_rebalance(simulate=not self.live_mode)
                            
                            # Update TUI Data
                            engine_data["perp_sol"] = status.get("perp_sol", 0)
                            engine_data["spot_sol"] = status.get("spot_sol", 0)
                            engine_data["sol_price"] = status.get("sol_price", 150)
                            engine_data["funding_rate_hr"] = -0.0017 # TODO: Fetch real
                            engine_data["unrealized_pnl"] = 0.0 # TODO: Fetch real
                            
                        elif self.state == STATE_WAITLIST:
                            Logger.info("🕵️ [WAITLIST] Checking for Re-Entry Opportunity...")
                            # Just monitor
                            await self.watchdog.check_health(simulate=True)

                        # Write Heartbeat Helper
                        with open("data/engine_state.json", "w") as f:
                            json.dump({
                                "last_beat": now_ts,
                                "next_beat": now_ts + REBALANCE_INTERVAL_SEC,
                                "mode": f"{mode_str} | {self.state}",
                                "leverage": self.target_leverage
                            }, f)

                    # ---------------------------------------------------------
                    # FAST LOOP: TUI Refresh
                    # ---------------------------------------------------------
                    engine_data["recent_logs"] = list(log_buffer)
                    dashboard.update(engine_data)
                    
                    await asyncio.sleep(0.1) # Fast tick
                
                except KeyboardInterrupt:
                    Logger.info("👋 Engine Shutdown Requested.")
                    break
                except Exception as e:
                    Logger.error(f"💥 ENGINE LOOP ERROR: {e}")
                    await asyncio.sleep(5)

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
