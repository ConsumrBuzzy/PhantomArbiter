"""
Risk Limits Configuration
========================

Defines risk limits and thresholds for portfolio risk management.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass

from ..sdk.models.risk import RiskMetrics


@dataclass
class RiskLimits:
    """
    Risk limits configuration for portfolio risk management.
    
    Defines maximum allowable risk levels across various dimensions.
    """
    
    # VaR limits
    max_var_1d: float = 50000.0  # Maximum 1-day VaR in USD
    max_var_7d: float = 150000.0  # Maximum 7-day VaR in USD
    var_confidence_level: float = 0.95  # VaR confidence level
    
    # Leverage limits
    max_leverage: float = 3.0  # Maximum portfolio leverage
    max_gross_leverage: float = 5.0  # Maximum gross leverage
    emergency_leverage_threshold: float = 4.0  # Emergency deleveraging threshold
    
    # Position limits
    max_position_size: float = 100000.0  # Maximum single position size in USD
    max_position_percentage: float = 0.20  # Maximum position as % of portfolio (20%)
    max_single_asset_exposure: float = 0.30  # Maximum exposure to single asset (30%)
    
    # Concentration limits
    max_concentration: float = 0.40  # Maximum portfolio concentration (HHI)
    min_diversification_ratio: float = 0.60  # Minimum diversification ratio
    max_sector_exposure: float = 0.50  # Maximum sector exposure (50%)
    
    # Drawdown limits
    max_drawdown: float = 0.15  # Maximum drawdown (15%)
    max_daily_loss: float = 0.05  # Maximum daily loss (5%)
    stop_loss_threshold: float = 0.10  # Stop loss threshold (10%)
    
    # Correlation limits
    max_correlation: float = 0.80  # Maximum average correlation with existing positions
    min_correlation_window: int = 30  # Minimum days for correlation calculation
    
    # Market condition limits
    max_spread_bps: float = 100.0  # Maximum spread in basis points
    max_market_volatility: float = 0.50  # Maximum market volatility (50% annualized)
    min_liquidity_score: float = 0.60  # Minimum liquidity score
    
    # Health and margin limits
    min_health_ratio: float = 0.20  # Minimum health ratio (20%)
    min_margin_buffer: float = 0.10  # Minimum margin buffer (10%)
    max_margin_utilization: float = 0.80  # Maximum margin utilization (80%)
    
    # Time-based limits
    max_daily_trades: int = 50  # Maximum trades per day
    max_hourly_trades: int = 10  # Maximum trades per hour
    cooldown_period_minutes: int = 5  # Minimum time between trades
    
    # Engine-specific limits
    engine_limits: Dict[str, Dict[str, Any]] = None
    
    def __post_init__(self):
        """Initialize engine-specific limits if not provided."""
        if self.engine_limits is None:
            self.engine_limits = {
                'DeltaNeutralHedgingEngine': {
                    'max_daily_trades': 20,
                    'max_exposure': 200000.0,
                    'max_position_percentage': 0.15
                },
                'VolatilityArbitrageEngine': {
                    'max_daily_trades': 30,
                    'max_exposure': 150000.0,
                    'max_position_percentage': 0.10
                },
                'RiskParityEngine': {
                    'max_daily_trades': 10,
                    'max_exposure': 500000.0,
                    'max_position_percentage': 0.25
                }
            }
    
    def check_var_breach(self, risk_metrics: RiskMetrics) -> Optional[str]:
        """Check for VaR limit breaches."""
        if risk_metrics.var_1d > self.max_var_1d:
            return f"1-day VaR ({risk_metrics.var_1d:.2f}) exceeds limit ({self.max_var_1d:.2f})"
        
        if risk_metrics.var_7d > self.max_var_7d:
            return f"7-day VaR ({risk_metrics.var_7d:.2f}) exceeds limit ({self.max_var_7d:.2f})"
        
        return None
    
    def check_leverage_breach(self, leverage: float, gross_leverage: float = None) -> Optional[str]:
        """Check for leverage limit breaches."""
        if leverage > self.max_leverage:
            return f"Leverage ({leverage:.2f}x) exceeds limit ({self.max_leverage:.2f}x)"
        
        if gross_leverage and gross_leverage > self.max_gross_leverage:
            return f"Gross leverage ({gross_leverage:.2f}x) exceeds limit ({self.max_gross_leverage:.2f}x)"
        
        return None
    
    def check_concentration_breach(self, risk_metrics: RiskMetrics) -> Optional[str]:
        """Check for concentration limit breaches."""
        if risk_metrics.portfolio_concentration > self.max_concentration:
            return f"Portfolio concentration ({risk_metrics.portfolio_concentration:.1%}) exceeds limit ({self.max_concentration:.1%})"
        
        if risk_metrics.diversification_ratio < self.min_diversification_ratio:
            return f"Diversification ratio ({risk_metrics.diversification_ratio:.1%}) below minimum ({self.min_diversification_ratio:.1%})"
        
        return None
    
    def check_drawdown_breach(self, risk_metrics: RiskMetrics) -> Optional[str]:
        """Check for drawdown limit breaches."""
        if risk_metrics.max_drawdown > self.max_drawdown:
            return f"Maximum drawdown ({risk_metrics.max_drawdown:.1%}) exceeds limit ({self.max_drawdown:.1%})"
        
        if risk_metrics.current_drawdown > self.max_drawdown:
            return f"Current drawdown ({risk_metrics.current_drawdown:.1%}) exceeds limit ({self.max_drawdown:.1%})"
        
        return None
    
    def check_health_breach(self, health_ratio: float) -> Optional[str]:
        """Check for health ratio breaches."""
        if health_ratio < self.min_health_ratio:
            return f"Health ratio ({health_ratio:.2f}) below minimum ({self.min_health_ratio:.2f})"
        
        return None
    
    def check_all_breaches(self, risk_metrics: RiskMetrics, leverage: float = None, health_ratio: float = None) -> List[str]:
        """Check all risk limit breaches."""
        breaches = []
        
        # VaR breaches
        var_breach = self.check_var_breach(risk_metrics)
        if var_breach:
            breaches.append(var_breach)
        
        # Leverage breaches
        if leverage is not None:
            leverage_breach = self.check_leverage_breach(leverage, risk_metrics.gross_leverage)
            if leverage_breach:
                breaches.append(leverage_breach)
        
        # Concentration breaches
        concentration_breach = self.check_concentration_breach(risk_metrics)
        if concentration_breach:
            breaches.append(concentration_breach)
        
        # Drawdown breaches
        drawdown_breach = self.check_drawdown_breach(risk_metrics)
        if drawdown_breach:
            breaches.append(drawdown_breach)
        
        # Health breaches
        if health_ratio is not None:
            health_breach = self.check_health_breach(health_ratio)
            if health_breach:
                breaches.append(health_breach)
        
        return breaches
    
    def get_engine_limits(self, engine_name: str) -> Optional[Dict[str, Any]]:
        """Get limits for specific engine."""
        return self.engine_limits.get(engine_name)
    
    def set_engine_limits(self, engine_name: str, limits: Dict[str, Any]) -> None:
        """Set limits for specific engine."""
        self.engine_limits[engine_name] = limits
    
    def scale_limits(self, scale_factor: float) -> 'RiskLimits':
        """Scale all limits by a factor (useful for different account sizes)."""
        return RiskLimits(
            max_var_1d=self.max_var_1d * scale_factor,
            max_var_7d=self.max_var_7d * scale_factor,
            var_confidence_level=self.var_confidence_level,
            max_leverage=self.max_leverage,
            max_gross_leverage=self.max_gross_leverage,
            emergency_leverage_threshold=self.emergency_leverage_threshold,
            max_position_size=self.max_position_size * scale_factor,
            max_position_percentage=self.max_position_percentage,
            max_single_asset_exposure=self.max_single_asset_exposure,
            max_concentration=self.max_concentration,
            min_diversification_ratio=self.min_diversification_ratio,
            max_sector_exposure=self.max_sector_exposure,
            max_drawdown=self.max_drawdown,
            max_daily_loss=self.max_daily_loss,
            stop_loss_threshold=self.stop_loss_threshold,
            max_correlation=self.max_correlation,
            min_correlation_window=self.min_correlation_window,
            max_spread_bps=self.max_spread_bps,
            max_market_volatility=self.max_market_volatility,
            min_liquidity_score=self.min_liquidity_score,
            min_health_ratio=self.min_health_ratio,
            min_margin_buffer=self.min_margin_buffer,
            max_margin_utilization=self.max_margin_utilization,
            max_daily_trades=self.max_daily_trades,
            max_hourly_trades=self.max_hourly_trades,
            cooldown_period_minutes=self.cooldown_period_minutes,
            engine_limits={
                engine: {
                    key: value * scale_factor if key in ['max_exposure', 'max_position_size'] else value
                    for key, value in limits.items()
                }
                for engine, limits in self.engine_limits.items()
            }
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'max_var_1d': self.max_var_1d,
            'max_var_7d': self.max_var_7d,
            'var_confidence_level': self.var_confidence_level,
            'max_leverage': self.max_leverage,
            'max_gross_leverage': self.max_gross_leverage,
            'emergency_leverage_threshold': self.emergency_leverage_threshold,
            'max_position_size': self.max_position_size,
            'max_position_percentage': self.max_position_percentage,
            'max_single_asset_exposure': self.max_single_asset_exposure,
            'max_concentration': self.max_concentration,
            'min_diversification_ratio': self.min_diversification_ratio,
            'max_sector_exposure': self.max_sector_exposure,
            'max_drawdown': self.max_drawdown,
            'max_daily_loss': self.max_daily_loss,
            'stop_loss_threshold': self.stop_loss_threshold,
            'max_correlation': self.max_correlation,
            'min_correlation_window': self.min_correlation_window,
            'max_spread_bps': self.max_spread_bps,
            'max_market_volatility': self.max_market_volatility,
            'min_liquidity_score': self.min_liquidity_score,
            'min_health_ratio': self.min_health_ratio,
            'min_margin_buffer': self.min_margin_buffer,
            'max_margin_utilization': self.max_margin_utilization,
            'max_daily_trades': self.max_daily_trades,
            'max_hourly_trades': self.max_hourly_trades,
            'cooldown_period_minutes': self.cooldown_period_minutes,
            'engine_limits': self.engine_limits
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RiskLimits':
        """Create from dictionary."""
        return cls(**data)
    
    @classmethod
    def conservative(cls) -> 'RiskLimits':
        """Create conservative risk limits."""
        return cls(
            max_var_1d=25000.0,
            max_var_7d=75000.0,
            max_leverage=2.0,
            max_position_percentage=0.10,
            max_single_asset_exposure=0.20,
            max_concentration=0.30,
            max_drawdown=0.10,
            max_daily_loss=0.03,
            max_correlation=0.70,
            max_daily_trades=20
        )
    
    @classmethod
    def aggressive(cls) -> 'RiskLimits':
        """Create aggressive risk limits."""
        return cls(
            max_var_1d=100000.0,
            max_var_7d=300000.0,
            max_leverage=5.0,
            max_position_percentage=0.30,
            max_single_asset_exposure=0.40,
            max_concentration=0.50,
            max_drawdown=0.20,
            max_daily_loss=0.08,
            max_correlation=0.90,
            max_daily_trades=100
        )