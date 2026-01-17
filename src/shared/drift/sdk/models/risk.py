"""
Risk Data Models
===============

Shared risk metrics and alert models for all trading engines.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum


class RiskLevel(Enum):
    """Risk level enumeration."""
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class RiskMetrics:
    """Comprehensive risk metrics for portfolio."""
    
    # Value at Risk metrics
    var_1d: float  # 1-day VaR at 95% confidence
    var_7d: float  # 7-day VaR at 95% confidence
    var_method: str  # VaR calculation method used
    
    # Volatility metrics
    portfolio_volatility: float  # Annualized portfolio volatility
    volatility_regime: str  # Current volatility regime
    
    # Drawdown metrics
    max_drawdown: float  # Maximum historical drawdown
    current_drawdown: float  # Current drawdown from peak
    drawdown_duration_days: int  # Days in current drawdown
    
    # Performance metrics
    sharpe_ratio: float  # Risk-adjusted return measure
    sortino_ratio: float  # Downside risk-adjusted return
    calmar_ratio: float  # Return to max drawdown ratio
    
    # Correlation and diversification
    correlation_matrix: Dict[str, Dict[str, float]]  # Asset correlation matrix
    portfolio_concentration: float  # Concentration risk (0-1, higher = more concentrated)
    diversification_ratio: float  # Portfolio diversification measure
    
    # Leverage and exposure metrics
    gross_leverage: float  # Total gross leverage
    net_leverage: float  # Net leverage
    sector_exposures: Dict[str, float]  # Exposure by sector/asset class
    
    # Liquidity risk
    liquidity_score: float  # Portfolio liquidity score (0-1, higher = more liquid)
    days_to_liquidate: float  # Estimated days to liquidate portfolio
    
    # Tail risk measures
    expected_shortfall: float  # Expected loss beyond VaR
    tail_ratio: float  # Ratio of gains to losses in tail events
    
    # Calculation metadata
    calculation_date: datetime
    data_quality_score: float  # Quality of underlying data (0-1)
    confidence_level: float  # Confidence level used for risk calculations
    
    @property
    def overall_risk_level(self) -> RiskLevel:
        """Determine overall risk level based on multiple factors."""
        risk_score = 0
        
        # VaR contribution (0-4 points)
        if self.var_1d > 0.05:  # >5% daily VaR
            risk_score += 4
        elif self.var_1d > 0.03:  # >3% daily VaR
            risk_score += 3
        elif self.var_1d > 0.02:  # >2% daily VaR
            risk_score += 2
        elif self.var_1d > 0.01:  # >1% daily VaR
            risk_score += 1
        
        # Leverage contribution (0-3 points)
        if self.gross_leverage > 5.0:
            risk_score += 3
        elif self.gross_leverage > 3.0:
            risk_score += 2
        elif self.gross_leverage > 2.0:
            risk_score += 1
        
        # Drawdown contribution (0-3 points)
        if self.current_drawdown > 0.2:  # >20% drawdown
            risk_score += 3
        elif self.current_drawdown > 0.1:  # >10% drawdown
            risk_score += 2
        elif self.current_drawdown > 0.05:  # >5% drawdown
            risk_score += 1
        
        # Concentration contribution (0-2 points)
        if self.portfolio_concentration > 0.8:
            risk_score += 2
        elif self.portfolio_concentration > 0.6:
            risk_score += 1
        
        # Classify based on total score
        if risk_score >= 8:
            return RiskLevel.CRITICAL
        elif risk_score >= 5:
            return RiskLevel.HIGH
        elif risk_score >= 2:
            return RiskLevel.MODERATE
        else:
            return RiskLevel.LOW
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'var_1d': self.var_1d,
            'var_7d': self.var_7d,
            'var_method': self.var_method,
            'portfolio_volatility': self.portfolio_volatility,
            'volatility_regime': self.volatility_regime,
            'max_drawdown': self.max_drawdown,
            'current_drawdown': self.current_drawdown,
            'drawdown_duration_days': self.drawdown_duration_days,
            'sharpe_ratio': self.sharpe_ratio,
            'sortino_ratio': self.sortino_ratio,
            'calmar_ratio': self.calmar_ratio,
            'correlation_matrix': self.correlation_matrix,
            'portfolio_concentration': self.portfolio_concentration,
            'diversification_ratio': self.diversification_ratio,
            'gross_leverage': self.gross_leverage,
            'net_leverage': self.net_leverage,
            'sector_exposures': self.sector_exposures,
            'liquidity_score': self.liquidity_score,
            'days_to_liquidate': self.days_to_liquidate,
            'expected_shortfall': self.expected_shortfall,
            'tail_ratio': self.tail_ratio,
            'calculation_date': self.calculation_date.isoformat(),
            'data_quality_score': self.data_quality_score,
            'confidence_level': self.confidence_level,
            'overall_risk_level': self.overall_risk_level.value
        }


@dataclass
class RiskLimits:
    """Risk limits configuration for portfolio management."""
    
    # VaR limits
    max_var_1d: float = 0.02  # Maximum 2% daily VaR
    max_var_7d: float = 0.06  # Maximum 6% weekly VaR
    
    # Leverage limits
    max_gross_leverage: float = 3.0  # Maximum 3x gross leverage
    max_net_leverage: float = 2.0  # Maximum 2x net leverage
    
    # Drawdown limits
    max_drawdown: float = 0.15  # Maximum 15% drawdown
    drawdown_stop_loss: float = 0.20  # Emergency stop at 20% drawdown
    
    # Position limits
    max_position_size: float = 0.1  # Maximum 10% of portfolio in single position
    max_sector_exposure: float = 0.3  # Maximum 30% exposure to single sector
    max_correlation_exposure: float = 0.5  # Maximum exposure to highly correlated assets
    
    # Liquidity limits
    min_liquidity_score: float = 0.3  # Minimum portfolio liquidity score
    max_days_to_liquidate: float = 5.0  # Maximum days to liquidate portfolio
    
    # Performance limits
    min_sharpe_ratio: float = 0.5  # Minimum acceptable Sharpe ratio
    max_volatility: float = 0.25  # Maximum 25% annualized volatility
    
    # Concentration limits
    max_concentration: float = 0.7  # Maximum concentration score
    min_diversification: float = 0.3  # Minimum diversification ratio
    
    def check_var_breach(self, risk_metrics: RiskMetrics) -> List[str]:
        """Check for VaR limit breaches."""
        breaches = []
        
        if risk_metrics.var_1d > self.max_var_1d:
            breaches.append(f"1-day VaR ({risk_metrics.var_1d:.2%}) exceeds limit ({self.max_var_1d:.2%})")
        
        if risk_metrics.var_7d > self.max_var_7d:
            breaches.append(f"7-day VaR ({risk_metrics.var_7d:.2%}) exceeds limit ({self.max_var_7d:.2%})")
        
        return breaches
    
    def check_leverage_breach(self, risk_metrics: RiskMetrics) -> List[str]:
        """Check for leverage limit breaches."""
        breaches = []
        
        if risk_metrics.gross_leverage > self.max_gross_leverage:
            breaches.append(f"Gross leverage ({risk_metrics.gross_leverage:.1f}x) exceeds limit ({self.max_gross_leverage:.1f}x)")
        
        if risk_metrics.net_leverage > self.max_net_leverage:
            breaches.append(f"Net leverage ({risk_metrics.net_leverage:.1f}x) exceeds limit ({self.max_net_leverage:.1f}x)")
        
        return breaches
    
    def check_all_breaches(self, risk_metrics: RiskMetrics) -> List[str]:
        """Check all risk limit breaches."""
        all_breaches = []
        
        all_breaches.extend(self.check_var_breach(risk_metrics))
        all_breaches.extend(self.check_leverage_breach(risk_metrics))
        
        # Drawdown checks
        if risk_metrics.current_drawdown > self.max_drawdown:
            all_breaches.append(f"Current drawdown ({risk_metrics.current_drawdown:.2%}) exceeds limit ({self.max_drawdown:.2%})")
        
        # Volatility checks
        if risk_metrics.portfolio_volatility > self.max_volatility:
            all_breaches.append(f"Portfolio volatility ({risk_metrics.portfolio_volatility:.2%}) exceeds limit ({self.max_volatility:.2%})")
        
        # Concentration checks
        if risk_metrics.portfolio_concentration > self.max_concentration:
            all_breaches.append(f"Portfolio concentration ({risk_metrics.portfolio_concentration:.2f}) exceeds limit ({self.max_concentration:.2f})")
        
        # Liquidity checks
        if risk_metrics.liquidity_score < self.min_liquidity_score:
            all_breaches.append(f"Liquidity score ({risk_metrics.liquidity_score:.2f}) below minimum ({self.min_liquidity_score:.2f})")
        
        return all_breaches


@dataclass
class RiskAlert:
    """Risk monitoring alert."""
    
    alert_id: str
    alert_type: str  # "var_breach", "leverage_breach", "drawdown_breach", etc.
    severity: AlertSeverity
    message: str
    current_value: float
    threshold_value: float
    breach_percentage: float  # How much the threshold was breached by
    
    # Timing information
    alert_time: datetime
    first_breach_time: Optional[datetime] = None  # When this breach first occurred
    
    # Context information
    affected_positions: List[str] = None  # Markets/positions involved
    recommended_actions: List[str] = None  # Suggested remediation actions
    
    # Alert metadata
    is_active: bool = True
    acknowledgment_required: bool = False
    auto_resolution_possible: bool = False
    
    @property
    def breach_severity_score(self) -> float:
        """Calculate breach severity score (0-1)."""
        # Base score on breach percentage
        base_score = min(1.0, self.breach_percentage / 100.0)
        
        # Adjust based on alert type criticality
        criticality_multipliers = {
            'drawdown_breach': 1.5,
            'leverage_breach': 1.3,
            'var_breach': 1.2,
            'liquidity_breach': 1.1,
            'concentration_breach': 1.0
        }
        
        multiplier = criticality_multipliers.get(self.alert_type, 1.0)
        return min(1.0, base_score * multiplier)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'alert_id': self.alert_id,
            'alert_type': self.alert_type,
            'severity': self.severity.value,
            'message': self.message,
            'current_value': self.current_value,
            'threshold_value': self.threshold_value,
            'breach_percentage': self.breach_percentage,
            'alert_time': self.alert_time.isoformat(),
            'first_breach_time': self.first_breach_time.isoformat() if self.first_breach_time else None,
            'affected_positions': self.affected_positions or [],
            'recommended_actions': self.recommended_actions or [],
            'is_active': self.is_active,
            'acknowledgment_required': self.acknowledgment_required,
            'auto_resolution_possible': self.auto_resolution_possible,
            'breach_severity_score': self.breach_severity_score
        }