"""
Value at Risk Calculator
=======================

Shared VaR calculations for all trading engines.
Provides multiple VaR calculation methods with consistent interfaces.

Features:
- Historical simulation VaR
- Parametric VaR (normal distribution)
- Monte Carlo VaR
- VaR backtesting and validation
- Statistical significance testing
"""

import math
import random
from typing import List, Tuple, Dict, Any
from statistics import mean, stdev
from dataclasses import dataclass
from datetime import datetime

try:
    from scipy.stats import norm, chi2
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

from src.shared.system.logging import Logger


@dataclass
class VaRResult:
    """Value at Risk calculation result."""
    var_1d: float  # 1-day VaR
    var_7d: float  # 7-day VaR
    confidence_level: float
    method: str  # "historical", "parametric", "monte_carlo"
    portfolio_value: float
    calculation_date: datetime


@dataclass
class VaRBacktestResult:
    """VaR backtesting result."""
    total_observations: int
    violations: int
    violation_rate: float
    expected_violation_rate: float
    kupiec_test_statistic: float
    kupiec_p_value: float
    model_performance: str  # "acceptable", "underestimating_risk", "overestimating_risk"


class VaRCalculator:
    """
    Stateless VaR calculator with multiple calculation methods.
    
    All methods are static to ensure thread safety and enable
    easy testing and validation.
    """
    
    logger = Logger
    
    @staticmethod
    def calculate_var(
        returns: List[float],
        portfolio_value: float,
        confidence_level: float = 0.95,
        horizon_days: int = 1,
        method: str = "historical_simulation"
    ) -> VaRResult:
        """
        Calculate Value at Risk using specified method.
        
        Args:
            returns: Historical return series
            portfolio_value: Current portfolio value
            confidence_level: Confidence level (default: 0.95)
            horizon_days: Time horizon in days (default: 1)
            method: Calculation method ("historical_simulation", "parametric", "monte_carlo")
            
        Returns:
            VaRResult with VaR calculations
            
        Raises:
            ValueError: If method is unknown or inputs are invalid
        """
        if portfolio_value <= 0:
            raise ValueError("Portfolio value must be positive")
        
        if not returns or len(returns) < 2:
            raise ValueError("Insufficient return data for VaR calculation")
        
        if not 0.5 <= confidence_level <= 0.999:
            raise ValueError("Confidence level must be between 0.5 and 0.999")
        
        # Calculate VaR based on method
        if method == "historical_simulation":
            var_1d = VaRCalculator.historical_simulation_var(returns, confidence_level, 1)
            var_7d = VaRCalculator.historical_simulation_var(returns, confidence_level, 7)
        elif method == "parametric":
            var_1d = VaRCalculator.parametric_var(returns, confidence_level, 1)
            var_7d = VaRCalculator.parametric_var(returns, confidence_level, 7)
        elif method == "monte_carlo":
            var_1d = VaRCalculator.monte_carlo_var(returns, confidence_level, 1)
            var_7d = VaRCalculator.monte_carlo_var(returns, confidence_level, 7)
        else:
            raise ValueError(f"Unknown VaR method: {method}")
        
        # Scale by portfolio value
        var_1d_dollar = var_1d * portfolio_value
        var_7d_dollar = var_7d * portfolio_value
        
        return VaRResult(
            var_1d=var_1d_dollar,
            var_7d=var_7d_dollar,
            confidence_level=confidence_level,
            method=method,
            portfolio_value=portfolio_value,
            calculation_date=datetime.now()
        )
    
    @staticmethod
    def historical_simulation_var(
        returns: List[float],
        confidence_level: float,
        horizon_days: int
    ) -> float:
        """
        Calculate VaR using historical simulation method.
        
        Args:
            returns: Historical return series
            confidence_level: Confidence level (e.g., 0.95 for 95% VaR)
            horizon_days: Time horizon in days
            
        Returns:
            VaR as a fraction of portfolio value (negative number representing loss)
        """
        if not returns:
            return 0.0
        
        # Sort returns in ascending order
        sorted_returns = sorted(returns)
        
        # Find percentile
        percentile = 1 - confidence_level
        index = int(percentile * len(sorted_returns))
        index = max(0, min(index, len(sorted_returns) - 1))
        
        # Get VaR (negative of the percentile return)
        var_1d = -sorted_returns[index]
        
        # Scale for horizon (square root of time rule)
        var_horizon = var_1d * math.sqrt(horizon_days)
        
        return var_horizon
    
    @staticmethod
    def parametric_var(
        returns: List[float],
        confidence_level: float,
        horizon_days: int
    ) -> float:
        """
        Calculate parametric VaR assuming normal distribution.
        
        Args:
            returns: Historical return series
            confidence_level: Confidence level
            horizon_days: Time horizon in days
            
        Returns:
            VaR as a fraction of portfolio value
        """
        if not returns:
            return 0.0
        
        # Calculate mean and standard deviation
        mean_return = mean(returns)
        volatility = stdev(returns) if len(returns) > 1 else 0.0
        
        # Z-score for confidence level
        if SCIPY_AVAILABLE:
            z_score = norm.ppf(1 - confidence_level)
        else:
            # Approximation for common confidence levels
            z_scores = {0.90: 1.28, 0.95: 1.645, 0.99: 2.33}
            z_score = z_scores.get(confidence_level, 1.645)  # Default to 95%
        
        # Parametric VaR (negative because we want loss)
        var_1d = -(mean_return + z_score * volatility)
        
        # Scale for horizon (square root of time rule)
        var_horizon = var_1d * math.sqrt(horizon_days)
        
        return var_horizon
    
    @staticmethod
    def monte_carlo_var(
        returns: List[float],
        confidence_level: float,
        horizon_days: int,
        num_simulations: int = 10000
    ) -> float:
        """
        Calculate Monte Carlo VaR using simulated returns.
        
        Args:
            returns: Historical return series for parameter estimation
            confidence_level: Confidence level
            horizon_days: Time horizon in days
            num_simulations: Number of Monte Carlo simulations
            
        Returns:
            VaR as a fraction of portfolio value
        """
        if not returns:
            return 0.0
        
        # Calculate historical mean and volatility
        mean_return = mean(returns)
        volatility = stdev(returns) if len(returns) > 1 else 0.0
        
        # Generate simulated returns
        simulated_returns = []
        for _ in range(num_simulations):
            # Simulate daily returns for the horizon
            cumulative_return = 0.0
            for _ in range(horizon_days):
                daily_return = random.gauss(mean_return, volatility)
                cumulative_return += daily_return
            simulated_returns.append(cumulative_return)
        
        # Calculate VaR from simulated returns
        sorted_returns = sorted(simulated_returns)
        percentile = 1 - confidence_level
        index = int(percentile * len(sorted_returns))
        index = max(0, min(index, len(sorted_returns) - 1))
        
        # VaR (negative of the percentile return)
        var_result = -sorted_returns[index]
        
        return var_result
    
    @staticmethod
    def backtest_var(
        var_results: List[VaRResult],
        actual_returns: List[float],
        confidence_level: float = 0.95
    ) -> VaRBacktestResult:
        """
        Backtest VaR model performance against actual returns.
        
        Args:
            var_results: List of historical VaR calculations
            actual_returns: List of actual portfolio returns
            confidence_level: Confidence level used for VaR calculations
            
        Returns:
            VaRBacktestResult with backtesting statistics
        """
        if len(var_results) != len(actual_returns):
            raise ValueError("VaR results and actual returns must have same length")
        
        if not var_results:
            return VaRBacktestResult(
                total_observations=0,
                violations=0,
                violation_rate=0.0,
                expected_violation_rate=0.0,
                kupiec_test_statistic=0.0,
                kupiec_p_value=1.0,
                model_performance='insufficient_data'
            )
        
        # Count VaR violations (actual loss > VaR)
        violations = 0
        total_observations = len(var_results)
        
        for var_result, actual_return in zip(var_results, actual_returns):
            # Convert return to dollar loss
            actual_loss = -actual_return * var_result.portfolio_value
            
            # Check if actual loss exceeded VaR
            if actual_loss > var_result.var_1d:
                violations += 1
        
        # Calculate violation rate
        violation_rate = violations / total_observations if total_observations > 0 else 0.0
        expected_violation_rate = 1 - confidence_level
        
        # Kupiec test for model accuracy
        kupiec_test_statistic, kupiec_p_value = VaRCalculator._kupiec_test(
            violations, total_observations, expected_violation_rate
        )
        
        # Determine model performance
        if kupiec_p_value > 0.05:
            model_performance = 'acceptable'
        elif violation_rate > expected_violation_rate * 1.5:
            model_performance = 'underestimating_risk'
        elif violation_rate < expected_violation_rate * 0.5:
            model_performance = 'overestimating_risk'
        else:
            model_performance = 'marginal'
        
        return VaRBacktestResult(
            total_observations=total_observations,
            violations=violations,
            violation_rate=violation_rate,
            expected_violation_rate=expected_violation_rate,
            kupiec_test_statistic=kupiec_test_statistic,
            kupiec_p_value=kupiec_p_value,
            model_performance=model_performance
        )
    
    @staticmethod
    def _kupiec_test(violations: int, observations: int, expected_rate: float) -> Tuple[float, float]:
        """
        Perform Kupiec test for VaR model accuracy.
        
        Returns:
            Tuple of (test_statistic, p_value)
        """
        if observations == 0 or expected_rate == 0 or expected_rate == 1:
            return 0.0, 1.0
        
        # Likelihood ratio test statistic
        observed_rate = violations / observations
        
        if observed_rate == 0:
            if expected_rate == 0:
                return 0.0, 1.0
            else:
                # Use approximation for zero violations
                test_statistic = 2 * observations * math.log(1 / (1 - expected_rate))
        elif observed_rate == 1:
            if expected_rate == 1:
                return 0.0, 1.0
            else:
                # Use approximation for all violations
                test_statistic = 2 * observations * math.log(1 / expected_rate)
        else:
            # Standard Kupiec test
            likelihood_ratio = (
                (observed_rate ** violations) * 
                ((1 - observed_rate) ** (observations - violations))
            ) / (
                (expected_rate ** violations) * 
                ((1 - expected_rate) ** (observations - violations))
            )
            
            test_statistic = -2 * math.log(likelihood_ratio)
        
        # Calculate p-value using chi-square distribution with 1 degree of freedom
        if SCIPY_AVAILABLE:
            p_value = 1 - chi2.cdf(test_statistic, df=1)
        else:
            # Approximation for chi-square p-value
            if test_statistic < 3.84:  # 95% critical value
                p_value = 0.95
            elif test_statistic < 6.63:  # 99% critical value
                p_value = 0.01
            else:
                p_value = 0.001
        
        return test_statistic, p_value