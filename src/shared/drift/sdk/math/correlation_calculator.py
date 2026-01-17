"""
Correlation Calculator
=====================

Shared correlation calculations for all trading engines.
Provides correlation matrix calculations, rolling correlations, and stability analysis.

Features:
- Pearson correlation calculations
- Rolling correlation windows
- Correlation matrix generation
- Correlation stability assessment
- Dynamic correlation tracking
"""

import math
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
from statistics import mean

from src.shared.system.logging import Logger


@dataclass
class CorrelationResult:
    """Correlation calculation result."""
    correlation: float
    p_value: Optional[float]
    sample_size: int
    calculation_date: datetime
    is_significant: bool


@dataclass
class CorrelationMatrix:
    """Correlation matrix with metadata."""
    matrix: Dict[str, Dict[str, float]]
    assets: List[str]
    sample_size: int
    calculation_date: datetime
    average_correlation: float
    max_correlation: float
    min_correlation: float


@dataclass
class CorrelationStability:
    """Correlation stability analysis result."""
    current_correlation: float
    historical_mean: float
    historical_std: float
    stability_score: float  # 0.0 to 1.0, higher = more stable
    regime_change_detected: bool
    confidence_interval: Tuple[float, float]


class CorrelationCalculator:
    """
    Stateless correlation calculator with multiple calculation methods.
    
    All methods are static to ensure thread safety and enable
    easy testing and validation.
    """
    
    logger = Logger
    
    @staticmethod
    def pearson_correlation(x: List[float], y: List[float]) -> float:
        """
        Calculate Pearson correlation coefficient between two series.
        
        Args:
            x: First data series
            y: Second data series
            
        Returns:
            Correlation coefficient (-1.0 to 1.0)
            
        Raises:
            ValueError: If series have different lengths or insufficient data
        """
        if len(x) != len(y):
            raise ValueError("Series must have equal length")
        
        if len(x) < 2:
            raise ValueError("Need at least 2 data points for correlation")
        
        n = len(x)
        
        # Calculate means
        mean_x = mean(x)
        mean_y = mean(y)
        
        # Calculate correlation components
        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        
        sum_sq_x = sum((x[i] - mean_x) ** 2 for i in range(n))
        sum_sq_y = sum((y[i] - mean_y) ** 2 for i in range(n))
        
        denominator = math.sqrt(sum_sq_x * sum_sq_y)
        
        if denominator == 0:
            return 0.0  # No correlation if either series has zero variance
        
        correlation = numerator / denominator
        
        # Clamp to valid range due to floating point precision
        return max(-1.0, min(1.0, correlation))
    
    @staticmethod
    def rolling_correlation(
        x: List[float], 
        y: List[float], 
        window: int
    ) -> List[float]:
        """
        Calculate rolling correlation between two series.
        
        Args:
            x: First data series
            y: Second data series
            window: Rolling window size
            
        Returns:
            List of rolling correlations
            
        Raises:
            ValueError: If window is larger than data or series have different lengths
        """
        if len(x) != len(y):
            raise ValueError("Series must have equal length")
        
        if window > len(x):
            raise ValueError("Window size cannot exceed data length")
        
        if window < 2:
            raise ValueError("Window size must be at least 2")
        
        rolling_correlations = []
        
        for i in range(window - 1, len(x)):
            start_idx = i - window + 1
            end_idx = i + 1
            
            x_window = x[start_idx:end_idx]
            y_window = y[start_idx:end_idx]
            
            correlation = CorrelationCalculator.pearson_correlation(x_window, y_window)
            rolling_correlations.append(correlation)
        
        return rolling_correlations
    
    @staticmethod
    def correlation_matrix(returns_dict: Dict[str, List[float]]) -> CorrelationMatrix:
        """
        Calculate correlation matrix for multiple asset return series.
        
        Args:
            returns_dict: Dictionary mapping asset names to return series
            
        Returns:
            CorrelationMatrix with full correlation data
            
        Raises:
            ValueError: If assets have different data lengths or insufficient data
        """
        if not returns_dict:
            raise ValueError("Need at least one asset for correlation matrix")
        
        assets = list(returns_dict.keys())
        
        # Validate all series have same length
        lengths = [len(returns_dict[asset]) for asset in assets]
        if len(set(lengths)) > 1:
            raise ValueError("All asset return series must have equal length")
        
        sample_size = lengths[0] if lengths else 0
        if sample_size < 2:
            raise ValueError("Need at least 2 data points for correlation matrix")
        
        # Calculate correlation matrix
        matrix = {}
        correlations = []
        
        for asset1 in assets:
            matrix[asset1] = {}
            for asset2 in assets:
                if asset1 == asset2:
                    correlation = 1.0
                else:
                    correlation = CorrelationCalculator.pearson_correlation(
                        returns_dict[asset1], returns_dict[asset2]
                    )
                
                matrix[asset1][asset2] = correlation
                
                # Collect off-diagonal correlations for statistics
                if asset1 != asset2:
                    correlations.append(correlation)
        
        # Calculate matrix statistics
        if correlations:
            avg_correlation = mean(correlations)
            max_correlation = max(correlations)
            min_correlation = min(correlations)
        else:
            avg_correlation = max_correlation = min_correlation = 1.0
        
        return CorrelationMatrix(
            matrix=matrix,
            assets=assets,
            sample_size=sample_size,
            calculation_date=datetime.now(),
            average_correlation=avg_correlation,
            max_correlation=max_correlation,
            min_correlation=min_correlation
        )
    
    @staticmethod
    def correlation_with_significance(
        x: List[float], 
        y: List[float], 
        alpha: float = 0.05
    ) -> CorrelationResult:
        """
        Calculate correlation with statistical significance testing.
        
        Args:
            x: First data series
            y: Second data series
            alpha: Significance level (default: 0.05)
            
        Returns:
            CorrelationResult with significance testing
        """
        correlation = CorrelationCalculator.pearson_correlation(x, y)
        n = len(x)
        
        # Calculate t-statistic for significance test
        if abs(correlation) == 1.0:
            # Perfect correlation
            p_value = 0.0
            is_significant = True
        else:
            t_stat = correlation * math.sqrt((n - 2) / (1 - correlation ** 2))
            
            # Approximate p-value using t-distribution
            # For large n, t-distribution approaches normal distribution
            if n > 30:
                # Use normal approximation
                p_value = 2 * (1 - CorrelationCalculator._normal_cdf(abs(t_stat)))
            else:
                # Use conservative estimate for small samples
                critical_t = 2.0  # Approximate critical value for small samples
                p_value = 0.05 if abs(t_stat) > critical_t else 0.1
            
            is_significant = p_value < alpha
        
        return CorrelationResult(
            correlation=correlation,
            p_value=p_value,
            sample_size=n,
            calculation_date=datetime.now(),
            is_significant=is_significant
        )
    
    @staticmethod
    def assess_correlation_stability(
        x: List[float], 
        y: List[float], 
        window: int = 30,
        stability_threshold: float = 0.1
    ) -> CorrelationStability:
        """
        Assess stability of correlation over time using rolling windows.
        
        Args:
            x: First data series
            y: Second data series
            window: Rolling window size for stability analysis
            stability_threshold: Threshold for detecting regime changes
            
        Returns:
            CorrelationStability with stability metrics
        """
        if len(x) < window * 2:
            raise ValueError(f"Need at least {window * 2} data points for stability analysis")
        
        # Calculate rolling correlations
        rolling_corrs = CorrelationCalculator.rolling_correlation(x, y, window)
        
        # Current correlation (most recent window)
        current_correlation = rolling_corrs[-1]
        
        # Historical statistics
        historical_mean = mean(rolling_corrs)
        historical_variance = sum((corr - historical_mean) ** 2 for corr in rolling_corrs) / len(rolling_corrs)
        historical_std = math.sqrt(historical_variance)
        
        # Stability score (inverse of coefficient of variation)
        if historical_std == 0:
            stability_score = 1.0
        else:
            cv = historical_std / abs(historical_mean) if historical_mean != 0 else float('inf')
            stability_score = max(0.0, min(1.0, 1.0 / (1.0 + cv)))
        
        # Regime change detection
        recent_window = rolling_corrs[-min(10, len(rolling_corrs)):]
        recent_mean = mean(recent_window)
        regime_change_detected = abs(recent_mean - historical_mean) > stability_threshold
        
        # Confidence interval (approximate)
        confidence_margin = 1.96 * historical_std  # 95% confidence
        confidence_interval = (
            max(-1.0, current_correlation - confidence_margin),
            min(1.0, current_correlation + confidence_margin)
        )
        
        return CorrelationStability(
            current_correlation=current_correlation,
            historical_mean=historical_mean,
            historical_std=historical_std,
            stability_score=stability_score,
            regime_change_detected=regime_change_detected,
            confidence_interval=confidence_interval
        )
    
    @staticmethod
    def dynamic_correlation_adjustment(
        base_correlation: float,
        market_stress_factor: float,
        volatility_regime: str = "normal"
    ) -> float:
        """
        Adjust correlation based on market conditions and volatility regime.
        
        Args:
            base_correlation: Base correlation estimate
            market_stress_factor: Market stress factor (0.0 to 2.0, 1.0 = normal)
            volatility_regime: Volatility regime ("low", "normal", "high")
            
        Returns:
            Adjusted correlation coefficient
        """
        # Correlations tend to increase during market stress
        stress_adjustment = (market_stress_factor - 1.0) * 0.3
        
        # Volatility regime adjustments
        volatility_adjustments = {
            "low": -0.1,      # Lower correlations in calm markets
            "normal": 0.0,    # No adjustment
            "high": 0.2       # Higher correlations in volatile markets
        }
        
        volatility_adjustment = volatility_adjustments.get(volatility_regime, 0.0)
        
        # Apply adjustments
        adjusted_correlation = base_correlation + stress_adjustment + volatility_adjustment
        
        # Clamp to valid correlation range
        return max(-1.0, min(1.0, adjusted_correlation))
    
    @staticmethod
    def _normal_cdf(x: float) -> float:
        """
        Approximate cumulative distribution function for standard normal distribution.
        
        Args:
            x: Input value
            
        Returns:
            Approximate CDF value
        """
        # Abramowitz and Stegun approximation
        if x < 0:
            return 1 - CorrelationCalculator._normal_cdf(-x)
        
        # Constants for approximation
        a1 = 0.254829592
        a2 = -0.284496736
        a3 = 1.421413741
        a4 = -1.453152027
        a5 = 1.061405429
        p = 0.3275911
        
        t = 1.0 / (1.0 + p * x)
        y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x)
        
        return y