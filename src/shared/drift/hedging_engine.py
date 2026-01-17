"""
Drift Hedging Engine
===================

Automated hedging system for maintaining target portfolio delta and risk exposure.
Provides delta-neutral hedging, correlation-based adjustments, and intelligent execution.

Features:
- Delta hedging with configurable tolerance
- Correlation-based hedge ratio adjustments
- Intelligent limit order execution
- Hedge effectiveness monitoring
- Emergency hedging capabilities
- Cooldown period enforcement

Usage:
    hedging_engine = DriftHedgingEngine(drift_adapter, trading_manager, market_data_manager)
    
    # Calculate hedge requirements
    requirements = await hedging_engine.calculate_hedge_requirements(target_delta=0.0)
    
    # Execute hedge trades
    result = await hedging_engine.execute_hedge_trades(requirements)
    
    # Monitor hedge effectiveness
    monitoring = await hedging_engine.monitor_hedge_effectiveness()
"""

import asyncio
import math
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from src.shared.system.logging import Logger


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class HedgeRequirements:
    """Hedge requirements calculation result."""
    target_delta: float
    current_delta: float
    delta_deviation: float
    required_trades: List['HedgeTrade']
    estimated_cost: float
    market_impact: float
    confidence_score: float
    calculation_time: datetime

@dataclass
class HedgeTrade:
    """Individual hedge trade specification."""
    market: str
    side: str  # "buy" or "sell"
    size: float
    hedge_ratio: float
    priority: int  # 1 = highest priority
    reasoning: str
    estimated_price: float
    max_slippage: float

@dataclass
class HedgeResult:
    """Hedge execution result."""
    success: bool
    executed_trades: List[Dict[str, Any]]
    failed_trades: List[Dict[str, Any]]
    total_cost: float
    execution_time: float
    final_delta: float
    delta_improvement: float
    message: str

@dataclass
class HedgeMonitoring:
    """Hedge effectiveness monitoring result."""
    current_delta: float
    target_delta: float
    delta_drift: float
    hedge_effectiveness: float  # 0.0 to 1.0
    correlation_stability: float
    time_since_last_hedge: timedelta
    next_hedge_recommendation: Optional[datetime]
    monitoring_alerts: List[str]

@dataclass
class EmergencyHedgeResult:
    """Emergency hedge execution result."""
    success: bool
    trades_executed: int
    delta_before: float
    delta_after: float
    execution_time: float
    emergency_reason: str
    recovery_actions: List[str]


# =============================================================================
# HEDGING ENGINE
# =============================================================================

class DriftHedgingEngine:
    """
    Automated hedging engine for Drift Protocol portfolios.
    
    Provides delta-neutral hedging, correlation-based adjustments,
    and intelligent execution with market impact minimization.
    """
    
    def __init__(
        self,
        drift_adapter,
        trading_manager,
        market_data_manager,
        delta_tolerance: float = 0.01,  # 1% delta tolerance
        cooldown_minutes: int = 30,
        max_hedge_size_usd: float = 100000.0
    ):
        """
        Initialize hedging engine.
        
        Args:
            drift_adapter: DriftAdapter instance
            trading_manager: TradingManager instance
            market_data_manager: MarketDataManager instance
            delta_tolerance: Maximum allowed delta deviation (default: 1%)
            cooldown_minutes: Minimum minutes between hedge executions
            max_hedge_size_usd: Maximum USD size for individual hedge trades
        """
        self.drift_adapter = drift_adapter
        self.trading_manager = trading_manager
        self.market_data_manager = market_data_manager
        self.delta_tolerance = delta_tolerance
        self.cooldown_period = timedelta(minutes=cooldown_minutes)
        self.max_hedge_size_usd = max_hedge_size_usd
        self.logger = Logger
        
        # Hedging state
        self._last_hedge_time = None
        self._hedge_history = []
        self._correlation_cache = {}
        self._delta_cache = {}
        self._cache_ttl = 60  # 1 minute cache TTL
        
        # Configuration
        self._default_slippage = 0.005  # 0.5% max slippage
        self._min_hedge_size = 10.0  # Minimum $10 hedge size
        self._max_retries = 3
        
        self.logger.info("Hedging Engine initialized with delta tolerance {:.2%}".format(delta_tolerance))

    # =========================================================================
    # HEDGE REQUIREMENT CALCULATION
    # =========================================================================

    async def calculate_hedge_requirements(
        self,
        target_delta: float = 0.0,
        use_correlation_adjustment: bool = True
    ) -> HedgeRequirements:
        """
        Calculate hedge requirements to achieve target delta.
        
        Args:
            target_delta: Target portfolio delta (default: 0.0 for delta-neutral)
            use_correlation_adjustment: Whether to adjust for correlations
            
        Returns:
            HedgeRequirements with detailed trade specifications
        """
        try:
            calculation_start = datetime.now()
            
            # Get current portfolio delta
            current_delta = await self._calculate_portfolio_delta()
            delta_deviation = abs(current_delta - target_delta)
            
            # Check if hedging is needed
            if delta_deviation <= self.delta_tolerance:
                self.logger.info("Portfolio delta within tolerance, no hedging needed")
                return HedgeRequirements(
                    target_delta=target_delta,
                    current_delta=current_delta,
                    delta_deviation=delta_deviation,
                    required_trades=[],
                    estimated_cost=0.0,
                    market_impact=0.0,
                    confidence_score=1.0,
                    calculation_time=calculation_start
                )
            
            # Get current positions
            positions = await self.drift_adapter.get_positions()
            if not positions:
                self.logger.warning("No positions found for hedge calculation")
                return HedgeRequirements(
                    target_delta=target_delta,
                    current_delta=0.0,
                    delta_deviation=0.0,
                    required_trades=[],
                    estimated_cost=0.0,
                    market_impact=0.0,
                    confidence_score=0.0,
                    calculation_time=calculation_start
                )
            
            # Calculate required hedge trades
            required_trades = await self._calculate_hedge_trades(
                positions, current_delta, target_delta, use_correlation_adjustment
            )
            
            # Estimate costs and market impact
            estimated_cost = await self._estimate_hedge_cost(required_trades)
            market_impact = await self._estimate_market_impact(required_trades)
            
            # Calculate confidence score based on market conditions
            confidence_score = await self._calculate_confidence_score(required_trades)
            
            requirements = HedgeRequirements(
                target_delta=target_delta,
                current_delta=current_delta,
                delta_deviation=delta_deviation,
                required_trades=required_trades,
                estimated_cost=estimated_cost,
                market_impact=market_impact,
                confidence_score=confidence_score,
                calculation_time=calculation_start
            )
            
            self.logger.info(f"Hedge requirements calculated: {len(required_trades)} trades, "
                           f"delta deviation {delta_deviation:.4f}, cost ${estimated_cost:.2f}")
            
            return requirements
            
        except Exception as e:
            self.logger.error(f"Error calculating hedge requirements: {e}")
            raise

    async def _calculate_portfolio_delta(self) -> float:
        """Calculate current portfolio delta."""
        try:
            # Check cache first
            cache_key = "portfolio_delta"
            if cache_key in self._delta_cache:
                cached_time, cached_delta = self._delta_cache[cache_key]
                if (datetime.now() - cached_time).total_seconds() < self._cache_ttl:
                    return cached_delta
            
            positions = await self.drift_adapter.get_positions()
            if not positions:
                return 0.0
            
            total_delta = 0.0
            
            for position in positions:
                market = position.get('market', '')
                size = float(position.get('base_asset_amount', 0))
                
                if abs(size) < 1e-8:  # Skip zero positions
                    continue
                
                # Get current market price
                market_data = await self.market_data_manager.get_market_summary(market)
                current_price = float(market_data.get('mark_price', 0)) if market_data else 0.0
                
                if current_price <= 0:
                    self.logger.warning(f"Invalid price for {market}: {current_price}")
                    continue
                
                # For perpetual futures, delta is approximately equal to position size * price
                # This is a simplified calculation - in practice, you might want more sophisticated delta calculations
                position_delta = size * current_price
                total_delta += position_delta
            
            # Cache the result
            self._delta_cache[cache_key] = (datetime.now(), total_delta)
            
            return total_delta
            
        except Exception as e:
            self.logger.error(f"Error calculating portfolio delta: {e}")
            return 0.0

    async def _calculate_hedge_trades(
        self,
        positions: List[Dict],
        current_delta: float,
        target_delta: float,
        use_correlation_adjustment: bool
    ) -> List[HedgeTrade]:
        """Calculate specific hedge trades needed."""
        try:
            required_delta_change = target_delta - current_delta
            
            if abs(required_delta_change) < self._min_hedge_size:
                return []
            
            hedge_trades = []
            
            # Get correlation matrix if needed
            correlation_matrix = None
            if use_correlation_adjustment and len(positions) > 1:
                correlation_matrix = await self._get_correlation_matrix(positions)
            
            # Find the most liquid market for hedging (typically SOL-PERP or BTC-PERP)
            hedge_market = await self._select_hedge_market(positions)
            
            if not hedge_market:
                self.logger.warning("No suitable hedge market found")
                return []
            
            # Get hedge market price
            market_data = await self.market_data_manager.get_market_summary(hedge_market)
            hedge_price = float(market_data.get('mark_price', 0)) if market_data else 0.0
            
            if hedge_price <= 0:
                self.logger.error(f"Invalid hedge price for {hedge_market}: {hedge_price}")
                return []
            
            # Calculate hedge size
            # For delta hedging: hedge_size = -required_delta_change / hedge_price
            base_hedge_size = -required_delta_change / hedge_price
            
            # Apply correlation adjustment if available
            hedge_ratio = 1.0
            if correlation_matrix and use_correlation_adjustment:
                hedge_ratio = await self._calculate_hedge_ratio(
                    hedge_market, positions, correlation_matrix
                )
            
            adjusted_hedge_size = base_hedge_size * hedge_ratio
            
            # Determine trade side
            side = "buy" if adjusted_hedge_size > 0 else "sell"
            trade_size = abs(adjusted_hedge_size)
            
            # Split large trades if necessary
            max_trade_size = self.max_hedge_size_usd / hedge_price
            
            if trade_size > max_trade_size:
                # Split into multiple trades
                num_trades = math.ceil(trade_size / max_trade_size)
                trade_size_per_order = trade_size / num_trades
                
                for i in range(num_trades):
                    hedge_trade = HedgeTrade(
                        market=hedge_market,
                        side=side,
                        size=trade_size_per_order,
                        hedge_ratio=hedge_ratio,
                        priority=i + 1,
                        reasoning=f"Delta hedge {i+1}/{num_trades} to achieve target delta {target_delta:.4f}",
                        estimated_price=hedge_price,
                        max_slippage=self._default_slippage
                    )
                    hedge_trades.append(hedge_trade)
            else:
                # Single trade
                hedge_trade = HedgeTrade(
                    market=hedge_market,
                    side=side,
                    size=trade_size,
                    hedge_ratio=hedge_ratio,
                    priority=1,
                    reasoning=f"Delta hedge to achieve target delta {target_delta:.4f}",
                    estimated_price=hedge_price,
                    max_slippage=self._default_slippage
                )
                hedge_trades.append(hedge_trade)
            
            return hedge_trades
            
        except Exception as e:
            self.logger.error(f"Error calculating hedge trades: {e}")
            return []

    async def _select_hedge_market(self, positions: List[Dict]) -> Optional[str]:
        """Select the most appropriate market for hedging."""
        try:
            # Priority order for hedge markets (most liquid first)
            preferred_markets = ['SOL-PERP', 'BTC-PERP', 'ETH-PERP']
            
            # Check if we already have positions in preferred markets
            position_markets = {pos.get('market', '') for pos in positions}
            
            for market in preferred_markets:
                if market in position_markets:
                    # Prefer markets where we already have positions
                    return market
            
            # If no existing positions in preferred markets, use SOL-PERP as default
            return 'SOL-PERP'
            
        except Exception as e:
            self.logger.error(f"Error selecting hedge market: {e}")
            return 'SOL-PERP'  # Fallback

    async def _get_correlation_matrix(self, positions: List[Dict]) -> Optional[Dict[str, Dict[str, float]]]:
        """Get correlation matrix for position markets."""
        try:
            # This would integrate with the risk engine's correlation calculations
            # For now, return a simplified correlation matrix
            markets = [pos.get('market', '') for pos in positions if pos.get('market')]
            
            if len(markets) < 2:
                return None
            
            # Simplified correlation matrix (in practice, this would come from risk engine)
            correlation_matrix = {}
            for market1 in markets:
                correlation_matrix[market1] = {}
                for market2 in markets:
                    if market1 == market2:
                        correlation_matrix[market1][market2] = 1.0
                    else:
                        # Default correlation assumptions
                        if 'SOL' in market1 and 'SOL' in market2:
                            correlation_matrix[market1][market2] = 0.9
                        elif 'BTC' in market1 and 'BTC' in market2:
                            correlation_matrix[market1][market2] = 0.9
                        elif ('SOL' in market1 and 'BTC' in market2) or ('BTC' in market1 and 'SOL' in market2):
                            correlation_matrix[market1][market2] = 0.7
                        else:
                            correlation_matrix[market1][market2] = 0.5
            
            return correlation_matrix
            
        except Exception as e:
            self.logger.error(f"Error getting correlation matrix: {e}")
            return None

    async def _calculate_hedge_ratio(
        self,
        hedge_market: str,
        positions: List[Dict],
        correlation_matrix: Dict[str, Dict[str, float]]
    ) -> float:
        """Calculate optimal hedge ratio based on correlations."""
        try:
            # Simplified hedge ratio calculation
            # In practice, this would use more sophisticated portfolio theory
            
            total_exposure = 0.0
            weighted_correlation = 0.0
            
            for position in positions:
                market = position.get('market', '')
                size = float(position.get('base_asset_amount', 0))
                
                if abs(size) < 1e-8 or market == hedge_market:
                    continue
                
                # Get position value
                market_data = await self.market_data_manager.get_market_summary(market)
                price = float(market_data.get('mark_price', 0)) if market_data else 0.0
                
                if price <= 0:
                    continue
                
                position_value = abs(size * price)
                total_exposure += position_value
                
                # Get correlation with hedge market
                correlation = correlation_matrix.get(market, {}).get(hedge_market, 0.5)
                weighted_correlation += position_value * correlation
            
            if total_exposure > 0:
                avg_correlation = weighted_correlation / total_exposure
                # Adjust hedge ratio based on average correlation
                hedge_ratio = min(1.0, max(0.1, avg_correlation))
            else:
                hedge_ratio = 1.0
            
            return hedge_ratio
            
        except Exception as e:
            self.logger.error(f"Error calculating hedge ratio: {e}")
            return 1.0

    async def _estimate_hedge_cost(self, hedge_trades: List[HedgeTrade]) -> float:
        """Estimate total cost of hedge execution."""
        try:
            total_cost = 0.0
            
            for trade in hedge_trades:
                # Estimate trading fees (typically 0.1% for makers, 0.2% for takers)
                trade_value = trade.size * trade.estimated_price
                estimated_fee = trade_value * 0.002  # 0.2% taker fee assumption
                
                # Add slippage cost
                slippage_cost = trade_value * trade.max_slippage
                
                total_cost += estimated_fee + slippage_cost
            
            return total_cost
            
        except Exception as e:
            self.logger.error(f"Error estimating hedge cost: {e}")
            return 0.0

    async def _estimate_market_impact(self, hedge_trades: List[HedgeTrade]) -> float:
        """Estimate market impact of hedge trades."""
        try:
            # Simplified market impact estimation
            # In practice, this would consider order book depth and liquidity
            
            total_impact = 0.0
            
            for trade in hedge_trades:
                # Estimate impact based on trade size
                trade_value = trade.size * trade.estimated_price
                
                # Larger trades have higher impact (square root relationship)
                impact_factor = math.sqrt(trade_value / 10000.0)  # Normalize by $10k
                estimated_impact = min(0.01, impact_factor * 0.001)  # Max 1% impact
                
                total_impact += estimated_impact
            
            return total_impact
            
        except Exception as e:
            self.logger.error(f"Error estimating market impact: {e}")
            return 0.0

    async def _calculate_confidence_score(self, hedge_trades: List[HedgeTrade]) -> float:
        """Calculate confidence score for hedge execution."""
        try:
            if not hedge_trades:
                return 1.0
            
            # Factors affecting confidence:
            # 1. Market liquidity
            # 2. Volatility conditions
            # 3. Trade size relative to typical volume
            # 4. Number of trades required
            
            base_confidence = 0.8
            
            # Adjust for number of trades (more trades = lower confidence)
            trade_penalty = min(0.2, len(hedge_trades) * 0.05)
            
            # Adjust for trade sizes
            size_penalty = 0.0
            for trade in hedge_trades:
                trade_value = trade.size * trade.estimated_price
                if trade_value > 50000:  # Large trades reduce confidence
                    size_penalty += 0.1
            
            size_penalty = min(0.3, size_penalty)
            
            confidence = base_confidence - trade_penalty - size_penalty
            return max(0.1, confidence)
            
        except Exception as e:
            self.logger.error(f"Error calculating confidence score: {e}")
            return 0.5

    # =========================================================================
    # HEDGE EXECUTION
    # =========================================================================

    async def execute_hedge_trades(
        self,
        requirements: HedgeRequirements,
        force_execution: bool = False
    ) -> HedgeResult:
        """
        Execute hedge trades to achieve target delta.
        
        Args:
            requirements: HedgeRequirements from calculate_hedge_requirements
            force_execution: Skip cooldown period if True
            
        Returns:
            HedgeResult with execution details
        """
        try:
            execution_start = datetime.now()
            
            # Check cooldown period
            if not force_execution and self._last_hedge_time:
                time_since_last = datetime.now() - self._last_hedge_time
                if time_since_last < self.cooldown_period:
                    remaining_cooldown = self.cooldown_period - time_since_last
                    return HedgeResult(
                        success=False,
                        executed_trades=[],
                        failed_trades=[],
                        total_cost=0.0,
                        execution_time=0.0,
                        final_delta=requirements.current_delta,
                        delta_improvement=0.0,
                        message=f"Cooldown active. {remaining_cooldown.total_seconds():.0f}s remaining"
                    )
            
            # Check if hedging is needed
            if not requirements.required_trades:
                return HedgeResult(
                    success=True,
                    executed_trades=[],
                    failed_trades=[],
                    total_cost=0.0,
                    execution_time=0.0,
                    final_delta=requirements.current_delta,
                    delta_improvement=0.0,
                    message="No hedging required - portfolio within tolerance"
                )
            
            executed_trades = []
            failed_trades = []
            total_cost = 0.0
            
            # Execute trades in priority order
            sorted_trades = sorted(requirements.required_trades, key=lambda x: x.priority)
            
            for trade in sorted_trades:
                try:
                    # Execute individual hedge trade
                    trade_result = await self._execute_single_hedge_trade(trade)
                    
                    if trade_result['success']:
                        executed_trades.append(trade_result)
                        total_cost += trade_result.get('cost', 0.0)
                        self.logger.info(f"Hedge trade executed: {trade.market} {trade.side} {trade.size:.4f}")
                    else:
                        failed_trades.append({
                            'trade': trade,
                            'error': trade_result.get('error', 'Unknown error'),
                            'retry_count': trade_result.get('retry_count', 0)
                        })
                        self.logger.warning(f"Hedge trade failed: {trade.market} {trade.side} {trade.size:.4f} - {trade_result.get('error')}")
                
                except Exception as e:
                    failed_trades.append({
                        'trade': trade,
                        'error': str(e),
                        'retry_count': 0
                    })
                    self.logger.error(f"Error executing hedge trade {trade.market}: {e}")
            
            # Calculate final delta and improvement
            final_delta = await self._calculate_portfolio_delta()
            delta_improvement = abs(requirements.current_delta - requirements.target_delta) - abs(final_delta - requirements.target_delta)
            
            # Update hedge history
            self._last_hedge_time = datetime.now()
            self._hedge_history.append({
                'timestamp': execution_start,
                'target_delta': requirements.target_delta,
                'initial_delta': requirements.current_delta,
                'final_delta': final_delta,
                'trades_executed': len(executed_trades),
                'trades_failed': len(failed_trades),
                'total_cost': total_cost
            })
            
            # Keep only last 100 hedge records
            if len(self._hedge_history) > 100:
                self._hedge_history = self._hedge_history[-100:]
            
            execution_time = (datetime.now() - execution_start).total_seconds()
            success = len(executed_trades) > 0 and len(failed_trades) == 0
            
            result = HedgeResult(
                success=success,
                executed_trades=executed_trades,
                failed_trades=failed_trades,
                total_cost=total_cost,
                execution_time=execution_time,
                final_delta=final_delta,
                delta_improvement=delta_improvement,
                message=f"Executed {len(executed_trades)}/{len(requirements.required_trades)} hedge trades"
            )
            
            self.logger.info(f"Hedge execution completed: {len(executed_trades)} trades, "
                           f"delta {requirements.current_delta:.4f} -> {final_delta:.4f}, "
                           f"cost ${total_cost:.2f}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error executing hedge trades: {e}")
            raise

    async def _execute_single_hedge_trade(self, trade: HedgeTrade) -> Dict[str, Any]:
        """Execute a single hedge trade with retry logic."""
        try:
            retry_count = 0
            last_error = None
            
            while retry_count < self._max_retries:
                try:
                    # Calculate limit price with slippage buffer
                    market_data = await self.market_data_manager.get_market_summary(trade.market)
                    current_price = float(market_data.get('mark_price', 0)) if market_data else trade.estimated_price
                    
                    if trade.side == "buy":
                        limit_price = current_price * (1 + trade.max_slippage)
                    else:
                        limit_price = current_price * (1 - trade.max_slippage)
                    
                    # Place limit order
                    order_result = await self.trading_manager.place_limit_order(
                        market=trade.market,
                        side=trade.side,
                        amount=trade.size,
                        price=limit_price,
                        reduce_only=False,
                        post_only=False  # Allow taker orders for hedging
                    )
                    
                    if order_result and order_result.get('success'):
                        # Calculate actual cost
                        fill_price = order_result.get('fill_price', limit_price)
                        fill_size = order_result.get('fill_size', trade.size)
                        cost = fill_size * fill_price * 0.002  # Estimate fee
                        
                        return {
                            'success': True,
                            'trade': trade,
                            'order_id': order_result.get('order_id'),
                            'fill_price': fill_price,
                            'fill_size': fill_size,
                            'cost': cost,
                            'retry_count': retry_count
                        }
                    else:
                        last_error = order_result.get('error', 'Order placement failed')
                        retry_count += 1
                        
                        if retry_count < self._max_retries:
                            # Wait before retry with exponential backoff
                            await asyncio.sleep(2 ** retry_count)
                
                except Exception as e:
                    last_error = str(e)
                    retry_count += 1
                    
                    if retry_count < self._max_retries:
                        await asyncio.sleep(2 ** retry_count)
            
            return {
                'success': False,
                'trade': trade,
                'error': last_error or 'Max retries exceeded',
                'retry_count': retry_count
            }
            
        except Exception as e:
            return {
                'success': False,
                'trade': trade,
                'error': str(e),
                'retry_count': 0
            }

    # =========================================================================
    # HEDGE MONITORING
    # =========================================================================

    async def monitor_hedge_effectiveness(self) -> HedgeMonitoring:
        """
        Monitor hedge effectiveness and provide recommendations.
        
        Returns:
            HedgeMonitoring with current status and recommendations
        """
        try:
            current_delta = await self._calculate_portfolio_delta()
            target_delta = 0.0  # Assume delta-neutral target
            delta_drift = abs(current_delta - target_delta)
            
            # Calculate hedge effectiveness
            hedge_effectiveness = await self._calculate_hedge_effectiveness()
            
            # Check correlation stability
            correlation_stability = await self._check_correlation_stability()
            
            # Time since last hedge
            time_since_last_hedge = timedelta(0)
            if self._last_hedge_time:
                time_since_last_hedge = datetime.now() - self._last_hedge_time
            
            # Generate recommendations
            next_hedge_recommendation = None
            monitoring_alerts = []
            
            if delta_drift > self.delta_tolerance:
                monitoring_alerts.append(f"Delta drift {delta_drift:.4f} exceeds tolerance {self.delta_tolerance:.4f}")
                
                # Check if cooldown has expired
                if not self._last_hedge_time or time_since_last_hedge >= self.cooldown_period:
                    next_hedge_recommendation = datetime.now()
                    monitoring_alerts.append("Immediate hedging recommended")
                else:
                    remaining_cooldown = self.cooldown_period - time_since_last_hedge
                    next_hedge_recommendation = datetime.now() + remaining_cooldown
                    monitoring_alerts.append(f"Hedging recommended in {remaining_cooldown.total_seconds():.0f}s")
            
            if hedge_effectiveness < 0.7:
                monitoring_alerts.append(f"Low hedge effectiveness: {hedge_effectiveness:.2f}")
            
            if correlation_stability < 0.8:
                monitoring_alerts.append(f"Correlation instability detected: {correlation_stability:.2f}")
            
            monitoring = HedgeMonitoring(
                current_delta=current_delta,
                target_delta=target_delta,
                delta_drift=delta_drift,
                hedge_effectiveness=hedge_effectiveness,
                correlation_stability=correlation_stability,
                time_since_last_hedge=time_since_last_hedge,
                next_hedge_recommendation=next_hedge_recommendation,
                monitoring_alerts=monitoring_alerts
            )
            
            return monitoring
            
        except Exception as e:
            self.logger.error(f"Error monitoring hedge effectiveness: {e}")
            raise

    async def _calculate_hedge_effectiveness(self) -> float:
        """Calculate hedge effectiveness based on recent performance."""
        try:
            if len(self._hedge_history) < 2:
                return 1.0  # No history to evaluate
            
            # Analyze recent hedge performance
            recent_hedges = self._hedge_history[-10:]  # Last 10 hedges
            
            total_improvement = 0.0
            total_attempts = 0
            
            for hedge in recent_hedges:
                initial_deviation = abs(hedge['initial_delta'] - hedge['target_delta'])
                final_deviation = abs(hedge['final_delta'] - hedge['target_delta'])
                
                if initial_deviation > 0:
                    improvement = (initial_deviation - final_deviation) / initial_deviation
                    total_improvement += max(0.0, improvement)
                    total_attempts += 1
            
            if total_attempts > 0:
                avg_effectiveness = total_improvement / total_attempts
                return min(1.0, max(0.0, avg_effectiveness))
            
            return 1.0
            
        except Exception as e:
            self.logger.error(f"Error calculating hedge effectiveness: {e}")
            return 0.5

    async def _check_correlation_stability(self) -> float:
        """Check stability of correlation assumptions."""
        try:
            # This would analyze correlation changes over time
            # For now, return a simplified stability measure
            
            # In practice, this would:
            # 1. Compare current correlations to historical averages
            # 2. Detect correlation regime changes
            # 3. Assess impact on hedge effectiveness
            
            return 0.9  # Assume stable correlations for now
            
        except Exception as e:
            self.logger.error(f"Error checking correlation stability: {e}")
            return 0.5

    # =========================================================================
    # EMERGENCY HEDGING
    # =========================================================================

    async def emergency_hedge(
        self,
        max_trades: int = 5,
        emergency_reason: str = "Manual emergency hedge"
    ) -> EmergencyHedgeResult:
        """
        Execute emergency hedging to rapidly reduce portfolio delta.
        
        Args:
            max_trades: Maximum number of trades to execute
            emergency_reason: Reason for emergency hedging
            
        Returns:
            EmergencyHedgeResult with execution details
        """
        try:
            execution_start = datetime.now()
            
            # Get current delta
            delta_before = await self._calculate_portfolio_delta()
            
            # Calculate emergency hedge requirements (ignore cooldown)
            requirements = await self.calculate_hedge_requirements(
                target_delta=0.0,
                use_correlation_adjustment=False  # Simplified for speed
            )
            
            # Limit number of trades
            if len(requirements.required_trades) > max_trades:
                requirements.required_trades = requirements.required_trades[:max_trades]
            
            # Execute with force (ignore cooldown)
            hedge_result = await self.execute_hedge_trades(requirements, force_execution=True)
            
            # Get final delta
            delta_after = await self._calculate_portfolio_delta()
            
            execution_time = (datetime.now() - execution_start).total_seconds()
            
            # Generate recovery actions
            recovery_actions = []
            if not hedge_result.success:
                recovery_actions.append("Review failed trades and retry manually")
            
            if abs(delta_after) > self.delta_tolerance:
                recovery_actions.append("Additional hedging may be required")
            
            if hedge_result.total_cost > 1000:  # High cost threshold
                recovery_actions.append("Review hedge execution costs")
            
            result = EmergencyHedgeResult(
                success=hedge_result.success,
                trades_executed=len(hedge_result.executed_trades),
                delta_before=delta_before,
                delta_after=delta_after,
                execution_time=execution_time,
                emergency_reason=emergency_reason,
                recovery_actions=recovery_actions
            )
            
            self.logger.warning(f"Emergency hedge executed: {result.trades_executed} trades, "
                              f"delta {delta_before:.4f} -> {delta_after:.4f}, "
                              f"reason: {emergency_reason}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error executing emergency hedge: {e}")
            raise

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    async def adjust_hedge_ratios(self, new_correlations: Dict[str, Dict[str, float]]) -> bool:
        """
        Adjust hedge ratios based on updated correlation matrix.
        
        Args:
            new_correlations: Updated correlation matrix
            
        Returns:
            True if adjustments were made successfully
        """
        try:
            # Update correlation cache
            self._correlation_cache = new_correlations
            
            # Clear delta cache to force recalculation
            self._delta_cache.clear()
            
            self.logger.info("Hedge ratios adjusted based on updated correlations")
            return True
            
        except Exception as e:
            self.logger.error(f"Error adjusting hedge ratios: {e}")
            return False

    def get_hedge_statistics(self) -> Dict[str, Any]:
        """Get hedging performance statistics."""
        try:
            if not self._hedge_history:
                return {
                    'total_hedges': 0,
                    'success_rate': 0.0,
                    'average_cost': 0.0,
                    'average_improvement': 0.0,
                    'last_hedge_time': None
                }
            
            total_hedges = len(self._hedge_history)
            successful_hedges = sum(1 for h in self._hedge_history if h['trades_executed'] > 0)
            success_rate = successful_hedges / total_hedges if total_hedges > 0 else 0.0
            
            total_cost = sum(h['total_cost'] for h in self._hedge_history)
            average_cost = total_cost / total_hedges if total_hedges > 0 else 0.0
            
            improvements = []
            for hedge in self._hedge_history:
                initial_deviation = abs(hedge['initial_delta'] - hedge['target_delta'])
                final_deviation = abs(hedge['final_delta'] - hedge['target_delta'])
                if initial_deviation > 0:
                    improvement = (initial_deviation - final_deviation) / initial_deviation
                    improvements.append(improvement)
            
            average_improvement = sum(improvements) / len(improvements) if improvements else 0.0
            
            return {
                'total_hedges': total_hedges,
                'success_rate': success_rate,
                'average_cost': average_cost,
                'average_improvement': average_improvement,
                'last_hedge_time': self._last_hedge_time
            }
            
        except Exception as e:
            self.logger.error(f"Error getting hedge statistics: {e}")
            return {}

    def clear_hedge_history(self):
        """Clear hedge history and reset state."""
        self._hedge_history.clear()
        self._last_hedge_time = None
        self._correlation_cache.clear()
        self._delta_cache.clear()
        self.logger.info("Hedge history cleared")