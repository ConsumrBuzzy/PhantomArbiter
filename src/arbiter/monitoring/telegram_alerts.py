"""
V1.1: Telegram Alerts for Arbitrage
===================================
Sends notifications for opportunities and executed trades.

Uses the existing NotificationService for reliable delivery.
"""

import time
from typing import Optional
from config.settings import Settings
from src.system.logging import Logger


class ArbitrageTelegramAlerts:
    """
    Telegram notification handler for arbitrage events.
    
    Sends alerts for:
    - High-value opportunities detected
    - Trade executions (entry/exit)
    - Periodic status updates (every N minutes)
    - Daily summaries
    """
    
    def __init__(self):
        self.enabled = getattr(Settings, 'TELEGRAM_ENABLED', True)
        self.alert_threshold = getattr(Settings, 'TELEGRAM_ALERT_THRESHOLD', 0.3)
        
        # Status update interval (seconds)
        self.status_interval = 300  # 5 minutes
        self.last_status_time = 0.0
        
        # Try to import existing notifier
        self._notifier = None
        self._init_notifier()
    
    def _init_notifier(self):
        """Initialize the notification service."""
        try:
            from src.utils.notifications import get_notifier
            self._notifier = get_notifier()
            if self._notifier and self._notifier.enabled:
                Logger.info("📱 Telegram alerts enabled for arbitrage")
        except Exception as e:
            Logger.debug(f"Telegram notifier init error: {e}")
    
    def _send(self, message: str, priority: str = "INFO"):
        """Send message via Telegram."""
        if not self.enabled or not self._notifier:
            Logger.debug(f"[TG] {message[:50]}...")
            return
            
        try:
            self._notifier.send_alert(message, priority)
        except Exception as e:
            Logger.debug(f"Telegram send error: {e}")
    
    def alert_opportunity(self, opportunity) -> None:
        """Alert for a detected opportunity above threshold."""
        if opportunity.spread_pct < self.alert_threshold:
            return  # Below threshold
            
        emoji = "🔔" if opportunity.spread_pct >= 0.5 else "📊"
        
        msg = (
            f"{emoji} <b>ARBITRAGE OPPORTUNITY</b>\n\n"
            f"Pair: <code>{opportunity.pair}</code>\n"
            f"Spread: <code>+{opportunity.spread_pct:.2f}%</code>\n"
            f"Buy: {opportunity.buy_dex} @ <code>{opportunity.buy_price:.6f}</code>\n"
            f"Sell: {opportunity.sell_dex} @ <code>{opportunity.sell_price:.6f}</code>\n\n"
            f"Est. Profit: <code>${opportunity.net_profit_usd:.2f}</code>\n"
            f"Status: <code>{opportunity.status}</code>"
        )
        
        self._send(msg, "INFO")
    
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
            f"{emoji} <b>ARBITRAGE EXECUTED</b>\n\n"
            f"Pair: <code>{pair}</code>\n"
            f"Strategy: <code>{strategy}</code>\n"
            f"Size: <code>${size_usd:.2f}</code>\n\n"
            f"Result: <code>{profit_sign}${profit_usd:.2f}</code>\n\n"
            f"<b>Daily P&L:</b> <code>{profit_sign}${daily_profit:.2f} ({daily_return_pct:+.2f}%)</code>"
        )
        
        self._send(msg, "SELL" if profit_usd >= 0 else "STOP_LOSS")
    
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
