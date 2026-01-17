"""
Volatility Calculator
====================

Shared volatility calculations for all trading engines.
Provides multiple volatility estimation methods and forecasting capabilities.

Features:
- Historical volatility calculations
- EWMA (Exponentially Weighted Moving Average) volatility
- GARCH volatility modeling
- Realized volatility calculations
- Volatility forecasting
- Volatility regime detection
"""

import math
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
from statistics import mean, stdev

from src.shared.system.logging import Logger


@dataclass
class VolatilityResult:
    """Volatility calculation result."""
    volatility: float
    annualized_volatility: float
    method: str
    sample_size: int
    calculation_date: datetime
    confidence_interval: Optional[Tuple[float, float]] = None


@dataclass
class VolatilityForecast:
    """Volatility forecast result."""
    current_volatility: float
    forecasted_volatility: float
    forecast_horizon: int  # days
    confidence_interval: Tuple[float, float]
    method: str
    forecast_date: datetime


@dataclass
class VolatilityRegime:
    """Volatility regime classification."""
    current_regime: str  # "low", "normal", "high", "extreme"
    regime_probability: float
    regime_threshold: Dict[str, float]
    regime_duration: int  # days in current regime
    last_regime_change: Optional[datetime]


@dataclass
class RealizedVolatility:
    """Realized volatility calculation result."""
    daily_volatility: float
    weekly_volatility: float
    monthly_volatility: float
    intraday_volatility: Optional[float]
    overnight_volatility: Optional[float]
    calculation_period: int  # days


class VolatilityCalculator:
    """
    Stateless volatility calculator with multiple estimation methods.
    
    All methods are static to ensure thread safety and enable
    easy testing and validation.
    """
    
    logger = Logger
    
    # Volatility regime thresholds (annualized)
    REGIME_THRESHOLDS = {
        "low": 0.15,      # < 15% annualized
        "normal": 0.30,   # 15-30% annualized
        "high": 0.50,     # 30-50% annualized
        "extreme": 1.0    # > 50% annualized
    }
    
    @staticmethod
    def historical_volatility(
        returns: List[float], 
        annualize: bool = True,
        trading_days_per_year: int = 365
    ) -> VolatilityResult:
        """
        Calculate historical volatility using standard deviation.
        
        Args:
            returns: Return series
            annualize: Whether to annualize the volatility
            trading_days_per_year: Trading days per year for annualization
            
        Returns:
            VolatilityResult with historical volatility
            
        Raises:
            ValueError: If insufficient data provided
        """
        if len(returns) < 2:
            raise ValueError("Need at least 2 returns for volatility calculation")
        
        # Calculate daily volatility
        daily_vol = stdev(returns)
        
        # Annualize if requested
        if annualize:
            annualized_vol = daily_vol * math.sqrt(trading_days_per_year)
        else:
            annualized_vol = daily_vol
        
        return VolatilityResult(
            volatility=daily_vol,
            annualized_volatility=annualized_vol,
            method="historical",
            sample_size=len(returns),
            calculation_date=datetime.now()
        )
    
    @staticmethod
    def ewma_volatility(
        returns: List[float], 
        lambda_param: float = 0.94,
        annualize: bool = True,
        trading_days_per_year: int = 365
    ) -> VolatilityResult:
        """
        Calculate EWMA (Exponentially Weighted Moving Average) volatility.
        
        Args:
            returns: Return series
            lambda_param: Decay factor (default: 0.94, RiskMetrics standard)
            annualize: Whether to annualize the volatility
            trading_days_per_year: Trading days per year for annualization
            
        Returns:
            VolatilityResult with EWMA volatility
            
        Raises:
            ValueError: If insufficient data or invalid lambda parameter
        """
        if len(returns) < 2:
            raise ValueError("Need at least 2 returns for EWMA volatility")
        
        if not 0 < lambda_param < 1:
            raise ValueError("Lambda parameter must be between 0 and 1")
        
        # Initialize with first squared return
        ewma_variance = returns[0] ** 2
        
        # Calculate EWMA variance
        for i in range(1, len(returns)):
            ewma_variance = lambda_param * ewma_variance + (1 - lambda_param) * (returns[i] ** 2)
        
        # Calculate volatility
        daily_vol = math.sqrt(ewma_variance)
        
        # Annualize if requested
        if annualize:
            annualized_vol = daily_vol * math.sqrt(trading_days_per_year)
        else:
            annualized_vol = daily_vol
        
        return VolatilityResult(
            volatility=daily_vol,
            annualized_volatility=annualized_vol,
            method=f"ewma_lambda_{lambda_param}",
            sample_size=len(returns),
            calculation_date=datetime.now()
        )
    
    @staticmethod
    def garch_volatility(
        returns: List[float],
        alpha: float = 0.1,
        beta: float = 0.85,
        omega: float = 0.000001,
        annualize: bool = True,
        trading_days_per_year: int = 365
    ) -> VolatilityResult:
        """
        Calculate GARCH(1,1) volatility estimate.
        
        Args:
            returns: Return series
            alpha: ARCH parameter (default: 0.1)
            beta: GARCH parameter (default: 0.85)
            omega: Constant term (default: 0.000001)
            annualize: Whether to annualize the volatility
            trading_days_per_year: Trading days per year for annualization
            
        Returns:
            VolatilityResult with GARCH volatility
            
        Raises:
            ValueError: If insufficient data or invalid parameters
        """
        if len(returns) < 10:
            raise ValueError("Need at least 10 returns for GARCH volatility")
        
        if alpha + beta >= 1.0:
            raise ValueError("Alpha + Beta must be less than 1 for stationarity")
        
        if alpha < 0 or beta < 0 or omega < 0:
            raise ValueError("GARCH parameters must be non-negative")
        
        # Initialize variance with sample variance
        initial_variance = sum(r ** 2 for r in returns[:10]) / 10
        variance = initial_variance
        
        # GARCH(1,1) recursion
        for i in range(1, len(returns)):
            variance = omega + alpha * (returns[i-1] ** 2) + beta * variance
        
        # Calculate volatility
        daily_vol = math.sqrt(variance)
        
        # Annualize if requested
        if annualize:
            annualized_vol = daily_vol * math.sqrt(trading_days_per_year)
        else:
            annualized_vol = daily_vol
        
        return VolatilityResult(
            volatility=daily_vol,
            annualized_volatility=annualized_vol,
            method=f"garch_a{alpha}_b{beta}",
            sample_size=len(returns),
            calculation_date=datetime.now()
        )
    
    @staticmethod
    def realized_volatility(
        returns: List[float],
        intraday_returns: Optional[List[float]] = None,
        overnight_returns: Optional[List[float]] = None,
        annualize: bool = True,
        trading_days_per_year: int = 365
    ) -> RealizedVolatility:
        """
        Calculate realized volatility with optional intraday/overnight decomposition.
        
        Args:
            returns: Daily return series
            intraday_returns: Optional intraday return series
            overnight_returns: Optional overnight return series
            annualize: Whether to annualize volatilities
            trading_days_per_year: Trading days per year for annualization
            
        Returns:
            RealizedVolatility with multiple time horizon volatilities
        """
        if len(returns) < 2:
            raise ValueError("Need at least 2 returns for realized volatility")
        
        # Daily volatility
        daily_vol = stdev(returns)
        
        # Weekly volatility (if enough data)
        if len(returns) >= 7:
            # Group returns into weeks and calculate weekly volatility
            weekly_returns = []
            for i in range(0, len(returns) - 6, 7):
                week_return = sum(returns[i:i+7])
                weekly_returns.append(week_return)
            
            weekly_vol = stdev(weekly_returns) if len(weekly_returns) > 1 else daily_vol * math.sqrt(7)
        else:
            weekly_vol = daily_vol * math.sqrt(7)
        
        # Monthly volatility (if enough data)
        if len(returns) >= 30:
            # Group returns into months and calculate monthly volatility
            monthly_returns = []
            for i in range(0, len(returns) - 29, 30):
                month_return = sum(returns[i:i+30])
                monthly_returns.append(month_return)
            
            monthly_vol = stdev(monthly_returns) if len(monthly_returns) > 1 else daily_vol * math.sqrt(30)
        else:
            monthly_vol = daily_vol * math.sqrt(30)
        
        # Intraday volatility
        intraday_vol = None
        if intraday_returns and len(intraday_returns) > 1:
            intraday_vol = stdev(intraday_returns)
        
        # Overnight volatility
        overnight_vol = None
        if overnight_returns and len(overnight_returns) > 1:
            overnight_vol = stdev(overnight_returns)
        
        # Annualize if requested
        if annualize:
            daily_vol *= math.sqrt(trading_days_per_year)
            weekly_vol *= math.sqrt(52)  # 52 weeks per year
            monthly_vol *= math.sqrt(12)  # 12 months per year
            
            if intraday_vol:
                intraday_vol *= math.sqrt(trading_days_per_year)
            if overnight_vol:
                overnight_vol *= math.sqrt(trading_days_per_year)
        
        return RealizedVolatility(
            daily_volatility=daily_vol,
            weekly_volatility=weekly_vol,
            monthly_volatility=monthly_vol,
            intraday_volatility=intraday_vol,
            overnight_volatility=overnight_vol,
            calculation_period=len(returns)
        )
    
    @staticmethod
    def forecast_volatility(
        returns: List[float],
        forecast_horizon: int = 1,
        method: str = "ewma",
        confidence_level: float = 0.95
    ) -> VolatilityForecast:
        """
        Forecast volatility for specified horizon.
        
        Args:
            returns: Historical return series
            forecast_horizon: Forecast horizon in days
            method: Forecasting method ("ewma", "garch", "historical")
            confidence_level: Confidence level for forecast interval
            
        Returns:
            VolatilityForecast with forecasted volatility
        """
        if len(returns) < 10:
            raise ValueError("Need at least 10 returns for volatility forecasting")
        
        # Calculate current volatility
        if method == "ewma":
            current_vol_result = VolatilityCalculator.ewma_volatility(returns, annualize=False)
        elif method == "garch":
            current_vol_result = VolatilityCalculator.garch_volatility(returns, annualize=False)
        else:  # historical
            current_vol_result = VolatilityCalculator.historical_volatility(returns, annualize=False)
        
        current_vol = current_vol_result.volatility
        
        # Simple forecast scaling (square root of time rule)
        forecasted_vol = current_vol * math.sqrt(forecast_horizon)
        
        # Calculate confidence interval (approximate)
        # Using chi-square distribution approximation for volatility forecasts
        n = len(returns)
        chi_lower = (n - 1) / (n - 1 + 1.96 * math.sqrt(2 * (n - 1)))  # Approximate
        chi_upper = (n - 1) / (n - 1 - 1.96 * math.sqrt(2 * (n - 1)))  # Approximate
        
        lower_bound = forecasted_vol * math.sqrt(chi_lower)
        upper_bound = forecasted_vol * math.sqrt(chi_upper)
        
        return VolatilityForecast(
            current_volatility=current_vol,
            forecasted_volatility=forecasted_vol,
            forecast_horizon=forecast_horizon,
            confidence_interval=(lower_bound, upper_bound),
            method=method,
            forecast_date=datetime.now()
        )
    
    @staticmethod
    def detect_volatility_regime(
        returns: List[float],
        lookback_window: int = 30,
        regime_thresholds: Optional[Dict[str, float]] = None
    ) -> VolatilityRegime:
        """
        Detect current volatility regime based on recent volatility levels.
        
        Args:
            returns: Return series
            lookback_window: Window for current volatility calculation
            regime_thresholds: Custom regime thresholds (optional)
            
        Returns:
            VolatilityRegime with regime classification
        """
        if len(returns) < lookback_window:
            raise ValueError(f"Need at least {lookback_window} returns for regime detection")
        
        # Use default thresholds if not provided
        thresholds = regime_thresholds or VolatilityCalculator.REGIME_THRESHOLDS
        
        # Calculate recent volatility
        recent_returns = returns[-lookback_window:]
        recent_vol_result = VolatilityCalculator.historical_volatility(recent_returns, annualize=True)
        current_vol = recent_vol_result.annualized_volatility
        
        # Classify regime
        if current_vol < thresholds["low"]:
            current_regime = "low"
            regime_probability = 1.0 - (current_vol / thresholds["low"])
        elif current_vol < thresholds["normal"]:
            current_regime = "normal"
            regime_probability = 1.0 - abs(current_vol - (thresholds["low"] + thresholds["normal"]) / 2) / (thresholds["normal"] - thresholds["low"])
        elif current_vol < thresholds["high"]:
            current_regime = "high"
            regime_probability = 1.0 - abs(current_vol - (thresholds["normal"] + thresholds["high"]) / 2) / (thresholds["high"] - thresholds["normal"])
        else:
            current_regime = "extreme"
            regime_probability = min(1.0, current_vol / thresholds["extreme"])
        
        # Estimate regime duration (simplified)
        regime_duration = 1  # Would need historical regime tracking for accurate duration
        
        return VolatilityRegime(
            current_regime=current_regime,
            regime_probability=max(0.0, min(1.0, regime_probability)),
            regime_threshold=thresholds,
            regime_duration=regime_duration,
            last_regime_change=None  # Would need historical tracking
        )
    
    @staticmethod
    def volatility_contribution(
        portfolio_returns: List[float],
        asset_returns: Dict[str, List[float]],
        weights: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Calculate each asset's contribution to portfolio volatility.
        
        Args:
            portfolio_returns: Portfolio return series
            asset_returns: Dictionary of asset return series
            weights: Dictionary of asset weights
            
        Returns:
            Dictionary mapping asset names to volatility contributions
        """
        if not asset_returns:
            return {}
        
        # Calculate portfolio volatility
        portfolio_vol = stdev(portfolio_returns) if len(portfolio_returns) > 1 else 0.0
        
        if portfolio_vol == 0:
            return {asset: 0.0 for asset in asset_returns.keys()}
        
        # Calculate asset volatilities and correlations with portfolio
        contributions = {}
        
        for asset, returns in asset_returns.items():
            if asset not in weights:
                contributions[asset] = 0.0
                continue
            
            if len(returns) != len(portfolio_returns):
                contributions[asset] = 0.0
                continue
            
            # Asset volatility
            asset_vol = stdev(returns) if len(returns) > 1 else 0.0
            
            # Correlation with portfolio
            if asset_vol > 0:
                from .correlation_calculator import CorrelationCalculator
                correlation = CorrelationCalculator.pearson_correlation(returns, portfolio_returns)
            else:
                correlation = 0.0
            
            # Volatility contribution = weight * asset_vol * correlation / portfolio_vol
            weight = weights[asset]
            contribution = (weight * asset_vol * correlation) / portfolio_vol if portfolio_vol > 0 else 0.0
            contributions[asset] = contribution
        
        return contributions
    
    @staticmethod
    def volatility_adjusted_returns(
        returns: List[float],
        target_volatility: float = 0.15,
        lookback_window: int = 30
    ) -> List[float]:
        """
        Adjust returns to target volatility level using volatility scaling.
        
        Args:
            returns: Return series to adjust
            target_volatility: Target annualized volatility
            lookback_window: Window for volatility calculation
            
        Returns:
            List of volatility-adjusted returns
        """
        if len(returns) < lookback_window:
            return returns  # Not enough data for adjustment
        
        adjusted_returns = []
        
        for i in range(len(returns)):
            if i < lookback_window:
                # Not enough history, use original return
                adjusted_returns.append(returns[i])
            else:
                # Calculate recent volatility
                recent_returns = returns[i-lookback_window:i]
                recent_vol_result = VolatilityCalculator.historical_volatility(
                    recent_returns, annualize=True
                )
                current_vol = recent_vol_result.annualized_volatility
                
                # Calculate scaling factor
                if current_vol > 0:
                    scaling_factor = target_volatility / current_vol
                    adjusted_return = returns[i] * scaling_factor
                else:
                    adjusted_return = returns[i]
                
                adjusted_returns.append(adjusted_return)
        
        return adjusted_returns