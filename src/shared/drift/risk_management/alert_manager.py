"""
Alert Manager
============

Manages risk alerts and notifications across the trading system.
"""

from typing import List, Dict, Any, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import asyncio

from ..sdk.models.risk import RiskAlert
from src.shared.system.logging import Logger


class AlertChannel(Enum):
    """Alert delivery channels."""
    LOG = "log"
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"
    DATABASE = "database"


@dataclass
class AlertRule:
    """Alert rule configuration."""
    
    alert_type: str
    severity_threshold: str  # "info", "warning", "critical"
    channels: List[AlertChannel]
    cooldown_minutes: int = 5  # Minimum time between same alerts
    max_alerts_per_hour: int = 10  # Rate limiting
    enabled: bool = True


class AlertManager:
    """
    Manages risk alerts and notifications.
    
    Handles alert routing, rate limiting, and delivery across
    multiple channels (logging, email, Slack, webhooks, etc.).
    """
    
    def __init__(self):
        self.logger = Logger
        
        # Alert storage
        self._alert_history: List[RiskAlert] = []
        self._alert_counts: Dict[str, int] = {}  # For rate limiting
        self._last_alert_times: Dict[str, datetime] = {}  # For cooldown
        
        # Alert rules
        self._alert_rules: Dict[str, AlertRule] = {}
        self._setup_default_rules()
        
        # Alert handlers
        self._alert_handlers: Dict[AlertChannel, Callable] = {}
        self._setup_default_handlers()
        
        # Configuration
        self._max_history_size = 1000
        self._cleanup_interval_hours = 24
        
        # Start cleanup task
        asyncio.create_task(self._periodic_cleanup())
        
        self.logger.info("Alert Manager initialized")
    
    async def send_alert(self, alert: RiskAlert) -> bool:
        """
        Send risk alert through configured channels.
        
        Args:
            alert: Risk alert to send
            
        Returns:
            True if alert was sent successfully
        """
        try:
            # Check if alert should be sent
            if not self._should_send_alert(alert):
                return False
            
            # Get alert rule
            rule = self._alert_rules.get(alert.alert_type)
            if not rule or not rule.enabled:
                self.logger.debug(f"Alert type {alert.alert_type} not configured or disabled")
                return False
            
            # Check severity threshold
            if not self._meets_severity_threshold(alert.severity, rule.severity_threshold):
                return False
            
            # Check rate limiting
            if not self._check_rate_limit(alert, rule):
                self.logger.debug(f"Alert {alert.alert_id} rate limited")
                return False
            
            # Send through configured channels
            success = True
            for channel in rule.channels:
                try:
                    handler = self._alert_handlers.get(channel)
                    if handler:
                        await handler(alert)
                    else:
                        self.logger.warning(f"No handler configured for channel {channel}")
                        success = False
                except Exception as e:
                    self.logger.error(f"Error sending alert through {channel}: {e}")
                    success = False
            
            # Store alert in history
            self._store_alert(alert)
            
            # Update rate limiting counters
            self._update_rate_limiting(alert)
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error sending alert {alert.alert_id}: {e}")
            return False
    
    async def get_recent_alerts(
        self, 
        hours: int = 24,
        severity: Optional[str] = None,
        alert_type: Optional[str] = None
    ) -> List[RiskAlert]:
        """
        Get recent alerts with optional filtering.
        
        Args:
            hours: Number of hours to look back
            severity: Filter by severity level
            alert_type: Filter by alert type
            
        Returns:
            List of matching alerts
        """
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            filtered_alerts = []
            for alert in self._alert_history:
                # Time filter
                if alert.alert_time < cutoff_time:
                    continue
                
                # Severity filter
                if severity and alert.severity != severity:
                    continue
                
                # Type filter
                if alert_type and alert.alert_type != alert_type:
                    continue
                
                filtered_alerts.append(alert)
            
            # Sort by time (most recent first)
            filtered_alerts.sort(key=lambda x: x.alert_time, reverse=True)
            
            return filtered_alerts
            
        except Exception as e:
            self.logger.error(f"Error getting recent alerts: {e}")
            return []
    
    def get_alert_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get alert statistics for the specified period.
        
        Args:
            hours: Number of hours to analyze
            
        Returns:
            Dictionary with alert statistics
        """
        try:
            recent_alerts = asyncio.run(self.get_recent_alerts(hours))
            
            if not recent_alerts:
                return {
                    'total_alerts': 0,
                    'by_severity': {},
                    'by_type': {},
                    'alert_rate_per_hour': 0.0,
                    'most_common_type': None,
                    'analysis_period_hours': hours
                }
            
            # Count by severity
            severity_counts = {}
            for alert in recent_alerts:
                severity_counts[alert.severity] = severity_counts.get(alert.severity, 0) + 1
            
            # Count by type
            type_counts = {}
            for alert in recent_alerts:
                type_counts[alert.alert_type] = type_counts.get(alert.alert_type, 0) + 1
            
            # Calculate rate
            alert_rate = len(recent_alerts) / hours if hours > 0 else 0
            
            # Find most common type
            most_common_type = max(type_counts.items(), key=lambda x: x[1])[0] if type_counts else None
            
            return {
                'total_alerts': len(recent_alerts),
                'by_severity': severity_counts,
                'by_type': type_counts,
                'alert_rate_per_hour': alert_rate,
                'most_common_type': most_common_type,
                'analysis_period_hours': hours,
                'latest_alert_time': recent_alerts[0].alert_time.isoformat() if recent_alerts else None
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating alert statistics: {e}")
            return {}
    
    def configure_alert_rule(self, alert_type: str, rule: AlertRule) -> None:
        """
        Configure alert rule for specific alert type.
        
        Args:
            alert_type: Type of alert
            rule: Alert rule configuration
        """
        self._alert_rules[alert_type] = rule
        self.logger.info(f"Configured alert rule for {alert_type}")
    
    def add_alert_handler(self, channel: AlertChannel, handler: Callable) -> None:
        """
        Add custom alert handler for a channel.
        
        Args:
            channel: Alert channel
            handler: Async function to handle alerts
        """
        self._alert_handlers[channel] = handler
        self.logger.info(f"Added alert handler for {channel}")
    
    def disable_alert_type(self, alert_type: str) -> None:
        """Disable alerts for specific type."""
        if alert_type in self._alert_rules:
            self._alert_rules[alert_type].enabled = False
            self.logger.info(f"Disabled alerts for {alert_type}")
    
    def enable_alert_type(self, alert_type: str) -> None:
        """Enable alerts for specific type."""
        if alert_type in self._alert_rules:
            self._alert_rules[alert_type].enabled = True
            self.logger.info(f"Enabled alerts for {alert_type}")
    
    # ==========================================================================
    # PRIVATE METHODS
    # ==========================================================================
    
    def _setup_default_rules(self) -> None:
        """Setup default alert rules."""
        default_rules = {
            'var_breach': AlertRule(
                alert_type='var_breach',
                severity_threshold='critical',
                channels=[AlertChannel.LOG, AlertChannel.WEBHOOK],
                cooldown_minutes=10,
                max_alerts_per_hour=6
            ),
            'leverage_breach': AlertRule(
                alert_type='leverage_breach',
                severity_threshold='critical',
                channels=[AlertChannel.LOG, AlertChannel.WEBHOOK],
                cooldown_minutes=5,
                max_alerts_per_hour=12
            ),
            'drawdown_breach': AlertRule(
                alert_type='drawdown_breach',
                severity_threshold='warning',
                channels=[AlertChannel.LOG],
                cooldown_minutes=15,
                max_alerts_per_hour=4
            ),
            'concentration_risk': AlertRule(
                alert_type='concentration_risk',
                severity_threshold='warning',
                channels=[AlertChannel.LOG],
                cooldown_minutes=30,
                max_alerts_per_hour=2
            ),
            'health_ratio_breach': AlertRule(
                alert_type='health_ratio_breach',
                severity_threshold='critical',
                channels=[AlertChannel.LOG, AlertChannel.WEBHOOK],
                cooldown_minutes=5,
                max_alerts_per_hour=12
            ),
            'volatility_spike': AlertRule(
                alert_type='volatility_spike',
                severity_threshold='warning',
                channels=[AlertChannel.LOG],
                cooldown_minutes=20,
                max_alerts_per_hour=3
            )
        }
        
        self._alert_rules.update(default_rules)
    
    def _setup_default_handlers(self) -> None:
        """Setup default alert handlers."""
        self._alert_handlers = {
            AlertChannel.LOG: self._log_handler,
            AlertChannel.WEBHOOK: self._webhook_handler,
            AlertChannel.DATABASE: self._database_handler
        }
    
    async def _log_handler(self, alert: RiskAlert) -> None:
        """Handle alert through logging."""
        severity_map = {
            'info': self.logger.info,
            'warning': self.logger.warning,
            'critical': self.logger.error
        }
        
        log_func = severity_map.get(alert.severity, self.logger.info)
        log_func(f"🚨 RISK ALERT [{alert.alert_type.upper()}]: {alert.message}")
    
    async def _webhook_handler(self, alert: RiskAlert) -> None:
        """Handle alert through webhook (placeholder)."""
        # This would send HTTP POST to configured webhook URL
        self.logger.debug(f"Webhook alert: {alert.alert_id} - {alert.message}")
        # TODO: Implement actual webhook sending
    
    async def _database_handler(self, alert: RiskAlert) -> None:
        """Handle alert through database storage (placeholder)."""
        # This would store alert in database
        self.logger.debug(f"Database alert: {alert.alert_id} - {alert.message}")
        # TODO: Implement actual database storage
    
    def _should_send_alert(self, alert: RiskAlert) -> bool:
        """Check if alert should be sent."""
        # Basic validation
        if not alert.alert_id or not alert.alert_type or not alert.message:
            return False
        
        # Check cooldown
        last_time = self._last_alert_times.get(alert.alert_type)
        if last_time:
            rule = self._alert_rules.get(alert.alert_type)
            if rule:
                cooldown = timedelta(minutes=rule.cooldown_minutes)
                if datetime.now() - last_time < cooldown:
                    return False
        
        return True
    
    def _meets_severity_threshold(self, alert_severity: str, threshold: str) -> bool:
        """Check if alert meets severity threshold."""
        severity_levels = {'info': 1, 'warning': 2, 'critical': 3}
        
        alert_level = severity_levels.get(alert_severity, 1)
        threshold_level = severity_levels.get(threshold, 1)
        
        return alert_level >= threshold_level
    
    def _check_rate_limit(self, alert: RiskAlert, rule: AlertRule) -> bool:
        """Check if alert passes rate limiting."""
        # Count alerts of this type in the last hour
        cutoff_time = datetime.now() - timedelta(hours=1)
        
        count = 0
        for stored_alert in self._alert_history:
            if (stored_alert.alert_type == alert.alert_type and 
                stored_alert.alert_time > cutoff_time):
                count += 1
        
        return count < rule.max_alerts_per_hour
    
    def _store_alert(self, alert: RiskAlert) -> None:
        """Store alert in history."""
        self._alert_history.append(alert)
        
        # Trim history if too large
        if len(self._alert_history) > self._max_history_size:
            self._alert_history = self._alert_history[-self._max_history_size:]
    
    def _update_rate_limiting(self, alert: RiskAlert) -> None:
        """Update rate limiting counters."""
        self._last_alert_times[alert.alert_type] = datetime.now()
        
        # Update hourly count
        hour_key = f"{alert.alert_type}_{datetime.now().hour}"
        self._alert_counts[hour_key] = self._alert_counts.get(hour_key, 0) + 1
    
    async def _periodic_cleanup(self) -> None:
        """Periodic cleanup of old alerts and counters."""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                
                # Clean old alerts
                cutoff_time = datetime.now() - timedelta(hours=self._cleanup_interval_hours)
                self._alert_history = [
                    alert for alert in self._alert_history 
                    if alert.alert_time > cutoff_time
                ]
                
                # Clean old counters
                current_hour = datetime.now().hour
                keys_to_remove = []
                for key in self._alert_counts:
                    if key.endswith(f"_{current_hour}"):
                        continue  # Keep current hour
                    # Remove old hour counters
                    keys_to_remove.append(key)
                
                for key in keys_to_remove:
                    del self._alert_counts[key]
                
                self.logger.debug("Alert manager cleanup completed")
                
            except Exception as e:
                self.logger.error(f"Error in alert manager cleanup: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes before retry