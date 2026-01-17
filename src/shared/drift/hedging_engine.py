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
        """Execute a single hedge trade with intelligent execution and retry logic."""
        try:
            retry_count = 0
            last_error = None
            
            while retry_count < self._max_retries:
                try:
                    # Get current market data for intelligent execution
                    market_data = await self.market_data_manager.get_market_summary(trade.market)
                    current_price = float(market_data.get('mark_price', 0)) if market_data else trade.estimated_price
                    
                    if current_price <= 0:
                        raise ValueError(f"Invalid current price for {trade.market}: {current_price}")
                    
                    # Intelligent order type selection based on market conditions
                    order_type, limit_price = await self._select_optimal_order_type(
                        trade, current_price, market_data, retry_count
                    )
                    
                    # Market impact minimization - split large orders if needed
                    execution_chunks = await self._optimize_execution_size(
                        trade, current_price, market_data
                    )
                    
                    executed_chunks = []
                    total_fill_size = 0.0
                    total_cost = 0.0
                    
                    # Execute chunks with intelligent timing
                    for i, chunk in enumerate(execution_chunks):
                        chunk_result = await self._execute_trade_chunk(
                            chunk, trade, order_type, limit_price, retry_count, i
                        )
                        
                        if chunk_result['success']:
                            executed_chunks.append(chunk_result)
                            total_fill_size += chunk_result.get('fill_size', 0)
                            total_cost += chunk_result.get('cost', 0)
                        else:
                            # If any chunk fails, record the error but continue with others
                            self.logger.warning(f"Chunk {i+1}/{len(execution_chunks)} failed: {chunk_result.get('error')}")
                    
                    # Check if execution was successful overall
                    if executed_chunks and total_fill_size >= trade.size * 0.8:  # 80% fill threshold
                        # Calculate weighted average fill price
                        total_value = sum(chunk.get('fill_price', 0) * chunk.get('fill_size', 0) for chunk in executed_chunks)
                        avg_fill_price = total_value / total_fill_size if total_fill_size > 0 else limit_price
                        
                        return {
                            'success': True,
                            'trade': trade,
                            'order_ids': [chunk.get('order_id') for chunk in executed_chunks if chunk.get('order_id')],
                            'fill_price': avg_fill_price,
                            'fill_size': total_fill_size,
                            'cost': total_cost,
                            'retry_count': retry_count,
                            'execution_method': order_type,
                            'chunks_executed': len(executed_chunks),
                            'total_chunks': len(execution_chunks)
                        }
                    else:
                        last_error = f"Insufficient fill: {total_fill_size:.4f}/{trade.size:.4f}"
                        retry_count += 1
                        
                        if retry_count < self._max_retries:
                            # Adaptive backoff based on market conditions
                            backoff_time = await self._calculate_adaptive_backoff(retry_count, market_data)
                            await asyncio.sleep(backoff_time)
                
                except Exception as e:
                    last_error = str(e)
                    retry_count += 1
                    
                    if retry_count < self._max_retries:
                        backoff_time = await self._calculate_adaptive_backoff(retry_count, None)
                        await asyncio.sleep(backoff_time)
            
            return {
                'success': False,
                'trade': trade,
                'error': last_error or 'Max retries exceeded',
                'retry_count': retry_count,
                'execution_method': 'failed'
            }
            
        except Exception as e:
            return {
                'success': False,
                'trade': trade,
                'error': str(e),
                'retry_count': 0,
                'execution_method': 'error'
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

    # =========================================================================
    # INTELLIGENT EXECUTION METHODS
    # =========================================================================

    async def _select_optimal_order_type(
        self,
        trade: HedgeTrade,
        current_price: float,
        market_data: Dict[str, Any],
        retry_count: int
    ) -> Tuple[str, float]:
        """
        Select optimal order type and price based on market conditions.
        
        Args:
            trade: HedgeTrade specification
            current_price: Current market price
            market_data: Market data summary
            retry_count: Current retry attempt
            
        Returns:
            Tuple of (order_type, limit_price)
        """
        try:
            # Get market depth information if available
            bid_price = float(market_data.get('bid_price', current_price * 0.999))
            ask_price = float(market_data.get('ask_price', current_price * 1.001))
            spread = ask_price - bid_price
            spread_pct = spread / current_price if current_price > 0 else 0.01
            
            # Get volume information if available
            volume_24h = float(market_data.get('volume_24h', 1000000))  # Default 1M volume
            
            # Determine urgency based on delta deviation and retry count
            urgency_factor = min(1.0, retry_count * 0.3 + 0.1)  # Increases with retries
            
            # Calculate trade size relative to daily volume
            trade_value = trade.size * current_price
            volume_impact = trade_value / volume_24h if volume_24h > 0 else 0.01
            
            # Order type selection logic
            if urgency_factor > 0.7 or volume_impact > 0.05:
                # High urgency or large trade - use market order with limit protection
                order_type = "market_with_protection"
                if trade.side == "buy":
                    limit_price = current_price * (1 + min(trade.max_slippage, 0.02))  # Max 2% slippage
                else:
                    limit_price = current_price * (1 - min(trade.max_slippage, 0.02))
                    
            elif spread_pct < 0.001:  # Very tight spread (< 0.1%)
                # Tight spread - try to get better execution with limit order
                order_type = "limit_aggressive"
                if trade.side == "buy":
                    limit_price = bid_price + spread * 0.3  # Slightly aggressive
                else:
                    limit_price = ask_price - spread * 0.3
                    
            elif spread_pct > 0.01:  # Wide spread (> 1%)
                # Wide spread - be more conservative
                order_type = "limit_conservative"
                if trade.side == "buy":
                    limit_price = bid_price + spread * 0.1  # Conservative
                else:
                    limit_price = ask_price - spread * 0.1
                    
            else:
                # Normal conditions - balanced approach
                order_type = "limit_balanced"
                if trade.side == "buy":
                    limit_price = current_price * (1 + trade.max_slippage * 0.5)
                else:
                    limit_price = current_price * (1 - trade.max_slippage * 0.5)
            
            self.logger.debug(f"Selected {order_type} for {trade.market} {trade.side} {trade.size:.4f} at {limit_price:.4f}")
            return order_type, limit_price
            
        except Exception as e:
            self.logger.error(f"Error selecting order type: {e}")
            # Fallback to simple limit order
            if trade.side == "buy":
                limit_price = current_price * (1 + trade.max_slippage)
            else:
                limit_price = current_price * (1 - trade.max_slippage)
            return "limit_fallback", limit_price

    async def _optimize_execution_size(
        self,
        trade: HedgeTrade,
        current_price: float,
        market_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Optimize execution by splitting large trades to minimize market impact.
        
        Args:
            trade: HedgeTrade specification
            current_price: Current market price
            market_data: Market data summary
            
        Returns:
            List of trade chunks for execution
        """
        try:
            trade_value = trade.size * current_price
            volume_24h = float(market_data.get('volume_24h', 1000000))
            
            # Calculate optimal chunk size based on market impact models
            # Using square root law: impact ∝ sqrt(trade_size / daily_volume)
            volume_impact = trade_value / volume_24h if volume_24h > 0 else 0.01
            
            # Determine if splitting is beneficial
            if volume_impact < 0.01:  # Less than 1% of daily volume
                # Small trade - execute as single chunk
                return [{
                    'size': trade.size,
                    'delay_seconds': 0,
                    'chunk_id': 1,
                    'total_chunks': 1
                }]
            
            elif volume_impact < 0.05:  # 1-5% of daily volume
                # Medium trade - split into 2-3 chunks
                num_chunks = 2 if volume_impact < 0.03 else 3
                chunk_size = trade.size / num_chunks
                
                chunks = []
                for i in range(num_chunks):
                    chunks.append({
                        'size': chunk_size,
                        'delay_seconds': i * 30,  # 30 second delays between chunks
                        'chunk_id': i + 1,
                        'total_chunks': num_chunks
                    })
                return chunks
            
            else:  # Large trade - more aggressive splitting
                # Calculate optimal number of chunks (max 5 for practical reasons)
                optimal_chunks = min(5, max(3, int(volume_impact * 20)))
                chunk_size = trade.size / optimal_chunks
                
                chunks = []
                for i in range(optimal_chunks):
                    # Progressive delays - longer delays for later chunks
                    delay = i * (60 + i * 15)  # 60s, 75s, 90s, 105s, 120s
                    
                    chunks.append({
                        'size': chunk_size,
                        'delay_seconds': delay,
                        'chunk_id': i + 1,
                        'total_chunks': optimal_chunks
                    })
                return chunks
            
        except Exception as e:
            self.logger.error(f"Error optimizing execution size: {e}")
            # Fallback to single chunk
            return [{
                'size': trade.size,
                'delay_seconds': 0,
                'chunk_id': 1,
                'total_chunks': 1
            }]

    async def _execute_trade_chunk(
        self,
        chunk: Dict[str, Any],
        trade: HedgeTrade,
        order_type: str,
        limit_price: float,
        retry_count: int,
        chunk_index: int
    ) -> Dict[str, Any]:
        """
        Execute a single trade chunk with intelligent timing.
        
        Args:
            chunk: Chunk specification
            trade: Original HedgeTrade specification
            order_type: Selected order type
            limit_price: Calculated limit price
            retry_count: Current retry count
            chunk_index: Index of this chunk
            
        Returns:
            Chunk execution result
        """
        try:
            # Apply delay for market impact minimization
            if chunk['delay_seconds'] > 0 and chunk_index > 0:
                self.logger.debug(f"Delaying chunk {chunk['chunk_id']}/{chunk['total_chunks']} by {chunk['delay_seconds']}s")
                await asyncio.sleep(chunk['delay_seconds'])
            
            # Determine order parameters based on order type
            post_only = order_type in ["limit_conservative", "limit_balanced"]
            reduce_only = False  # Hedging trades are not reduce-only
            
            # Execute the chunk
            order_result = await self.trading_manager.place_limit_order(
                market=trade.market,
                side=trade.side,
                amount=chunk['size'],
                price=limit_price,
                reduce_only=reduce_only,
                post_only=post_only
            )
            
            if order_result and order_result.get('success'):
                # Calculate actual cost
                fill_price = order_result.get('fill_price', limit_price)
                fill_size = order_result.get('fill_size', chunk['size'])
                
                # Estimate fees based on order type
                if post_only and order_result.get('maker_fill', False):
                    fee_rate = 0.001  # 0.1% maker fee
                else:
                    fee_rate = 0.002  # 0.2% taker fee
                
                cost = fill_size * fill_price * fee_rate
                
                return {
                    'success': True,
                    'chunk_id': chunk['chunk_id'],
                    'order_id': order_result.get('order_id'),
                    'fill_price': fill_price,
                    'fill_size': fill_size,
                    'cost': cost,
                    'order_type': order_type,
                    'maker_fill': order_result.get('maker_fill', False)
                }
            else:
                return {
                    'success': False,
                    'chunk_id': chunk['chunk_id'],
                    'error': order_result.get('error', 'Order placement failed'),
                    'order_type': order_type
                }
                
        except Exception as e:
            return {
                'success': False,
                'chunk_id': chunk['chunk_id'],
                'error': str(e),
                'order_type': order_type
            }

    async def _calculate_adaptive_backoff(
        self,
        retry_count: int,
        market_data: Optional[Dict[str, Any]]
    ) -> float:
        """
        Calculate adaptive backoff time based on market conditions and retry count.
        
        Args:
            retry_count: Current retry attempt
            market_data: Market data for adaptive timing (optional)
            
        Returns:
            Backoff time in seconds
        """
        try:
            # Base exponential backoff
            base_backoff = min(60, 2 ** retry_count)  # Cap at 60 seconds
            
            if market_data:
                # Adjust based on market conditions
                spread_pct = 0.001  # Default spread
                
                bid_price = float(market_data.get('bid_price', 0))
                ask_price = float(market_data.get('ask_price', 0))
                
                if bid_price > 0 and ask_price > 0:
                    spread_pct = (ask_price - bid_price) / ((ask_price + bid_price) / 2)
                
                # Wider spreads suggest less liquidity - wait longer
                spread_multiplier = 1.0 + min(2.0, spread_pct * 100)  # 1.0 to 3.0
                
                # Volume-based adjustment
                volume_24h = float(market_data.get('volume_24h', 1000000))
                if volume_24h < 100000:  # Low volume
                    volume_multiplier = 1.5
                elif volume_24h > 10000000:  # High volume
                    volume_multiplier = 0.7
                else:
                    volume_multiplier = 1.0
                
                adaptive_backoff = base_backoff * spread_multiplier * volume_multiplier
            else:
                adaptive_backoff = base_backoff
            
            # Add small random jitter to avoid thundering herd
            import random
            jitter = random.uniform(0.8, 1.2)
            
            final_backoff = adaptive_backoff * jitter
            
            self.logger.debug(f"Adaptive backoff: {final_backoff:.1f}s (retry {retry_count})")
            return final_backoff
            
        except Exception as e:
            self.logger.error(f"Error calculating adaptive backoff: {e}")
            return min(60, 2 ** retry_count)  # Fallback to simple exponential backoff