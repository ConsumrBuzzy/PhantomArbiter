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

    async def calculate_correlation_matrix(self, window_days: int = 30) -> CorrelationMatrix:
        """
        Calculate correlation matrix between portfolio positions and market indices.
        
        Args:
            window_days: Rolling window for correlation calculation
            
        Returns:
            CorrelationMatrix with correlation data
        """
        try:
            # Get position returns (placeholder)
            positions = await self.drift_adapter.get_positions()
            if not positions:
                return CorrelationMatrix(
                    matrix={},
                    assets=[],
                    calculation_date=datetime.now(),
                    window_days=window_days,
                    method="pearson"
                )
            
            # Extract market symbols
            markets = [pos.get('market', 'UNKNOWN') for pos in positions if pos.get('market')]
            
            # Add benchmark indices
            benchmarks = ['SOL', 'BTC', 'ETH']
            all_assets = list(set(markets + benchmarks))
            
            # Calculate correlation matrix (placeholder with realistic values)
            matrix = {}
            for asset1 in all_assets:
                matrix[asset1] = {}
                for asset2 in all_assets:
                    if asset1 == asset2:
                        correlation = 1.0
                    elif asset1 in ['SOL', 'SOL-PERP'] and asset2 in ['SOL', 'SOL-PERP']:
                        correlation = 0.95
                    elif asset1 in ['BTC', 'BTC-PERP'] and asset2 in ['BTC', 'BTC-PERP']:
                        correlation = 0.95
                    elif 'SOL' in asset1 and 'BTC' in asset2:
                        correlation = 0.7
                    elif 'BTC' in asset1 and 'ETH' in asset2:
                        correlation = 0.8
                    else:
                        correlation = 0.5  # Default moderate correlation
                    
                    matrix[asset1][asset2] = correlation
            
            correlation_matrix = CorrelationMatrix(
                matrix=matrix,
                assets=all_assets,
                calculation_date=datetime.now(),
                window_days=window_days,
                method="pearson"
            )
            
            self.logger.info(f"Correlation matrix calculated for {len(all_assets)} assets")
            return correlation_matrix
            
        except Exception as e:
            self.logger.error(f"Error calculating correlation matrix: {e}")
            raise

    async def calculate_volatility_metrics(self) -> VolatilityMetrics:
        """
        Calculate comprehensive volatility metrics.
        
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
                    calculation_method="historical"
                )
            
            # Portfolio volatility
            portfolio_volatility = stdev(returns) * math.sqrt(252) if len(returns) > 1 else 0.0
            
            # Position volatilities (placeholder)
            positions = await self.drift_adapter.get_positions()
            position_volatilities = {}
            volatility_contributions = {}
            
            for pos in positions or []:
                market = pos.get('market', 'UNKNOWN')
                # Placeholder volatility based on asset type
                if 'SOL' in market:
                    vol = 0.8  # 80% annual volatility
                elif 'BTC' in market:
                    vol = 0.6  # 60% annual volatility
                else:
                    vol = 0.7  # 70% default volatility
                
                position_volatilities[market] = vol
                
                # Simple volatility contribution (position weight * volatility)
                position_size = abs(float(pos.get('base_asset_amount', 0)))
                total_exposure = sum(abs(float(p.get('base_asset_amount', 0))) for p in positions)
                weight = position_size / total_exposure if total_exposure > 0 else 0
                volatility_contributions[market] = weight * vol
            
            # Realized volatility (same as portfolio volatility for now)
            realized_volatility = portfolio_volatility
            
            # Volatility forecast (simple EWMA)
            volatility_forecast = self._forecast_volatility(returns)
            
            metrics = VolatilityMetrics(
                portfolio_volatility=portfolio_volatility,
                position_volatilities=position_volatilities,
                volatility_contributions=volatility_contributions,
                realized_volatility=realized_volatility,
                implied_volatility=None,  # Would need options data
                volatility_forecast=volatility_forecast,
                calculation_method="historical_ewma"
            )
            
            self.logger.info(f"Volatility metrics: Portfolio {portfolio_volatility:.1%}")
            return metrics
            
        except Exception as e:
            self.logger.error(f"Error calculating volatility metrics: {e}")
            raise

    def _forecast_volatility(self, returns: List[float], lambda_param: float = 0.94) -> float:
        """Forecast volatility using EWMA model."""
        if len(returns) < 2:
            return 0.0
        
        # Simple EWMA volatility forecast
        variance = 0.0
        for i, ret in enumerate(reversed(returns[:30])):  # Use last 30 observations
            weight = (1 - lambda_param) * (lambda_param ** i)
            variance += weight * (ret ** 2)
        
        return math.sqrt(variance * 252)  # Annualized

    # =========================================================================
    # BETA ANALYSIS
    # =========================================================================

    async def calculate_beta_analysis(self) -> BetaAnalysis:
        """
        Calculate beta analysis relative to major crypto assets.
        
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
            
            # Get benchmark returns (placeholder)
            sol_returns = await self._get_benchmark_returns('SOL')
            btc_returns = await self._get_benchmark_returns('BTC')
            market_returns = await self._get_benchmark_returns('CRYPTO_MARKET')
            
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
            
            self.logger.info(f"Beta analysis: SOL {beta_sol:.2f}, BTC {beta_btc:.2f}")
            return analysis
            
        except Exception as e:
            self.logger.error(f"Error calculating beta analysis: {e}")
            raise

    def _calculate_beta(self, portfolio_returns: List[float], benchmark_returns: List[float]) -> Tuple[float, float, float]:
        """Calculate beta, alpha, and R-squared."""
        if len(portfolio_returns) != len(benchmark_returns) or len(portfolio_returns) < 2:
            return 0.0, 0.0, 0.0
        
        # Calculate covariance and variance
        port_mean = mean(portfolio_returns)
        bench_mean = mean(benchmark_returns)
        
        covariance = sum((p - port_mean) * (b - bench_mean) 
                        for p, b in zip(portfolio_returns, benchmark_returns)) / (len(portfolio_returns) - 1)
        
        benchmark_variance = sum((b - bench_mean) ** 2 
                               for b in benchmark_returns) / (len(benchmark_returns) - 1)
        
        # Beta calculation
        beta = covariance / benchmark_variance if benchmark_variance > 0 else 0.0
        
        # Alpha calculation (intercept)
        alpha = port_mean - beta * bench_mean
        
        # R-squared calculation
        predicted_returns = [alpha + beta * b for b in benchmark_returns]
        ss_res = sum((p - pred) ** 2 for p, pred in zip(portfolio_returns, predicted_returns))
        ss_tot = sum((p - port_mean) ** 2 for p in portfolio_returns)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
        
        return beta, alpha, r_squared

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

    async def _get_benchmark_returns(self, benchmark: str) -> List[float]:
        """Get benchmark returns (placeholder)."""
        import random
        
        # Different seeds for different benchmarks
        seed_map = {'SOL': 123, 'BTC': 456, 'CRYPTO_MARKET': 789}
        random.seed(seed_map.get(benchmark, 42))
        
        returns = []
        for _ in range(min(self.lookback_days, 100)):
            if benchmark == 'SOL':
                ret = random.gauss(0.001, 0.05)  # Higher volatility
            elif benchmark == 'BTC':
                ret = random.gauss(0.0008, 0.03)  # Moderate volatility
            else:  # CRYPTO_MARKET
                ret = random.gauss(0.0006, 0.025)  # Market average
            
            returns.append(ret)
        
        return returns