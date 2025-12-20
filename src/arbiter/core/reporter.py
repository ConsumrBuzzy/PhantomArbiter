"""
Arbiter Reporter
================
Handles session reporting, ROI calculations, and persistence.
Integrates with CapitalManager and DBManager.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from src.shared.system.logging import Logger
from src.shared.system.db_manager import db_manager

class ArbiterReporter:
    """Consolidates reporting and session tracking for the Arbiter."""
    
    def __init__(self, telegram=None, capital_manager=None):
        self.telegram = telegram
        self.capital_manager = capital_manager
        self.sessions_dir = Path("data/sessions")
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def print_summary(self, start_time: float, mode: str, engine_name: str = "ARBITER"):
        """Print final session summary to console."""
        duration = time.time() - start_time
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Get data from CapitalManager if available
        if self.capital_manager:
            state = self.capital_manager.get_engine_state(engine_name)
            stats = state.get("stats", {})
            pnl = stats.get("total_pnl_usd", 0.0)
            wins = stats.get("wins", 0)
            losses = stats.get("losses", 0)
            daily_start = state.get("daily_start_equity", 0.0)
            current_bal = state.get("cash_balance", 0.0)
            
            total_trades = wins + losses
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
            roi = (pnl / daily_start * 100) if daily_start > 0 else 0
        else:
            # Fallback (though unlikely in this refactor)
            pnl = 0.0
            wins = losses = total_trades = win_rate = roi = 0
            current_bal = 0.0

        print("\n" + "═"*60)
        print(f" 🏁 SESSION COMPLETE | {now}")
        print("═"*60)
        print(f"   Mode:      {mode}")
        print(f"   Duration:  {duration/60:.1f} minutes")
        print(f"   Trades:    {total_trades} ({wins}W / {losses}L | {win_rate:.1f}% WR)")
        print(f"   Session:   ${pnl:+.4f} ({roi:+.2f}% ROI)")
        print(f"   Final Bal: ${current_bal:.2f}")
        print("═"*60 + "\n")

    def save_session(self, mode: str, total_trades: int, engine_name: str = "ARBITER"):
        """Save session data to JSON for history tracking."""
        if not self.capital_manager:
            return
            
        state = self.capital_manager.get_engine_state(engine_name)
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        
        filename = self.sessions_dir / f"session_{timestamp}.json"
        
        data = {
            "timestamp": now.isoformat(),
            "mode": mode,
            "total_trades": total_trades,
            "final_state": state,
            "version": "12.5_SRP"
        }
        
        try:
            with open(filename, 'w') as f:
                json.dump(data, f, indent=4)
            Logger.info(f"💾 Session data saved to {filename}")
        except Exception as e:
            Logger.error(f"Failed to save session: {e}")

    def update_telegram(self, message: str):
        """Update the Telegram dashboard."""
        if self.telegram:
            self.telegram.update_dashboard(message)
