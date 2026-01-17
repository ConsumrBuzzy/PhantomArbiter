"""
Correlation Calculator
=====================

Shared correlation calculations for all trading engines.
Provides correlation analysis with consistent interfaces.

Features:
- Pearson correlation coefficient
- Rolling correlation analysis
- Correlation matrix calculations
- Correlation stability analysis
- Cross-asset correlation monitoring
- Regime change detection based on correlation shifts
"""

import math
from typing import List, Dict, Any, Optional, Tuple
from statistics import mean, stdev
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.shared.system.logging import Logger


@dataclass
class CorrelationResult:
    """Single correlation calculation result."""
    asset1: str
    asset2: str
    correlation: float
    confidence_interval: Tuple[float, float]
    sample_size: int
    calculation_date: datetime
    is_significant: bool  # Statistical significance at 95% level


@dataclass
class CorrelationMatrix:
    """Correlation matrix with metadata."""
    matrix: Dict[str, Dict[str, float]]
    assets: List[str]
    calculation_date: datetime
    window_days: int
    average_correlation: float
    min_correlation: float
    max_correlation: float


@dataclass
class RollingCorrelation:
    """Rolling correlation analysis result."""
    asset1: str
    asset2: str
    correlations: List[float]
    dates: List[datetime]
    window_size: int
    mean_correlation: float
    correlation_volatility: float
    trend: str  # "increasing", "decreasing", "stable"


@dataclass
class CorrelationRegimeChange:
    """Correlation regime change detection."""
    asset1: str
    asset2: str
    change_date: datetime
    correlation_before: float
    correlation_after: float
    change_magnitude: float
    confidence_score: float
    regime_type: str  # "breakdown", "strengthening", "reversal"


class CorrelationCalculator:
    """
    Stateless correlation calculator with comprehensive analysis methods.
    
    All methods are static to ensure thread safety and enable
    easy testing and validation.
    """
    
    logger = Logger
    
    @staticmethod
    def pearson_correlation(x: List[float], y: List[float]) -> float:
        """
        Calculate Pearson correlation coefficient.
        
        Args:
            x: First data series
            y: Second data series
            
        Returns:
            Correlation coefficient (-1 to 1)
            
        Raises:
            ValueError: If series have different lengths or insufficient data
        """
        if len(x) != len(y):
            raise ValueError("Data series must have the same length")
        
        if len(x) < 2:
            raise ValueError("Need at least 2 data points for correlation")
        
        # Calculate means
        mean_x = mean(x)
        mean_y = mean(y)
        
        # Calculate correlation components
        numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        
        sum_sq_x = sum((xi - mean_x) ** 2 for xi in x)
        sum_sq_y = sum((yi - mean_y) ** 2 for yi in y)
        
        denominator = math.sqrt(sum_sq_x * sum_sq_y)
        
        if denominator == 0:
            return 0.0
        
        correlation = numerator / denominator
        
        # Clamp to valid range due to floating point precision
        return max(-1.0, min(1.0, correlation))
    
    @staticmethod
    def correlation_with_confidence(
        x: List[float],
        y: List[float],
        asset1_name: str = "Asset1",
        asset2_name: str = "Asset2",
        confidence_level: float = 0.95
    ) -> CorrelationResult:
        """
        Calculate correlation with confidence interval and significance testing.
        
        Args:
            x: First data series
            y: Second data series
            asset1_name: Name of first asset
            asset2_name: Name of second asset
            confidence_level: Confidence level for interval (default: 0.95)
            
        Returns:
            CorrelationResult with correlation and statistical measures
        """
        correlation = CorrelationCalculator.pearson_correlation(x, y)
        sample_size = len(x)
        
        # Calculate confidence interval using Fisher transformation
        confidence_interval = CorrelationCalculator._calculate_confidence_interval(
            correlation, sample_size, confidence_level
        )
        
        # Test statistical significance (H0: correlation = 0)
        is_significant = CorrelationCalculator._test_significance(correlation, sample_size)
        
        return CorrelationResult(
            asset1=asset1_name,
            asset2=asset2_name,
            correlation=correlation,
            confidence_interval=confidence_interval,
            sample_size=sample_size,
            calculation_date=datetime.now(),
            is_significant=is_significant
        )
    
    @staticmethod
    def rolling_correlation(
        x: List[float],
        y: List[float],
        window: int,
        asset1_name: str = "Asset1",
        asset2_name: str = "Asset2"
    ) -> RollingCorrelation:
        """
        Calculate rolling correlation over time.
        
        Args:
            x: First data series
            y: Second data series
            window: Rolling window size
            asset1_name: Name of first asset
            asset2_name: Name of second asset
            
        Returns:
            RollingCorrelation with time series of correlations
        """
        if len(x) != len(y):
            raise ValueError("Data series must have the same length")
        
        if window > len(x):
            raise ValueError("Window size cannot be larger than data series")
        
        correlations = []
        dates = []
        
        for i in range(window - 1, len(x)):
            window_x = x[i - window + 1:i + 1]
            window_y = y[i - window + 1:i + 1]
            
            try:
                corr = CorrelationCalculator.pearson_correlation(window_x, window_y)
                correlations.append(corr)
                dates.append(datetime.now() - timedelta(days=len(x) - i - 1))
            except ValueError:
                # Skip windows with insufficient variance
                correlations.append(0.0)
                dates.append(datetime.now() - timedelta(days=len(x) - i - 1))
        
        # Calculate summary statistics
        mean_correlation = mean(correlations) if correlations else 0.0
        correlation_volatility = stdev(correlations) if len(correlations) > 1 else 0.0
        
        # Determine trend
        trend = CorrelationCalculator._determine_trend(correlations)
        
        return RollingCorrelation(
            asset1=asset1_name,
            asset2=asset2_name,
            correlations=correlations,
            dates=dates,
            window_size=window,
            mean_correlation=mean_correlation,
            correlation_volatility=correlation_volatility,
            trend=trend
        )
    
    @staticmethod
    def correlation_matrix(
        returns_dict: Dict[str, List[float]],
        window_days: Optional[int] = None
    ) -> CorrelationMatrix:
        """
        Calculate correlation matrix for multiple assets.
        
        Args:
            returns_dict: Dictionary of asset names to return series
            window_days: Optional window for recent correlations
            
        Returns:
            CorrelationMatrix with pairwise correlations
        """
        if not returns_dict:
            return CorrelationMatrix(
                matrix={},
                assets=[],
                calculation_date=datetime.now(),
                window_days=window_days or 0,
                average_correlation=0.0,
                min_correlation=0.0,
                max_correlation=0.0
            )
        
        assets = list(returns_dict.keys())
        
        # Ensure all series have the same length
        min_length = min(len(returns) for returns in returns_dict.values())
        if window_days:
            min_length = min(min_length, window_days)
        
        # Truncate series to common length and window
        processed_returns = {}
        for asset, returns in returns_dict.items():
            processed_returns[asset] = returns[-min_length:] if returns else []
        
        # Calculate correlation matrix
        matrix = {}
        all_correlations = []
        
        for asset1 in assets:
            matrix[asset1] = {}
            for asset2 in assets:
                if asset1 == asset2:
                    correlation = 1.0
                else:
                    try:
                        correlation = CorrelationCalculator.pearson_correlation(
                            processed_returns[asset1],
                            processed_returns[asset2]
                        )
                    except (ValueError, ZeroDivisionError):
                        correlation = 0.0
                
                matrix[asset1][asset2] = correlation
                
                # Collect off-diagonal correlations for statistics
                if asset1 != asset2:
                    all_correlations.append(correlation)
        
        # Calculate summary statistics
        average_correlation = mean(all_correlations) if all_correlations else 0.0
        min_correlation = min(all_correlations) if all_correlations else 0.0
        max_correlation = max(all_correlations) if all_correlations else 0.0
        
        return CorrelationMatrix(
            matrix=matrix,
            assets=assets,
            calculation_date=datetime.now(),
            window_days=window_days or min_length,
            average_correlation=average_correlation,
            min_correlation=min_correlation,
            max_correlation=max_correlation
        )
    
    @staticmethod
    def detect_regime_changes(
        x: List[float],
        y: List[float],
        window: int = 30,
        threshold: float = 0.3,
        asset1_name: str = "Asset1",
        asset2_name: str = "Asset2"
    ) -> List[CorrelationRegimeChange]:
        """
        Detect correlation regime changes using rolling correlation analysis.
        
        Args:
            x: First data series
            y: Second data series
            window: Rolling window for correlation calculation
            threshold: Minimum change magnitude to consider a regime change
            asset1_name: Name of first asset
            asset2_name: Name of second asset
            
        Returns:
            List of detected regime changes
        """
        rolling_corr = CorrelationCalculator.rolling_correlation(
            x, y, window, asset1_name, asset2_name
        )
        
        regime_changes = []
        correlations = rolling_corr.correlations
        dates = rolling_corr.dates
        
        if len(correlations) < 2:
            return regime_changes
        
        # Look for significant changes in correlation
        for i in range(1, len(correlations)):
            correlation_before = correlations[i - 1]
            correlation_after = correlations[i]
            change_magnitude = abs(correlation_after - correlation_before)
            
            if change_magnitude >= threshold:
                # Determine regime type
                if correlation_before > 0.5 and correlation_after < 0.2:
                    regime_type = "breakdown"
                elif correlation_before < 0.2 and correlation_after > 0.5:
                    regime_type = "strengthening"
                elif correlation_before * correlation_after < 0:
                    regime_type = "reversal"
                else:
                    continue  # Not a significant regime change
                
                # Calculate confidence score based on change magnitude
                confidence_score = min(1.0, change_magnitude / 0.8)
                
                regime_change = CorrelationRegimeChange(
                    asset1=asset1_name,
                    asset2=asset2_name,
                    change_date=dates[i],
                    correlation_before=correlation_before,
                    correlation_after=correlation_after,
                    change_magnitude=change_magnitude,
                    confidence_score=confidence_score,
                    regime_type=regime_type
                )
                
                regime_changes.append(regime_change)
        
        return regime_changes
    
    @staticmethod
    def correlation_stability_score(
        x: List[float],
        y: List[float],
        window: int = 30
    ) -> float:
        """
        Calculate correlation stability score (0 = unstable, 1 = very stable).
        
        Args:
            x: First data series
            y: Second data series
            window: Rolling window for stability analysis
            
        Returns:
            Stability score between 0 and 1
        """
        if len(x) < window * 2:
            return 0.0
        
        rolling_corr = CorrelationCalculator.rolling_correlation(x, y, window)
        correlations = rolling_corr.correlations
        
        if len(correlations) < 2:
            return 0.0
        
        # Calculate volatility of correlations
        correlation_volatility = stdev(correlations)
        
        # Convert volatility to stability score (lower volatility = higher stability)
        # Use exponential decay: stability = exp(-volatility * scale_factor)
        scale_factor = 3.0  # Adjust this to change sensitivity
        stability_score = math.exp(-correlation_volatility * scale_factor)
        
        return min(1.0, max(0.0, stability_score))
    
    @staticmethod
    def _calculate_confidence_interval(
        correlation: float,
        sample_size: int,
        confidence_level: float
    ) -> Tuple[float, float]:
        """Calculate confidence interval for correlation using Fisher transformation."""
        if sample_size < 4:
            return (correlation, correlation)
        
        # Fisher transformation
        z = 0.5 * math.log((1 + correlation) / (1 - correlation))
        
        # Standard error
        se = 1.0 / math.sqrt(sample_size - 3)
        
        # Z-score for confidence level (approximation)
        z_scores = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}
        z_score = z_scores.get(confidence_level, 1.96)
        
        # Confidence interval in Fisher space
        z_lower = z - z_score * se
        z_upper = z + z_score * se
        
        # Transform back to correlation space
        r_lower = (math.exp(2 * z_lower) - 1) / (math.exp(2 * z_lower) + 1)
        r_upper = (math.exp(2 * z_upper) - 1) / (math.exp(2 * z_upper) + 1)
        
        # Clamp to valid range
        r_lower = max(-1.0, min(1.0, r_lower))
        r_upper = max(-1.0, min(1.0, r_upper))
        
        return (r_lower, r_upper)
    
    @staticmethod
    def _test_significance(correlation: float, sample_size: int, alpha: float = 0.05) -> bool:
        """Test if correlation is statistically significant."""
        if sample_size < 4:
            return False
        
        # Calculate t-statistic
        t_stat = correlation * math.sqrt((sample_size - 2) / (1 - correlation ** 2))
        
        # Critical value for two-tailed test (approximation)
        # For large samples, t-distribution approaches normal
        critical_values = {0.05: 1.96, 0.01: 2.576}
        critical_value = critical_values.get(alpha, 1.96)
        
        return abs(t_stat) > critical_value
    
    @staticmethod
    def _determine_trend(correlations: List[float]) -> str:
        """Determine trend in correlation series."""
        if len(correlations) < 3:
            return "stable"
        
        # Simple trend detection using first and last third
        first_third = correlations[:len(correlations) // 3]
        last_third = correlations[-len(correlations) // 3:]
        
        first_avg = mean(first_third)
        last_avg = mean(last_third)
        
        change = last_avg - first_avg
        
        if change > 0.1:
            return "increasing"
        elif change < -0.1:
            return "decreasing"
        else:
            return "stable"