"""
V1.0: Dashboard Formatter
=========================
Handles all visual formatting for the terminal and Telegram dashboards.
Responsible for "How the data looks".
"""

from datetime import datetime
from typing import List, Dict, Optional
from src.legacy.arbiter.core.spread_detector import SpreadOpportunity


class DashboardFormatter:
    """
    Static utility for formatting market data into tables and alerts.
    """

    @staticmethod
    def format_terminal_header(
        balance: float,
        gas: float,
        daily_profit: float,
        pod_names: List[str] = None,
        trades: int = 0,
        volume: float = 0,
        turnover: float = 0,
    ) -> str:
        """Create the terminal dashboard header."""
        now = datetime.now().strftime("%H:%M:%S")
        pod_str = f" | Pods: {','.join(pod_names)}" if pod_names else ""

        lines = [
            f"\n   [{now}] MARKET SCAN{pod_str}",
            f"   💰 Bal: ${balance:.2f} | ⛽ Gas: ${gas:.2f} | 📈 P/L: ${daily_profit:+.2f} ({trades} tx)",
            f"   📊 Vol: ${volume:,.0f} | 🔄 Turnover: {turnover:.1f}x",
            f"   {'Pair':<12} {'Buy':<8} {'Sell':<8} {'Spread':<8} {'Net':<10} {'Status'}",
            "   " + "-" * 75,
        ]
        return "\n".join(lines)

    @staticmethod
    def format_terminal_row(
        opp: SpreadOpportunity, status_override: Optional[str] = None
    ) -> str:
        """Format a single row for the terminal table."""
        status = (
            status_override or getattr(opp, "verification_status", None) or "🔍 SCAN"
        )

        # Shorten status for table
        if "LIVE" in status or "READY" in status:
            status = "✅ READY"
        elif "LIQ" in status:
            status = "❌ LIQ"
        elif "SLIP" in status:
            status = "❌ SLIP"
        elif "SCALED" in status:
            status = "⚠️ SCALED"

        net_profit = getattr(opp, "net_profit_usd", 0.0)

        return f"   {opp.pair:<12} {opp.buy_dex:<8} {opp.sell_dex:<8} +{opp.spread_pct:.2f}%   ${net_profit:+.3f}    {status}"

    @staticmethod
    def format_telegram_dashboard(
        spreads: List[SpreadOpportunity],
        balance: float,
        gas: float,
        daily_profit: float,
        pod_names: List[str] = None,
    ) -> str:
        """Create a compact dashboard for Telegram."""
        now = datetime.now().strftime("%H:%M:%S")
        pod_str = f" | {','.join(pod_names)}" if pod_names else ""

        lines = [
            f"[{now}] SCAN{pod_str}",
            f"💰 ${balance:.2f} | ⛽ ${gas:.2f} | P/L: ${daily_profit:+.2f}",
            f"{'Pair':<11} {'Spread':<7} {'Net':<8} {'St'}",
            "-" * 33,
        ]

        for opp in spreads:
            status_raw = getattr(opp, "verification_status", "") or ""
            status_icon = "🕵️"  # Default Scan

            if "LIVE" in status_raw or "READY" in status_raw:
                status_icon = "✅"
            elif "SCALED" in status_raw:
                status_icon = "⚠️"
            elif "LIQ" in status_raw:
                status_icon = "💧"
            elif "SLIP" in status_raw:
                status_icon = "📉"

            net = f"${opp.net_profit_usd:+.3f}"
            spread = f"{opp.spread_pct:+.2f}%"
            lines.append(f"{opp.pair[:10]:<11} {spread:<7} {net:<8} {status_icon}")

        return "```\n" + "\n".join(lines) + "\n```"

    @staticmethod
    def format_trade_announcement(trade: Dict, current_balance: float) -> str:
        """Format a successful trade announcement."""
        now = datetime.now().strftime("%H:%M:%S")
        emoji = "💰" if trade.get("net_profit", 0) > 0 else "📉"
        mode = trade.get("mode", "PAPER")

        lines = [
            f"   [{now}] {emoji} {mode} #{trade.get('id', '?')}: {trade['pair']}",
            f"            Spread: +{trade['spread_pct']:.2f}% → Net: ${trade['net_profit']:+.4f}",
            f"            Balance: ${current_balance:.4f}\n",
        ]
        return "\n".join(lines)
