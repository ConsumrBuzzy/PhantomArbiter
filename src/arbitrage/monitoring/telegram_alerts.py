"""
V1.0: Telegram Alerts for Arbitrage
===================================
Sends notifications for opportunities and executed trades.
"""

from typing import Optional
from config.settings import Settings
from src.system.logging import Logger


class ArbitrageTelegramAlerts:
    """
    Telegram notification handler for arbitrage events.
    
    Sends alerts for:
    - High-value opportunities detected
    - Trade executions
    - Daily summaries
    """
    
    def __init__(self):
        self.enabled = getattr(Settings, 'TELEGRAM_ENABLED', True)
        self.alert_threshold = getattr(Settings, 'TELEGRAM_ALERT_THRESHOLD', 0.3)
        
        # Try to import existing telegram module
        self._notifier = None
        try:
            from src.utils.notifications import TelegramNotifier
            self._notifier = TelegramNotifier()
        except Exception:
            pass
    
    def _send(self, message: str):
        """Send message via Telegram."""
        if not self.enabled or not self._notifier:
            Logger.debug(f"[TG] {message}")
            return
            
        try:
            self._notifier.send(message, parse_mode='Markdown')
        except Exception as e:
            Logger.debug(f"Telegram send error: {e}")
    
    def alert_opportunity(self, opportunity) -> None:
        """Alert for a detected opportunity."""
        if opportunity.spread_pct < self.alert_threshold:
            return  # Below threshold
            
        emoji = "🔔" if opportunity.spread_pct >= 0.5 else "📊"
        
        msg = (
            f"{emoji} *ARBITRAGE OPPORTUNITY*\n\n"
            f"Pair: `{opportunity.pair}`\n"
            f"Spread: `+{opportunity.spread_pct:.2f}%`\n"
            f"Buy: {opportunity.buy_dex} @ `{opportunity.buy_price:.6f}`\n"
            f"Sell: {opportunity.sell_dex} @ `{opportunity.sell_price:.6f}`\n\n"
            f"Est. Profit: `${opportunity.net_profit_usd:.2f}`\n"
            f"Status: `{opportunity.status}`"
        )
        
        self._send(msg)
    
    def alert_trade_executed(
        self,
        pair: str,
        strategy: str,
        size_usd: float,
        profit_usd: float,
        daily_profit: float,
        daily_return_pct: float
    ) -> None:
        """Alert for an executed trade."""
        emoji = "✅" if profit_usd >= 0 else "⚠️"
        profit_sign = "+" if profit_usd >= 0 else ""
        
        msg = (
            f"{emoji} *ARBITRAGE EXECUTED*\n\n"
            f"Pair: `{pair}`\n"
            f"Strategy: `{strategy}`\n"
            f"Size: `${size_usd:.2f}`\n\n"
            f"Result: `{profit_sign}${profit_usd:.2f}`\n\n"
            f"*Daily P&L:* `{profit_sign}${daily_profit:.2f} ({daily_return_pct:+.2f}%)`"
        )
        
        self._send(msg)
    
    def send_daily_summary(self, tracker) -> None:
        """Send end-of-day summary."""
        profit = tracker.daily_profit
        emoji = "📈" if profit >= 0 else "📉"
        profit_sign = "+" if profit >= 0 else ""
        
        msg = (
            f"{emoji} *DAILY SUMMARY*\n\n"
            f"• Turnover: `{tracker.turnover_ratio:.1f}x`\n"
            f"• Trades: `{tracker.trade_count}`\n"
            f"• Volume: `${tracker.daily_volume:,.2f}`\n"
            f"• Profit: `{profit_sign}${profit:.2f} ({tracker.daily_return_pct:+.2f}%)`\n\n"
            f"_Projected APY: {tracker.effective_apy:+,.0f}%_"
        )
        
        self._send(msg)
    
    def send_status_update(self, dashboard) -> None:
        """Send periodic status update."""
        msg = dashboard.get_telegram_summary()
        self._send(msg)
