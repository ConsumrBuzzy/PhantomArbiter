"""
Drift Risk Engine
================

Specialized calculation engine for comprehensive risk metrics and analysis.
Provides advanced risk calculations including VaR, volatility, correlation, and performance metrics.

Features:
- Value at Risk (VaR) calculations using multiple methods
- Performance metrics (Sharpe, Sortino, Calmar ratios)
- Drawdown analysis and tracking
- Correlation matrix calculations
- Volatility modeling and forecasting
- Beta analysis relative to major assets
- Real-time risk monitoring and alerts

Usage:
    risk_engine = DriftRiskEngine(drift_adapter)
    
    # Calculate VaR
    var_result = await risk_engine.calculate_var(confidence_level=0.95)
    
    # Get performance metrics
    performance = await risk_engine.calculate_performance_metrics()
    
    # Monitor risk changes
    alerts = await risk_engine.monitor_risk_changes()
"""

import asyncio
import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
import math
from statistics import mean, stdev

try:
    from scipy.stats import norm, chi2
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

from src.shared.system.logging import Logger


# =============================================================================
# DATA STRUCTURES
# =============================================================================

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
class PerformanceMetrics:
    """Comprehensive performance metrics."""
    total_return: float
    annualized_return: float
    volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    information_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    average_win: float
    average_loss: float
    largest_win: float
    largest_loss: float
    total_trades: int
    winning_trades: int
    losing_trades: int

@dataclass
class DrawdownAnalysis:
    """Drawdown analysis results."""
    max_drawdown: float
    current_drawdown: float
    drawdown_duration: int  # days
    peak_date: datetime
    trough_date: datetime
    recovery_date: Optional[datetime]
    underwater_periods: List[Dict[str, Any]]

@dataclass
class CorrelationMatrix:
    """Correlation matrix with metadata."""
    matrix: Dict[str, Dict[str, float]]
    assets: List[str]
    calculation_date: datetime
    window_days: int
    method: str  # "pearson", "spearman", "kendall"

@dataclass
class VolatilityMetrics:
    """Volatility analysis results."""
    portfolio_volatility: float
    position_volatilities: Dict[str, float]
    volatility_contributions: Dict[str, float]
    realized_volatility: float
    implied_volatility: Optional[float]
    volatility_forecast: float
    calculation_method: str

@dataclass
class BetaAnalysis:
    """Beta analysis results."""
    beta_sol: float
    beta_btc: float
    beta_market: float
    r_squared_sol: float
    r_squared_btc: float
    r_squared_market: float
    alpha_sol: float
    alpha_btc: float
    alpha_market: float

@dataclass
class RiskChangeAlert:
    """Risk change monitoring alert."""
    alert_type: str  # "var_increase", "correlation_breakdown", "volatility_spike"
    severity: str  # "info", "warning", "critical"
    current_value: float
    previous_value: float
    threshold: float
    message: str
    timestamp: datetime
    recommended_action: str


# =============================================================================
# RISK ENGINE
# =============================================================================

class DriftRiskEngine:
    """
    Advanced risk calculation engine for Drift Protocol portfolios.
    
    Provides comprehensive risk analytics including VaR, performance metrics,
    correlation analysis, and real-time risk monitoring.
    """
    
    def __init__(self, drift_adapter, lookback_days: int = 252):
        """
        Initialize risk engine.
        
        Args:
            drift_adapter: DriftAdapter instance
            lookback_days: Days of historical data for calculations (default: 252 trading days)
        """
        self.drift_adapter = drift_adapter
        self.lookback_days = lookback_days
        self.logger = Logger
        
        # Risk monitoring state
        self._previous_metrics = {}
        self._alert_thresholds = {
            "var_increase": 0.5,  # 50% increase in VaR
            "volatility_spike": 2.0,  # 2x volatility increase
            "correlation_breakdown": 0.3  # 30% correlation change
        }
        
        # Cache for expensive calculations
        self._calculation_cache = {}
        self._cache_ttl = 300  # 5 minutes
        
        self.logger.info(f"Risk Engine initialized with {lookback_days} day lookback")

    # =========================================================================
    # VALUE AT RISK CALCULATIONS
    # =========================================================================

    async def calculate_var(
        self,
        confidence_level: float = 0.95,
        horizon_days: int = 1,
        method: str = "historical_simulation"
    ) -> VaRResult:
        """
        Calculate Value at Risk using multiple methods.
        
        Args:
            confidence_level: Confidence level (default: 0.95 for 95% VaR)
            horizon_days: Time horizon in days (default: 1)
            method: VaR calculation method ("historical_simulation", "parametric", "monte_carlo")
            
        Returns:
            VaRResult with VaR calculations
        """
        try:
            # Get portfolio value
            account = await self.drift_adapter.get_user_account()
            portfolio_value = float(account.get('total_collateral', 0)) if account else 0.0
            
            if portfolio_value <= 0:
                raise ValueError("Cannot calculate VaR for zero portfolio value")
            
            # Get historical returns (placeholder - would need actual price history)
            returns = await self._get_portfolio_returns()
            
            if len(returns) < 30:
                self.logger.warning(f"Limited return data: {len(returns)} observations")
            
            # Calculate VaR based on method
            if method == "historical_simulation":
                var_1d = self._calculate_historical_var(returns, confidence_level, 1)
                var_7d = self._calculate_historical_var(returns, confidence_level, 7)
            elif method == "parametric":
                var_1d = self._calculate_parametric_var(returns, confidence_level, 1)
                var_7d = self._calculate_parametric_var(returns, confidence_level, 7)
            elif method == "monte_carlo":
                var_1d = self._calculate_monte_carlo_var(returns, confidence_level, 1)
                var_7d = self._calculate_monte_carlo_var(returns, confidence_level, 7)
            else:
                raise ValueError(f"Unknown VaR method: {method}")
            
            # Scale by portfolio value
            var_1d_dollar = var_1d * portfolio_value
            var_7d_dollar = var_7d * portfolio_value
            
            result = VaRResult(
                var_1d=var_1d_dollar,
                var_7d=var_7d_dollar,
                confidence_level=confidence_level,
                method=method,
                portfolio_value=portfolio_value,
                calculation_date=datetime.now()
            )
            
            self.logger.info(f"VaR calculated ({method}): 1D=${var_1d_dollar:.2f}, 7D=${var_7d_dollar:.2f}")
            return result
            
        except Exception as e:
            self.logger.error(f"Error calculating VaR: {e}")
            raise

    def _calculate_historical_var(
        self,
        returns: List[float],
        confidence_level: float,
        horizon_days: int
    ) -> float:
        """Calculate historical simulation VaR."""
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

    def _calculate_parametric_var(
        self,
        returns: List[float],
        confidence_level: float,
        horizon_days: int
    ) -> float:
        """Calculate parametric VaR assuming normal distribution."""
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

    def _calculate_monte_carlo_var(
        self,
        returns: List[float],
        confidence_level: float,
        horizon_days: int,
        num_simulations: int = 1000  # Reduced from 10000 for better performance
    ) -> float:
        """Calculate Monte Carlo VaR using simulated returns."""
        if not returns:
            return 0.0
        
        import random
        
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

    async def backtest_var(
        self,
        var_results: List[VaRResult],
        actual_returns: List[float],
        confidence_level: float = 0.95
    ) -> Dict[str, Any]:
        """
        Backtest VaR model performance against actual returns.
        
        Args:
            var_results: List of historical VaR calculations
            actual_returns: List of actual portfolio returns
            confidence_level: Confidence level used for VaR calculations
            
        Returns:
            Dictionary with backtesting results
        """
        try:
            if len(var_results) != len(actual_returns):
                raise ValueError("VaR results and actual returns must have same length")
            
            if not var_results:
                return {
                    'total_observations': 0,
                    'violations': 0,
                    'violation_rate': 0.0,
                    'expected_violations': 0,
                    'kupiec_test_statistic': 0.0,
                    'kupiec_p_value': 1.0,
                    'model_performance': 'insufficient_data'
                }
            
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
            expected_violations = expected_violation_rate * total_observations
            
            # Kupiec test for model accuracy
            kupiec_test_statistic, kupiec_p_value = self._kupiec_test(
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
            
            backtest_results = {
                'total_observations': total_observations,
                'violations': violations,
                'violation_rate': violation_rate,
                'expected_violation_rate': expected_violation_rate,
                'expected_violations': expected_violations,
                'kupiec_test_statistic': kupiec_test_statistic,
                'kupiec_p_value': kupiec_p_value,
                'model_performance': model_performance,
                'confidence_level': confidence_level
            }
            
            self.logger.info(f"VaR backtest: {violations}/{total_observations} violations ({violation_rate:.2%}), performance: {model_performance}")
            return backtest_results
            
        except Exception as e:
            self.logger.error(f"Error backtesting VaR: {e}")
            raise

    def _kupiec_test(self, violations: int, observations: int, expected_rate: float) -> Tuple[float, float]:
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

    # =========================================================================
    # PERFORMANCE METRICS
    # =========================================================================

    async def calculate_performance_metrics(self) -> PerformanceMetrics:
        """
        Calculate comprehensive performance metrics.
        
        Returns:
            PerformanceMetrics with all performance statistics
        """
        try:
            # Get portfolio returns
            returns = await self._get_portfolio_returns()
            
            if len(returns) < 2:
                # Return default metrics for insufficient data
                return PerformanceMetrics(
                    total_return=0.0, annualized_return=0.0, volatility=0.0,
                    sharpe_ratio=0.0, sortino_ratio=0.0, calmar_ratio=0.0,
                    information_ratio=0.0, max_drawdown=0.0, win_rate=0.0,
                    profit_factor=0.0, average_win=0.0, average_loss=0.0,
                    largest_win=0.0, largest_loss=0.0, total_trades=0,
                    winning_trades=0, losing_trades=0
                )
            
            # Calculate basic metrics
            total_return = sum(returns)
            mean_return = mean(returns)
            volatility = stdev(returns) if len(returns) > 1 else 0.0
            
            # Annualize metrics (assuming daily returns)
            annualized_return = mean_return * 252
            annualized_volatility = volatility * math.sqrt(252)
            
            # Risk-adjusted metrics
            risk_free_rate = 0.02  # 2% annual risk-free rate
            sharpe_ratio = (annualized_return - risk_free_rate) / annualized_volatility if annualized_volatility > 0 else 0.0
            
            # Sortino ratio (downside deviation)
            downside_returns = [r for r in returns if r < 0]
            downside_volatility = stdev(downside_returns) * math.sqrt(252) if len(downside_returns) > 1 else annualized_volatility
            sortino_ratio = (annualized_return - risk_free_rate) / downside_volatility if downside_volatility > 0 else 0.0
            
            # Drawdown analysis
            drawdown_analysis = await self.calculate_drawdown_analysis()
            max_drawdown = abs(drawdown_analysis.max_drawdown)
            
            # Calmar ratio
            calmar_ratio = annualized_return / max_drawdown if max_drawdown > 0 else 0.0
            
            # Trade statistics (placeholder - would need actual trade data)
            positive_returns = [r for r in returns if r > 0]
            negative_returns = [r for r in returns if r < 0]
            
            win_rate = len(positive_returns) / len(returns) if returns else 0.0
            average_win = mean(positive_returns) if positive_returns else 0.0
            average_loss = mean(negative_returns) if negative_returns else 0.0
            largest_win = max(returns) if returns else 0.0
            largest_loss = min(returns) if returns else 0.0
            
            total_wins = sum(positive_returns) if positive_returns else 0.0
            total_losses = abs(sum(negative_returns)) if negative_returns else 0.0
            profit_factor = total_wins / total_losses if total_losses > 0 else float('inf') if total_wins > 0 else 0.0
            
            metrics = PerformanceMetrics(
                total_return=total_return,
                annualized_return=annualized_return,
                volatility=annualized_volatility,
                sharpe_ratio=sharpe_ratio,
                sortino_ratio=sortino_ratio,
                calmar_ratio=calmar_ratio,
                information_ratio=sharpe_ratio,  # Simplified
                max_drawdown=max_drawdown,
                win_rate=win_rate,
                profit_factor=profit_factor,
                average_win=average_win,
                average_loss=average_loss,
                largest_win=largest_win,
                largest_loss=largest_loss,
                total_trades=len(returns),
                winning_trades=len(positive_returns),
                losing_trades=len(negative_returns)
            )
            
            self.logger.info(f"Performance metrics: Sharpe {sharpe_ratio:.2f}, Max DD {max_drawdown:.2%}")
            return metrics
            
        except Exception as e:
            self.logger.error(f"Error calculating performance metrics: {e}")
            raise

    # =========================================================================
    # DRAWDOWN ANALYSIS
    # =========================================================================

    async def calculate_drawdown_analysis(self) -> DrawdownAnalysis:
        """
        Calculate comprehensive drawdown analysis.
        
        Returns:
            DrawdownAnalysis with drawdown statistics
        """
        try:
            # Get portfolio value history (placeholder)
            value_history = await self._get_portfolio_value_history()
            
            if len(value_history) < 2:
                return DrawdownAnalysis(
                    max_drawdown=0.0,
                    current_drawdown=0.0,
                    drawdown_duration=0,
                    peak_date=datetime.now(),
                    trough_date=datetime.now(),
                    recovery_date=None,
                    underwater_periods=[]
                )
            
            # Calculate running maximum (peak)
            peaks = []
            current_peak = value_history[0]['value']
            
            for i, point in enumerate(value_history):
                if point['value'] > current_peak:
                    current_peak = point['value']
                peaks.append(current_peak)
            
            # Calculate drawdowns
            drawdowns = []
            for i, point in enumerate(value_history):
                if peaks[i] > 0:
                    dd = (point['value'] - peaks[i]) / peaks[i]
                    drawdowns.append({
                        'date': point['date'],
                        'value': point['value'],
                        'peak': peaks[i],
                        'drawdown': dd
                    })
            
            # Find maximum drawdown
            max_dd = min(drawdowns, key=lambda x: x['drawdown']) if drawdowns else {'drawdown': 0.0}
            max_drawdown = max_dd['drawdown']
            
            # Current drawdown
            current_drawdown = drawdowns[-1]['drawdown'] if drawdowns else 0.0
            
            # Find drawdown periods
            underwater_periods = []
            in_drawdown = False
            start_date = None
            
            for dd in drawdowns:
                if dd['drawdown'] < -0.001 and not in_drawdown:  # Start of drawdown (0.1% threshold)
                    in_drawdown = True
                    start_date = dd['date']
                elif dd['drawdown'] >= -0.001 and in_drawdown:  # End of drawdown
                    in_drawdown = False
                    if start_date:
                        underwater_periods.append({
                            'start': start_date,
                            'end': dd['date'],
                            'duration': (dd['date'] - start_date).days,
                            'max_dd': min(d['drawdown'] for d in drawdowns 
                                        if start_date <= d['date'] <= dd['date'])
                        })
            
            # Calculate duration
            drawdown_duration = underwater_periods[-1]['duration'] if underwater_periods else 0
            
            analysis = DrawdownAnalysis(
                max_drawdown=max_drawdown,
                current_drawdown=current_drawdown,
                drawdown_duration=drawdown_duration,
                peak_date=max_dd.get('date', datetime.now()),
                trough_date=max_dd.get('date', datetime.now()),
                recovery_date=None,  # TODO: Calculate recovery date
                underwater_periods=underwater_periods
            )
            
            self.logger.info(f"Drawdown analysis: Max {max_drawdown:.2%}, Current {current_drawdown:.2%}")
            return analysis
            
        except Exception as e:
            self.logger.error(f"Error calculating drawdown analysis: {e}")
            raise

    # =========================================================================
    # CORRELATION AND VOLATILITY
    # =========================================================================

    async def calculate_correlation_matrix(self, window_days: int = 30, method: str = "pearson") -> CorrelationMatrix:
        """
        Calculate correlation matrix between portfolio positions and market indices.
        
        Args:
            window_days: Rolling window for correlation calculation (default: 30 days)
            method: Correlation method ("pearson", "spearman", "kendall")
            
        Returns:
            CorrelationMatrix with correlation data
        """
        try:
            # Get current positions
            positions = await self.drift_adapter.get_positions()
            if not positions:
                return CorrelationMatrix(
                    matrix={},
                    assets=[],
                    calculation_date=datetime.now(),
                    window_days=window_days,
                    method=method
                )
            
            # Extract market symbols from positions
            position_markets = [pos.get('market', 'UNKNOWN') for pos in positions if pos.get('market')]
            
            # Add major market indices as benchmarks
            benchmarks = ['SOL', 'BTC', 'ETH', 'CRYPTO_MARKET']
            all_assets = list(set(position_markets + benchmarks))
            
            # Get historical returns for all assets
            asset_returns = {}
            for asset in all_assets:
                if asset in position_markets:
                    # Get position-specific returns (would integrate with market data manager)
                    returns = await self._get_asset_returns(asset, window_days)
                else:
                    # Get benchmark returns
                    returns = await self._get_benchmark_returns(asset, window_days)
                
                asset_returns[asset] = returns
            
            # Calculate correlation matrix
            matrix = {}
            for asset1 in all_assets:
                matrix[asset1] = {}
                for asset2 in all_assets:
                    if asset1 == asset2:
                        correlation = 1.0
                    else:
                        correlation = self._calculate_correlation(
                            asset_returns[asset1], 
                            asset_returns[asset2], 
                            method
                        )
                    
                    matrix[asset1][asset2] = correlation
            
            correlation_matrix = CorrelationMatrix(
                matrix=matrix,
                assets=all_assets,
                calculation_date=datetime.now(),
                window_days=window_days,
                method=method
            )
            
            # Store for dynamic tracking
            self._store_correlation_history(correlation_matrix)
            
            self.logger.info(f"Correlation matrix calculated for {len(all_assets)} assets using {method} method")
            return correlation_matrix
            
        except Exception as e:
            self.logger.error(f"Error calculating correlation matrix: {e}")
            raise

    def _calculate_correlation(self, returns1: List[float], returns2: List[float], method: str = "pearson") -> float:
        """
        Calculate correlation between two return series.
        
        Args:
            returns1: First return series
            returns2: Second return series
            method: Correlation method ("pearson", "spearman", "kendall")
            
        Returns:
            Correlation coefficient
        """
        if len(returns1) != len(returns2) or len(returns1) < 2:
            return 0.0
        
        if method == "pearson":
            # Pearson correlation coefficient
            mean1 = mean(returns1)
            mean2 = mean(returns2)
            
            numerator = sum((r1 - mean1) * (r2 - mean2) for r1, r2 in zip(returns1, returns2))
            
            sum_sq1 = sum((r1 - mean1) ** 2 for r1 in returns1)
            sum_sq2 = sum((r2 - mean2) ** 2 for r2 in returns2)
            
            denominator = math.sqrt(sum_sq1 * sum_sq2)
            
            return numerator / denominator if denominator > 0 else 0.0
            
        elif method == "spearman":
            # Spearman rank correlation
            ranks1 = self._calculate_ranks(returns1)
            ranks2 = self._calculate_ranks(returns2)
            return self._calculate_correlation(ranks1, ranks2, "pearson")
            
        elif method == "kendall":
            # Kendall's tau (simplified implementation)
            n = len(returns1)
            concordant = 0
            discordant = 0
            
            for i in range(n):
                for j in range(i + 1, n):
                    sign1 = 1 if returns1[i] < returns1[j] else -1 if returns1[i] > returns1[j] else 0
                    sign2 = 1 if returns2[i] < returns2[j] else -1 if returns2[i] > returns2[j] else 0
                    
                    if sign1 * sign2 > 0:
                        concordant += 1
                    elif sign1 * sign2 < 0:
                        discordant += 1
            
            total_pairs = n * (n - 1) // 2
            return (concordant - discordant) / total_pairs if total_pairs > 0 else 0.0
        
        else:
            raise ValueError(f"Unknown correlation method: {method}")

    def _calculate_ranks(self, values: List[float]) -> List[float]:
        """Calculate ranks for Spearman correlation."""
        sorted_values = sorted(enumerate(values), key=lambda x: x[1])
        ranks = [0.0] * len(values)
        
        for rank, (original_index, _) in enumerate(sorted_values):
            ranks[original_index] = float(rank + 1)
        
        return ranks

    async def _get_asset_returns(self, asset: str, window_days: int) -> List[float]:
        """
        Get historical returns for a specific asset.
        
        This would integrate with the market data manager to get real price data.
        For now, using simulated data with realistic correlations.
        """
        import random
        
        # Use asset-specific seed for consistent results
        asset_seed = hash(asset) % 1000000
        random.seed(asset_seed)
        
        returns = []
        for _ in range(window_days):
            # Simulate returns with asset-specific characteristics
            if 'SOL' in asset:
                base_return = random.gauss(0.001, 0.05)  # Higher volatility
            elif 'BTC' in asset:
                base_return = random.gauss(0.0008, 0.03)  # Moderate volatility
            elif 'ETH' in asset:
                base_return = random.gauss(0.0009, 0.04)  # Moderate-high volatility
            else:
                base_return = random.gauss(0.0005, 0.035)  # Default volatility
            
            returns.append(base_return)
        
        return returns

    def _store_correlation_history(self, correlation_matrix: CorrelationMatrix):
        """Store correlation matrix for dynamic tracking."""
        if not hasattr(self, '_correlation_history'):
            self._correlation_history = []
        
        # Keep last 30 correlation matrices for trend analysis
        self._correlation_history.append({
            'date': correlation_matrix.calculation_date,
            'matrix': correlation_matrix.matrix,
            'method': correlation_matrix.method
        })
        
        # Limit history size
        if len(self._correlation_history) > 30:
            self._correlation_history = self._correlation_history[-30:]

    async def get_correlation_trends(self, asset1: str, asset2: str, lookback_periods: int = 10) -> Dict[str, Any]:
        """
        Analyze correlation trends between two assets.
        
        Args:
            asset1: First asset symbol
            asset2: Second asset symbol
            lookback_periods: Number of historical periods to analyze
            
        Returns:
            Dictionary with trend analysis
        """
        try:
            if not hasattr(self, '_correlation_history') or len(self._correlation_history) < 2:
                return {
                    'current_correlation': 0.0,
                    'average_correlation': 0.0,
                    'correlation_trend': 'insufficient_data',
                    'volatility': 0.0,
                    'periods_analyzed': 0
                }
            
            # Extract correlations for the asset pair
            correlations = []
            for hist in self._correlation_history[-lookback_periods:]:
                if asset1 in hist['matrix'] and asset2 in hist['matrix'][asset1]:
                    correlations.append(hist['matrix'][asset1][asset2])
            
            if len(correlations) < 2:
                return {
                    'current_correlation': 0.0,
                    'average_correlation': 0.0,
                    'correlation_trend': 'insufficient_data',
                    'volatility': 0.0,
                    'periods_analyzed': len(correlations)
                }
            
            # Calculate trend statistics
            current_correlation = correlations[-1]
            average_correlation = mean(correlations)
            correlation_volatility = stdev(correlations) if len(correlations) > 1 else 0.0
            
            # Determine trend direction
            if len(correlations) >= 3:
                recent_avg = mean(correlations[-3:])
                older_avg = mean(correlations[:-3]) if len(correlations) > 3 else correlations[0]
                
                if recent_avg > older_avg + 0.1:
                    trend = 'increasing'
                elif recent_avg < older_avg - 0.1:
                    trend = 'decreasing'
                else:
                    trend = 'stable'
            else:
                trend = 'stable'
            
            return {
                'current_correlation': current_correlation,
                'average_correlation': average_correlation,
                'correlation_trend': trend,
                'volatility': correlation_volatility,
                'periods_analyzed': len(correlations),
                'min_correlation': min(correlations),
                'max_correlation': max(correlations)
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing correlation trends: {e}")
            return {
                'current_correlation': 0.0,
                'average_correlation': 0.0,
                'correlation_trend': 'error',
                'volatility': 0.0,
                'periods_analyzed': 0
            }

    async def detect_correlation_regime_changes(self, threshold: float = 0.3) -> List[Dict[str, Any]]:
        """
        Detect significant changes in correlation regimes.
        
        Args:
            threshold: Minimum correlation change to trigger regime change detection
            
        Returns:
            List of detected regime changes
        """
        try:
            if not hasattr(self, '_correlation_history') or len(self._correlation_history) < 5:
                return []
            
            regime_changes = []
            
            # Get all unique asset pairs
            if not self._correlation_history:
                return []
            
            latest_matrix = self._correlation_history[-1]['matrix']
            asset_pairs = []
            
            for asset1 in latest_matrix:
                for asset2 in latest_matrix[asset1]:
                    if asset1 < asset2:  # Avoid duplicates
                        asset_pairs.append((asset1, asset2))
            
            # Check each asset pair for regime changes
            for asset1, asset2 in asset_pairs:
                correlations = []
                dates = []
                
                for hist in self._correlation_history:
                    if asset1 in hist['matrix'] and asset2 in hist['matrix'][asset1]:
                        correlations.append(hist['matrix'][asset1][asset2])
                        dates.append(hist['date'])
                
                if len(correlations) < 5:
                    continue
                
                # Check for significant changes
                recent_corr = mean(correlations[-3:])  # Last 3 periods
                older_corr = mean(correlations[-6:-3]) if len(correlations) >= 6 else correlations[0]
                
                change = abs(recent_corr - older_corr)
                
                if change > threshold:
                    regime_changes.append({
                        'asset_pair': f"{asset1}-{asset2}",
                        'old_correlation': older_corr,
                        'new_correlation': recent_corr,
                        'change_magnitude': change,
                        'change_direction': 'increase' if recent_corr > older_corr else 'decrease',
                        'detection_date': dates[-1],
                        'significance': 'high' if change > threshold * 2 else 'medium'
                    })
            
            if regime_changes:
                self.logger.warning(f"Detected {len(regime_changes)} correlation regime changes")
            
            return regime_changes
            
        except Exception as e:
            self.logger.error(f"Error detecting correlation regime changes: {e}")
            return []

    async def calculate_volatility_metrics(self, method: str = "historical_ewma") -> VolatilityMetrics:
        """
        Calculate comprehensive volatility metrics.
        
        Args:
            method: Volatility calculation method ("historical", "historical_ewma", "garch")
        
        Returns:
            VolatilityMetrics with volatility analysis
        """
        try:
            # Get portfolio returns
            returns = await self._get_portfolio_returns()
            
            if len(returns) < 2:
                return VolatilityMetrics(
                    portfolio_volatility=0.0,
                    position_volatilities={},
                    volatility_contributions={},
                    realized_volatility=0.0,
                    implied_volatility=None,
                    volatility_forecast=0.0,
                    calculation_method=method
                )
            
            # Calculate portfolio volatility using specified method
            if method == "historical":
                portfolio_volatility = stdev(returns) * math.sqrt(252) if len(returns) > 1 else 0.0
            elif method == "historical_ewma":
                portfolio_volatility = self._calculate_ewma_volatility(returns)
            elif method == "garch":
                portfolio_volatility = self._calculate_garch_volatility(returns)
            else:
                raise ValueError(f"Unknown volatility method: {method}")
            
            # Get current positions
            positions = await self.drift_adapter.get_positions()
            position_volatilities = {}
            volatility_contributions = {}
            
            if positions:
                # Calculate individual position volatilities
                total_portfolio_value = 0.0
                position_values = {}
                
                for pos in positions:
                    market = pos.get('market', 'UNKNOWN')
                    position_size = abs(float(pos.get('base_asset_amount', 0)))
                    
                    if position_size > 0:
                        # Get position-specific returns
                        position_returns = await self._get_asset_returns(market, len(returns))
                        
                        # Calculate position volatility
                        if method == "historical":
                            pos_vol = stdev(position_returns) * math.sqrt(252) if len(position_returns) > 1 else 0.0
                        elif method == "historical_ewma":
                            pos_vol = self._calculate_ewma_volatility(position_returns)
                        else:  # garch
                            pos_vol = self._calculate_garch_volatility(position_returns)
                        
                        position_volatilities[market] = pos_vol
                        
                        # Calculate position value for contribution calculation
                        position_value = position_size * float(pos.get('quote_entry_amount', 0)) / position_size if position_size > 0 else 0.0
                        position_values[market] = abs(position_value)
                        total_portfolio_value += abs(position_value)
                
                # Calculate volatility contributions
                if total_portfolio_value > 0:
                    for market, pos_vol in position_volatilities.items():
                        weight = position_values.get(market, 0) / total_portfolio_value
                        
                        # Volatility contribution = weight * position_volatility * correlation_with_portfolio
                        # For simplicity, using weight * volatility (assumes perfect correlation)
                        # In practice, would use correlation matrix for more accurate calculation
                        volatility_contributions[market] = weight * pos_vol
            
            # Calculate realized volatility (using recent returns)
            recent_returns = returns[-30:] if len(returns) >= 30 else returns
            realized_volatility = stdev(recent_returns) * math.sqrt(252) if len(recent_returns) > 1 else 0.0
            
            # Volatility forecast
            volatility_forecast = self._forecast_volatility(returns, method=method)
            
            metrics = VolatilityMetrics(
                portfolio_volatility=portfolio_volatility,
                position_volatilities=position_volatilities,
                volatility_contributions=volatility_contributions,
                realized_volatility=realized_volatility,
                implied_volatility=None,  # Would need options data
                volatility_forecast=volatility_forecast,
                calculation_method=method
            )
            
            self.logger.info(f"Volatility metrics ({method}): Portfolio {portfolio_volatility:.1%}, {len(position_volatilities)} positions")
            return metrics
            
        except Exception as e:
            self.logger.error(f"Error calculating volatility metrics: {e}")
            raise

    def _calculate_ewma_volatility(self, returns: List[float], lambda_param: float = 0.94) -> float:
        """
        Calculate volatility using Exponentially Weighted Moving Average (EWMA).
        
        Args:
            returns: List of returns
            lambda_param: Decay factor (default: 0.94 for daily data)
            
        Returns:
            Annualized EWMA volatility
        """
        if len(returns) < 2:
            return 0.0
        
        # Initialize with first return squared
        ewma_variance = returns[0] ** 2
        
        # Calculate EWMA variance
        for ret in returns[1:]:
            ewma_variance = lambda_param * ewma_variance + (1 - lambda_param) * (ret ** 2)
        
        # Return annualized volatility
        return math.sqrt(ewma_variance * 252)

    def _calculate_garch_volatility(self, returns: List[float]) -> float:
        """
        Calculate volatility using simplified GARCH(1,1) model.
        
        This is a simplified implementation. In practice, would use
        proper GARCH estimation with maximum likelihood.
        
        Args:
            returns: List of returns
            
        Returns:
            Annualized GARCH volatility
        """
        if len(returns) < 10:
            # Fall back to EWMA for insufficient data
            return self._calculate_ewma_volatility(returns)
        
        # GARCH(1,1) parameters (simplified estimation)
        omega = 0.000001  # Long-term variance component
        alpha = 0.1       # ARCH coefficient
        beta = 0.85       # GARCH coefficient
        
        # Initialize variance with sample variance
        variance = sum(r ** 2 for r in returns[:10]) / 10
        
        # GARCH recursion
        for ret in returns[10:]:
            variance = omega + alpha * (ret ** 2) + beta * variance
        
        # Return annualized volatility
        return math.sqrt(variance * 252)

    def _forecast_volatility(self, returns: List[float], method: str = "ewma", horizon_days: int = 1) -> float:
        """
        Forecast volatility for specified horizon.
        
        Args:
            returns: Historical returns
            method: Forecasting method ("ewma", "garch", "historical")
            horizon_days: Forecast horizon in days
            
        Returns:
            Forecasted annualized volatility
        """
        if len(returns) < 2:
            return 0.0
        
        if method == "ewma":
            # EWMA forecast (constant volatility)
            current_vol = self._calculate_ewma_volatility(returns)
            return current_vol  # EWMA assumes constant volatility
            
        elif method == "garch":
            # GARCH forecast with mean reversion
            current_vol = self._calculate_garch_volatility(returns)
            long_term_vol = stdev(returns) * math.sqrt(252)
            
            # Simple mean reversion (in practice, would use proper GARCH forecasting)
            decay_factor = 0.95 ** horizon_days
            forecast_vol = decay_factor * current_vol + (1 - decay_factor) * long_term_vol
            
            return forecast_vol
            
        else:  # historical
            # Historical average with recent weighting
            if len(returns) >= 30:
                recent_vol = stdev(returns[-30:]) * math.sqrt(252)
                long_term_vol = stdev(returns) * math.sqrt(252)
                # Weight recent more heavily
                return 0.7 * recent_vol + 0.3 * long_term_vol
            else:
                return stdev(returns) * math.sqrt(252)

    async def calculate_volatility_surface(self, assets: List[str] = None) -> Dict[str, Dict[str, float]]:
        """
        Calculate volatility surface across different time horizons.
        
        Args:
            assets: List of assets to calculate volatility for (default: all positions)
            
        Returns:
            Dictionary with volatility surface data
        """
        try:
            if assets is None:
                positions = await self.drift_adapter.get_positions()
                assets = [pos.get('market', 'UNKNOWN') for pos in positions if pos.get('market')]
            
            if not assets:
                return {}
            
            horizons = [1, 7, 30, 90, 252]  # 1D, 1W, 1M, 3M, 1Y
            methods = ['historical', 'ewma', 'garch']
            
            volatility_surface = {}
            
            for asset in assets:
                asset_returns = await self._get_asset_returns(asset, 252)  # Get 1 year of data
                
                if len(asset_returns) < 10:
                    continue
                
                volatility_surface[asset] = {}
                
                for method in methods:
                    volatility_surface[asset][method] = {}
                    
                    for horizon in horizons:
                        if method == 'historical':
                            # Use data up to horizon for historical
                            horizon_returns = asset_returns[-min(horizon, len(asset_returns)):]
                            vol = stdev(horizon_returns) * math.sqrt(252) if len(horizon_returns) > 1 else 0.0
                        else:
                            # Use forecast for EWMA/GARCH
                            vol = self._forecast_volatility(asset_returns, method=method, horizon_days=horizon)
                        
                        volatility_surface[asset][method][f"{horizon}d"] = vol
            
            self.logger.info(f"Volatility surface calculated for {len(volatility_surface)} assets")
            return volatility_surface
            
        except Exception as e:
            self.logger.error(f"Error calculating volatility surface: {e}")
            return {}

    async def detect_volatility_regime_changes(self, threshold_multiplier: float = 2.0) -> List[Dict[str, Any]]:
        """
        Detect significant changes in volatility regimes.
        
        Args:
            threshold_multiplier: Multiplier for volatility change detection
            
        Returns:
            List of detected volatility regime changes
        """
        try:
            regime_changes = []
            
            # Get current positions
            positions = await self.drift_adapter.get_positions()
            if not positions:
                return []
            
            for pos in positions:
                market = pos.get('market', 'UNKNOWN')
                if not market or market == 'UNKNOWN':
                    continue
                
                # Get returns for volatility calculation
                returns = await self._get_asset_returns(market, 60)  # 60 days of data
                
                if len(returns) < 30:
                    continue
                
                # Calculate recent vs historical volatility
                recent_returns = returns[-10:]  # Last 10 days
                historical_returns = returns[:-10]  # Earlier data
                
                if len(recent_returns) < 5 or len(historical_returns) < 10:
                    continue
                
                recent_vol = stdev(recent_returns) * math.sqrt(252)
                historical_vol = stdev(historical_returns) * math.sqrt(252)
                
                # Check for regime change
                vol_ratio = recent_vol / historical_vol if historical_vol > 0 else 1.0
                
                if vol_ratio > threshold_multiplier or vol_ratio < (1.0 / threshold_multiplier):
                    regime_changes.append({
                        'asset': market,
                        'recent_volatility': recent_vol,
                        'historical_volatility': historical_vol,
                        'volatility_ratio': vol_ratio,
                        'change_type': 'increase' if vol_ratio > 1.0 else 'decrease',
                        'severity': 'high' if abs(vol_ratio - 1.0) > threshold_multiplier else 'medium',
                        'detection_date': datetime.now()
                    })
            
            if regime_changes:
                self.logger.warning(f"Detected {len(regime_changes)} volatility regime changes")
            
            return regime_changes
            
        except Exception as e:
            self.logger.error(f"Error detecting volatility regime changes: {e}")
            return []

    # =========================================================================
    # BETA ANALYSIS
    # =========================================================================

    async def calculate_beta_analysis(self, window_days: int = 252) -> BetaAnalysis:
        """
        Calculate beta analysis relative to major crypto assets.
        
        Args:
            window_days: Number of days for beta calculation (default: 252 for 1 year)
        
        Returns:
            BetaAnalysis with beta coefficients and statistics
        """
        try:
            # Get portfolio returns
            portfolio_returns = await self._get_portfolio_returns()
            
            if len(portfolio_returns) < 10:
                return BetaAnalysis(
                    beta_sol=0.0, beta_btc=0.0, beta_market=0.0,
                    r_squared_sol=0.0, r_squared_btc=0.0, r_squared_market=0.0,
                    alpha_sol=0.0, alpha_btc=0.0, alpha_market=0.0
                )
            
            # Limit portfolio returns to window
            portfolio_returns = portfolio_returns[-window_days:] if len(portfolio_returns) > window_days else portfolio_returns
            
            # Get benchmark returns with same length
            sol_returns = await self._get_benchmark_returns('SOL', len(portfolio_returns))
            btc_returns = await self._get_benchmark_returns('BTC', len(portfolio_returns))
            market_returns = await self._get_benchmark_returns('CRYPTO_MARKET', len(portfolio_returns))
            
            # Calculate betas
            beta_sol, alpha_sol, r_squared_sol = self._calculate_beta(portfolio_returns, sol_returns)
            beta_btc, alpha_btc, r_squared_btc = self._calculate_beta(portfolio_returns, btc_returns)
            beta_market, alpha_market, r_squared_market = self._calculate_beta(portfolio_returns, market_returns)
            
            analysis = BetaAnalysis(
                beta_sol=beta_sol,
                beta_btc=beta_btc,
                beta_market=beta_market,
                r_squared_sol=r_squared_sol,
                r_squared_btc=r_squared_btc,
                r_squared_market=r_squared_market,
                alpha_sol=alpha_sol,
                alpha_btc=alpha_btc,
                alpha_market=alpha_market
            )
            
            self.logger.info(f"Beta analysis ({window_days}d): SOL {beta_sol:.2f} (R²={r_squared_sol:.2f}), BTC {beta_btc:.2f} (R²={r_squared_btc:.2f})")
            return analysis
            
        except Exception as e:
            self.logger.error(f"Error calculating beta analysis: {e}")
            raise

    def _calculate_beta(self, portfolio_returns: List[float], benchmark_returns: List[float]) -> Tuple[float, float, float]:
        """
        Calculate beta, alpha, and R-squared using linear regression.
        
        Args:
            portfolio_returns: Portfolio return series
            benchmark_returns: Benchmark return series
            
        Returns:
            Tuple of (beta, alpha, r_squared)
        """
        if len(portfolio_returns) != len(benchmark_returns) or len(portfolio_returns) < 2:
            return 0.0, 0.0, 0.0
        
        # Calculate means
        port_mean = mean(portfolio_returns)
        bench_mean = mean(benchmark_returns)
        
        # Calculate covariance and variance
        covariance = sum((p - port_mean) * (b - bench_mean) 
                        for p, b in zip(portfolio_returns, benchmark_returns)) / (len(portfolio_returns) - 1)
        
        benchmark_variance = sum((b - bench_mean) ** 2 
                               for b in benchmark_returns) / (len(benchmark_returns) - 1)
        
        # Beta calculation (slope of regression line)
        beta = covariance / benchmark_variance if benchmark_variance > 0 else 0.0
        
        # Alpha calculation (intercept of regression line)
        alpha = port_mean - beta * bench_mean
        
        # R-squared calculation (coefficient of determination)
        predicted_returns = [alpha + beta * b for b in benchmark_returns]
        ss_res = sum((p - pred) ** 2 for p, pred in zip(portfolio_returns, predicted_returns))
        ss_tot = sum((p - port_mean) ** 2 for p in portfolio_returns)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
        
        # Ensure R-squared is between 0 and 1
        r_squared = max(0.0, min(1.0, r_squared))
        
        return beta, alpha, r_squared

    async def calculate_rolling_beta(self, benchmark: str, window_days: int = 60, step_days: int = 5) -> Dict[str, List[float]]:
        """
        Calculate rolling beta over time to analyze beta stability.
        
        Args:
            benchmark: Benchmark asset ('SOL', 'BTC', 'CRYPTO_MARKET')
            window_days: Rolling window size in days
            step_days: Step size between calculations
            
        Returns:
            Dictionary with rolling beta time series
        """
        try:
            # Get full return series
            portfolio_returns = await self._get_portfolio_returns()
            benchmark_returns = await self._get_benchmark_returns(benchmark, len(portfolio_returns))
            
            if len(portfolio_returns) < window_days + step_days:
                return {
                    'dates': [],
                    'betas': [],
                    'alphas': [],
                    'r_squareds': []
                }
            
            # Calculate rolling statistics
            dates = []
            betas = []
            alphas = []
            r_squareds = []
            
            base_date = datetime.now() - timedelta(days=len(portfolio_returns))
            
            for i in range(window_days, len(portfolio_returns), step_days):
                # Get window data
                port_window = portfolio_returns[i-window_days:i]
                bench_window = benchmark_returns[i-window_days:i]
                
                # Calculate beta for this window
                beta, alpha, r_squared = self._calculate_beta(port_window, bench_window)
                
                dates.append(base_date + timedelta(days=i))
                betas.append(beta)
                alphas.append(alpha)
                r_squareds.append(r_squared)
            
            self.logger.info(f"Rolling beta calculated for {benchmark}: {len(betas)} periods")
            
            return {
                'dates': dates,
                'betas': betas,
                'alphas': alphas,
                'r_squareds': r_squareds,
                'benchmark': benchmark,
                'window_days': window_days
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating rolling beta: {e}")
            return {
                'dates': [],
                'betas': [],
                'alphas': [],
                'r_squareds': []
            }

    async def analyze_beta_stability(self, lookback_periods: int = 12) -> Dict[str, Any]:
        """
        Analyze beta stability across different time periods.
        
        Args:
            lookback_periods: Number of periods to analyze
            
        Returns:
            Dictionary with beta stability analysis
        """
        try:
            benchmarks = ['SOL', 'BTC', 'CRYPTO_MARKET']
            stability_analysis = {}
            
            for benchmark in benchmarks:
                # Calculate rolling betas
                rolling_data = await self.calculate_rolling_beta(
                    benchmark=benchmark,
                    window_days=60,
                    step_days=10
                )
                
                if len(rolling_data['betas']) < 3:
                    stability_analysis[benchmark] = {
                        'stability_score': 0.0,
                        'beta_trend': 'insufficient_data',
                        'volatility': 0.0,
                        'current_beta': 0.0,
                        'average_beta': 0.0
                    }
                    continue
                
                betas = rolling_data['betas'][-lookback_periods:] if len(rolling_data['betas']) > lookback_periods else rolling_data['betas']
                
                # Calculate stability metrics
                current_beta = betas[-1]
                average_beta = mean(betas)
                beta_volatility = stdev(betas) if len(betas) > 1 else 0.0
                
                # Stability score (inverse of volatility, normalized)
                stability_score = 1.0 / (1.0 + beta_volatility) if beta_volatility > 0 else 1.0
                
                # Trend analysis
                if len(betas) >= 3:
                    recent_avg = mean(betas[-3:])
                    older_avg = mean(betas[:-3]) if len(betas) > 3 else betas[0]
                    
                    if recent_avg > older_avg + 0.1:
                        trend = 'increasing'
                    elif recent_avg < older_avg - 0.1:
                        trend = 'decreasing'
                    else:
                        trend = 'stable'
                else:
                    trend = 'stable'
                
                stability_analysis[benchmark] = {
                    'stability_score': stability_score,
                    'beta_trend': trend,
                    'volatility': beta_volatility,
                    'current_beta': current_beta,
                    'average_beta': average_beta,
                    'min_beta': min(betas),
                    'max_beta': max(betas),
                    'periods_analyzed': len(betas)
                }
            
            self.logger.info(f"Beta stability analysis completed for {len(benchmarks)} benchmarks")
            return stability_analysis
            
        except Exception as e:
            self.logger.error(f"Error analyzing beta stability: {e}")
            return {}

    async def calculate_multi_factor_beta(self) -> Dict[str, Any]:
        """
        Calculate multi-factor beta model (Fama-French style for crypto).
        
        Returns:
            Dictionary with multi-factor model results
        """
        try:
            # Get portfolio returns
            portfolio_returns = await self._get_portfolio_returns()
            
            if len(portfolio_returns) < 30:
                return {
                    'market_beta': 0.0,
                    'size_beta': 0.0,
                    'momentum_beta': 0.0,
                    'alpha': 0.0,
                    'r_squared': 0.0,
                    'model': 'insufficient_data'
                }
            
            # Get factor returns
            market_returns = await self._get_benchmark_returns('CRYPTO_MARKET', len(portfolio_returns))
            
            # Create size factor (small cap - large cap, simplified)
            size_factor = await self._create_size_factor(len(portfolio_returns))
            
            # Create momentum factor (winners - losers, simplified)
            momentum_factor = await self._create_momentum_factor(len(portfolio_returns))
            
            # Multi-factor regression: R_p = alpha + beta_m * R_m + beta_s * SMB + beta_mom * MOM + error
            # Simplified implementation using sequential regression
            
            # First, regress against market
            market_beta, market_alpha, market_r2 = self._calculate_beta(portfolio_returns, market_returns)
            
            # Calculate residuals from market model
            market_predicted = [market_alpha + market_beta * r for r in market_returns]
            residuals = [p - pred for p, pred in zip(portfolio_returns, market_predicted)]
            
            # Regress residuals against size factor
            size_beta, _, size_r2 = self._calculate_beta(residuals, size_factor)
            
            # Update residuals
            size_predicted = [size_beta * f for f in size_factor]
            residuals = [r - pred for r, pred in zip(residuals, size_predicted)]
            
            # Regress residuals against momentum factor
            momentum_beta, _, momentum_r2 = self._calculate_beta(residuals, momentum_factor)
            
            # Calculate overall model R-squared
            # Full model prediction
            full_predicted = [
                market_alpha + market_beta * m + size_beta * s + momentum_beta * mom
                for m, s, mom in zip(market_returns, size_factor, momentum_factor)
            ]
            
            port_mean = mean(portfolio_returns)
            ss_res = sum((p - pred) ** 2 for p, pred in zip(portfolio_returns, full_predicted))
            ss_tot = sum((p - port_mean) ** 2 for p in portfolio_returns)
            full_r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
            full_r_squared = max(0.0, min(1.0, full_r_squared))
            
            result = {
                'market_beta': market_beta,
                'size_beta': size_beta,
                'momentum_beta': momentum_beta,
                'alpha': market_alpha,
                'r_squared': full_r_squared,
                'market_r_squared': market_r2,
                'size_r_squared': size_r2,
                'momentum_r_squared': momentum_r2,
                'model': 'three_factor'
            }
            
            self.logger.info(f"Multi-factor beta: Market {market_beta:.2f}, Size {size_beta:.2f}, Momentum {momentum_beta:.2f} (R²={full_r_squared:.2f})")
            return result
            
        except Exception as e:
            self.logger.error(f"Error calculating multi-factor beta: {e}")
            return {
                'market_beta': 0.0,
                'size_beta': 0.0,
                'momentum_beta': 0.0,
                'alpha': 0.0,
                'r_squared': 0.0,
                'model': 'error'
            }

    async def _create_size_factor(self, length: int) -> List[float]:
        """Create size factor (SMB - Small Minus Big) for crypto."""
        import random
        random.seed(456)  # Consistent results
        
        # Simulate size factor returns (small cap outperformance)
        factor_returns = []
        for _ in range(length):
            # Size factor typically has lower volatility than individual assets
            factor_return = random.gauss(0.0002, 0.015)  # Small positive bias, low volatility
            factor_returns.append(factor_return)
        
        return factor_returns

    async def _create_momentum_factor(self, length: int) -> List[float]:
        """Create momentum factor (WML - Winners Minus Losers) for crypto."""
        import random
        random.seed(789)  # Consistent results
        
        # Simulate momentum factor returns
        factor_returns = []
        for _ in range(length):
            # Momentum factor can be more volatile
            factor_return = random.gauss(0.0001, 0.02)  # Small positive bias, moderate volatility
            factor_returns.append(factor_return)
        
        return factor_returns

    # =========================================================================
    # RISK MONITORING
    # =========================================================================

    async def monitor_risk_changes(self) -> List[RiskChangeAlert]:
        """
        Monitor for significant risk changes and generate alerts.
        
        Returns:
            List of risk change alerts
        """
        try:
            alerts = []
            
            # Calculate current metrics
            current_var = await self.calculate_var()
            current_volatility = await self.calculate_volatility_metrics()
            current_correlation = await self.calculate_correlation_matrix()
            
            # Check for VaR increases
            if 'var_1d' in self._previous_metrics:
                prev_var = self._previous_metrics['var_1d']
                var_change = (current_var.var_1d - prev_var) / prev_var if prev_var > 0 else 0
                
                if var_change > self._alert_thresholds['var_increase']:
                    alerts.append(RiskChangeAlert(
                        alert_type="var_increase",
                        severity="warning" if var_change < 1.0 else "critical",
                        current_value=current_var.var_1d,
                        previous_value=prev_var,
                        threshold=self._alert_thresholds['var_increase'],
                        message=f"VaR increased by {var_change:.1%}",
                        timestamp=datetime.now(),
                        recommended_action="Review position sizes and consider hedging"
                    ))
            
            # Check for volatility spikes
            if 'portfolio_volatility' in self._previous_metrics:
                prev_vol = self._previous_metrics['portfolio_volatility']
                vol_ratio = current_volatility.portfolio_volatility / prev_vol if prev_vol > 0 else 1
                
                if vol_ratio > self._alert_thresholds['volatility_spike']:
                    alerts.append(RiskChangeAlert(
                        alert_type="volatility_spike",
                        severity="warning" if vol_ratio < 3.0 else "critical",
                        current_value=current_volatility.portfolio_volatility,
                        previous_value=prev_vol,
                        threshold=self._alert_thresholds['volatility_spike'],
                        message=f"Volatility increased by {(vol_ratio-1)*100:.0f}%",
                        timestamp=datetime.now(),
                        recommended_action="Reduce position sizes and increase monitoring frequency"
                    ))
            
            # Update previous metrics
            self._previous_metrics.update({
                'var_1d': current_var.var_1d,
                'portfolio_volatility': current_volatility.portfolio_volatility,
                'correlation_matrix': current_correlation.matrix
            })
            
            if alerts:
                self.logger.warning(f"Generated {len(alerts)} risk alerts")
            
            return alerts
            
        except Exception as e:
            self.logger.error(f"Error monitoring risk changes: {e}")
            return []

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    async def _get_portfolio_returns(self) -> List[float]:
        """Get historical portfolio returns (placeholder)."""
        # This would fetch actual portfolio value history and calculate returns
        # For now, return simulated returns
        import random
        random.seed(42)  # Consistent results
        
        returns = []
        for _ in range(min(self.lookback_days, 100)):
            # Simulate daily returns with some volatility
            ret = random.gauss(0.0005, 0.02)  # 0.05% mean, 2% daily vol
            returns.append(ret)
        
        return returns

    async def _get_portfolio_value_history(self) -> List[Dict[str, Any]]:
        """Get historical portfolio values (placeholder)."""
        # This would fetch actual portfolio value history
        # For now, return simulated history
        import random
        random.seed(42)
        
        history = []
        value = 10000.0  # Starting value
        base_date = datetime.now() - timedelta(days=self.lookback_days)
        
        for i in range(min(self.lookback_days, 100)):
            # Simulate value changes
            change = random.gauss(0.0005, 0.02)
            value *= (1 + change)
            
            history.append({
                'date': base_date + timedelta(days=i),
                'value': value
            })
        
        return history

    async def _get_benchmark_returns(self, benchmark: str, window_days: int = None) -> List[float]:
        """Get benchmark returns (placeholder)."""
        import random
        
        if window_days is None:
            window_days = min(self.lookback_days, 100)
        
        # Different seeds for different benchmarks
        seed_map = {'SOL': 123, 'BTC': 456, 'ETH': 789, 'CRYPTO_MARKET': 999}
        random.seed(seed_map.get(benchmark, 42))
        
        returns = []
        for _ in range(window_days):
            if benchmark == 'SOL':
                ret = random.gauss(0.001, 0.05)  # Higher volatility
            elif benchmark == 'BTC':
                ret = random.gauss(0.0008, 0.03)  # Moderate volatility
            elif benchmark == 'ETH':
                ret = random.gauss(0.0009, 0.04)  # Moderate-high volatility
            else:  # CRYPTO_MARKET
                ret = random.gauss(0.0006, 0.025)  # Market average
            
            returns.append(ret)
        
        return returns