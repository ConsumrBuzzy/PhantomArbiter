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
        """Calculate optimal hedge ratio based on correlations and portfolio theory."""
        try:
            # Enhanced hedge ratio calculation using portfolio theory
            
            total_exposure = 0.0
            weighted_correlation = 0.0
            correlation_variance = 0.0
            position_data = []
            
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
                
                # Store position data for advanced calculations
                position_data.append({
                    'market': market,
                    'value': position_value,
                    'correlation': correlation,
                    'size': size
                })
                
                weighted_correlation += position_value * correlation
                correlation_variance += position_value * (correlation ** 2)
            
            if total_exposure == 0 or not position_data:
                return 1.0
            
            # Calculate base hedge ratio (value-weighted average correlation)
            avg_correlation = weighted_correlation / total_exposure
            
            # Enhanced hedge ratio calculation considering:
            # 1. Correlation stability
            # 2. Portfolio concentration
            # 3. Market volatility relationships
            
            # 1. Correlation stability adjustment
            correlation_stability = await self._assess_correlation_stability(
                hedge_market, position_data
            )
            stability_adjustment = 0.8 + (0.4 * correlation_stability)  # 0.8 to 1.2 range
            
            # 2. Portfolio concentration adjustment
            concentration_risk = await self._calculate_concentration_risk(position_data, total_exposure)
            concentration_adjustment = 1.0 + (0.2 * concentration_risk)  # Up to 20% increase for concentrated portfolios
            
            # 3. Volatility relationship adjustment
            volatility_adjustment = await self._calculate_volatility_adjustment(
                hedge_market, position_data
            )
            
            # Combine adjustments
            base_hedge_ratio = abs(avg_correlation)
            adjusted_hedge_ratio = (
                base_hedge_ratio * 
                stability_adjustment * 
                concentration_adjustment * 
                volatility_adjustment
            )
            
            # Ensure hedge ratio is within reasonable bounds
            final_hedge_ratio = min(1.5, max(0.1, adjusted_hedge_ratio))
            
            self.logger.debug(
                f"Hedge ratio calculation for {hedge_market}: "
                f"base={base_hedge_ratio:.3f}, "
                f"stability_adj={stability_adjustment:.3f}, "
                f"concentration_adj={concentration_adjustment:.3f}, "
                f"volatility_adj={volatility_adjustment:.3f}, "
                f"final={final_hedge_ratio:.3f}"
            )
            
            return final_hedge_ratio
            
        except Exception as e:
            self.logger.error(f"Error calculating hedge ratio: {e}")
            return 1.0

    async def _assess_correlation_stability(
        self, 
        hedge_market: str, 
        position_data: List[Dict]
    ) -> float:
        """
        Assess correlation stability for hedge ratio adjustment.
        
        Returns:
            Stability score between 0.0 (unstable) and 1.0 (stable)
        """
        try:
            # Check if we have correlation history
            if not hasattr(self, '_correlation_history'):
                return 0.8  # Default moderate stability
            
            if len(getattr(self, '_correlation_history', [])) < 3:
                return 0.8  # Insufficient history
            
            stability_scores = []
            
            for pos_data in position_data:
                market = pos_data['market']
                
                # Get recent correlation values for this market pair
                recent_correlations = []
                for hist in self._correlation_history[-5:]:  # Last 5 periods
                    if market in hist.get('matrix', {}) and hedge_market in hist['matrix'][market]:
                        recent_correlations.append(hist['matrix'][market][hedge_market])
                
                if len(recent_correlations) >= 3:
                    # Calculate correlation volatility
                    from statistics import stdev
                    corr_volatility = stdev(recent_correlations)
                    
                    # Convert to stability score (lower volatility = higher stability)
                    stability = max(0.0, 1.0 - (corr_volatility * 5))  # Scale volatility
                    stability_scores.append(stability)
            
            if stability_scores:
                # Weight by position value
                total_value = sum(pos['value'] for pos in position_data)
                weighted_stability = sum(
                    score * pos['value'] / total_value 
                    for score, pos in zip(stability_scores, position_data)
                )
                return weighted_stability
            
            return 0.8  # Default
            
        except Exception as e:
            self.logger.error(f"Error assessing correlation stability: {e}")
            return 0.8

    async def _calculate_concentration_risk(
        self, 
        position_data: List[Dict], 
        total_exposure: float
    ) -> float:
        """
        Calculate portfolio concentration risk.
        
        Returns:
            Concentration risk score between 0.0 (diversified) and 1.0 (concentrated)
        """
        try:
            if not position_data or total_exposure <= 0:
                return 0.0
            
            # Calculate Herfindahl-Hirschman Index (HHI) for concentration
            hhi = sum((pos['value'] / total_exposure) ** 2 for pos in position_data)
            
            # Convert HHI to concentration risk score
            # HHI ranges from 1/n (diversified) to 1 (concentrated)
            # For 10 equal positions: HHI = 0.1, for 1 position: HHI = 1.0
            n_positions = len(position_data)
            min_hhi = 1.0 / n_positions if n_positions > 0 else 1.0
            
            # Normalize to 0-1 scale
            concentration_risk = (hhi - min_hhi) / (1.0 - min_hhi) if min_hhi < 1.0 else 0.0
            
            return min(1.0, max(0.0, concentration_risk))
            
        except Exception as e:
            self.logger.error(f"Error calculating concentration risk: {e}")
            return 0.0

    async def _calculate_volatility_adjustment(
        self, 
        hedge_market: str, 
        position_data: List[Dict]
    ) -> float:
        """
        Calculate volatility-based hedge ratio adjustment.
        
        Returns:
            Volatility adjustment factor (typically 0.8 to 1.2)
        """
        try:
            # Get hedge market volatility
            hedge_returns = await self._get_asset_returns(hedge_market, 30)
            if len(hedge_returns) < 10:
                return 1.0
            
            from statistics import stdev
            hedge_volatility = stdev(hedge_returns) * (252 ** 0.5)  # Annualized
            
            # Calculate portfolio-weighted average volatility
            total_value = sum(pos['value'] for pos in position_data)
            weighted_volatility = 0.0
            
            for pos_data in position_data:
                market = pos_data['market']
                weight = pos_data['value'] / total_value if total_value > 0 else 0
                
                # Get market volatility
                market_returns = await self._get_asset_returns(market, 30)
                if len(market_returns) >= 10:
                    market_volatility = stdev(market_returns) * (252 ** 0.5)
                    weighted_volatility += weight * market_volatility
            
            if weighted_volatility <= 0 or hedge_volatility <= 0:
                return 1.0
            
            # Volatility ratio adjustment
            # If portfolio is more volatile than hedge market, increase hedge ratio
            volatility_ratio = weighted_volatility / hedge_volatility
            
            # Convert to adjustment factor (bounded between 0.8 and 1.2)
            adjustment = 0.9 + (0.1 * min(2.0, max(0.5, volatility_ratio)))
            
            return adjustment
            
        except Exception as e:
            self.logger.error(f"Error calculating volatility adjustment: {e}")
            return 1.0

    async def _get_asset_returns(self, asset: str, days: int) -> List[float]:
        """Get historical returns for an asset (simplified implementation)."""
        import random
        
        # Use asset-specific seed for consistent results
        asset_seed = hash(asset) % 1000000
        random.seed(asset_seed)
        
        returns = []
        for _ in range(days):
            if 'SOL' in asset:
                ret = random.gauss(0.001, 0.05)
            elif 'BTC' in asset:
                ret = random.gauss(0.0008, 0.03)
            elif 'ETH' in asset:
                ret = random.gauss(0.0009, 0.04)
            else:
                ret = random.gauss(0.0005, 0.035)
            
            returns.append(ret)
        
        return returns

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
        """Check stability of correlation assumptions with enhanced analysis."""
        try:
            # Enhanced correlation stability check
            if not hasattr(self, '_correlation_history'):
                return 0.9  # Assume stable if no history
            
            correlation_history = getattr(self, '_correlation_history', [])
            if len(correlation_history) < 3:
                return 0.9  # Insufficient history
            
            # Analyze correlation stability across all pairs
            stability_scores = []
            
            # Get current positions to focus on relevant correlations
            positions = await self.drift_adapter.get_positions()
            if not positions:
                return 0.9
            
            position_markets = [pos.get('market', '') for pos in positions if pos.get('market')]
            hedge_markets = ['SOL-PERP', 'BTC-PERP', 'ETH-PERP']
            
            # Check stability for position-hedge market pairs
            for pos_market in position_markets:
                for hedge_market in hedge_markets:
                    if pos_market == hedge_market:
                        continue
                    
                    # Extract correlation time series
                    correlations = []
                    for hist in correlation_history[-10:]:  # Last 10 periods
                        matrix = hist.get('matrix', {})
                        if pos_market in matrix and hedge_market in matrix[pos_market]:
                            correlations.append(matrix[pos_market][hedge_market])
                    
                    if len(correlations) >= 3:
                        # Calculate stability metrics
                        from statistics import mean, stdev
                        
                        corr_mean = mean(correlations)
                        corr_std = stdev(correlations) if len(correlations) > 1 else 0.0
                        
                        # Stability score based on coefficient of variation
                        if abs(corr_mean) > 0.1:  # Avoid division by very small numbers
                            cv = corr_std / abs(corr_mean)
                            stability = max(0.0, 1.0 - cv)  # Lower CV = higher stability
                        else:
                            stability = 0.5  # Neutral for near-zero correlations
                        
                        stability_scores.append(stability)
            
            if stability_scores:
                overall_stability = sum(stability_scores) / len(stability_scores)
                
                # Apply additional checks for regime changes
                recent_regime_changes = await self._detect_recent_correlation_changes()
                if recent_regime_changes > 0:
                    # Reduce stability score if recent regime changes detected
                    regime_penalty = min(0.3, recent_regime_changes * 0.1)
                    overall_stability = max(0.1, overall_stability - regime_penalty)
                
                return overall_stability
            
            return 0.9  # Default stable assumption
            
        except Exception as e:
            self.logger.error(f"Error checking correlation stability: {e}")
            return 0.5

    async def _detect_recent_correlation_changes(self) -> int:
        """
        Detect recent correlation changes that might affect hedge effectiveness.
        
        Returns:
            Number of significant correlation changes in recent periods
        """
        try:
            if not hasattr(self, '_correlation_history'):
                return 0
            
            correlation_history = getattr(self, '_correlation_history', [])
            if len(correlation_history) < 2:
                return 0
            
            # Compare last 2 periods
            recent = correlation_history[-1].get('matrix', {})
            previous = correlation_history[-2].get('matrix', {})
            
            if not recent or not previous:
                return 0
            
            significant_changes = 0
            change_threshold = 0.2  # 20% correlation change threshold
            
            for asset1 in recent:
                if asset1 not in previous:
                    continue
                
                for asset2 in recent[asset1]:
                    if asset2 not in previous[asset1]:
                        continue
                    
                    if asset1 >= asset2:  # Avoid duplicates
                        continue
                    
                    recent_corr = recent[asset1][asset2]
                    previous_corr = previous[asset1][asset2]
                    change = abs(recent_corr - previous_corr)
                    
                    if change > change_threshold:
                        significant_changes += 1
            
            return significant_changes
            
        except Exception as e:
            self.logger.error(f"Error detecting recent correlation changes: {e}")
            return 0

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
            # Store previous correlations for comparison
            previous_correlations = self._correlation_cache.copy() if self._correlation_cache else {}
            
            # Update correlation cache
            self._correlation_cache = new_correlations
            
            # Clear delta cache to force recalculation
            self._delta_cache.clear()
            
            # Analyze correlation changes and their impact
            correlation_changes = await self._analyze_correlation_changes(
                previous_correlations, new_correlations
            )
            
            # Log significant changes
            if correlation_changes['significant_changes']:
                self.logger.warning(
                    f"Significant correlation changes detected: "
                    f"{len(correlation_changes['significant_changes'])} pairs affected, "
                    f"max change: {correlation_changes['max_change']:.3f}"
                )
                
                # Log details of significant changes
                for change in correlation_changes['significant_changes'][:5]:  # Log top 5
                    self.logger.info(
                        f"Correlation change: {change['pair']} "
                        f"{change['old_correlation']:.3f} -> {change['new_correlation']:.3f} "
                        f"(Δ{change['change']:.3f})"
                    )
            
            # Trigger hedge effectiveness recalculation if significant changes
            if correlation_changes['requires_hedge_adjustment']:
                self.logger.info("Correlation changes require hedge adjustment - clearing effectiveness cache")
                # Force recalculation of hedge effectiveness
                if hasattr(self, '_hedge_effectiveness_cache'):
                    delattr(self, '_hedge_effectiveness_cache')
            
            self.logger.info(
                f"Hedge ratios adjusted: {len(new_correlations)} assets, "
                f"{correlation_changes['total_pairs']} correlation pairs updated"
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Error adjusting hedge ratios: {e}")
            return False

    async def _analyze_correlation_changes(
        self, 
        old_correlations: Dict[str, Dict[str, float]], 
        new_correlations: Dict[str, Dict[str, float]]
    ) -> Dict[str, Any]:
        """
        Analyze correlation changes and determine if hedge adjustments are needed.
        
        Args:
            old_correlations: Previous correlation matrix
            new_correlations: New correlation matrix
            
        Returns:
            Dictionary with change analysis
        """
        try:
            analysis = {
                'significant_changes': [],
                'total_pairs': 0,
                'max_change': 0.0,
                'avg_change': 0.0,
                'requires_hedge_adjustment': False
            }
            
            if not old_correlations or not new_correlations:
                return analysis
            
            changes = []
            significant_threshold = 0.2  # 20% correlation change threshold
            
            # Compare correlations for all asset pairs
            for asset1 in new_correlations:
                if asset1 not in old_correlations:
                    continue
                    
                for asset2 in new_correlations[asset1]:
                    if asset2 not in old_correlations[asset1]:
                        continue
                    
                    if asset1 >= asset2:  # Avoid duplicate pairs
                        continue
                    
                    old_corr = old_correlations[asset1][asset2]
                    new_corr = new_correlations[asset1][asset2]
                    change = abs(new_corr - old_corr)
                    
                    changes.append(change)
                    analysis['total_pairs'] += 1
                    
                    if change > significant_threshold:
                        analysis['significant_changes'].append({
                            'pair': f"{asset1}-{asset2}",
                            'old_correlation': old_corr,
                            'new_correlation': new_corr,
                            'change': change,
                            'change_direction': 'increase' if new_corr > old_corr else 'decrease'
                        })
            
            if changes:
                analysis['max_change'] = max(changes)
                analysis['avg_change'] = sum(changes) / len(changes)
                
                # Determine if hedge adjustment is required
                # Criteria: significant changes in >20% of pairs OR max change >30%
                significant_ratio = len(analysis['significant_changes']) / len(changes)
                analysis['requires_hedge_adjustment'] = (
                    significant_ratio > 0.2 or analysis['max_change'] > 0.3
                )
            
            return analysis
            
        except Exception as e:
            self.logger.error(f"Error analyzing correlation changes: {e}")
            return {
                'significant_changes': [],
                'total_pairs': 0,
                'max_change': 0.0,
                'avg_change': 0.0,
                'requires_hedge_adjustment': False
            }

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

    async def monitor_correlation_changes(self, risk_engine) -> Dict[str, Any]:
        """
        Monitor correlation changes and automatically adjust hedge ratios if needed.
        
        Args:
            risk_engine: DriftRiskEngine instance for correlation monitoring
            
        Returns:
            Dictionary with monitoring results
        """
        try:
            # Detect correlation regime changes
            regime_changes = await risk_engine.detect_correlation_regime_changes(threshold=0.2)
            
            monitoring_result = {
                'regime_changes_detected': len(regime_changes),
                'adjustments_made': False,
                'hedge_effectiveness_impact': 'none',
                'recommended_actions': []
            }
            
            if regime_changes:
                self.logger.warning(f"Correlation regime changes detected: {len(regime_changes)} changes")
                
                # Get updated correlation matrix
                updated_correlations = await risk_engine.calculate_correlation_matrix(window_days=30)
                
                # Adjust hedge ratios based on new correlations
                adjustment_success = await self.adjust_hedge_ratios(updated_correlations.matrix)
                monitoring_result['adjustments_made'] = adjustment_success
                
                # Assess impact on hedge effectiveness
                current_effectiveness = await self._calculate_hedge_effectiveness()
                
                if current_effectiveness < 0.7:
                    monitoring_result['hedge_effectiveness_impact'] = 'degraded'
                    monitoring_result['recommended_actions'].append(
                        "Consider emergency hedging due to correlation breakdown"
                    )
                elif current_effectiveness < 0.8:
                    monitoring_result['hedge_effectiveness_impact'] = 'reduced'
                    monitoring_result['recommended_actions'].append(
                        "Monitor hedge performance closely"
                    )
                
                # Check if any changes affect our primary hedge markets
                hedge_markets = ['SOL-PERP', 'BTC-PERP', 'ETH-PERP']
                affected_hedge_markets = []
                
                for change in regime_changes:
                    pair = change['asset_pair']
                    for market in hedge_markets:
                        if market.replace('-PERP', '') in pair:
                            affected_hedge_markets.append(market)
                
                if affected_hedge_markets:
                    monitoring_result['recommended_actions'].append(
                        f"Review hedge markets: {', '.join(set(affected_hedge_markets))}"
                    )
                
                # Log detailed regime change information
                for change in regime_changes[:3]:  # Log top 3 changes
                    self.logger.info(
                        f"Regime change: {change['asset_pair']} correlation "
                        f"{change['old_correlation']:.3f} -> {change['new_correlation']:.3f} "
                        f"({change['change_direction']}, magnitude: {change['change_magnitude']:.3f})"
                    )
            
            return monitoring_result
            
        except Exception as e:
            self.logger.error(f"Error monitoring correlation changes: {e}")
            return {
                'regime_changes_detected': 0,
                'adjustments_made': False,
                'hedge_effectiveness_impact': 'error',
                'recommended_actions': ['Review correlation monitoring system']
            }

    async def enable_automatic_correlation_monitoring(
        self, 
        risk_engine, 
        monitoring_interval_minutes: int = 15
    ) -> bool:
        """
        Enable automatic correlation monitoring and hedge ratio adjustment.
        
        Args:
            risk_engine: DriftRiskEngine instance
            monitoring_interval_minutes: How often to check for correlation changes
            
        Returns:
            True if monitoring was enabled successfully
        """
        try:
            # Store risk engine reference for monitoring
            self._risk_engine = risk_engine
            self._correlation_monitoring_interval = timedelta(minutes=monitoring_interval_minutes)
            self._last_correlation_check = datetime.now()
            self._correlation_monitoring_enabled = True
            
            self.logger.info(
                f"Automatic correlation monitoring enabled: "
                f"checking every {monitoring_interval_minutes} minutes"
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Error enabling correlation monitoring: {e}")
            return False

    async def check_correlation_monitoring_due(self) -> bool:
        """
        Check if correlation monitoring is due to run.
        
        Returns:
            True if monitoring should be performed
        """
        if not getattr(self, '_correlation_monitoring_enabled', False):
            return False
        
        if not hasattr(self, '_last_correlation_check'):
            return True
        
        time_since_check = datetime.now() - self._last_correlation_check
        return time_since_check >= self._correlation_monitoring_interval

    async def run_correlation_monitoring_if_due(self) -> Optional[Dict[str, Any]]:
        """
        Run correlation monitoring if it's due.
        
        Returns:
            Monitoring results if monitoring was performed, None otherwise
        """
        try:
            if not await self.check_correlation_monitoring_due():
                return None
            
            if not hasattr(self, '_risk_engine'):
                self.logger.warning("Risk engine not available for correlation monitoring")
                return None
            
            # Update last check time
            self._last_correlation_check = datetime.now()
            
            # Perform monitoring
            monitoring_result = await self.monitor_correlation_changes(self._risk_engine)
            
            # Log monitoring summary
            if monitoring_result['regime_changes_detected'] > 0:
                self.logger.info(
                    f"Correlation monitoring: {monitoring_result['regime_changes_detected']} changes, "
                    f"adjustments made: {monitoring_result['adjustments_made']}, "
                    f"effectiveness impact: {monitoring_result['hedge_effectiveness_impact']}"
                )
            
            return monitoring_result
            
        except Exception as e:
            self.logger.error(f"Error running correlation monitoring: {e}")
            return None

    def clear_hedge_history(self):
        """Clear hedge history and reset state."""
        self._hedge_history.clear()
        self._last_hedge_time = None
        self._correlation_cache.clear()
        self._delta_cache.clear()
        self.logger.info("Hedge history cleared")

    async def integrate_with_risk_engine(self, risk_engine) -> bool:
        """
        Integrate hedging engine with risk engine for automatic correlation monitoring.
        
        Args:
            risk_engine: DriftRiskEngine instance
            
        Returns:
            True if integration was successful
        """
        try:
            # Store risk engine reference
            self._risk_engine = risk_engine
            
            # Enable automatic correlation monitoring
            await self.enable_automatic_correlation_monitoring(risk_engine, monitoring_interval_minutes=15)
            
            # Set up correlation history sharing
            if hasattr(risk_engine, '_correlation_history'):
                self._correlation_history = risk_engine._correlation_history
            
            self.logger.info("Hedging engine integrated with risk engine for correlation monitoring")
            return True
            
        except Exception as e:
            self.logger.error(f"Error integrating with risk engine: {e}")
            return False

    def get_correlation_monitoring_status(self) -> Dict[str, Any]:
        """
        Get status of correlation monitoring and hedge ratio adjustments.
        
        Returns:
            Dictionary with monitoring status information
        """
        try:
            status = {
                'monitoring_enabled': getattr(self, '_correlation_monitoring_enabled', False),
                'risk_engine_integrated': hasattr(self, '_risk_engine'),
                'last_correlation_check': getattr(self, '_last_correlation_check', None),
                'monitoring_interval_minutes': getattr(self, '_correlation_monitoring_interval', timedelta(minutes=15)).total_seconds() / 60,
                'correlation_cache_size': len(self._correlation_cache) if self._correlation_cache else 0,
                'correlation_history_size': len(getattr(self, '_correlation_history', [])),
                'next_check_due': None
            }
            
            # Calculate when next check is due
            if status['monitoring_enabled'] and status['last_correlation_check']:
                next_check = status['last_correlation_check'] + self._correlation_monitoring_interval
                status['next_check_due'] = next_check
                status['minutes_until_next_check'] = max(0, (next_check - datetime.now()).total_seconds() / 60)
            
            return status
            
        except Exception as e:
            self.logger.error(f"Error getting correlation monitoring status: {e}")
            return {
                'monitoring_enabled': False,
                'risk_engine_integrated': False,
                'error': str(e)
            }

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