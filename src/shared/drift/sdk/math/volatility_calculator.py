"""
Volatility Calculator
====================

Shared volatility calculations for all trading engines.
Provides multiple volatility estimation methods with consistent interfaces.

Features:
- Historical volatility (simple and exponentially weighted)
- GARCH volatility modeling
- Realized volatility from high-frequency data
- Implied volatility analysis
- Volatility forecasting
- Volatility regime detection
"""

import math
from typing import List, Dict, Any, Optional, Tuple
from statistics import mean, stdev
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.shared.system.logging import Logger


@dataclass
class VolatilityResult:
    """Volatility calculation result."""
    volatility: float  # Annualized volatility
    method: str  # Calculation method used
    window_days: int  # Window size used
    confidence_interval: Tuple[float, float]
    calculation_date: datetime
    is_forecast: bool  # Whether this is a forecast or historical measure


@dataclass
class VolatilityForecast:
    """Volatility forecast result."""
    current_volatility: float
    forecasted_volatility: float
    forecast_horizon_days: int
    confidence_level: float
    forecast_date: datetime
    model_type: str  # "ewma", "garch", "historical"


@dataclass
class VolatilityRegime:
    """Volatility regime classification."""
    regime_type: str  # "low", "normal", "high", "crisis"
    volatility_level: float
    regime_start_date: datetime
    regime_duration_days: int
    regime_percentile: float  # Percentile relative to historical distribution


@dataclass
class RealizedVolatility:
    """Realized volatility from high-frequency data."""
    daily_rv: List[float]  # Daily realized volatility
    dates: List[datetime]
    average_rv: float
    rv_volatility: float  # Volatility of volatility
    jump_component: float  # Estimated jump contribution


class VolatilityCalculator:
    """
    Stateless volatility calculator with multiple estimation methods.
    
    All methods are static to ensure thread safety and enable
    easy testing and validation.
    """
    
    logger = Logger
    
    @staticmethod
    def historical_volatility(
        returns: List[float],
        window_days: Optional[int] = None,
        trading_days_per_year: int = 252
    ) -> VolatilityResult:
        """
        Calculate historical volatility using standard deviation.
        
        Args:
            returns: List of period returns
            window_days: Optional window size (uses all data if None)
            trading_days_per_year: Trading days per year for annualization
            
        Returns:
            VolatilityResult with historical volatility
        """
        if not returns:
            return VolatilityCalculator._empty_volatility_result("historical")
        
        # Use specified window or all data
        if window_days and window_days < len(returns):
            data = returns[-window_days:]
        else:
            data = returns
            window_days = len(returns)
        
        if len(data) < 2:
            return VolatilityCalculator._empty_volatility_result("historical")
        
        # Calculate standard deviation
        volatility_period = stdev(data)
        
        # Annualize volatility
        annualized_volatility = volatility_period * math.sqrt(trading_days_per_year)
        
        # Calculate confidence interval (approximate)
        confidence_interval = VolatilityCalculator._volatility_confidence_interval(
            volatility_period, len(data), trading_days_per_year
        )
        
        return VolatilityResult(
            volatility=annualized_volatility,
            method="historical",
            window_days=window_days,
            confidence_interval=confidence_interval,
            calculation_date=datetime.now(),
            is_forecast=False
        )
    
    @staticmethod
    def ewma_volatility(
        returns: List[float],
        lambda_param: float = 0.94,
        trading_days_per_year: int = 252
    ) -> VolatilityResult:
        """
        Calculate Exponentially Weighted Moving Average (EWMA) volatility.
        
        Args:
            returns: List of period returns
            lambda_param: Decay factor (default: 0.94 for daily data)
            trading_days_per_year: Trading days per year for annualization
            
        Returns:
            VolatilityResult with EWMA volatility
        """
        if not returns or len(returns) < 2:
            return VolatilityCalculator._empty_volatility_result("ewma")
        
        # Initialize with first squared return
        ewma_variance = returns[0] ** 2
        
        # Calculate EWMA variance
        for ret in returns[1:]:
            ewma_variance = lambda_param * ewma_variance + (1 - lambda_param) * (ret ** 2)
        
        # Convert to volatility and annualize
        ewma_volatility = math.sqrt(ewma_variance)
        annualized_volatility = ewma_volatility * math.sqrt(trading_days_per_year)
        
        # Approximate confidence interval (EWMA has different properties)
        confidence_interval = (
            annualized_volatility * 0.8,
            annualized_volatility * 1.2
        )
        
        return VolatilityResult(
            volatility=annualized_volatility,
            method="ewma",
            window_days=len(returns),
            confidence_interval=confidence_interval,
            calculation_date=datetime.now(),
            is_forecast=False
        )
    
    @staticmethod
    def garch_volatility(
        returns: List[float],
        trading_days_per_year: int = 252
    ) -> VolatilityResult:
        """
        Calculate GARCH(1,1) volatility (simplified implementation).
        
        Args:
            returns: List of period returns
            trading_days_per_year: Trading days per year for annualization
            
        Returns:
            VolatilityResult with GARCH volatility
        """
        if not returns or len(returns) < 10:
            # Fall back to EWMA for insufficient data
            return VolatilityCalculator.ewma_volatility(returns, trading_days_per_year=trading_days_per_year)
        
        # Simplified GARCH(1,1) parameters (would normally be estimated via MLE)
        omega = 0.000001  # Long-term variance component
        alpha = 0.1       # ARCH parameter
        beta = 0.85       # GARCH parameter
        
        # Initialize variance with sample variance
        initial_variance = (stdev(returns[:10]) ** 2) if len(returns) >= 10 else (returns[0] ** 2)
        
        # Calculate GARCH variance
        variances = [initial_variance]
        
        for i, ret in enumerate(returns):
            if i == 0:
                continue
            
            # GARCH(1,1): σ²(t) = ω + α*ε²(t-1) + β*σ²(t-1)
            new_variance = omega + alpha * (returns[i-1] ** 2) + beta * variances[-1]
            variances.append(new_variance)
        
        # Current volatility
        current_variance = variances[-1]
        current_volatility = math.sqrt(current_variance)
        annualized_volatility = current_volatility * math.sqrt(trading_days_per_year)
        
        # Confidence interval based on GARCH properties
        confidence_interval = (
            annualized_volatility * 0.7,
            annualized_volatility * 1.3
        )
        
        return VolatilityResult(
            volatility=annualized_volatility,
            method="garch",
            window_days=len(returns),
            confidence_interval=confidence_interval,
            calculation_date=datetime.now(),
            is_forecast=False
        )
    
    @staticmethod
    def realized_volatility(
        high_freq_returns: List[float],
        sampling_frequency: str = "5min",
        trading_days_per_year: int = 252
    ) -> RealizedVolatility:
        """
        Calculate realized volatility from high-frequency returns.
        
        Args:
            high_freq_returns: High-frequency return series
            sampling_frequency: Frequency of returns ("1min", "5min", "15min", "1h")
            trading_days_per_year: Trading days per year
            
        Returns:
            RealizedVolatility with detailed analysis
        """
        if not high_freq_returns:
            return RealizedVolatility(
                daily_rv=[],
                dates=[],
                average_rv=0.0,
                rv_volatility=0.0,
                jump_component=0.0
            )
        
        # Determine periods per day based on sampling frequency
        periods_per_day = {
            "1min": 390,   # 6.5 hours * 60 minutes
            "5min": 78,    # 6.5 hours * 12 five-minute periods
            "15min": 26,   # 6.5 hours * 4 fifteen-minute periods
            "1h": 6        # 6.5 hours (approximately)
        }.get(sampling_frequency, 78)
        
        # Calculate daily realized volatility
        daily_rv = []
        dates = []
        
        for i in range(0, len(high_freq_returns), periods_per_day):
            day_returns = high_freq_returns[i:i + periods_per_day]
            
            if len(day_returns) >= periods_per_day // 2:  # At least half day of data
                # Realized variance = sum of squared returns
                rv = sum(ret ** 2 for ret in day_returns)
                daily_rv.append(math.sqrt(rv * trading_days_per_year))
                dates.append(datetime.now() - timedelta(days=len(daily_rv)))
        
        if not daily_rv:
            return RealizedVolatility(
                daily_rv=[],
                dates=[],
                average_rv=0.0,
                rv_volatility=0.0,
                jump_component=0.0
            )
        
        # Calculate summary statistics
        average_rv = mean(daily_rv)
        rv_volatility = stdev(daily_rv) if len(daily_rv) > 1 else 0.0
        
        # Estimate jump component (simplified)
        jump_component = VolatilityCalculator._estimate_jump_component(high_freq_returns, periods_per_day)
        
        return RealizedVolatility(
            daily_rv=daily_rv,
            dates=dates,
            average_rv=average_rv,
            rv_volatility=rv_volatility,
            jump_component=jump_component
        )
    
    @staticmethod
    def volatility_forecast(
        returns: List[float],
        forecast_horizon_days: int = 1,
        method: str = "ewma",
        confidence_level: float = 0.95,
        trading_days_per_year: int = 252
    ) -> VolatilityForecast:
        """
        Forecast future volatility.
        
        Args:
            returns: Historical return series
            forecast_horizon_days: Forecast horizon in days
            method: Forecasting method ("ewma", "garch", "historical")
            confidence_level: Confidence level for forecast
            trading_days_per_year: Trading days per year
            
        Returns:
            VolatilityForecast with predicted volatility
        """
        if not returns:
            return VolatilityForecast(
                current_volatility=0.0,
                forecasted_volatility=0.0,
                forecast_horizon_days=forecast_horizon_days,
                confidence_level=confidence_level,
                forecast_date=datetime.now(),
                model_type=method
            )
        
        # Calculate current volatility
        if method == "ewma":
            current_vol_result = VolatilityCalculator.ewma_volatility(returns, trading_days_per_year=trading_days_per_year)
        elif method == "garch":
            current_vol_result = VolatilityCalculator.garch_volatility(returns, trading_days_per_year=trading_days_per_year)
        else:  # historical
            current_vol_result = VolatilityCalculator.historical_volatility(returns, trading_days_per_year=trading_days_per_year)
        
        current_volatility = current_vol_result.volatility
        
        # Simple forecast (would be more sophisticated in practice)
        if method == "ewma":
            # EWMA forecast: volatility mean-reverts slowly
            long_term_vol = VolatilityCalculator.historical_volatility(returns, trading_days_per_year=trading_days_per_year).volatility
            decay_factor = 0.95 ** forecast_horizon_days
            forecasted_volatility = decay_factor * current_volatility + (1 - decay_factor) * long_term_vol
        elif method == "garch":
            # GARCH forecast: mean reversion to long-term volatility
            long_term_vol = mean([abs(ret) for ret in returns]) * math.sqrt(trading_days_per_year * 2 / math.pi)
            decay_factor = 0.9 ** forecast_horizon_days
            forecasted_volatility = decay_factor * current_volatility + (1 - decay_factor) * long_term_vol
        else:
            # Historical: assume persistence
            forecasted_volatility = current_volatility
        
        return VolatilityForecast(
            current_volatility=current_volatility,
            forecasted_volatility=forecasted_volatility,
            forecast_horizon_days=forecast_horizon_days,
            confidence_level=confidence_level,
            forecast_date=datetime.now(),
            model_type=method
        )
    
    @staticmethod
    def detect_volatility_regime(
        returns: List[float],
        window_days: int = 60,
        trading_days_per_year: int = 252
    ) -> VolatilityRegime:
        """
        Detect current volatility regime.
        
        Args:
            returns: Return series
            window_days: Window for regime detection
            trading_days_per_year: Trading days per year
            
        Returns:
            VolatilityRegime classification
        """
        if len(returns) < window_days:
            return VolatilityRegime(
                regime_type="unknown",
                volatility_level=0.0,
                regime_start_date=datetime.now(),
                regime_duration_days=0,
                regime_percentile=0.0
            )
        
        # Calculate current volatility
        current_vol = VolatilityCalculator.historical_volatility(
            returns[-window_days:], trading_days_per_year=trading_days_per_year
        ).volatility
        
        # Calculate historical volatility distribution
        historical_vols = []
        for i in range(window_days, len(returns)):
            window_returns = returns[i-window_days:i]
            vol = stdev(window_returns) * math.sqrt(trading_days_per_year)
            historical_vols.append(vol)
        
        if not historical_vols:
            return VolatilityRegime(
                regime_type="unknown",
                volatility_level=current_vol,
                regime_start_date=datetime.now(),
                regime_duration_days=0,
                regime_percentile=0.0
            )
        
        # Calculate percentile
        sorted_vols = sorted(historical_vols)
        percentile = sum(1 for vol in sorted_vols if vol <= current_vol) / len(sorted_vols)
        
        # Classify regime
        if percentile < 0.25:
            regime_type = "low"
        elif percentile < 0.75:
            regime_type = "normal"
        elif percentile < 0.95:
            regime_type = "high"
        else:
            regime_type = "crisis"
        
        # Estimate regime duration (simplified)
        regime_duration = VolatilityCalculator._estimate_regime_duration(returns, current_vol, window_days)
        
        return VolatilityRegime(
            regime_type=regime_type,
            volatility_level=current_vol,
            regime_start_date=datetime.now() - timedelta(days=regime_duration),
            regime_duration_days=regime_duration,
            regime_percentile=percentile
        )
    
    @staticmethod
    def volatility_surface_analysis(
        returns_dict: Dict[str, List[float]],
        trading_days_per_year: int = 252
    ) -> Dict[str, Dict[str, float]]:
        """
        Analyze volatility surface across multiple assets and time horizons.
        
        Args:
            returns_dict: Dictionary of asset returns
            trading_days_per_year: Trading days per year
            
        Returns:
            Dictionary with volatility analysis for each asset
        """
        surface = {}
        
        for asset, returns in returns_dict.items():
            if not returns or len(returns) < 10:
                continue
            
            asset_analysis = {}
            
            # Multiple time horizons
            horizons = [10, 30, 60, 120, 252]  # Different window sizes
            
            for horizon in horizons:
                if len(returns) >= horizon:
                    vol_result = VolatilityCalculator.historical_volatility(
                        returns, window_days=horizon, trading_days_per_year=trading_days_per_year
                    )
                    asset_analysis[f"vol_{horizon}d"] = vol_result.volatility
            
            # Term structure slope (short vs long term volatility)
            if "vol_30d" in asset_analysis and "vol_120d" in asset_analysis:
                term_structure_slope = asset_analysis["vol_30d"] - asset_analysis["vol_120d"]
                asset_analysis["term_structure_slope"] = term_structure_slope
            
            # Volatility of volatility
            if len(returns) >= 60:
                rolling_vols = []
                for i in range(30, len(returns)):
                    window_returns = returns[i-30:i]
                    vol = stdev(window_returns) * math.sqrt(trading_days_per_year)
                    rolling_vols.append(vol)
                
                if len(rolling_vols) > 1:
                    vol_of_vol = stdev(rolling_vols)
                    asset_analysis["volatility_of_volatility"] = vol_of_vol
            
            surface[asset] = asset_analysis
        
        return surface
    
    @staticmethod
    def _volatility_confidence_interval(
        volatility: float,
        sample_size: int,
        trading_days_per_year: int,
        confidence_level: float = 0.95
    ) -> Tuple[float, float]:
        """Calculate confidence interval for volatility estimate."""
        if sample_size < 4:
            return (volatility, volatility)
        
        # Chi-square distribution for variance
        # Approximate confidence interval
        degrees_of_freedom = sample_size - 1
        
        # Simplified confidence interval (would use chi-square distribution in practice)
        margin_factor = 1.96 / math.sqrt(2 * degrees_of_freedom)  # Approximation
        
        annualized_vol = volatility * math.sqrt(trading_days_per_year)
        margin = annualized_vol * margin_factor
        
        lower_bound = max(0, annualized_vol - margin)
        upper_bound = annualized_vol + margin
        
        return (lower_bound, upper_bound)
    
    @staticmethod
    def _estimate_jump_component(
        high_freq_returns: List[float],
        periods_per_day: int
    ) -> float:
        """Estimate jump component in realized volatility."""
        if len(high_freq_returns) < periods_per_day:
            return 0.0
        
        # Simple jump detection: returns exceeding 3 standard deviations
        if len(high_freq_returns) < 2:
            return 0.0
        
        vol_threshold = 3 * stdev(high_freq_returns)
        
        jump_returns = [ret for ret in high_freq_returns if abs(ret) > vol_threshold]
        jump_variance = sum(ret ** 2 for ret in jump_returns)
        total_variance = sum(ret ** 2 for ret in high_freq_returns)
        
        if total_variance == 0:
            return 0.0
        
        jump_component = jump_variance / total_variance
        return min(1.0, jump_component)
    
    @staticmethod
    def _estimate_regime_duration(
        returns: List[float],
        current_vol: float,
        window_days: int
    ) -> int:
        """Estimate how long the current volatility regime has persisted."""
        if len(returns) < window_days * 2:
            return 0
        
        # Look backwards to find when volatility regime started
        vol_threshold = current_vol * 0.2  # 20% tolerance
        
        duration = 0
        for i in range(len(returns) - window_days, 0, -1):
            window_returns = returns[i:i + window_days]
            if len(window_returns) < window_days:
                break
            
            window_vol = stdev(window_returns) * math.sqrt(252)
            
            if abs(window_vol - current_vol) <= vol_threshold:
                duration += 1
            else:
                break
        
        return duration
    
    @staticmethod
    def _empty_volatility_result(method: str) -> VolatilityResult:
        """Return empty volatility result for edge cases."""
        return VolatilityResult(
            volatility=0.0,
            method=method,
            window_days=0,
            confidence_interval=(0.0, 0.0),
            calculation_date=datetime.now(),
            is_forecast=False
        )