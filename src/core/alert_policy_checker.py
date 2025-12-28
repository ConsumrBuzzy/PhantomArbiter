"""
V133: AlertPolicyChecker - Extracted from DataBroker (SRP Refactor)
==================================================================
Handles market metric monitoring and threshold-based alerting.

Responsibilities:
- Check Raw Market/DEX metrics against configured thresholds
- Manage alert cooldowns to prevent spam
- Send consolidated notifications via Telegram
"""

import time
import asyncio
from typing import Optional, Dict, List
from config.settings import Settings
from src.shared.system.logging import Logger
from src.shared.system.comms_daemon import send_telegram


class AlertPolicyChecker:
    """
    V133: Monitors market metrics and fires alerts based on policies.
    
    This component manages the state for alert cooldowns and executes
    the periodic check against MarketAggregator metrics.
    """
    
    def __init__(self, market_aggregator):
        """
        Initialize AlertPolicyChecker.
        
        Args:
            market_aggregator: Instance of MarketAggregator to pull metrics from
        """
        self.market_aggregator = market_aggregator
        self._last_alert_check = 0
        self._last_alert_sent: Dict[str, float] = {}
        
    def check(self):
        """
        Check market metrics against alert thresholds.
        Usually called every 60 seconds from the main loop.
        """
        now = time.time()
        # V40.0: Check interval (every 60 seconds)
        if now - self._last_alert_check < 60:
            return
        
        self._last_alert_check = now
        
        if not self.market_aggregator:
            return
        
        try:
            # Get raw metrics (async -> sync bridge)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                metrics = loop.run_until_complete(self.market_aggregator.get_raw_metrics())
            finally:
                loop.close()
            
            policies = getattr(Settings, 'ALERT_POLICIES', {})
            cooldown = policies.get('ALERT_COOLDOWN_SECONDS', 300)
            
            alerts = []
            
            # Policy 1: DEX Volatility High
            atr_threshold = policies.get('DEX_VOLATILITY_HIGH_ATR_PCT', 0.04)
            if metrics.get('atr_pct', 0) > atr_threshold:
                alert_key = 'dex_volatility'
                if self._can_send_alert(alert_key, cooldown):
                    alerts.append(f"🚨 **DEX ALERT:** Volatility HIGH! ATR: {metrics['atr_pct']*100:.2f}%")
                    self._mark_alert_sent(alert_key)
            
            # Policy 2: DEX Trend Breakout
            adx_threshold = policies.get('DEX_TREND_BREAKOUT_ADX', 30.0)
            if metrics.get('adx', 0) > adx_threshold:
                alert_key = 'dex_trend'
                if self._can_send_alert(alert_key, cooldown):
                    alerts.append(f"📈 **TREND ALERT:** Strong trend detected! ADX: {metrics['adx']:.1f}")
                    self._mark_alert_sent(alert_key)
            
            # Policy 3: dYdX Margin Low
            margin_threshold = policies.get('DYDX_MARGIN_LOW_RATIO', 0.30)
            if metrics.get('dydx_margin_ratio', 1.0) < margin_threshold and metrics.get('dydx_equity', 0) > 0:
                alert_key = 'dydx_margin'
                if self._can_send_alert(alert_key, cooldown):
                    alerts.append(f"⚠️ **dYdX RISK:** Margin low at {metrics['dydx_margin_ratio']*100:.1f}%!")
                    self._mark_alert_sent(alert_key)
            
            # Send consolidated alerts
            if alerts:
                alert_msg = "🔔 **ALERT NOTIFICATION**\n" + "\n".join(alerts)
                send_telegram(alert_msg, source="ALERT", priority="HIGH")
                Logger.info(f"⚡ [ALERT] Sent {len(alerts)} notifications")
                
        except Exception as e:
            Logger.warning(f"[ALERT_SERVICE] Alert check failed: {e}")

    def _can_send_alert(self, key: str, cooldown: int) -> bool:
        """Check if we can send an alert (respects cooldown)."""
        last_sent = self._last_alert_sent.get(key, 0)
        return time.time() - last_sent >= cooldown
    
    def _mark_alert_sent(self, key: str):
        """Mark an alert as sent."""
        self._last_alert_sent[key] = time.time()
