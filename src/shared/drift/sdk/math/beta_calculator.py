"""
Beta Calculator
==============

Shared beta calculations for all trading engines.
Provides beta analysis and systematic risk measurement with consistent interfaces.

Features:
- Market beta calculation (CAPM)
- Rolling beta analysis
- Multi-factor beta models
- Beta stability analysis
- Downside beta (bear market beta)
- Beta forecasting and regime analysis
"""

import math
from typing import List, Dict, Any, Optional, Tuple
from statistics import mean, stdev
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.shared.system.logging import Logger


@dataclass
class BetaResult:
    """Beta calculation result."""
    beta: float
    alpha: float  # Jensen's alpha
    r_squared: float  # Coefficient of determination
    correlation: float
    tracking_error: float
    information_ratio: float
    sample_size: int
    calculation_date: datetime
    is_significant: bool  # Statistical significance


@dataclass
class RollingBeta:
    """Rolling beta analysis result."""
    asset_name: str
    benchmark_name: str
    betas: List[float]
    dates: List[datetime]
    window_size: int
    mean_beta: float
    beta_volatility: float
    beta_trend: str  # "increasing", "decreasing", "stable"
    current_beta: float


@dataclass
class MultifactorBeta:
    """Multi-factor beta model result."""
    asset_name: str
    factor_betas: Dict[str, float]  # Factor name -> beta
    factor_significance: Dict[str, bool]  # Factor name -> is significant
    alpha: float
    r_squared: float
    residual_volatility: float
    model_type: str  # "fama_french_3", "fama_french_5", "custom"


@dataclass
class BetaRegime:
    """Beta regime analysis."""
    regime_type: str  # "low_beta", "market_beta", "high_beta", "defensive", "aggressive"
    beta_level: float
    regime_start_date: datetime
    regime_duration_days: int
    regime_stability: float  # 0 to 1, higher = more stable


@dataclass
class DownsideBeta:
    """Downside beta analysis (bear market sensitivity)."""
    upside_beta: float  # Beta during market up periods
    downside_beta: float  # Beta during market down periods
    beta_asymmetry: float  # Difference between up and down betas
    bear_market_correlation: float
    bull_market_correlation: float


class BetaCalculator:
    """
    Stateless beta calculator with comprehensive analysis methods.
    
    All methods are static to ensure thread safety and enable
    easy testing and validation.
    """
    
    logger = Logger
    
    @staticmethod
    def calculate_beta(
        asset_returns: List[float],
        market_returns: List[float],
        risk_free_rate: float = 0.02,
        trading_days_per_year: int = 252,
        asset_name: str = "Asset",
        benchmark_name: str = "Market"
    ) -> BetaResult:
        """
        Calculate market beta using CAPM model.
        
        Args:
            asset_returns: Asset return series
            market_returns: Market/benchmark return series
            risk_free_rate: Annual risk-free rate
            trading_days_per_year: Trading days per year
            asset_name: Name of the asset
            benchmark_name: Name of the benchmark
            
        Returns:
            BetaResult with beta and related metrics
        """
        if len(asset_returns) != len(market_returns):
            raise ValueError("Asset and market returns must have the same length")
        
        if len(asset_returns) < 2:
            return BetaCalculator._empty_beta_result()
        
        # Convert to excess returns
        daily_rf_rate = risk_free_rate / trading_days_per_year
        asset_excess = [ret - daily_rf_rate for ret in asset_returns]
        market_excess = [ret - daily_rf_rate for ret in market_returns]
        
        # Calculate beta using linear regression (market model)
        beta, alpha, r_squared = BetaCalculator._linear_regression(asset_excess, market_excess)
        
        # Calculate correlation
        correlation = BetaCalculator._calculate_correlation(asset_returns, market_returns)
        
        # Calculate tracking error (standard deviation of excess returns)
        excess_returns = [a - m for a, m in zip(asset_returns, market_returns)]
        tracking_error = stdev(excess_returns) * math.sqrt(trading_days_per_year) if len(excess_returns) > 1 else 0.0
        
        # Information ratio (alpha / tracking error)
        annualized_alpha = alpha * trading_days_per_year
        information_ratio = annualized_alpha / tracking_error if tracking_error != 0 else 0.0
        
        # Test statistical significance
        is_significant = BetaCalculator._test_beta_significance(beta, len(asset_returns), r_squared)
        
        return BetaResult(
            beta=beta,
            alpha=annualized_alpha,
            r_squared=r_squared,
            correlation=correlation,
            tracking_error=tracking_error,
            information_ratio=information_ratio,
            sample_size=len(asset_returns),
            calculation_date=datetime.now(),
            is_significant=is_significant
        )
    
    @staticmethod
    def rolling_beta(
        asset_returns: List[float],
        market_returns: List[float],
        window: int = 60,
        asset_name: str = "Asset",
        benchmark_name: str = "Market"
    ) -> RollingBeta:
        """
        Calculate rolling beta over time.
        
        Args:
            asset_returns: Asset return series
            market_returns: Market return series
            window: Rolling window size
            asset_name: Name of the asset
            benchmark_name: Name of the benchmark
            
        Returns:
            RollingBeta with time series of betas
        """
        if len(asset_returns) != len(market_returns):
            raise ValueError("Asset and market returns must have the same length")
        
        if window > len(asset_returns):
            raise ValueError("Window size cannot be larger than data series")
        
        betas = []
        dates = []
        
        for i in range(window - 1, len(asset_returns)):
            window_asset = asset_returns[i - window + 1:i + 1]
            window_market = market_returns[i - window + 1:i + 1]
            
            try:
                beta, _, _ = BetaCalculator._linear_regression(window_asset, window_market)
                betas.append(beta)
                dates.append(datetime.now() - timedelta(days=len(asset_returns) - i - 1))
            except (ValueError, ZeroDivisionError):
                betas.append(1.0)  # Default to market beta
                dates.append(datetime.now() - timedelta(days=len(asset_returns) - i - 1))
        
        # Calculate summary statistics
        mean_beta = mean(betas) if betas else 1.0
        beta_volatility = stdev(betas) if len(betas) > 1 else 0.0
        current_beta = betas[-1] if betas else 1.0
        
        # Determine trend
        beta_trend = BetaCalculator._determine_beta_trend(betas)
        
        return RollingBeta(
            asset_name=asset_name,
            benchmark_name=benchmark_name,
            betas=betas,
            dates=dates,
            window_size=window,
            mean_beta=mean_beta,
            beta_volatility=beta_volatility,
            beta_trend=beta_trend,
            current_beta=current_beta
        )
    
    @staticmethod
    def multifactor_beta(
        asset_returns: List[float],
        factor_returns: Dict[str, List[float]],
        model_type: str = "custom",
        asset_name: str = "Asset"
    ) -> MultifactorBeta:
        """
        Calculate multi-factor beta model.
        
        Args:
            asset_returns: Asset return series
            factor_returns: Dictionary of factor name -> return series
            model_type: Type of model ("fama_french_3", "fama_french_5", "custom")
            asset_name: Name of the asset
            
        Returns:
            MultifactorBeta with factor exposures
        """
        if not factor_returns:
            return MultifactorBeta(
                asset_name=asset_name,
                factor_betas={},
                factor_significance={},
                alpha=0.0,
                r_squared=0.0,
                residual_volatility=0.0,
                model_type=model_type
            )
        
        # Ensure all factor series have the same length as asset returns
        min_length = min(len(asset_returns), min(len(returns) for returns in factor_returns.values()))
        
        if min_length < 2:
            return MultifactorBeta(
                asset_name=asset_name,
                factor_betas={},
                factor_significance={},
                alpha=0.0,
                r_squared=0.0,
                residual_volatility=0.0,
                model_type=model_type
            )
        
        # Truncate all series to common length
        asset_data = asset_returns[-min_length:]
        factor_data = {name: returns[-min_length:] for name, returns in factor_returns.items()}
        
        # Perform multiple regression (simplified implementation)
        factor_betas = {}
        factor_significance = {}
        
        # For simplicity, calculate each factor beta individually
        # In practice, would use proper multiple regression
        total_r_squared = 0.0
        
        for factor_name, factor_returns_data in factor_data.items():
            try:
                beta, alpha, r_squared = BetaCalculator._linear_regression(asset_data, factor_returns_data)
                factor_betas[factor_name] = beta
                factor_significance[factor_name] = BetaCalculator._test_beta_significance(
                    beta, len(asset_data), r_squared
                )
                total_r_squared = max(total_r_squared, r_squared)  # Simplified
            except (ValueError, ZeroDivisionError):
                factor_betas[factor_name] = 0.0
                factor_significance[factor_name] = False
        
        # Calculate residual volatility
        # Simplified: use the best single-factor model's residuals
        best_factor = max(factor_betas.keys(), key=lambda f: abs(factor_betas[f])) if factor_betas else None
        
        if best_factor:
            predicted_returns = [
                factor_betas[best_factor] * factor_data[best_factor][i]
                for i in range(len(asset_data))
            ]
            residuals = [asset_data[i] - predicted_returns[i] for i in range(len(asset_data))]
            residual_volatility = stdev(residuals) if len(residuals) > 1 else 0.0
        else:
            residual_volatility = stdev(asset_data) if len(asset_data) > 1 else 0.0
        
        # Alpha from the best single-factor model
        if best_factor:
            _, alpha, _ = BetaCalculator._linear_regression(asset_data, factor_data[best_factor])
        else:
            alpha = mean(asset_data) if asset_data else 0.0
        
        return MultifactorBeta(
            asset_name=asset_name,
            factor_betas=factor_betas,
            factor_significance=factor_significance,
            alpha=alpha,
            r_squared=total_r_squared,
            residual_volatility=residual_volatility,
            model_type=model_type
        )
    
    @staticmethod
    def downside_beta(
        asset_returns: List[float],
        market_returns: List[float],
        asset_name: str = "Asset"
    ) -> DownsideBeta:
        """
        Calculate upside and downside beta (asymmetric beta).
        
        Args:
            asset_returns: Asset return series
            market_returns: Market return series
            asset_name: Name of the asset
            
        Returns:
            DownsideBeta with asymmetric beta analysis
        """
        if len(asset_returns) != len(market_returns):
            raise ValueError("Asset and market returns must have the same length")
        
        if len(asset_returns) < 4:
            return DownsideBeta(
                upside_beta=1.0,
                downside_beta=1.0,
                beta_asymmetry=0.0,
                bear_market_correlation=0.0,
                bull_market_correlation=0.0
            )
        
        # Separate up and down market periods
        up_periods = [(a, m) for a, m in zip(asset_returns, market_returns) if m > 0]
        down_periods = [(a, m) for a, m in zip(asset_returns, market_returns) if m < 0]
        
        # Calculate upside beta
        if len(up_periods) >= 2:
            up_asset = [a for a, m in up_periods]
            up_market = [m for a, m in up_periods]
            upside_beta, _, _ = BetaCalculator._linear_regression(up_asset, up_market)
            bull_market_correlation = BetaCalculator._calculate_correlation(up_asset, up_market)
        else:
            upside_beta = 1.0
            bull_market_correlation = 0.0
        
        # Calculate downside beta
        if len(down_periods) >= 2:
            down_asset = [a for a, m in down_periods]
            down_market = [m for a, m in down_periods]
            downside_beta, _, _ = BetaCalculator._linear_regression(down_asset, down_market)
            bear_market_correlation = BetaCalculator._calculate_correlation(down_asset, down_market)
        else:
            downside_beta = 1.0
            bear_market_correlation = 0.0
        
        # Beta asymmetry
        beta_asymmetry = downside_beta - upside_beta
        
        return DownsideBeta(
            upside_beta=upside_beta,
            downside_beta=downside_beta,
            beta_asymmetry=beta_asymmetry,
            bear_market_correlation=bear_market_correlation,
            bull_market_correlation=bull_market_correlation
        )
    
    @staticmethod
    def beta_regime_analysis(
        asset_returns: List[float],
        market_returns: List[float],
        window: int = 60,
        asset_name: str = "Asset"
    ) -> BetaRegime:
        """
        Analyze current beta regime.
        
        Args:
            asset_returns: Asset return series
            market_returns: Market return series
            window: Window for regime analysis
            asset_name: Name of the asset
            
        Returns:
            BetaRegime classification
        """
        if len(asset_returns) < window:
            return BetaRegime(
                regime_type="unknown",
                beta_level=1.0,
                regime_start_date=datetime.now(),
                regime_duration_days=0,
                regime_stability=0.0
            )
        
        # Calculate current beta
        current_beta_result = BetaCalculator.calculate_beta(
            asset_returns[-window:], market_returns[-window:]
        )
        current_beta = current_beta_result.beta
        
        # Classify regime based on beta level
        if current_beta < 0.5:
            regime_type = "defensive"
        elif current_beta < 0.8:
            regime_type = "low_beta"
        elif current_beta < 1.2:
            regime_type = "market_beta"
        elif current_beta < 1.5:
            regime_type = "high_beta"
        else:
            regime_type = "aggressive"
        
        # Calculate rolling beta for stability analysis
        rolling_beta_result = BetaCalculator.rolling_beta(
            asset_returns, market_returns, window=window // 2, asset_name=asset_name
        )
        
        # Regime stability (inverse of beta volatility)
        beta_volatility = rolling_beta_result.beta_volatility
        regime_stability = math.exp(-beta_volatility * 5)  # Scale factor for stability
        regime_stability = min(1.0, max(0.0, regime_stability))
        
        # Estimate regime duration
        regime_duration = BetaCalculator._estimate_beta_regime_duration(
            rolling_beta_result.betas, current_beta
        )
        
        return BetaRegime(
            regime_type=regime_type,
            beta_level=current_beta,
            regime_start_date=datetime.now() - timedelta(days=regime_duration),
            regime_duration_days=regime_duration,
            regime_stability=regime_stability
        )
    
    @staticmethod
    def beta_forecast(
        asset_returns: List[float],
        market_returns: List[float],
        forecast_horizon_days: int = 30,
        method: str = "ewma"
    ) -> float:
        """
        Forecast future beta.
        
        Args:
            asset_returns: Asset return series
            market_returns: Market return series
            forecast_horizon_days: Forecast horizon in days
            method: Forecasting method ("ewma", "rolling_average", "trend")
            
        Returns:
            Forecasted beta
        """
        if len(asset_returns) < 30:
            return 1.0  # Default market beta
        
        if method == "ewma":
            # EWMA-weighted beta calculation
            weights = [0.94 ** i for i in range(len(asset_returns))]
            weights.reverse()  # Most recent gets highest weight
            
            # Weighted covariance and variance
            asset_mean = sum(w * r for w, r in zip(weights, asset_returns)) / sum(weights)
            market_mean = sum(w * r for w, r in zip(weights, market_returns)) / sum(weights)
            
            weighted_covariance = sum(
                w * (a - asset_mean) * (m - market_mean)
                for w, a, m in zip(weights, asset_returns, market_returns)
            ) / sum(weights)
            
            weighted_market_variance = sum(
                w * (m - market_mean) ** 2
                for w, m in zip(weights, market_returns)
            ) / sum(weights)
            
            if weighted_market_variance == 0:
                return 1.0
            
            forecasted_beta = weighted_covariance / weighted_market_variance
            
        elif method == "rolling_average":
            # Simple rolling average of recent betas
            window = min(60, len(asset_returns))
            rolling_beta_result = BetaCalculator.rolling_beta(
                asset_returns, market_returns, window=window // 3
            )
            forecasted_beta = rolling_beta_result.mean_beta
            
        elif method == "trend":
            # Trend-based forecast
            rolling_beta_result = BetaCalculator.rolling_beta(
                asset_returns, market_returns, window=30
            )
            
            if len(rolling_beta_result.betas) >= 2:
                # Simple linear trend
                recent_betas = rolling_beta_result.betas[-10:]  # Last 10 observations
                trend_slope = (recent_betas[-1] - recent_betas[0]) / len(recent_betas)
                forecasted_beta = recent_betas[-1] + trend_slope * (forecast_horizon_days / 30)
            else:
                forecasted_beta = 1.0
        else:
            # Default to current beta
            current_beta_result = BetaCalculator.calculate_beta(asset_returns[-60:], market_returns[-60:])
            forecasted_beta = current_beta_result.beta
        
        # Clamp to reasonable range
        return max(-2.0, min(3.0, forecasted_beta))
    
    @staticmethod
    def _linear_regression(y: List[float], x: List[float]) -> Tuple[float, float, float]:
        """
        Perform simple linear regression: y = alpha + beta * x
        
        Returns:
            Tuple of (beta, alpha, r_squared)
        """
        if len(x) != len(y) or len(x) < 2:
            raise ValueError("Invalid data for regression")
        
        n = len(x)
        
        # Calculate means
        x_mean = mean(x)
        y_mean = mean(y)
        
        # Calculate beta (slope)
        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return 0.0, y_mean, 0.0
        
        beta = numerator / denominator
        
        # Calculate alpha (intercept)
        alpha = y_mean - beta * x_mean
        
        # Calculate R-squared
        y_pred = [alpha + beta * x[i] for i in range(n)]
        ss_res = sum((y[i] - y_pred[i]) ** 2 for i in range(n))
        ss_tot = sum((y[i] - y_mean) ** 2 for i in range(n))
        
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0.0
        r_squared = max(0.0, min(1.0, r_squared))  # Clamp to [0, 1]
        
        return beta, alpha, r_squared
    
    @staticmethod
    def _calculate_correlation(x: List[float], y: List[float]) -> float:
        """Calculate Pearson correlation coefficient."""
        if len(x) != len(y) or len(x) < 2:
            return 0.0
        
        x_mean = mean(x)
        y_mean = mean(y)
        
        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(len(x)))
        
        x_ss = sum((x[i] - x_mean) ** 2 for i in range(len(x)))
        y_ss = sum((y[i] - y_mean) ** 2 for i in range(len(y)))
        
        denominator = math.sqrt(x_ss * y_ss)
        
        if denominator == 0:
            return 0.0
        
        correlation = numerator / denominator
        return max(-1.0, min(1.0, correlation))
    
    @staticmethod
    def _test_beta_significance(beta: float, sample_size: int, r_squared: float) -> bool:
        """Test if beta is statistically significant."""
        if sample_size < 4 or r_squared >= 1.0:
            return False
        
        # Calculate t-statistic for beta
        # t = beta / SE(beta), where SE(beta) = sqrt((1-R²)/(n-2)) * sqrt(1/Σ(x-x̄)²)
        # Simplified approximation
        degrees_of_freedom = sample_size - 2
        
        if degrees_of_freedom <= 0:
            return False
        
        # Approximate standard error
        se_beta = math.sqrt((1 - r_squared) / degrees_of_freedom)
        
        if se_beta == 0:
            return abs(beta) > 0.1  # Arbitrary threshold
        
        t_stat = abs(beta / se_beta)
        
        # Critical value for 95% confidence (approximation)
        critical_value = 1.96 if degrees_of_freedom > 30 else 2.0
        
        return t_stat > critical_value
    
    @staticmethod
    def _determine_beta_trend(betas: List[float]) -> str:
        """Determine trend in beta series."""
        if len(betas) < 3:
            return "stable"
        
        # Simple trend detection
        first_third = betas[:len(betas) // 3]
        last_third = betas[-len(betas) // 3:]
        
        first_avg = mean(first_third)
        last_avg = mean(last_third)
        
        change = last_avg - first_avg
        
        if change > 0.1:
            return "increasing"
        elif change < -0.1:
            return "decreasing"
        else:
            return "stable"
    
    @staticmethod
    def _estimate_beta_regime_duration(betas: List[float], current_beta: float) -> int:
        """Estimate how long the current beta regime has persisted."""
        if not betas:
            return 0
        
        # Look backwards to find when beta regime started
        beta_threshold = abs(current_beta) * 0.2  # 20% tolerance
        
        duration = 0
        for i in range(len(betas) - 1, -1, -1):
            if abs(betas[i] - current_beta) <= beta_threshold:
                duration += 1
            else:
                break
        
        return duration
    
    @staticmethod
    def _empty_beta_result() -> BetaResult:
        """Return empty beta result for edge cases."""
        return BetaResult(
            beta=1.0,
            alpha=0.0,
            r_squared=0.0,
            correlation=0.0,
            tracking_error=0.0,
            information_ratio=0.0,
            sample_size=0,
            calculation_date=datetime.now(),
            is_significant=False
        )