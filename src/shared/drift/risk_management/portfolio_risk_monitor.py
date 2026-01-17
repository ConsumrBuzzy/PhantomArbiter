"""
Portfolio Risk Monitor
=====================

Cross-cutting risk monitoring for all trading engines.
Validates trade signals against portfolio-wide risk limits.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from ..sdk.models.portfolio import PortfolioState
from ..sdk.models.trading import TradeSignal
from ..sdk.models.risk import RiskMetrics, RiskAlert
from ..sdk.data.market_data_provider import MarketDataProvider
from ..sdk.data.portfolio_data_provider import PortfolioDataProvider
from ..sdk.data.risk_data_provider import RiskDataProvider
from ..sdk.math.var_calculator import VaRCalculator
from ..sdk.math.correlation_calculator import CorrelationCalculator

from .alert_manager import AlertManager
from .risk_limits import RiskLimits
from src.shared.system.logging import Logger


class ValidationStatus(Enum):
    """Trade signal validation status."""
    APPROVED = "approved"
    REJECTED = "rejected"
    WARNING = "warning"
    CONDITIONAL = "conditional"


@dataclass
class RiskValidationResult:
    """Result of trade signal risk validation."""
    
    status: ValidationStatus
    signal_id: str
    engine_name: str
    
    # Risk assessment
    risk_score: float  # 0-1 scale
    projected_var_impact: float  # Change in portfolio VaR
    projected_leverage_impact: float  # Change in leverage
    position_size_impact: float  # Impact on position concentration
    
    # Validation details
    passed_checks: List[str]
    failed_checks: List[str]
    warnings: List[str]
    
    # Risk limits
    current_var: float
    var_limit: float
    current_leverage: float
    leverage_limit: float
    
    # Recommendations
    recommended_size_adjustment: Optional[float] = None
    alternative_markets: List[str] = None
    
    # Metadata
    validation_time: datetime
    confidence_level: float = 0.95
    
    @property
    def is_approved(self) -> bool:
        """Check if signal is approved."""
        return self.status == ValidationStatus.APPROVED
    
    @property
    def is_rejected(self) -> bool:
        """Check if signal is rejected."""
        return self.status == ValidationStatus.REJECTED
    
    @property
    def has_warnings(self) -> bool:
        """Check if validation has warnings."""
        return len(self.warnings) > 0 or self.status == ValidationStatus.WARNING


class PortfolioRiskMonitor:
    """
    Cross-cutting risk monitoring for all trading engines.
    
    Validates trade signals against portfolio-wide risk limits,
    monitors real-time risk metrics, and generates risk alerts.
    """
    
    def __init__(
        self,
        market_data_provider: MarketDataProvider,
        portfolio_data_provider: PortfolioDataProvider,
        risk_data_provider: RiskDataProvider,
        risk_limits: Optional[RiskLimits] = None
    ):
        """
        Initialize portfolio risk monitor.
        
        Args:
            market_data_provider: Market data provider
            portfolio_data_provider: Portfolio data provider
            risk_data_provider: Risk data provider
            risk_limits: Risk limits configuration
        """
        self.market_data = market_data_provider
        self.portfolio_data = portfolio_data_provider
        self.risk_data = risk_data_provider
        self.risk_limits = risk_limits or RiskLimits()
        
        self.alert_manager = AlertManager()
        self.logger = Logger
        
        # Monitoring state
        self._last_risk_calculation = None
        self._risk_history = []
        self._validation_cache = {}
        
        # Configuration
        self._risk_calculation_interval = 300  # 5 minutes
        self._max_risk_history = 1000  # Keep last 1000 risk calculations
        
        self.logger.info("Portfolio Risk Monitor initialized")
    
    async def validate_trade_signal(self, signal: TradeSignal) -> RiskValidationResult:
        """
        Validate trade signal against portfolio risk limits.
        
        Args:
            signal: Trade signal to validate
            
        Returns:
            Risk validation result
        """
        try:
            self.logger.debug(f"Validating trade signal: {signal.signal_id} from {signal.engine_name}")
            
            # Get current portfolio state
            portfolio_state = await self.portfolio_data.get_portfolio_state()
            if not portfolio_state:
                return self._create_error_result(signal, "Portfolio state unavailable")
            
            # Calculate current risk metrics
            current_risk = await self.risk_data.calculate_portfolio_risk(portfolio_state)
            
            # Initialize validation tracking
            passed_checks = []
            failed_checks = []
            warnings = []
            
            # 1. Portfolio VaR Check
            var_check = await self._validate_var_impact(signal, portfolio_state, current_risk)
            if var_check['passed']:
                passed_checks.append("VaR limit check")
            else:
                failed_checks.append(f"VaR limit exceeded: {var_check['message']}")
            
            # 2. Leverage Check
            leverage_check = await self._validate_leverage_impact(signal, portfolio_state)
            if leverage_check['passed']:
                passed_checks.append("Leverage limit check")
            else:
                failed_checks.append(f"Leverage limit exceeded: {leverage_check['message']}")
            
            # 3. Position Size Check
            position_check = await self._validate_position_size(signal, portfolio_state)
            if position_check['passed']:
                passed_checks.append("Position size check")
            else:
                failed_checks.append(f"Position size limit exceeded: {position_check['message']}")
            
            # 4. Concentration Check
            concentration_check = await self._validate_concentration(signal, portfolio_state)
            if concentration_check['passed']:
                passed_checks.append("Concentration check")
            else:
                warnings.append(f"High concentration risk: {concentration_check['message']}")
            
            # 5. Correlation Check
            correlation_check = await self._validate_correlation_risk(signal, portfolio_state)
            if correlation_check['passed']:
                passed_checks.append("Correlation risk check")
            else:
                warnings.append(f"Correlation risk: {correlation_check['message']}")
            
            # 6. Market Conditions Check
            market_check = await self._validate_market_conditions(signal)
            if market_check['passed']:
                passed_checks.append("Market conditions check")
            else:
                warnings.append(f"Market conditions: {market_check['message']}")
            
            # 7. Engine-Specific Limits
            engine_check = await self._validate_engine_limits(signal, portfolio_state)
            if engine_check['passed']:
                passed_checks.append("Engine limits check")
            else:
                failed_checks.append(f"Engine limits exceeded: {engine_check['message']}")
            
            # Determine validation status
            status = self._determine_validation_status(failed_checks, warnings)
            
            # Calculate risk metrics
            risk_score = self._calculate_risk_score(signal, portfolio_state, current_risk)
            projected_var_impact = var_check.get('projected_impact', 0.0)
            projected_leverage_impact = leverage_check.get('projected_impact', 0.0)
            position_size_impact = position_check.get('size_impact', 0.0)
            
            # Generate recommendations if needed
            recommended_size_adjustment = None
            alternative_markets = []
            
            if status == ValidationStatus.REJECTED:
                recommended_size_adjustment = self._calculate_safe_size(signal, portfolio_state)
                alternative_markets = await self._suggest_alternative_markets(signal)
            
            # Create validation result
            result = RiskValidationResult(
                status=status,
                signal_id=signal.signal_id,
                engine_name=signal.engine_name,
                risk_score=risk_score,
                projected_var_impact=projected_var_impact,
                projected_leverage_impact=projected_leverage_impact,
                position_size_impact=position_size_impact,
                passed_checks=passed_checks,
                failed_checks=failed_checks,
                warnings=warnings,
                current_var=current_risk.var_1d,
                var_limit=self.risk_limits.max_var_1d,
                current_leverage=portfolio_state.leverage,
                leverage_limit=self.risk_limits.max_leverage,
                recommended_size_adjustment=recommended_size_adjustment,
                alternative_markets=alternative_markets,
                validation_time=datetime.now()
            )
            
            # Log validation result
            self._log_validation_result(result)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error validating trade signal {signal.signal_id}: {e}")
            return self._create_error_result(signal, f"Validation error: {e}")
    
    async def monitor_real_time_risk(self) -> List[RiskAlert]:
        """
        Monitor portfolio risk in real-time and generate alerts.
        
        Returns:
            List of current risk alerts
        """
        try:
            # Check if we need to recalculate risk
            if not self._should_recalculate_risk():
                return []
            
            # Get current portfolio state
            portfolio_state = await self.portfolio_data.get_portfolio_state()
            if not portfolio_state:
                return []
            
            # Calculate current risk metrics
            current_risk = await self.risk_data.calculate_portfolio_risk(portfolio_state)
            
            # Update risk history
            self._update_risk_history(current_risk)
            
            # Check for risk limit breaches
            alerts = []
            
            # VaR breach check
            if current_risk.var_1d > self.risk_limits.max_var_1d:
                alert = RiskAlert(
                    alert_id=f"var_breach_{datetime.now().timestamp()}",
                    alert_type="var_breach",
                    severity="critical",
                    message=f"Portfolio VaR ({current_risk.var_1d:.2f}) exceeds limit ({self.risk_limits.max_var_1d:.2f})",
                    current_value=current_risk.var_1d,
                    threshold_value=self.risk_limits.max_var_1d,
                    breach_percentage=(current_risk.var_1d / self.risk_limits.max_var_1d - 1) * 100,
                    alert_time=datetime.now()
                )
                alerts.append(alert)
            
            # Leverage breach check
            if portfolio_state.leverage > self.risk_limits.max_leverage:
                alert = RiskAlert(
                    alert_id=f"leverage_breach_{datetime.now().timestamp()}",
                    alert_type="leverage_breach",
                    severity="critical",
                    message=f"Portfolio leverage ({portfolio_state.leverage:.2f}x) exceeds limit ({self.risk_limits.max_leverage:.2f}x)",
                    current_value=portfolio_state.leverage,
                    threshold_value=self.risk_limits.max_leverage,
                    breach_percentage=(portfolio_state.leverage / self.risk_limits.max_leverage - 1) * 100,
                    alert_time=datetime.now()
                )
                alerts.append(alert)
            
            # Drawdown breach check
            if current_risk.current_drawdown > self.risk_limits.max_drawdown:
                alert = RiskAlert(
                    alert_id=f"drawdown_breach_{datetime.now().timestamp()}",
                    alert_type="drawdown_breach",
                    severity="warning",
                    message=f"Current drawdown ({current_risk.current_drawdown:.1%}) exceeds limit ({self.risk_limits.max_drawdown:.1%})",
                    current_value=current_risk.current_drawdown,
                    threshold_value=self.risk_limits.max_drawdown,
                    breach_percentage=(current_risk.current_drawdown / self.risk_limits.max_drawdown - 1) * 100,
                    alert_time=datetime.now()
                )
                alerts.append(alert)
            
            # Concentration risk check
            if current_risk.portfolio_concentration > self.risk_limits.max_concentration:
                alert = RiskAlert(
                    alert_id=f"concentration_breach_{datetime.now().timestamp()}",
                    alert_type="concentration_risk",
                    severity="warning",
                    message=f"Portfolio concentration ({current_risk.portfolio_concentration:.1%}) exceeds limit ({self.risk_limits.max_concentration:.1%})",
                    current_value=current_risk.portfolio_concentration,
                    threshold_value=self.risk_limits.max_concentration,
                    breach_percentage=(current_risk.portfolio_concentration / self.risk_limits.max_concentration - 1) * 100,
                    alert_time=datetime.now()
                )
                alerts.append(alert)
            
            # Health ratio check
            if portfolio_state.health_ratio < self.risk_limits.min_health_ratio:
                alert = RiskAlert(
                    alert_id=f"health_breach_{datetime.now().timestamp()}",
                    alert_type="health_ratio_breach",
                    severity="critical",
                    message=f"Portfolio health ratio ({portfolio_state.health_ratio:.2f}) below minimum ({self.risk_limits.min_health_ratio:.2f})",
                    current_value=portfolio_state.health_ratio,
                    threshold_value=self.risk_limits.min_health_ratio,
                    breach_percentage=(1 - portfolio_state.health_ratio / self.risk_limits.min_health_ratio) * 100,
                    alert_time=datetime.now()
                )
                alerts.append(alert)
            
            # Send alerts through alert manager
            for alert in alerts:
                await self.alert_manager.send_alert(alert)
            
            return alerts
            
        except Exception as e:
            self.logger.error(f"Error monitoring real-time risk: {e}")
            return []
    
    async def get_risk_dashboard(self) -> Dict[str, Any]:
        """
        Get comprehensive risk dashboard data.
        
        Returns:
            Dictionary with risk dashboard information
        """
        try:
            # Get current portfolio state
            portfolio_state = await self.portfolio_data.get_portfolio_state()
            if not portfolio_state:
                return {}
            
            # Calculate current risk metrics
            current_risk = await self.risk_data.calculate_portfolio_risk(portfolio_state)
            
            # Get recent alerts
            recent_alerts = await self.alert_manager.get_recent_alerts(hours=24)
            
            # Calculate risk trends
            risk_trends = self._calculate_risk_trends()
            
            dashboard = {
                'portfolio_overview': {
                    'total_value': portfolio_state.total_value,
                    'unrealized_pnl': portfolio_state.unrealized_pnl,
                    'health_ratio': portfolio_state.health_ratio,
                    'leverage': portfolio_state.leverage,
                    'position_count': len(portfolio_state.positions)
                },
                'risk_metrics': {
                    'var_1d': current_risk.var_1d,
                    'var_7d': current_risk.var_7d,
                    'portfolio_volatility': current_risk.portfolio_volatility,
                    'max_drawdown': current_risk.max_drawdown,
                    'current_drawdown': current_risk.current_drawdown,
                    'sharpe_ratio': current_risk.sharpe_ratio,
                    'concentration': current_risk.portfolio_concentration,
                    'diversification_ratio': current_risk.diversification_ratio
                },
                'risk_limits': {
                    'var_utilization': current_risk.var_1d / self.risk_limits.max_var_1d if self.risk_limits.max_var_1d > 0 else 0,
                    'leverage_utilization': portfolio_state.leverage / self.risk_limits.max_leverage if self.risk_limits.max_leverage > 0 else 0,
                    'concentration_utilization': current_risk.portfolio_concentration / self.risk_limits.max_concentration if self.risk_limits.max_concentration > 0 else 0
                },
                'alerts': {
                    'active_alerts': len([a for a in recent_alerts if a.severity == 'critical']),
                    'warnings': len([a for a in recent_alerts if a.severity == 'warning']),
                    'recent_alerts': [
                        {
                            'type': alert.alert_type,
                            'severity': alert.severity,
                            'message': alert.message,
                            'time': alert.alert_time.isoformat()
                        }
                        for alert in recent_alerts[-10:]  # Last 10 alerts
                    ]
                },
                'trends': risk_trends,
                'last_updated': datetime.now().isoformat()
            }
            
            return dashboard
            
        except Exception as e:
            self.logger.error(f"Error generating risk dashboard: {e}")
            return {}
    
    # ==========================================================================
    # VALIDATION METHODS
    # ==========================================================================
    
    async def _validate_var_impact(
        self, 
        signal: TradeSignal, 
        portfolio_state: PortfolioState,
        current_risk: RiskMetrics
    ) -> Dict[str, Any]:
        """Validate VaR impact of trade signal."""
        try:
            # Estimate position change
            position_value = signal.size * signal.target_price if signal.target_price else 0
            
            # Simple VaR impact estimation (would be more sophisticated in practice)
            # Assume new position adds proportional risk
            portfolio_value = portfolio_state.total_value
            position_weight = position_value / portfolio_value if portfolio_value > 0 else 0
            
            # Estimate volatility for the market
            market_volatility = await self.market_data.get_market_volatility(signal.market, window_days=30)
            
            # Estimate VaR impact
            estimated_var_impact = position_weight * market_volatility * portfolio_value * 1.65  # 95% confidence
            projected_var = current_risk.var_1d + estimated_var_impact
            
            passed = projected_var <= self.risk_limits.max_var_1d
            
            return {
                'passed': passed,
                'projected_impact': estimated_var_impact,
                'projected_var': projected_var,
                'message': f"Projected VaR: {projected_var:.2f}, Limit: {self.risk_limits.max_var_1d:.2f}"
            }
            
        except Exception as e:
            self.logger.error(f"Error validating VaR impact: {e}")
            return {'passed': False, 'projected_impact': 0.0, 'message': f"VaR validation error: {e}"}
    
    async def _validate_leverage_impact(
        self, 
        signal: TradeSignal, 
        portfolio_state: PortfolioState
    ) -> Dict[str, Any]:
        """Validate leverage impact of trade signal."""
        try:
            # Calculate additional margin requirement
            position_value = signal.size * signal.target_price if signal.target_price else 0
            
            # Estimate margin requirement (simplified - would use actual margin requirements)
            margin_requirement = position_value * 0.1  # Assume 10% margin requirement
            
            # Calculate projected leverage
            new_margin_used = portfolio_state.margin_used + margin_requirement
            projected_leverage = new_margin_used / portfolio_state.total_collateral if portfolio_state.total_collateral > 0 else 0
            
            passed = projected_leverage <= self.risk_limits.max_leverage
            
            return {
                'passed': passed,
                'projected_impact': projected_leverage - portfolio_state.leverage,
                'projected_leverage': projected_leverage,
                'message': f"Projected leverage: {projected_leverage:.2f}x, Limit: {self.risk_limits.max_leverage:.2f}x"
            }
            
        except Exception as e:
            self.logger.error(f"Error validating leverage impact: {e}")
            return {'passed': False, 'projected_impact': 0.0, 'message': f"Leverage validation error: {e}"}
    
    async def _validate_position_size(
        self, 
        signal: TradeSignal, 
        portfolio_state: PortfolioState
    ) -> Dict[str, Any]:
        """Validate position size limits."""
        try:
            position_value = signal.size * signal.target_price if signal.target_price else 0
            portfolio_value = portfolio_state.total_value
            
            # Check absolute position size
            if position_value > self.risk_limits.max_position_size:
                return {
                    'passed': False,
                    'size_impact': position_value,
                    'message': f"Position size {position_value:.2f} exceeds limit {self.risk_limits.max_position_size:.2f}"
                }
            
            # Check position size as percentage of portfolio
            position_percentage = position_value / portfolio_value if portfolio_value > 0 else 0
            if position_percentage > self.risk_limits.max_position_percentage:
                return {
                    'passed': False,
                    'size_impact': position_percentage,
                    'message': f"Position percentage {position_percentage:.1%} exceeds limit {self.risk_limits.max_position_percentage:.1%}"
                }
            
            return {
                'passed': True,
                'size_impact': position_percentage,
                'message': f"Position size within limits: {position_percentage:.1%} of portfolio"
            }
            
        except Exception as e:
            self.logger.error(f"Error validating position size: {e}")
            return {'passed': False, 'size_impact': 0.0, 'message': f"Position size validation error: {e}"}
    
    async def _validate_concentration(
        self, 
        signal: TradeSignal, 
        portfolio_state: PortfolioState
    ) -> Dict[str, Any]:
        """Validate concentration risk."""
        try:
            # Get current exposure to this asset
            asset = signal.market.split('-')[0] if '-' in signal.market else signal.market
            current_exposure = await self.portfolio_data.get_net_exposure(asset)
            
            # Calculate new exposure
            position_value = signal.size * signal.target_price if signal.target_price else 0
            if signal.side.value.lower() == 'sell':
                position_value = -position_value
            
            new_exposure = current_exposure + position_value
            portfolio_value = portfolio_state.total_value
            
            # Calculate concentration
            concentration = abs(new_exposure) / portfolio_value if portfolio_value > 0 else 0
            
            passed = concentration <= self.risk_limits.max_single_asset_exposure
            
            return {
                'passed': passed,
                'concentration': concentration,
                'message': f"Asset concentration: {concentration:.1%}, Limit: {self.risk_limits.max_single_asset_exposure:.1%}"
            }
            
        except Exception as e:
            self.logger.error(f"Error validating concentration: {e}")
            return {'passed': True, 'concentration': 0.0, 'message': f"Concentration validation error: {e}"}
    
    async def _validate_correlation_risk(
        self, 
        signal: TradeSignal, 
        portfolio_state: PortfolioState
    ) -> Dict[str, Any]:
        """Validate correlation risk."""
        try:
            # Get correlation matrix
            markets = [pos.market for pos in portfolio_state.positions]
            if signal.market not in markets:
                markets.append(signal.market)
            
            if len(markets) < 2:
                return {'passed': True, 'message': "Insufficient positions for correlation analysis"}
            
            correlation_matrix = await self.market_data.get_correlation_matrix(markets, window_days=30)
            
            # Calculate average correlation with existing positions
            correlations = []
            for market in markets:
                if market != signal.market and market in correlation_matrix:
                    corr = correlation_matrix.get(market, {}).get(signal.market, 0.0)
                    correlations.append(abs(corr))
            
            if not correlations:
                return {'passed': True, 'message': "No correlation data available"}
            
            avg_correlation = sum(correlations) / len(correlations)
            passed = avg_correlation <= self.risk_limits.max_correlation
            
            return {
                'passed': passed,
                'avg_correlation': avg_correlation,
                'message': f"Average correlation: {avg_correlation:.2f}, Limit: {self.risk_limits.max_correlation:.2f}"
            }
            
        except Exception as e:
            self.logger.error(f"Error validating correlation risk: {e}")
            return {'passed': True, 'avg_correlation': 0.0, 'message': f"Correlation validation error: {e}"}
    
    async def _validate_market_conditions(self, signal: TradeSignal) -> Dict[str, Any]:
        """Validate market conditions for trading."""
        try:
            # Get market data
            market_data = await self.market_data.get_market_data(signal.market)
            
            if not market_data or not market_data.summary:
                return {'passed': False, 'message': "Market data unavailable"}
            
            # Check market status
            if market_data.summary.status.value != 'active':
                return {'passed': False, 'message': f"Market status: {market_data.summary.status.value}"}
            
            # Check liquidity
            if market_data.orderbook:
                spread_bps = market_data.orderbook.spread_bps
                if spread_bps > self.risk_limits.max_spread_bps:
                    return {
                        'passed': False, 
                        'message': f"Spread too wide: {spread_bps:.1f} bps > {self.risk_limits.max_spread_bps:.1f} bps"
                    }
            
            # Check volatility
            volatility = await self.market_data.get_market_volatility(signal.market, window_days=7)
            if volatility > self.risk_limits.max_market_volatility:
                return {
                    'passed': False,
                    'message': f"Market volatility too high: {volatility:.1%} > {self.risk_limits.max_market_volatility:.1%}"
                }
            
            return {'passed': True, 'message': "Market conditions acceptable"}
            
        except Exception as e:
            self.logger.error(f"Error validating market conditions: {e}")
            return {'passed': True, 'message': f"Market conditions validation error: {e}"}
    
    async def _validate_engine_limits(
        self, 
        signal: TradeSignal, 
        portfolio_state: PortfolioState
    ) -> Dict[str, Any]:
        """Validate engine-specific limits."""
        try:
            # Get engine-specific limits
            engine_limits = self.risk_limits.get_engine_limits(signal.engine_name)
            
            if not engine_limits:
                return {'passed': True, 'message': "No engine-specific limits"}
            
            # Check daily trade count
            today = datetime.now().date()
            recent_trades = await self.portfolio_data.get_trade_history(
                start_time=datetime.combine(today, datetime.min.time()),
                end_time=datetime.now()
            )
            
            engine_trades_today = len([t for t in recent_trades if hasattr(t, 'engine_name') and t.engine_name == signal.engine_name])
            
            if engine_trades_today >= engine_limits.get('max_daily_trades', float('inf')):
                return {
                    'passed': False,
                    'message': f"Engine daily trade limit exceeded: {engine_trades_today} >= {engine_limits['max_daily_trades']}"
                }
            
            # Check engine exposure
            engine_exposure = sum(
                abs(pos.notional_value) for pos in portfolio_state.positions 
                if hasattr(pos, 'engine_name') and pos.engine_name == signal.engine_name
            )
            
            max_engine_exposure = engine_limits.get('max_exposure', float('inf'))
            if engine_exposure > max_engine_exposure:
                return {
                    'passed': False,
                    'message': f"Engine exposure limit exceeded: {engine_exposure:.2f} > {max_engine_exposure:.2f}"
                }
            
            return {'passed': True, 'message': "Engine limits satisfied"}
            
        except Exception as e:
            self.logger.error(f"Error validating engine limits: {e}")
            return {'passed': True, 'message': f"Engine limits validation error: {e}"}
    
    # ==========================================================================
    # UTILITY METHODS
    # ==========================================================================
    
    def _determine_validation_status(self, failed_checks: List[str], warnings: List[str]) -> ValidationStatus:
        """Determine overall validation status."""
        if failed_checks:
            return ValidationStatus.REJECTED
        elif warnings:
            return ValidationStatus.WARNING
        else:
            return ValidationStatus.APPROVED
    
    def _calculate_risk_score(
        self, 
        signal: TradeSignal, 
        portfolio_state: PortfolioState,
        current_risk: RiskMetrics
    ) -> float:
        """Calculate overall risk score for the signal."""
        try:
            risk_factors = []
            
            # Size risk
            position_value = signal.size * signal.target_price if signal.target_price else 0
            size_risk = min(1.0, position_value / portfolio_state.total_value) if portfolio_state.total_value > 0 else 0
            risk_factors.append(size_risk)
            
            # Volatility risk
            # This would use actual market volatility
            volatility_risk = min(1.0, signal.risk_score) if hasattr(signal, 'risk_score') else 0.3
            risk_factors.append(volatility_risk)
            
            # Leverage risk
            leverage_risk = min(1.0, portfolio_state.leverage / self.risk_limits.max_leverage) if self.risk_limits.max_leverage > 0 else 0
            risk_factors.append(leverage_risk)
            
            # Concentration risk
            concentration_risk = min(1.0, current_risk.portfolio_concentration / self.risk_limits.max_concentration) if self.risk_limits.max_concentration > 0 else 0
            risk_factors.append(concentration_risk)
            
            # Average risk factors
            return sum(risk_factors) / len(risk_factors) if risk_factors else 0.5
            
        except Exception as e:
            self.logger.error(f"Error calculating risk score: {e}")
            return 0.5
    
    def _calculate_safe_size(self, signal: TradeSignal, portfolio_state: PortfolioState) -> float:
        """Calculate safe position size that would pass validation."""
        try:
            # Start with maximum allowed position percentage
            max_percentage = self.risk_limits.max_position_percentage
            safe_value = portfolio_state.total_value * max_percentage
            
            # Adjust for leverage constraints
            available_margin = portfolio_state.margin_available
            leverage_adjusted_size = available_margin * 0.8  # Use 80% of available margin
            
            safe_value = min(safe_value, leverage_adjusted_size)
            
            # Convert to size
            if signal.target_price and signal.target_price > 0:
                safe_size = safe_value / signal.target_price
                return min(safe_size, signal.size * 0.5)  # At most 50% of original size
            
            return signal.size * 0.5
            
        except Exception as e:
            self.logger.error(f"Error calculating safe size: {e}")
            return signal.size * 0.1  # Very conservative fallback
    
    async def _suggest_alternative_markets(self, signal: TradeSignal) -> List[str]:
        """Suggest alternative markets with lower risk."""
        try:
            # Get all available markets
            all_markets = await self.market_data.get_all_markets() if hasattr(self.market_data, 'get_all_markets') else []
            
            # Filter for similar assets
            base_asset = signal.market.split('-')[0] if '-' in signal.market else signal.market
            similar_markets = [m for m in all_markets if base_asset in m and m != signal.market]
            
            # Return up to 3 alternatives
            return similar_markets[:3]
            
        except Exception as e:
            self.logger.error(f"Error suggesting alternative markets: {e}")
            return []
    
    def _should_recalculate_risk(self) -> bool:
        """Check if risk should be recalculated."""
        if not self._last_risk_calculation:
            return True
        
        time_since_last = (datetime.now() - self._last_risk_calculation).total_seconds()
        return time_since_last >= self._risk_calculation_interval
    
    def _update_risk_history(self, risk_metrics: RiskMetrics) -> None:
        """Update risk history with new metrics."""
        self._risk_history.append({
            'timestamp': datetime.now(),
            'var_1d': risk_metrics.var_1d,
            'leverage': risk_metrics.gross_leverage,
            'volatility': risk_metrics.portfolio_volatility,
            'drawdown': risk_metrics.current_drawdown,
            'concentration': risk_metrics.portfolio_concentration
        })
        
        # Keep only recent history
        if len(self._risk_history) > self._max_risk_history:
            self._risk_history = self._risk_history[-self._max_risk_history:]
        
        self._last_risk_calculation = datetime.now()
    
    def _calculate_risk_trends(self) -> Dict[str, Any]:
        """Calculate risk trends from history."""
        if len(self._risk_history) < 2:
            return {}
        
        try:
            recent = self._risk_history[-10:]  # Last 10 observations
            older = self._risk_history[-20:-10] if len(self._risk_history) >= 20 else self._risk_history[:-10]
            
            if not older:
                return {}
            
            # Calculate trends
            trends = {}
            
            for metric in ['var_1d', 'leverage', 'volatility', 'drawdown', 'concentration']:
                recent_avg = sum(obs[metric] for obs in recent) / len(recent)
                older_avg = sum(obs[metric] for obs in older) / len(older)
                
                if older_avg > 0:
                    trend = (recent_avg - older_avg) / older_avg
                    trends[f'{metric}_trend'] = trend
                    trends[f'{metric}_direction'] = 'increasing' if trend > 0.05 else 'decreasing' if trend < -0.05 else 'stable'
            
            return trends
            
        except Exception as e:
            self.logger.error(f"Error calculating risk trends: {e}")
            return {}
    
    def _create_error_result(self, signal: TradeSignal, error_message: str) -> RiskValidationResult:
        """Create error validation result."""
        return RiskValidationResult(
            status=ValidationStatus.REJECTED,
            signal_id=signal.signal_id,
            engine_name=signal.engine_name,
            risk_score=1.0,  # Maximum risk for errors
            projected_var_impact=0.0,
            projected_leverage_impact=0.0,
            position_size_impact=0.0,
            passed_checks=[],
            failed_checks=[error_message],
            warnings=[],
            current_var=0.0,
            var_limit=0.0,
            current_leverage=0.0,
            leverage_limit=0.0,
            validation_time=datetime.now()
        )
    
    def _log_validation_result(self, result: RiskValidationResult) -> None:
        """Log validation result."""
        if result.is_approved:
            self.logger.info(f"✅ Signal {result.signal_id} approved (risk score: {result.risk_score:.2f})")
        elif result.is_rejected:
            self.logger.warning(f"❌ Signal {result.signal_id} rejected: {', '.join(result.failed_checks)}")
        else:
            self.logger.info(f"⚠️ Signal {result.signal_id} approved with warnings: {', '.join(result.warnings)}")
    
    # ==========================================================================
    # CONFIGURATION METHODS
    # ==========================================================================
    
    def update_risk_limits(self, new_limits: RiskLimits) -> None:
        """Update risk limits."""
        self.risk_limits = new_limits
        self.logger.info("Risk limits updated")
    
    def set_monitoring_interval(self, interval_seconds: int) -> None:
        """Set risk monitoring interval."""
        self._risk_calculation_interval = interval_seconds
        self.logger.info(f"Risk monitoring interval set to {interval_seconds} seconds")