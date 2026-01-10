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

    def print_dashboard(
        self,
        spreads: List[SpreadOpportunity],
        balance: float,
        gas: float,
        daily_profit: float,
        total_trades: int = 0,
        volume: float = 0,
        turnover: float = 0,
        verified_opps: List[SpreadOpportunity] = None,
        pod_names: List[str] = None,
    ):
        """Print the market dashboard."""
        from src.arbiter.ui.dashboard_formatter import DashboardFormatter

        # 1. Terminal Output
        print(
            DashboardFormatter.format_terminal_header(
                balance=balance,
                gas=gas,
                daily_profit=daily_profit,
                pod_names=pod_names,
                trades=total_trades,
                volume=volume,
                turnover=turnover,
            )
        )

        # Merge verified status for rows
        verified_map = {op.pair: op for op in (verified_opps or [])}
        profitable_count = 0

        for opp in spreads:
            verified = verified_map.get(opp.pair)
            status = (
                getattr(verified, "verification_status", None) if verified else None
            )

            # Near-miss enrichment
            if not status:
                metrics = NearMissAnalyzer.calculate_metrics(opp)
                status = metrics.status_icon

            print(DashboardFormatter.format_terminal_row(opp, status_override=status))
            if opp.is_profitable:
                profitable_count += 1

        print("-" * 75)
        if profitable_count > 0:
            print(
                f"   🎯 {profitable_count} profitable opportunit{'y' if profitable_count == 1 else 'ies'}!"
            )

        # 2. Telegram Output
        if self.telegram:
            final_msg = DashboardFormatter.format_telegram_dashboard(
                spreads=spreads,
                balance=balance,
                gas=gas,
                daily_profit=daily_profit,
                pod_names=pod_names,
            )
            self.telegram.update_dashboard(final_msg)

    def print_summary(
        self,
        start_time: float,
        initial_balance: float,
        final_balance: float,
        trades: List[Dict],
        mode_str: str = "PAPER",
    ):
        """Print session summary."""
        duration = (time.time() - start_time) / 60
        profit = final_balance - initial_balance
        if initial_balance > 0:
            roi = (profit / initial_balance) * 100
        else:
            roi = 0.0

        print("\n" + "=" * 70)
        print(f"   SESSION SUMMARY ({mode_str})")
        print("=" * 70)
        print(f"   Runtime:      {duration:.1f} minutes")
        print(f"   Starting:     ${initial_balance:.2f}")
        print(f"   Ending:       ${final_balance:.4f}")
        print(f"   Profit:       ${profit:+.4f}")
        print(f"   ROI:          {roi:+.2f}%")
        print(f"   Trades:       {len(trades)}")
        print("=" * 70)
        print("")

        # Send to Telegram
        if self.telegram:
            self.telegram.send_alert(
                f"🏁 <b>Session Ended</b>\n"
                f"Runtime: {duration:.1f} min\n"
                f"Profit: ${profit:+.4f} (ROI: {roi:+.2f}%)\n"
                f"Trades: {len(trades)}"
            )

    def save_session(
        self,
        trades: List[Dict],
        initial_balance: float,
        final_balance: float,
        start_time: float,
        tracker_data: Any = None,
    ):
        """Save session data to JSON."""
        try:
            session_data = {
                "timestamp": datetime.now().isoformat(),
                "duration_sec": time.time() - start_time,
                "initial_balance": initial_balance,
                "final_balance": final_balance,
                "profit": final_balance - initial_balance,
                "trades": trades,
                "stats": tracker_data.get_stats() if tracker_data else {},
            }

            # Ensure directory exists
            Path("data/trading_sessions").mkdir(parents=True, exist_ok=True)

            filename = f"data/trading_sessions/live_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, "w") as f:
                json.dump(session_data, f, indent=4)

            print(f"   Session saved: {filename}")

        except Exception as e:
            Logger.error(f"Failed to save session: {e}")
