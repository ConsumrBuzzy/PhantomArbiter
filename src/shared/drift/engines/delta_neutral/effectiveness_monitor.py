"""
Hedge Effectiveness Monitor
==========================

Monitors and analyzes the effectiveness of delta hedging strategies.
Provides real-time feedback on hedge performance and recommendations.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean, stdev
import math

from ...sdk.models.portfolio import PortfolioState
from ...sdk.models.trading import TradeResult
from ...sdk.math.correlation_calculator import CorrelationCalculator
from ...sdk.math.performance_calculator import PerformanceCalculator
from ...sdk.data.market_data_provider import MarketDataProvider
from ...sdk.data.portfolio_data_provider import PortfolioDataProvider
from src.shared.system.logging import Logger


@dataclass
class HedgeEffectivenessResult:
    """Hedge effectiveness analysis result."""
    
    # Overall effectiveness metrics
    effectiveness_score: float  # 0-1 score (1 = perfect hedge)
    hedge_ratio_stability: float  # How stable the hedge ratio has been
    delta_reduction_achieved: float  # Actual delta reduction vs target
    
    # Performance metrics
    tracking_error: float  # Standard deviation of hedge errors
    correlation_with_underlying: float  # Correlation between hedge and underlying
    hedge_cost_efficiency: float  # Cost per unit of risk reduction
    
    # Timing and execution
    average_hedge_delay: float  # Average time from signal to execution (ms)
    execution_quality_score: float  # Quality of hedge executions
    
    # Risk metrics
    residual_risk: float  # Remaining unhedged risk
    basis_risk: float  # Risk from hedge instrument vs underlying mismatch
    
    # Recommendations
    recommended_adjustments: List[str]  # Suggested improvements
    next_rebalance_time: Optional[datetime]  # When to next rebalance
    
    # Metadata
    analysis_period_days: int
    calculation_time: datetime
    confidence_level: float


@dataclass
class HedgePerformanceMetrics:
    """Detailed hedge performance metrics."""
    
    # Delta tracking
    target_delta_history: List[float]
    actual_delta_history: List[float]
    delta_error_history: List[float]
    
    # Hedge ratios
    hedge_ratio_history: List[float]
    optimal_hedge_ratios: List[float]  # Theoretical optimal ratios
    
    # Costs and PnL
    hedge_costs: List[float]
    hedge_pnl: List[float]
    net_hedge_benefit: List[float]  # Risk reduction minus costs
    
    # Execution metrics
    execution_delays: List[float]  # Time delays in milliseconds
    slippage_costs: List[float]
    market_impact_costs: List[float]
    
    # Timestamps
    timestamps: List[datetime]


class EffectivenessMonitor:
    """
    Monitors hedge effectiveness and provides performance analytics.
    
    Analyzes how well the delta hedging strategy is working and provides
    recommendations for improvements.
    """
    
    def __init__(
        self,
        market_data_provider: MarketDataProvider,
        portfolio_data_provider: PortfolioDataProvider
    ):
        """
        Initialize effectiveness monitor.
        
        Args:
            market_data_provider: Market data provider instance
            portfolio_data_provider: Portfolio data provider instance
        """
        self.market_data = market_data_provider
        self.portfolio_data = portfolio_data_provider
        self.logger = Logger
        
        # Performance tracking
        self._performance_history = []
        self._hedge_history = []
        self._effectiveness_cache = {}
        
        # Configuration
        self._analysis_window_days = 30  # Default analysis window
        self._min_observations = 10  # Minimum observations for analysis
        self._target_effectiveness = 0.8  # Target effectiveness score
        
        self.logger.info("Hedge Effectiveness Monitor initialized")
    
    async def analyze_hedge_effectiveness(
        self,
        analysis_days: int = 30,
        confidence_level: float = 0.95
    ) -> HedgeEffectivenessResult:
        """
        Analyze hedge effectiveness over specified period.
        
        Args:
            analysis_days: Number of days to analyze
            confidence_level: Confidence level for statistical tests
            
        Returns:
            Comprehensive hedge effectiveness analysis
        """
        try:
            self.logger.info(f"Analyzing hedge effectiveness over {analysis_days} days")
            
            # Get performance metrics
            performance_metrics = await self._collect_performance_metrics(analysis_days)
            
            if not performance_metrics or len(performance_metrics.timestamps) < self._min_observations:
                self.logger.warning("Insufficient data for hedge effectiveness analysis")
                return self._empty_effectiveness_result(analysis_days)
            
            # Calculate effectiveness score
            effectiveness_score = await self._calculate_effectiveness_score(performance_metrics)
            
            # Analyze hedge ratio stability
            hedge_ratio_stability = self._analyze_hedge_ratio_stability(performance_metrics)
            
            # Calculate delta reduction achieved
            delta_reduction = self._calculate_delta_reduction(performance_metrics)
            
            # Calculate tracking error
            tracking_error = self._calculate_tracking_error(performance_metrics)
            
            # Analyze correlation with underlying
            correlation = await self._analyze_hedge_correlation(performance_metrics, analysis_days)
            
            # Calculate cost efficiency
            cost_efficiency = self._calculate_cost_efficiency(performance_metrics)
            
            # Analyze execution quality
            execution_quality = self._analyze_execution_quality(performance_metrics)
            avg_delay = mean(performance_metrics.execution_delays) if performance_metrics.execution_delays else 0.0
            
            # Calculate residual and basis risk
            residual_risk = self._calculate_residual_risk(performance_metrics)
            basis_risk = await self._calculate_basis_risk(performance_metrics, analysis_days)
            
            # Generate recommendations
            recommendations = await self._generate_recommendations(
                effectiveness_score, performance_metrics
            )
            
            # Determine next rebalance time
            next_rebalance = self._calculate_next_rebalance_time(performance_metrics)
            
            result = HedgeEffectivenessResult(
                effectiveness_score=effectiveness_score,
                hedge_ratio_stability=hedge_ratio_stability,
                delta_reduction_achieved=delta_reduction,
                tracking_error=tracking_error,
                correlation_with_underlying=correlation,
                hedge_cost_efficiency=cost_efficiency,
                average_hedge_delay=avg_delay,
                execution_quality_score=execution_quality,
                residual_risk=residual_risk,
                basis_risk=basis_risk,
                recommended_adjustments=recommendations,
                next_rebalance_time=next_rebalance,
                analysis_period_days=analysis_days,
                calculation_time=datetime.now(),
                confidence_level=confidence_level
            )
            
            self.logger.info(f"Hedge effectiveness analysis complete: score={effectiveness_score:.3f}")
            return result
            
        except Exception as e:
            self.logger.error(f"Error analyzing hedge effectiveness: {e}")
            return self._empty_effectiveness_result(analysis_days)
    
    async def monitor_real_time_effectiveness(self) -> Dict[str, Any]:
        """
        Monitor real-time hedge effectiveness.
        
        Returns:
            Dictionary with current effectiveness metrics
        """
        try:
            # Get current portfolio state
            portfolio_state = await self.portfolio_data.get_portfolio_state()
            if not portfolio_state:
                return {}
            
            # Get recent performance data (last 24 hours)
            recent_metrics = await self._collect_performance_metrics(1)
            
            # Calculate current delta
            current_delta = portfolio_state.get_portfolio_delta()
            
            # Get recent hedge trades
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=24)
            recent_trades = await self.portfolio_data.get_trade_history(start_time, end_time)
            hedge_trades = [t for t in recent_trades if 'hedge' in t.engine_name.lower() if hasattr(t, 'engine_name')]
            
            # Calculate real-time metrics
            monitoring_data = {
                'current_delta': current_delta,
                'target_delta': 0.0,  # Assuming delta-neutral target
                'delta_deviation': abs(current_delta),
                'recent_hedge_trades': len(hedge_trades),
                'last_hedge_time': max([t.execution_end for t in hedge_trades]) if hedge_trades else None,
                'portfolio_value': portfolio_state.total_value,
                'health_ratio': portfolio_state.health_ratio,
                'leverage': portfolio_state.leverage,
                'timestamp': datetime.now().isoformat()
            }
            
            # Add effectiveness indicators if we have recent data
            if recent_metrics and len(recent_metrics.timestamps) > 0:
                monitoring_data.update({
                    'recent_tracking_error': self._calculate_tracking_error(recent_metrics),
                    'recent_hedge_cost': sum(recent_metrics.hedge_costs) if recent_metrics.hedge_costs else 0.0,
                    'recent_execution_quality': self._analyze_execution_quality(recent_metrics)
                })
            
            return monitoring_data
            
        except Exception as e:
            self.logger.error(f"Error monitoring real-time effectiveness: {e}")
            return {}
    
    async def _collect_performance_metrics(self, days: int) -> Optional[HedgePerformanceMetrics]:
        """Collect hedge performance metrics over specified period."""
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)
            
            # Get trade history
            trades = await self.portfolio_data.get_trade_history(start_time, end_time)
            hedge_trades = [t for t in trades if self._is_hedge_trade(t)]
            
            if not hedge_trades:
                return None
            
            # Get portfolio value history
            value_history = await self.portfolio_data.get_portfolio_value_history(
                start_time, end_time, "1h"
            )
            
            # Initialize metrics
            metrics = HedgePerformanceMetrics(
                target_delta_history=[],
                actual_delta_history=[],
                delta_error_history=[],
                hedge_ratio_history=[],
                optimal_hedge_ratios=[],
                hedge_costs=[],
                hedge_pnl=[],
                net_hedge_benefit=[],
                execution_delays=[],
                slippage_costs=[],
                market_impact_costs=[],
                timestamps=[]
            )
            
            # Process hedge trades
            for trade in hedge_trades:
                metrics.timestamps.append(trade.execution_end)
                metrics.hedge_costs.append(trade.total_fees)
                metrics.hedge_pnl.append(trade.estimated_pnl)
                
                # Calculate execution delay
                if hasattr(trade, 'signal_time') and trade.signal_time:
                    delay_ms = trade.signal_to_execution_delay_ms
                    metrics.execution_delays.append(delay_ms)
                
                # Add slippage and market impact
                metrics.slippage_costs.append(abs(trade.slippage) * trade.notional_value)
                metrics.market_impact_costs.append(trade.market_impact_bps / 10000 * trade.notional_value)
                
                # Estimate hedge ratio (simplified)
                hedge_ratio = self._estimate_hedge_ratio_from_trade(trade)
                metrics.hedge_ratio_history.append(hedge_ratio)
            
            # Calculate delta history from portfolio values
            for value_point in value_history:
                # This is simplified - in practice would calculate actual delta
                estimated_delta = value_point.get('estimated_delta', 0.0)
                metrics.actual_delta_history.append(estimated_delta)
                metrics.target_delta_history.append(0.0)  # Assuming delta-neutral target
                metrics.delta_error_history.append(abs(estimated_delta))
            
            # Calculate net hedge benefit
            for i in range(len(metrics.hedge_costs)):
                cost = metrics.hedge_costs[i]
                pnl = metrics.hedge_pnl[i] if i < len(metrics.hedge_pnl) else 0.0
                # Simplified benefit calculation
                risk_reduction_value = cost * 2  # Assume hedge reduces risk worth 2x the cost
                net_benefit = risk_reduction_value - cost + pnl
                metrics.net_hedge_benefit.append(net_benefit)
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"Error collecting performance metrics: {e}")
            return None
    
    async def _calculate_effectiveness_score(self, metrics: HedgePerformanceMetrics) -> float:
        """Calculate overall hedge effectiveness score."""
        try:
            if not metrics.delta_error_history:
                return 0.0
            
            # Component scores (each 0-1)
            scores = []
            
            # 1. Delta tracking accuracy (40% weight)
            avg_delta_error = mean(metrics.delta_error_history)
            max_acceptable_error = 0.05  # 5% of portfolio value
            delta_score = max(0.0, 1.0 - (avg_delta_error / max_acceptable_error))
            scores.append(('delta_tracking', delta_score, 0.4))
            
            # 2. Hedge ratio stability (20% weight)
            if len(metrics.hedge_ratio_history) > 1:
                ratio_volatility = stdev(metrics.hedge_ratio_history)
                stability_score = max(0.0, 1.0 - (ratio_volatility * 2))  # Penalize high volatility
                scores.append(('ratio_stability', stability_score, 0.2))
            
            # 3. Cost efficiency (20% weight)
            if metrics.hedge_costs and metrics.net_hedge_benefit:
                total_costs = sum(metrics.hedge_costs)
                total_benefits = sum(metrics.net_hedge_benefit)
                if total_costs > 0:
                    cost_efficiency = min(1.0, total_benefits / total_costs)
                    scores.append(('cost_efficiency', max(0.0, cost_efficiency), 0.2))
            
            # 4. Execution quality (20% weight)
            if metrics.execution_delays:
                avg_delay = mean(metrics.execution_delays)
                max_acceptable_delay = 5000  # 5 seconds
                execution_score = max(0.0, 1.0 - (avg_delay / max_acceptable_delay))
                scores.append(('execution_quality', execution_score, 0.2))
            
            # Calculate weighted average
            if not scores:
                return 0.0
            
            total_weight = sum(weight for _, _, weight in scores)
            weighted_score = sum(score * weight for _, score, weight in scores) / total_weight
            
            return min(1.0, max(0.0, weighted_score))
            
        except Exception as e:
            self.logger.error(f"Error calculating effectiveness score: {e}")
            return 0.0
    
    def _analyze_hedge_ratio_stability(self, metrics: HedgePerformanceMetrics) -> float:
        """Analyze stability of hedge ratios over time."""
        try:
            if len(metrics.hedge_ratio_history) < 2:
                return 1.0  # Perfect stability if only one observation
            
            # Calculate coefficient of variation
            mean_ratio = mean(metrics.hedge_ratio_history)
            if mean_ratio == 0:
                return 0.0
            
            ratio_std = stdev(metrics.hedge_ratio_history)
            coefficient_of_variation = ratio_std / abs(mean_ratio)
            
            # Convert to stability score (lower CV = higher stability)
            stability = max(0.0, 1.0 - coefficient_of_variation)
            
            return min(1.0, stability)
            
        except Exception as e:
            self.logger.error(f"Error analyzing hedge ratio stability: {e}")
            return 0.0
    
    def _calculate_delta_reduction(self, metrics: HedgePerformanceMetrics) -> float:
        """Calculate how much delta reduction was achieved."""
        try:
            if not metrics.delta_error_history:
                return 0.0
            
            # Compare delta errors before and after hedging
            # This is simplified - in practice would need pre-hedge delta measurements
            
            initial_errors = metrics.delta_error_history[:len(metrics.delta_error_history)//2]
            final_errors = metrics.delta_error_history[len(metrics.delta_error_history)//2:]
            
            if not initial_errors or not final_errors:
                return 0.0
            
            initial_avg = mean(initial_errors)
            final_avg = mean(final_errors)
            
            if initial_avg == 0:
                return 1.0 if final_avg == 0 else 0.0
            
            reduction = (initial_avg - final_avg) / initial_avg
            return max(0.0, min(1.0, reduction))
            
        except Exception as e:
            self.logger.error(f"Error calculating delta reduction: {e}")
            return 0.0
    
    def _calculate_tracking_error(self, metrics: HedgePerformanceMetrics) -> float:
        """Calculate tracking error of hedge performance."""
        try:
            if not metrics.delta_error_history:
                return 0.0
            
            # Standard deviation of delta errors
            tracking_error = stdev(metrics.delta_error_history) if len(metrics.delta_error_history) > 1 else 0.0
            
            # Annualize assuming daily observations
            annualized_tracking_error = tracking_error * math.sqrt(252)
            
            return annualized_tracking_error
            
        except Exception as e:
            self.logger.error(f"Error calculating tracking error: {e}")
            return 0.0
    
    async def _analyze_hedge_correlation(self, metrics: HedgePerformanceMetrics, days: int) -> float:
        """Analyze correlation between hedge and underlying positions."""
        try:
            # Get portfolio returns
            portfolio_returns = await self.portfolio_data.get_portfolio_returns(days)
            
            # Get hedge PnL as returns
            if not metrics.hedge_pnl or len(portfolio_returns) < 2:
                return 0.0
            
            # Align hedge PnL with portfolio returns (simplified)
            hedge_returns = []
            for pnl in metrics.hedge_pnl:
                # Convert PnL to return (simplified)
                hedge_return = pnl / 100000  # Normalize by assumed portfolio size
                hedge_returns.append(hedge_return)
            
            # Take minimum length
            min_length = min(len(portfolio_returns), len(hedge_returns))
            if min_length < 2:
                return 0.0
            
            portfolio_subset = portfolio_returns[:min_length]
            hedge_subset = hedge_returns[:min_length]
            
            # Calculate correlation
            correlation = CorrelationCalculator.pearson_correlation(portfolio_subset, hedge_subset)
            
            # For hedging, we want negative correlation (hedge moves opposite to portfolio)
            hedge_correlation = -correlation  # Flip sign for hedge effectiveness
            
            return max(-1.0, min(1.0, hedge_correlation))
            
        except Exception as e:
            self.logger.error(f"Error analyzing hedge correlation: {e}")
            return 0.0
    
    def _calculate_cost_efficiency(self, metrics: HedgePerformanceMetrics) -> float:
        """Calculate cost efficiency of hedging strategy."""
        try:
            if not metrics.hedge_costs or not metrics.net_hedge_benefit:
                return 0.0
            
            total_costs = sum(metrics.hedge_costs)
            total_benefits = sum(metrics.net_hedge_benefit)
            
            if total_costs == 0:
                return 1.0 if total_benefits >= 0 else 0.0
            
            # Cost efficiency = benefits / costs
            efficiency = total_benefits / total_costs
            
            # Normalize to 0-1 scale (efficiency > 1 is capped at 1)
            return max(0.0, min(1.0, efficiency))
            
        except Exception as e:
            self.logger.error(f"Error calculating cost efficiency: {e}")
            return 0.0
    
    def _analyze_execution_quality(self, metrics: HedgePerformanceMetrics) -> float:
        """Analyze quality of hedge executions."""
        try:
            if not metrics.execution_delays:
                return 1.0
            
            # Component scores
            scores = []
            
            # 1. Speed score (based on execution delays)
            avg_delay = mean(metrics.execution_delays)
            max_acceptable_delay = 5000  # 5 seconds
            speed_score = max(0.0, 1.0 - (avg_delay / max_acceptable_delay))
            scores.append(speed_score)
            
            # 2. Consistency score (based on delay variance)
            if len(metrics.execution_delays) > 1:
                delay_std = stdev(metrics.execution_delays)
                consistency_score = max(0.0, 1.0 - (delay_std / max_acceptable_delay))
                scores.append(consistency_score)
            
            # 3. Cost score (based on slippage and market impact)
            if metrics.slippage_costs:
                avg_slippage_cost = mean(metrics.slippage_costs)
                # Normalize by typical trade size
                typical_trade_size = 10000  # $10k
                slippage_ratio = avg_slippage_cost / typical_trade_size
                cost_score = max(0.0, 1.0 - slippage_ratio * 10)  # Penalize high slippage
                scores.append(cost_score)
            
            # Average all component scores
            return mean(scores) if scores else 1.0
            
        except Exception as e:
            self.logger.error(f"Error analyzing execution quality: {e}")
            return 0.0
    
    def _calculate_residual_risk(self, metrics: HedgePerformanceMetrics) -> float:
        """Calculate remaining unhedged risk."""
        try:
            if not metrics.delta_error_history:
                return 1.0  # Maximum risk if no data
            
            # Use recent delta errors as proxy for residual risk
            recent_errors = metrics.delta_error_history[-10:] if len(metrics.delta_error_history) >= 10 else metrics.delta_error_history
            
            # Calculate average absolute error
            avg_residual_risk = mean(recent_errors)
            
            # Normalize to 0-1 scale (5% error = 1.0 risk)
            max_acceptable_risk = 0.05
            normalized_risk = min(1.0, avg_residual_risk / max_acceptable_risk)
            
            return normalized_risk
            
        except Exception as e:
            self.logger.error(f"Error calculating residual risk: {e}")
            return 1.0
    
    async def _calculate_basis_risk(self, metrics: HedgePerformanceMetrics, days: int) -> float:
        """Calculate basis risk from hedge instrument mismatch."""
        try:
            # This would require correlation analysis between hedge instruments and underlying
            # Simplified implementation
            
            if not metrics.hedge_ratio_history:
                return 0.5  # Moderate basis risk assumption
            
            # Analyze hedge ratio stability as proxy for basis risk
            if len(metrics.hedge_ratio_history) > 1:
                ratio_volatility = stdev(metrics.hedge_ratio_history)
                # Higher volatility in hedge ratios suggests higher basis risk
                basis_risk = min(1.0, ratio_volatility * 2)
                return basis_risk
            
            return 0.3  # Default moderate basis risk
            
        except Exception as e:
            self.logger.error(f"Error calculating basis risk: {e}")
            return 0.5
    
    async def _generate_recommendations(
        self, 
        effectiveness_score: float, 
        metrics: HedgePerformanceMetrics
    ) -> List[str]:
        """Generate recommendations for improving hedge effectiveness."""
        recommendations = []
        
        try:
            # Low effectiveness score
            if effectiveness_score < 0.6:
                recommendations.append("Overall hedge effectiveness is low - consider reviewing hedge strategy")
            
            # High tracking error
            if metrics.delta_error_history:
                avg_error = mean(metrics.delta_error_history)
                if avg_error > 0.03:  # >3% average error
                    recommendations.append("High tracking error detected - consider more frequent rebalancing")
            
            # Execution delays
            if metrics.execution_delays:
                avg_delay = mean(metrics.execution_delays)
                if avg_delay > 3000:  # >3 seconds
                    recommendations.append("Execution delays are high - optimize order routing and sizing")
            
            # High costs
            if metrics.hedge_costs and metrics.net_hedge_benefit:
                total_costs = sum(metrics.hedge_costs)
                total_benefits = sum(metrics.net_hedge_benefit)
                if total_costs > 0 and total_benefits / total_costs < 0.5:
                    recommendations.append("Hedge costs are high relative to benefits - review cost efficiency")
            
            # Unstable hedge ratios
            if len(metrics.hedge_ratio_history) > 1:
                ratio_volatility = stdev(metrics.hedge_ratio_history)
                if ratio_volatility > 0.2:
                    recommendations.append("Hedge ratios are unstable - consider dynamic ratio adjustment")
            
            # Add positive recommendations for good performance
            if effectiveness_score > 0.8:
                recommendations.append("Hedge effectiveness is excellent - maintain current strategy")
            
            return recommendations
            
        except Exception as e:
            self.logger.error(f"Error generating recommendations: {e}")
            return ["Unable to generate recommendations due to analysis error"]
    
    def _calculate_next_rebalance_time(self, metrics: HedgePerformanceMetrics) -> Optional[datetime]:
        """Calculate when the next hedge rebalance should occur."""
        try:
            if not metrics.timestamps:
                return None
            
            # Analyze rebalancing frequency
            if len(metrics.timestamps) > 1:
                # Calculate average time between hedges
                time_diffs = []
                for i in range(1, len(metrics.timestamps)):
                    diff = (metrics.timestamps[i] - metrics.timestamps[i-1]).total_seconds()
                    time_diffs.append(diff)
                
                avg_interval = mean(time_diffs) if time_diffs else 3600  # Default 1 hour
                
                # Suggest next rebalance based on recent activity and effectiveness
                last_hedge_time = max(metrics.timestamps)
                next_rebalance = last_hedge_time + timedelta(seconds=avg_interval)
                
                return next_rebalance
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error calculating next rebalance time: {e}")
            return None
    
    def _is_hedge_trade(self, trade: TradeResult) -> bool:
        """Determine if a trade is a hedge trade."""
        # Check if trade has hedge-related metadata
        if hasattr(trade, 'engine_name') and trade.engine_name:
            return 'hedge' in trade.engine_name.lower()
        
        # Check signal type if available
        if hasattr(trade, 'signal_id') and trade.signal_id:
            return 'hedge' in trade.signal_id.lower()
        
        # Default to false
        return False
    
    def _estimate_hedge_ratio_from_trade(self, trade: TradeResult) -> float:
        """Estimate hedge ratio from trade characteristics."""
        # This is simplified - in practice would use more sophisticated calculation
        # Based on trade size relative to portfolio
        
        if trade.notional_value == 0:
            return 1.0
        
        # Assume hedge ratio is proportional to trade size
        # This would need actual portfolio delta and target delta for accurate calculation
        estimated_ratio = min(2.0, max(0.1, trade.executed_size / 1000))  # Normalize by 1000
        
        return estimated_ratio
    
    def _empty_effectiveness_result(self, analysis_days: int) -> HedgeEffectivenessResult:
        """Return empty effectiveness result for error cases."""
        return HedgeEffectivenessResult(
            effectiveness_score=0.0,
            hedge_ratio_stability=0.0,
            delta_reduction_achieved=0.0,
            tracking_error=0.0,
            correlation_with_underlying=0.0,
            hedge_cost_efficiency=0.0,
            average_hedge_delay=0.0,
            execution_quality_score=0.0,
            residual_risk=1.0,
            basis_risk=0.5,
            recommended_adjustments=["Insufficient data for analysis"],
            next_rebalance_time=None,
            analysis_period_days=analysis_days,
            calculation_time=datetime.now(),
            confidence_level=0.95
        )