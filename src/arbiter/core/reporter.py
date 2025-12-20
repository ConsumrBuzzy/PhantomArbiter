"""
Reporter
========
Handles user interface, dashboard printing, and session summaries.
Separates "View" logic from the Arbiter "Controller".
"""

import time
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.shared.system.logging import Logger
from src.arbiter.core.spread_detector import SpreadOpportunity
from src.arbiter.core.near_miss_analyzer import NearMissAnalyzer
from src.shared.notification.telegram_manager import TelegramManager

class ArbiterReporter:
    """
    Handles all output (Console + Telegram) for the Arbiter.
    """
    
    def __init__(self, telegram: Optional[TelegramManager] = None):
        self.telegram = telegram
    
    def print_dashboard(self, 
                        spreads: List[SpreadOpportunity], 
                        balance: float,
                        gas: float,
                        daily_profit: float,
                        verified_opps: List[SpreadOpportunity] = None, 
                        pod_names: List[str] = None):
        """Print the market dashboard with merged verification status."""
        now = datetime.now().strftime("%H:%M:%S")
        
        # Verify map for O(1) lookup
        verified_map = {op.pair: op for op in (verified_opps or [])}
        
        # Pod info for display
        pod_str = f" | Pod: {','.join(pod_names)}" if pod_names else ""
        
        # Clear line and print table header
        print(f"\n   [{now}] MARKET SCAN | Bal: ${balance:.2f} | Gas: ${gas:.2f} | Day P/L: ${daily_profit:+.2f}")
        print(f"   {'Pair':<12} {'Buy':<8} {'Sell':<8} {'Spread':<8} {'Net':<10} {'Status'}")
        print("   " + "-"*60)
        
        profitable_count = 0
        
        for opp in spreads:
            # Check if we have verified data for this opp
            verified = verified_map.get(opp.pair)
            
            if verified:
                # Use verified data (Real Net Profit & Status)
                net_profit = verified.net_profit_usd
                spread_pct = verified.spread_pct
                
                # Status: "✅ LIVE" or "❌ LIQ ($...)"
                status = verified.verification_status or "✅ LIVE"
                if "LIVE" in status:
                     status = "✅ READY" # Keep UI consistent for good ones
                elif "LIQ" in status:
                     status = "❌ LIQ" # Shorten for table
                elif "SCALED" in status:
                     status = "⚠️ SCALED"
                
            else:
                # Use Scan data + NearMissAnalyzer for nuanced status
                net_profit = opp.net_profit_usd
                spread_pct = opp.spread_pct
                
                # Calculate near-miss metrics for rich status display
                metrics = NearMissAnalyzer.calculate_metrics(opp)
                status = metrics.status_icon
                
                # Add decay indicator if we have decay data
                try:
                    from src.shared.system.db_manager import db_manager
                    decay_v = db_manager.get_decay_velocity(opp.pair)
                    if decay_v > 0.1:
                        status += f" ⚡{decay_v:.1f}%/s"  # Fast decay warning
                    elif decay_v > 0:
                        status += f" 📉"  # Has decay data
                except:
                    pass
            
            if opp.is_profitable:
                profitable_count += 1
                
            # Color/Format based on status
            print(f"   {opp.pair:<12} {opp.buy_dex:<8} {opp.sell_dex:<8} +{spread_pct:.2f}%   ${net_profit:+.3f}    {status}")
        
        print("-" * 60)
        
        if profitable_count > 0:
            print(f"   🎯 {profitable_count} profitable opportunit{'y' if profitable_count == 1 else 'ies'}!")
        
        # ═══ TELEGRAM DASHBOARD ═══
        if self.telegram:
            tg_table = [
                f"[{now}] SCAN{pod_str} | P/L: ${daily_profit:+.2f}",
                f"{'Pair':<11} {'Spread':<7} {'Net':<8} {'St'}",
                "-" * 33
            ]
            
            # Add ALL rows to TG table
            for i, opp in enumerate(spreads):
                verified = verified_map.get(opp.pair)
                status = "❌"
                net = f"${opp.net_profit_usd:+.3f}"
                spread = f"{opp.spread_pct:+.2f}%"
                
                if verified:
                    net = f"${verified.net_profit_usd:+.3f}"
                    if "LIVE" in (verified.verification_status or ""):
                        status = "✅"
                    elif "SCALED" in (verified.verification_status or ""):
                        status = "⚠️"
                    elif "LIQ" in (verified.verification_status or ""):
                        status = "💧"
                else:
                    # Use NearMissAnalyzer for better status
                    metrics = NearMissAnalyzer.calculate_metrics(opp)
                    match metrics.status:
                        case "VIABLE": status = "✅"
                        case "NEAR_MISS": status = "⚡"
                        case "WARM": status = "🔸"
                        case _: status = "❌"
                
                tg_table.append(f"{opp.pair[:10]:<11} {spread:<7} {net:<8} {status}")
                
            if profitable_count:
                tg_table.append(f"\n🎯 {profitable_count} Opportunities!")
                
            # Beam to Telegram (Wrapped in Code Block)
            final_msg = "```\n" + "\n".join(tg_table) + "\n```"
            self.telegram.update_dashboard(final_msg)

    def print_summary(self, 
                      start_time: float, 
                      initial_balance: float,
                      final_balance: float,
                      trades: List[Dict],
                      mode_str: str = "PAPER"):
        """Print session summary."""
        duration = (time.time() - start_time) / 60
        profit = final_balance - initial_balance
        if initial_balance > 0:
            roi = (profit / initial_balance) * 100
        else:
            roi = 0.0
        
        print("\n" + "="*70)
        print(f"   SESSION SUMMARY ({mode_str})")
        print("="*70)
        print(f"   Runtime:      {duration:.1f} minutes")
        print(f"   Starting:     ${initial_balance:.2f}")
        print(f"   Ending:       ${final_balance:.4f}")
        print(f"   Profit:       ${profit:+.4f}")
        print(f"   ROI:          {roi:+.2f}%")
        print(f"   Trades:       {len(trades)}")
        print("="*70)
        print("")
        
        # Send to Telegram
        if self.telegram:
            self.telegram.send_alert(
                 f"🏁 <b>Session Ended</b>\n"
                 f"Runtime: {duration:.1f} min\n"
                 f"Profit: ${profit:+.4f} (ROI: {roi:+.2f}%)\n"
                 f"Trades: {len(trades)}"
            )

    def save_session(self, 
                     trades: List[Dict], 
                     initial_balance: float, 
                     final_balance: float, 
                     start_time: float, 
                     tracker_data: Any = None):
        """Save session data to JSON."""
        try:
            session_data = {
                "timestamp": datetime.now().isoformat(),
                "duration_sec": time.time() - start_time,
                "initial_balance": initial_balance,
                "final_balance": final_balance,
                "profit": final_balance - initial_balance,
                "trades": trades,
                "stats": tracker_data.get_stats() if tracker_data else {}
            }
            
            # Ensure directory exists
            Path("data/trading_sessions").mkdir(parents=True, exist_ok=True)
            
            filename = f"data/trading_sessions/live_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, "w") as f:
                json.dump(session_data, f, indent=4)
                
            print(f"   Session saved: {filename}")
            
        except Exception as e:
            Logger.error(f"Failed to save session: {e}")
