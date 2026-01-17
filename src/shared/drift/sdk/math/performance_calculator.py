"""
Performance Calculator
=====================

Shared performance calculations for all trading engines.
Provides comprehensive performance metrics with consistent interfaces.

Features:
- Return calculations (total, annualized, risk-adjusted)
- Risk-adjusted ratios (Sharpe, Sortino, Calmar, Information)
- Drawdown analysis and tracking
- Win/loss statistics
- Performance attribution analysis
- Benchmark comparison metrics
"""

import math
from typing import List, Tuple, Dict, Any, Optional
from statistics import mean, stdev
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.shared.system.logging import Logger


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics result."""
    total_return: float
    annualized_return: float
    volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    information_ratio: float
    max_drawdown: float
    current_drawdown: float
    win_rate: float
    profit_factor: float
    average_win: float
    average_loss: float
    largest_win: float
    largest_loss: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    calculation_date: datetime


@dataclass
class DrawdownPeriod:
    """Individual drawdown period."""
    start_date: datetime
    end_date: Optional[datetime]
    peak_value: float
    trough_value: float
    max_drawdown: float
    duration_days: int
    recovered: bool


@dataclass
class DrawdownAnalysis:
    """Comprehensive drawdown analysis."""
    max_drawdown: float
    current_drawdown: float
    average_drawdown: float
    drawdown_duration: int  # current drawdown duration in days
    max_drawdown_duration: int  # longest drawdown duration
    recovery_factor: float  # average recovery time
    underwater_periods: List[DrawdownPeriod]
    time_underwater_pct: float  # percentage of time in drawdown


@dataclass
class BenchmarkComparison:
    """Performance comparison against benchmark."""
    portfolio_return: float
    benchmark_return: float
    excess_return: float
    tracking_error: float
    information_ratio: float
    beta: float
    alpha: float
    correlation: float
    up_capture: float  # upside capture ratio
    down_capture: float  # downside capture ratio


class PerformanceCalculator:
    """
    Stateless performance calculator with comprehensive metrics.
    
    All methods are static to ensure thread safety and enable
    easy testing and validation.
    """
    
    logger = Logger
    
    @staticmethod
    def calculate_performance_metrics(
        returns: List[float],
        trades: Optional[List[Dict[str, Any]]] = None,
        risk_free_rate: float = 0.02,
        trading_days_per_year: int = 252
    ) -> PerformanceMetrics:
        """
        Calculate comprehensive performance metrics.
        
        Args:
            returns: List of period returns (e.g., daily returns)
            trades: Optional list of individual trades for trade-based metrics
            risk_free_rate: Annual risk-free rate (default: 2%)
            trading_days_per_year: Trading days per year (default: 252)
            
        Returns:
            PerformanceMetrics with all calculated metrics
        """
        if not returns:
            return PerformanceCalculator._empty_performance_metrics()
        
        # Basic return calculations
        total_return = PerformanceCalculator.calculate_total_return(returns)
        annualized_return = PerformanceCalculator.calculate_annualized_return(
            returns, trading_days_per_year
        )
        volatility = PerformanceCalculator.calculate_volatility(returns, trading_days_per_year)
        
        # Risk-adjusted ratios
        sharpe_ratio = PerformanceCalculator.calculate_sharpe_ratio(
            returns, risk_free_rate, trading_days_per_year
        )
        sortino_ratio = PerformanceCalculator.calculate_sortino_ratio(
            returns, risk_free_rate, trading_days_per_year
        )
        
        # Drawdown analysis
        drawdown_analysis = PerformanceCalculator.calculate_drawdown_analysis(returns)
        calmar_ratio = PerformanceCalculator.calculate_calmar_ratio(
            annualized_return, drawdown_analysis.max_drawdown
        )
        
        # Trade-based metrics
        trade_metrics = PerformanceCalculator._calculate_trade_metrics(trades) if trades else {}
        
        return PerformanceMetrics(
            total_return=total_return,
            annualized_return=annualized_return,
            volatility=volatility,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            information_ratio=0.0,  # Requires benchmark
            max_drawdown=drawdown_analysis.max_drawdown,
            current_drawdown=drawdown_analysis.current_drawdown,
            win_rate=trade_metrics.get('win_rate', 0.0),
            profit_factor=trade_metrics.get('profit_factor', 0.0),
            average_win=trade_metrics.get('average_win', 0.0),
            average_loss=trade_metrics.get('average_loss', 0.0),
            largest_win=trade_metrics.get('largest_win', 0.0),
            largest_loss=trade_metrics.get('largest_loss', 0.0),
            total_trades=trade_metrics.get('total_trades', 0),
            winning_trades=trade_metrics.get('winning_trades', 0),
            losing_trades=trade_metrics.get('losing_trades', 0),
            calculation_date=datetime.now()
        )
    
    @staticmethod
    def calculate_total_return(returns: List[float]) -> float:
        """
        Calculate total cumulative return.
        
        Args:
            returns: List of period returns
            
        Returns:
            Total return as decimal (e.g., 0.15 for 15%)
        """
        if not returns:
            return 0.0
        
        # Compound returns: (1 + r1) * (1 + r2) * ... - 1
        cumulative = 1.0
        for ret in returns:
            cumulative *= (1.0 + ret)
        
        return cumulative - 1.0
    
    @staticmethod
    def calculate_annualized_return(
        returns: List[float],
        trading_days_per_year: int = 252
    ) -> float:
        """
        Calculate annualized return.
        
        Args:
            returns: List of period returns
            trading_days_per_year: Trading days per year
            
        Returns:
            Annualized return as decimal
        """
        if not returns:
            return 0.0
        
        total_return = PerformanceCalculator.calculate_total_return(returns)
        periods = len(returns)
        
        if periods == 0:
            return 0.0
        
        # Annualize: (1 + total_return)^(trading_days_per_year / periods) - 1
        annualization_factor = trading_days_per_year / periods
        annualized = ((1.0 + total_return) ** annualization_factor) - 1.0
        
        return annualized
    
    @staticmethod
    def calculate_volatility(
        returns: List[float],
        trading_days_per_year: int = 252
    ) -> float:
        """
        Calculate annualized volatility.
        
        Args:
            returns: List of period returns
            trading_days_per_year: Trading days per year
            
        Returns:
            Annualized volatility as decimal
        """
        if not returns or len(returns) < 2:
            return 0.0
        
        # Calculate standard deviation of returns
        volatility_period = stdev(returns)
        
        # Annualize volatility: σ_daily * sqrt(trading_days_per_year)
        annualized_volatility = volatility_period * math.sqrt(trading_days_per_year)
        
        return annualized_volatility
    
    @staticmethod
    def calculate_sharpe_ratio(
        returns: List[float],
        risk_free_rate: float = 0.02,
        trading_days_per_year: int = 252
    ) -> float:
        """
        Calculate Sharpe ratio.
        
        Args:
            returns: List of period returns
            risk_free_rate: Annual risk-free rate
            trading_days_per_year: Trading days per year
            
        Returns:
            Sharpe ratio
        """
        if not returns or len(returns) < 2:
            return 0.0
        
        annualized_return = PerformanceCalculator.calculate_annualized_return(
            returns, trading_days_per_year
        )
        volatility = PerformanceCalculator.calculate_volatility(
            returns, trading_days_per_year
        )
        
        if volatility == 0:
            return 0.0
        
        excess_return = annualized_return - risk_free_rate
        sharpe_ratio = excess_return / volatility
        
        return sharpe_ratio
    
    @staticmethod
    def calculate_sortino_ratio(
        returns: List[float],
        risk_free_rate: float = 0.02,
        trading_days_per_year: int = 252
    ) -> float:
        """
        Calculate Sortino ratio (uses downside deviation instead of total volatility).
        
        Args:
            returns: List of period returns
            risk_free_rate: Annual risk-free rate
            trading_days_per_year: Trading days per year
            
        Returns:
            Sortino ratio
        """
        if not returns or len(returns) < 2:
            return 0.0
        
        annualized_return = PerformanceCalculator.calculate_annualized_return(
            returns, trading_days_per_year
        )
        
        # Calculate downside deviation (only negative returns)
        negative_returns = [ret for ret in returns if ret < 0]
        
        if not negative_returns:
            return float('inf') if annualized_return > risk_free_rate else 0.0
        
        downside_deviation = stdev(negative_returns) * math.sqrt(trading_days_per_year)
        
        if downside_deviation == 0:
            return 0.0
        
        excess_return = annualized_return - risk_free_rate
        sortino_ratio = excess_return / downside_deviation
        
        return sortino_ratio
    
    @staticmethod
    def calculate_calmar_ratio(annualized_return: float, max_drawdown: float) -> float:
        """
        Calculate Calmar ratio (annualized return / max drawdown).
        
        Args:
            annualized_return: Annualized return
            max_drawdown: Maximum drawdown (positive number)
            
        Returns:
            Calmar ratio
        """
        if max_drawdown == 0:
            return float('inf') if annualized_return > 0 else 0.0
        
        return annualized_return / max_drawdown
    
    @staticmethod
    def calculate_drawdown_analysis(returns: List[float]) -> DrawdownAnalysis:
        """
        Calculate comprehensive drawdown analysis.
        
        Args:
            returns: List of period returns
            
        Returns:
            DrawdownAnalysis with detailed drawdown metrics
        """
        if not returns:
            return DrawdownAnalysis(
                max_drawdown=0.0,
                current_drawdown=0.0,
                average_drawdown=0.0,
                drawdown_duration=0,
                max_drawdown_duration=0,
                recovery_factor=0.0,
                underwater_periods=[],
                time_underwater_pct=0.0
            )
        
        # Calculate cumulative returns and peaks
        cumulative_returns = []
        running_total = 1.0
        
        for ret in returns:
            running_total *= (1.0 + ret)
            cumulative_returns.append(running_total)
        
        # Calculate drawdowns
        drawdowns = []
        peaks = []
        current_peak = cumulative_returns[0]
        
        for value in cumulative_returns:
            if value > current_peak:
                current_peak = value
            
            peaks.append(current_peak)
            drawdown = (current_peak - value) / current_peak
            drawdowns.append(drawdown)
        
        # Find drawdown periods
        underwater_periods = []
        in_drawdown = False
        drawdown_start = 0
        peak_value = 0.0
        
        for i, (drawdown, cum_return, peak) in enumerate(zip(drawdowns, cumulative_returns, peaks)):
            if drawdown > 0 and not in_drawdown:
                # Start of drawdown
                in_drawdown = True
                drawdown_start = i
                peak_value = peak
            elif drawdown == 0 and in_drawdown:
                # End of drawdown (recovery)
                in_drawdown = False
                trough_value = min(cumulative_returns[drawdown_start:i+1])
                max_dd_in_period = max(drawdowns[drawdown_start:i+1])
                
                period = DrawdownPeriod(
                    start_date=datetime.now() - timedelta(days=len(returns) - drawdown_start),
                    end_date=datetime.now() - timedelta(days=len(returns) - i),
                    peak_value=peak_value,
                    trough_value=trough_value,
                    max_drawdown=max_dd_in_period,
                    duration_days=i - drawdown_start,
                    recovered=True
                )
                underwater_periods.append(period)
        
        # Handle ongoing drawdown
        if in_drawdown:
            trough_value = min(cumulative_returns[drawdown_start:])
            max_dd_in_period = max(drawdowns[drawdown_start:])
            
            period = DrawdownPeriod(
                start_date=datetime.now() - timedelta(days=len(returns) - drawdown_start),
                end_date=None,
                peak_value=peak_value,
                trough_value=trough_value,
                max_drawdown=max_dd_in_period,
                duration_days=len(returns) - drawdown_start,
                recovered=False
            )
            underwater_periods.append(period)
        
        # Calculate summary statistics
        max_drawdown = max(drawdowns) if drawdowns else 0.0
        current_drawdown = drawdowns[-1] if drawdowns else 0.0
        average_drawdown = mean([dd for dd in drawdowns if dd > 0]) if any(dd > 0 for dd in drawdowns) else 0.0
        
        current_drawdown_duration = 0
        if in_drawdown:
            current_drawdown_duration = len(returns) - drawdown_start
        
        max_drawdown_duration = max([p.duration_days for p in underwater_periods]) if underwater_periods else 0
        
        # Time underwater percentage
        underwater_days = sum([p.duration_days for p in underwater_periods])
        time_underwater_pct = underwater_days / len(returns) if returns else 0.0
        
        # Recovery factor (average recovery time)
        recovered_periods = [p for p in underwater_periods if p.recovered]
        recovery_factor = mean([p.duration_days for p in recovered_periods]) if recovered_periods else 0.0
        
        return DrawdownAnalysis(
            max_drawdown=max_drawdown,
            current_drawdown=current_drawdown,
            average_drawdown=average_drawdown,
            drawdown_duration=current_drawdown_duration,
            max_drawdown_duration=max_drawdown_duration,
            recovery_factor=recovery_factor,
            underwater_periods=underwater_periods,
            time_underwater_pct=time_underwater_pct
        )
    
    @staticmethod
    def calculate_benchmark_comparison(
        portfolio_returns: List[float],
        benchmark_returns: List[float],
        risk_free_rate: float = 0.02,
        trading_days_per_year: int = 252
    ) -> BenchmarkComparison:
        """
        Calculate performance comparison against benchmark.
        
        Args:
            portfolio_returns: Portfolio returns
            benchmark_returns: Benchmark returns
            risk_free_rate: Annual risk-free rate
            trading_days_per_year: Trading days per year
            
        Returns:
            BenchmarkComparison with relative performance metrics
        """
        if not portfolio_returns or not benchmark_returns or len(portfolio_returns) != len(benchmark_returns):
            return BenchmarkComparison(
                portfolio_return=0.0,
                benchmark_return=0.0,
                excess_return=0.0,
                tracking_error=0.0,
                information_ratio=0.0,
                beta=0.0,
                alpha=0.0,
                correlation=0.0,
                up_capture=0.0,
                down_capture=0.0
            )
        
        # Calculate returns
        portfolio_return = PerformanceCalculator.calculate_annualized_return(
            portfolio_returns, trading_days_per_year
        )
        benchmark_return = PerformanceCalculator.calculate_annualized_return(
            benchmark_returns, trading_days_per_year
        )
        
        # Excess returns
        excess_returns = [p - b for p, b in zip(portfolio_returns, benchmark_returns)]
        excess_return = portfolio_return - benchmark_return
        
        # Tracking error
        tracking_error = stdev(excess_returns) * math.sqrt(trading_days_per_year) if len(excess_returns) > 1 else 0.0
        
        # Information ratio
        information_ratio = excess_return / tracking_error if tracking_error != 0 else 0.0
        
        # Beta and Alpha (using simple linear regression)
        beta, alpha = PerformanceCalculator._calculate_beta_alpha(
            portfolio_returns, benchmark_returns, risk_free_rate, trading_days_per_year
        )
        
        # Correlation
        correlation = PerformanceCalculator._calculate_correlation(portfolio_returns, benchmark_returns)
        
        # Capture ratios
        up_capture, down_capture = PerformanceCalculator._calculate_capture_ratios(
            portfolio_returns, benchmark_returns
        )
        
        return BenchmarkComparison(
            portfolio_return=portfolio_return,
            benchmark_return=benchmark_return,
            excess_return=excess_return,
            tracking_error=tracking_error,
            information_ratio=information_ratio,
            beta=beta,
            alpha=alpha,
            correlation=correlation,
            up_capture=up_capture,
            down_capture=down_capture
        )
    
    @staticmethod
    def _calculate_trade_metrics(trades: List[Dict[str, Any]]) -> Dict[str, float]:
        """Calculate trade-based performance metrics."""
        if not trades:
            return {}
        
        # Extract PnL from trades
        pnls = []
        for trade in trades:
            pnl = trade.get('pnl', 0.0)
            if isinstance(pnl, (int, float)):
                pnls.append(float(pnl))
        
        if not pnls:
            return {}
        
        winning_trades = [pnl for pnl in pnls if pnl > 0]
        losing_trades = [pnl for pnl in pnls if pnl < 0]
        
        total_trades = len(pnls)
        winning_count = len(winning_trades)
        losing_count = len(losing_trades)
        
        win_rate = winning_count / total_trades if total_trades > 0 else 0.0
        
        average_win = mean(winning_trades) if winning_trades else 0.0
        average_loss = mean(losing_trades) if losing_trades else 0.0
        
        largest_win = max(winning_trades) if winning_trades else 0.0
        largest_loss = min(losing_trades) if losing_trades else 0.0
        
        # Profit factor: gross profit / gross loss
        gross_profit = sum(winning_trades) if winning_trades else 0.0
        gross_loss = abs(sum(losing_trades)) if losing_trades else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
        
        return {
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'average_win': average_win,
            'average_loss': average_loss,
            'largest_win': largest_win,
            'largest_loss': largest_loss,
            'total_trades': total_trades,
            'winning_trades': winning_count,
            'losing_trades': losing_count
        }
    
    @staticmethod
    def _calculate_beta_alpha(
        portfolio_returns: List[float],
        benchmark_returns: List[float],
        risk_free_rate: float,
        trading_days_per_year: int
    ) -> Tuple[float, float]:
        """Calculate beta and alpha using simple linear regression."""
        if len(portfolio_returns) != len(benchmark_returns) or len(portfolio_returns) < 2:
            return 0.0, 0.0
        
        # Convert to excess returns
        daily_rf_rate = risk_free_rate / trading_days_per_year
        portfolio_excess = [ret - daily_rf_rate for ret in portfolio_returns]
        benchmark_excess = [ret - daily_rf_rate for ret in benchmark_returns]
        
        # Calculate beta using covariance / variance
        if len(benchmark_excess) < 2:
            return 0.0, 0.0
        
        benchmark_var = stdev(benchmark_excess) ** 2
        if benchmark_var == 0:
            return 0.0, 0.0
        
        # Covariance calculation
        portfolio_mean = mean(portfolio_excess)
        benchmark_mean = mean(benchmark_excess)
        
        covariance = sum(
            (p - portfolio_mean) * (b - benchmark_mean)
            for p, b in zip(portfolio_excess, benchmark_excess)
        ) / (len(portfolio_excess) - 1)
        
        beta = covariance / benchmark_var
        
        # Alpha = portfolio_return - (risk_free_rate + beta * (benchmark_return - risk_free_rate))
        portfolio_return = mean(portfolio_excess) * trading_days_per_year
        benchmark_return = mean(benchmark_excess) * trading_days_per_year
        alpha = portfolio_return - (beta * benchmark_return)
        
        return beta, alpha
    
    @staticmethod
    def _calculate_correlation(returns1: List[float], returns2: List[float]) -> float:
        """Calculate Pearson correlation coefficient."""
        if len(returns1) != len(returns2) or len(returns1) < 2:
            return 0.0
        
        mean1 = mean(returns1)
        mean2 = mean(returns2)
        
        numerator = sum((x - mean1) * (y - mean2) for x, y in zip(returns1, returns2))
        
        sum_sq1 = sum((x - mean1) ** 2 for x in returns1)
        sum_sq2 = sum((y - mean2) ** 2 for y in returns2)
        
        denominator = math.sqrt(sum_sq1 * sum_sq2)
        
        if denominator == 0:
            return 0.0
        
        return numerator / denominator
    
    @staticmethod
    def _calculate_capture_ratios(
        portfolio_returns: List[float],
        benchmark_returns: List[float]
    ) -> Tuple[float, float]:
        """Calculate upside and downside capture ratios."""
        if len(portfolio_returns) != len(benchmark_returns):
            return 0.0, 0.0
        
        up_periods = [(p, b) for p, b in zip(portfolio_returns, benchmark_returns) if b > 0]
        down_periods = [(p, b) for p, b in zip(portfolio_returns, benchmark_returns) if b < 0]
        
        # Upside capture
        if up_periods:
            up_portfolio = mean([p for p, b in up_periods])
            up_benchmark = mean([b for p, b in up_periods])
            up_capture = up_portfolio / up_benchmark if up_benchmark != 0 else 0.0
        else:
            up_capture = 0.0
        
        # Downside capture
        if down_periods:
            down_portfolio = mean([p for p, b in down_periods])
            down_benchmark = mean([b for p, b in down_periods])
            down_capture = down_portfolio / down_benchmark if down_benchmark != 0 else 0.0
        else:
            down_capture = 0.0
        
        return up_capture, down_capture
    
    @staticmethod
    def _empty_performance_metrics() -> PerformanceMetrics:
        """Return empty performance metrics for edge cases."""
        return PerformanceMetrics(
            total_return=0.0,
            annualized_return=0.0,
            volatility=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            calmar_ratio=0.0,
            information_ratio=0.0,
            max_drawdown=0.0,
            current_drawdown=0.0,
            win_rate=0.0,
            profit_factor=0.0,
            average_win=0.0,
            average_loss=0.0,
            largest_win=0.0,
            largest_loss=0.0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            calculation_date=datetime.now()
        )