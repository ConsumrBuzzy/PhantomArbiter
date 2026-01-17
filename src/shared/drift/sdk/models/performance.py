"""
Performance Data Models
======================

Shared performance tracking models for all trading engines.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum


class PerformancePeriod(Enum):
    """Performance measurement periods."""
    INTRADAY = "intraday"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    INCEPTION = "inception"


class BenchmarkType(Enum):
    """Benchmark types for comparison."""
    MARKET_INDEX = "market_index"
    PEER_GROUP = "peer_group"
    RISK_FREE = "risk_free"
    CUSTOM = "custom"


@dataclass
class PerformanceSnapshot:
    """Point-in-time performance snapshot."""
    
    # Identification
    snapshot_id: str
    engine_name: Optional[str] = None  # Specific engine or portfolio-wide
    period: PerformancePeriod = PerformancePeriod.DAILY
    
    # Time range
    start_date: datetime
    end_date: datetime
    snapshot_time: datetime
    
    # Return metrics
    total_return: float  # Total return for period
    annualized_return: float  # Annualized return
    excess_return: float  # Return above benchmark
    
    # Risk metrics
    volatility: float  # Annualized volatility
    max_drawdown: float  # Maximum drawdown in period
    current_drawdown: float  # Current drawdown from peak
    
    # Risk-adjusted metrics
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    information_ratio: float
    
    # Trade statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    
    # Financial metrics
    starting_value: float = 0.0
    ending_value: float = 0.0
    peak_value: float = 0.0
    total_fees: float = 0.0
    net_deposits: float = 0.0  # Net deposits/withdrawals during period
    
    # Attribution
    alpha: float = 0.0  # Jensen's alpha
    beta: float = 1.0  # Market beta
    correlation_to_benchmark: float = 0.0
    
    @property
    def days_in_period(self) -> int:
        """Calculate number of days in performance period."""
        return (self.end_date - self.start_date).days
    
    @property
    def return_on_max_drawdown(self) -> float:
        """Calculate return relative to maximum drawdown."""
        if self.max_drawdown == 0:
            return 0.0
        return self.total_return / self.max_drawdown
    
    @property
    def risk_adjusted_return(self) -> float:
        """Calculate simple risk-adjusted return."""
        if self.volatility == 0:
            return 0.0
        return self.total_return / self.volatility
    
    def calculate_performance_score(self) -> float:
        """Calculate overall performance score (0-100)."""
        score = 50.0  # Base score
        
        # Return component (±30 points)
        if self.annualized_return > 0.2:  # >20% annual return
            score += 30
        elif self.annualized_return > 0.1:  # >10% annual return
            score += 20
        elif self.annualized_return > 0.05:  # >5% annual return
            score += 10
        elif self.annualized_return < -0.1:  # <-10% annual return
            score -= 20
        elif self.annualized_return < -0.05:  # <-5% annual return
            score -= 10
        
        # Sharpe ratio component (±20 points)
        if self.sharpe_ratio > 2.0:
            score += 20
        elif self.sharpe_ratio > 1.0:
            score += 15
        elif self.sharpe_ratio > 0.5:
            score += 10
        elif self.sharpe_ratio < -0.5:
            score -= 15
        
        # Drawdown component (±15 points)
        if self.max_drawdown < 0.05:  # <5% max drawdown
            score += 15
        elif self.max_drawdown < 0.1:  # <10% max drawdown
            score += 10
        elif self.max_drawdown > 0.3:  # >30% max drawdown
            score -= 15
        elif self.max_drawdown > 0.2:  # >20% max drawdown
            score -= 10
        
        # Win rate component (±10 points)
        if self.win_rate > 0.7:  # >70% win rate
            score += 10
        elif self.win_rate > 0.6:  # >60% win rate
            score += 5
        elif self.win_rate < 0.3:  # <30% win rate
            score -= 10
        elif self.win_rate < 0.4:  # <40% win rate
            score -= 5
        
        # Alpha component (±5 points)
        if self.alpha > 0.05:  # >5% alpha
            score += 5
        elif self.alpha < -0.05:  # <-5% alpha
            score -= 5
        
        return max(0.0, min(100.0, score))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'snapshot_id': self.snapshot_id,
            'engine_name': self.engine_name,
            'period': self.period.value,
            'start_date': self.start_date.isoformat(),
            'end_date': self.end_date.isoformat(),
            'snapshot_time': self.snapshot_time.isoformat(),
            'days_in_period': self.days_in_period,
            'total_return': self.total_return,
            'annualized_return': self.annualized_return,
            'excess_return': self.excess_return,
            'volatility': self.volatility,
            'max_drawdown': self.max_drawdown,
            'current_drawdown': self.current_drawdown,
            'sharpe_ratio': self.sharpe_ratio,
            'sortino_ratio': self.sortino_ratio,
            'calmar_ratio': self.calmar_ratio,
            'information_ratio': self.information_ratio,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': self.win_rate,
            'profit_factor': self.profit_factor,
            'starting_value': self.starting_value,
            'ending_value': self.ending_value,
            'peak_value': self.peak_value,
            'total_fees': self.total_fees,
            'net_deposits': self.net_deposits,
            'alpha': self.alpha,
            'beta': self.beta,
            'correlation_to_benchmark': self.correlation_to_benchmark,
            'performance_score': self.calculate_performance_score(),
            'return_on_max_drawdown': self.return_on_max_drawdown,
            'risk_adjusted_return': self.risk_adjusted_return
        }


@dataclass
class BenchmarkData:
    """Benchmark data for performance comparison."""
    
    # Benchmark identification
    benchmark_id: str
    benchmark_name: str
    benchmark_type: BenchmarkType
    
    # Time series data
    dates: List[datetime]
    returns: List[float]  # Period returns
    prices: List[float]  # Price levels
    
    # Benchmark characteristics
    volatility: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    
    # Metadata
    data_source: str = "unknown"
    last_updated: datetime
    
    def get_return_for_period(self, start_date: datetime, end_date: datetime) -> float:
        """Get benchmark return for specific period."""
        if not self.dates or not self.prices:
            return 0.0
        
        # Find closest dates
        start_idx = None
        end_idx = None
        
        for i, date in enumerate(self.dates):
            if start_idx is None and date >= start_date:
                start_idx = i
            if date <= end_date:
                end_idx = i
        
        if start_idx is None or end_idx is None or start_idx >= end_idx:
            return 0.0
        
        start_price = self.prices[start_idx]
        end_price = self.prices[end_idx]
        
        if start_price == 0:
            return 0.0
        
        return (end_price - start_price) / start_price
    
    def get_returns_for_period(self, start_date: datetime, end_date: datetime) -> List[float]:
        """Get benchmark returns for specific period."""
        period_returns = []
        
        for i, date in enumerate(self.dates):
            if start_date <= date <= end_date and i < len(self.returns):
                period_returns.append(self.returns[i])
        
        return period_returns
    
    @property
    def total_return(self) -> float:
        """Calculate total return over entire period."""
        if not self.prices or len(self.prices) < 2:
            return 0.0
        
        start_price = self.prices[0]
        end_price = self.prices[-1]
        
        if start_price == 0:
            return 0.0
        
        return (end_price - start_price) / start_price
    
    @property
    def annualized_return(self) -> float:
        """Calculate annualized return."""
        if not self.dates or len(self.dates) < 2:
            return 0.0
        
        total_days = (self.dates[-1] - self.dates[0]).days
        if total_days == 0:
            return 0.0
        
        years = total_days / 365.25
        total_ret = self.total_return
        
        return ((1 + total_ret) ** (1 / years)) - 1 if years > 0 else 0.0


@dataclass
class PerformanceComparison:
    """Performance comparison against benchmark."""
    
    # Comparison identification
    comparison_id: str
    portfolio_snapshot: PerformanceSnapshot
    benchmark_data: BenchmarkData
    
    # Relative performance metrics
    excess_return: float  # Portfolio return - benchmark return
    tracking_error: float  # Standard deviation of excess returns
    information_ratio: float  # Excess return / tracking error
    
    # Regression statistics
    alpha: float  # Jensen's alpha
    beta: float  # Market beta
    r_squared: float  # Coefficient of determination
    
    # Capture ratios
    upside_capture: float  # Upside capture ratio
    downside_capture: float  # Downside capture ratio
    
    # Risk comparison
    relative_volatility: float  # Portfolio vol / benchmark vol
    relative_max_drawdown: float  # Portfolio DD / benchmark DD
    
    # Performance attribution
    selection_effect: float = 0.0  # Security selection contribution
    allocation_effect: float = 0.0  # Asset allocation contribution
    interaction_effect: float = 0.0  # Interaction effect
    
    @property
    def outperformance(self) -> bool:
        """Check if portfolio outperformed benchmark."""
        return self.excess_return > 0
    
    @property
    def risk_adjusted_outperformance(self) -> bool:
        """Check if portfolio had better risk-adjusted performance."""
        portfolio_sharpe = self.portfolio_snapshot.sharpe_ratio
        benchmark_sharpe = self.benchmark_data.sharpe_ratio
        return portfolio_sharpe > benchmark_sharpe
    
    @property
    def batting_average(self) -> float:
        """Calculate percentage of periods with outperformance."""
        # This would require period-by-period data
        # Simplified implementation
        return 0.5 + (self.excess_return * 0.1)  # Rough approximation
    
    def calculate_comparison_score(self) -> float:
        """Calculate overall comparison score (0-100)."""
        score = 50.0  # Base score
        
        # Excess return component (±25 points)
        if self.excess_return > 0.1:  # >10% outperformance
            score += 25
        elif self.excess_return > 0.05:  # >5% outperformance
            score += 15
        elif self.excess_return > 0:  # Any outperformance
            score += 10
        elif self.excess_return < -0.1:  # >10% underperformance
            score -= 25
        elif self.excess_return < -0.05:  # >5% underperformance
            score -= 15
        
        # Information ratio component (±20 points)
        if self.information_ratio > 1.0:
            score += 20
        elif self.information_ratio > 0.5:
            score += 15
        elif self.information_ratio > 0:
            score += 5
        elif self.information_ratio < -0.5:
            score -= 15
        
        # Alpha component (±15 points)
        if self.alpha > 0.05:  # >5% alpha
            score += 15
        elif self.alpha > 0.02:  # >2% alpha
            score += 10
        elif self.alpha < -0.05:  # <-5% alpha
            score -= 15
        elif self.alpha < -0.02:  # <-2% alpha
            score -= 10
        
        # Risk management component (±10 points)
        if self.relative_max_drawdown < 0.8:  # Lower drawdown than benchmark
            score += 10
        elif self.relative_max_drawdown > 1.5:  # Much higher drawdown
            score -= 10
        
        return max(0.0, min(100.0, score))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'comparison_id': self.comparison_id,
            'portfolio_snapshot_id': self.portfolio_snapshot.snapshot_id,
            'benchmark_id': self.benchmark_data.benchmark_id,
            'excess_return': self.excess_return,
            'tracking_error': self.tracking_error,
            'information_ratio': self.information_ratio,
            'alpha': self.alpha,
            'beta': self.beta,
            'r_squared': self.r_squared,
            'upside_capture': self.upside_capture,
            'downside_capture': self.downside_capture,
            'relative_volatility': self.relative_volatility,
            'relative_max_drawdown': self.relative_max_drawdown,
            'selection_effect': self.selection_effect,
            'allocation_effect': self.allocation_effect,
            'interaction_effect': self.interaction_effect,
            'outperformance': self.outperformance,
            'risk_adjusted_outperformance': self.risk_adjusted_outperformance,
            'batting_average': self.batting_average,
            'comparison_score': self.calculate_comparison_score()
        }