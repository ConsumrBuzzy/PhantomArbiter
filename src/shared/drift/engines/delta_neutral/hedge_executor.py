"""
Hedge Executor
=============

Component for executing hedge trades with optimal execution strategies.
Cohesive with delta-neutral hedging logic.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from ...sdk.models.trading import TradeSignal, SignalType, OrderSide
from ...sdk.models.portfolio import PortfolioState
from ...sdk.data.market_data_provider import MarketDataProvider
from ...sdk.math.correlation_calculator import CorrelationCalculator
from src.shared.system.logging import Logger


class HedgeUrgency(Enum):
    """Hedge execution urgency levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    EMERGENCY = "emergency"


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
    urgency: HedgeUrgency
    calculation_time: datetime
    
    @classmethod
    def no_hedging_needed(cls, current_delta: float = 0.0, target_delta: float = 0.0):
        """Create HedgeRequirements indicating no hedging is needed."""
        return cls(
            target_delta=target_delta,
            current_delta=current_delta,
            delta_deviation=abs(current_delta - target_delta),
            required_trades=[],
            estimated_cost=0.0,
            market_impact=0.0,
            confidence_score=1.0,
            urgency=HedgeUrgency.LOW,
            calculation_time=datetime.now()
        )


@dataclass
class HedgeTrade:
    """Individual hedge trade specification."""
    market: str
    side: OrderSide
    size: float
    hedge_ratio: float
    priority: int  # 1 = highest priority
    reasoning: str
    estimated_price: float
    max_slippage: float
    urgency: HedgeUrgency
    
    # Execution parameters
    order_type: str = "limit"
    time_in_force: str = "GTC"
    reduce_only: bool = False


class HedgeExecutor:
    """
    Hedge execution component for delta-neutral strategies.
    
    Provides intelligent hedge execution including:
    - Optimal hedge market selection
    - Multi-asset hedge strategies
    - Execution timing optimization
    - Cost minimization
    - Market impact estimation
    """
    
    def __init__(self, market_data_provider: MarketDataProvider):
        """
        Initialize hedge executor.
        
        Args:
            market_data_provider: Market data provider for execution data
        """
        self.market_data = market_data_provider
        self.logger = Logger
        
        # Execution parameters
        self._default_slippage = 0.005  # 0.5% default max slippage
        self._min_hedge_size_usd = 10.0  # Minimum $10 hedge size
        self._max_hedge_size_usd = 100000.0  # Maximum $100k per hedge trade
        self._preferred_hedge_markets = ['SOL-PERP', 'BTC-PERP', 'ETH-PERP']
        
        # Market impact parameters
        self._impact_coefficient = 0.001  # Market impact coefficient
        self._liquidity_threshold = 10000.0  # Minimum liquidity threshold
    
    async def calculate_optimal_hedges(
        self,
        current_delta: float,
        target_delta: float,
        correlation_matrix: Optional[Dict[str, Dict[str, float]]] = None,
        portfolio_state: Optional[PortfolioState] = None
    ) -> HedgeRequirements:
        """
        Calculate optimal hedge trades to achieve target delta.
        
        Args:
            current_delta: Current portfolio delta
            target_delta: Target portfolio delta
            correlation_matrix: Asset correlation matrix for optimization
            portfolio_state: Current portfolio state for context
            
        Returns:
            HedgeRequirements with optimal hedge strategy
        """
        try:
            delta_deviation = abs(current_delta - target_delta)
            
            # Determine hedge urgency
            urgency = self._determine_hedge_urgency(delta_deviation, portfolio_state)
            
            # Calculate required hedge trades
            hedge_trades = await self._calculate_hedge_trades(
                current_delta, target_delta, correlation_matrix, urgency
            )
            
            # Estimate costs and market impact
            estimated_cost = await self._estimate_total_cost(hedge_trades)
            market_impact = await self._estimate_total_market_impact(hedge_trades)
            
            # Calculate confidence score
            confidence_score = await self._calculate_hedge_confidence(hedge_trades)
            
            return HedgeRequirements(
                target_delta=target_delta,
                current_delta=current_delta,
                delta_deviation=delta_deviation,
                required_trades=hedge_trades,
                estimated_cost=estimated_cost,
                market_impact=market_impact,
                confidence_score=confidence_score,
                urgency=urgency,
                calculation_time=datetime.now()
            )
            
        except Exception as e:
            self.logger.error(f"Error calculating optimal hedges: {e}")
            return HedgeRequirements.no_hedging_needed(current_delta, target_delta)
    
    async def convert_hedges_to_signals(self, hedge_requirements: HedgeRequirements) -> List[TradeSignal]:
        """
        Convert hedge requirements to executable trade signals.
        
        Args:
            hedge_requirements: Hedge requirements from calculation
            
        Returns:
            List of trade signals ready for execution
        """
        signals = []
        
        try:
            for i, hedge_trade in enumerate(hedge_requirements.required_trades):
                # Create unique signal ID
                signal_id = f"hedge_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i}"
                
                # Map urgency to signal urgency
                urgency_mapping = {
                    HedgeUrgency.LOW: 0.2,
                    HedgeUrgency.NORMAL: 0.5,
                    HedgeUrgency.HIGH: 0.8,
                    HedgeUrgency.EMERGENCY: 1.0
                }
                
                signal = TradeSignal(
                    signal_id=signal_id,
                    engine_name="delta_neutral_hedging",
                    signal_type=SignalType.HEDGE,
                    market=hedge_trade.market,
                    side=hedge_trade.side,
                    size=hedge_trade.size,
                    signal_strength=hedge_requirements.confidence_score,
                    target_price=hedge_trade.estimated_price,
                    max_slippage=hedge_trade.max_slippage,
                    urgency=urgency_mapping.get(hedge_trade.urgency, 0.5),
                    priority=hedge_trade.priority,
                    reasoning=hedge_trade.reasoning,
                    created_at=datetime.now(),
                    valid_until=datetime.now() + timedelta(minutes=30),  # 30 min expiry
                    metadata={
                        'hedge_ratio': hedge_trade.hedge_ratio,
                        'target_delta': hedge_requirements.target_delta,
                        'current_delta': hedge_requirements.current_delta,
                        'urgency': hedge_trade.urgency.value,
                        'order_type': hedge_trade.order_type,
                        'time_in_force': hedge_trade.time_in_force,
                        'reduce_only': hedge_trade.reduce_only
                    }
                )
                
                signals.append(signal)
            
            self.logger.info(f"Converted {len(hedge_requirements.required_trades)} hedges to {len(signals)} signals")
            return signals
            
        except Exception as e:
            self.logger.error(f"Error converting hedges to signals: {e}")
            return []
    
    async def _calculate_hedge_trades(
        self,
        current_delta: float,
        target_delta: float,
        correlation_matrix: Optional[Dict[str, Dict[str, float]]],
        urgency: HedgeUrgency
    ) -> List[HedgeTrade]:
        """Calculate specific hedge trades needed."""
        try:
            required_delta_change = target_delta - current_delta
            
            if abs(required_delta_change) * 1000 < self._min_hedge_size_usd:  # Assuming $1000 per delta unit
                return []
            
            # Select optimal hedge market
            hedge_market = await self._select_optimal_hedge_market(correlation_matrix)
            
            if not hedge_market:
                self.logger.warning("No suitable hedge market found")
                return []
            
            # Get market data for hedge market
            market_summary = await self.market_data.get_market_summary(hedge_market)
            if not market_summary:
                self.logger.error(f"No market data for hedge market {hedge_market}")
                return []
            
            hedge_price = market_summary.mark_price
            
            # Calculate hedge ratio (correlation-adjusted if available)
            hedge_ratio = await self._calculate_hedge_ratio(hedge_market, correlation_matrix)
            
            # Calculate base hedge size
            base_hedge_size = -required_delta_change / (hedge_price * hedge_ratio)
            
            # Determine trade side
            side = OrderSide.BUY if base_hedge_size > 0 else OrderSide.SELL
            trade_size = abs(base_hedge_size)
            
            # Split large trades if necessary
            hedge_trades = []
            max_trade_size_usd = self._get_max_trade_size_for_urgency(urgency)
            max_trade_size = max_trade_size_usd / hedge_price
            
            if trade_size > max_trade_size:
                # Split into multiple trades
                num_trades = int(trade_size / max_trade_size) + 1
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
                        max_slippage=self._get_slippage_for_urgency(urgency),
                        urgency=urgency,
                        order_type=self._get_order_type_for_urgency(urgency)
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
                    max_slippage=self._get_slippage_for_urgency(urgency),
                    urgency=urgency,
                    order_type=self._get_order_type_for_urgency(urgency)
                )
                hedge_trades.append(hedge_trade)
            
            return hedge_trades
            
        except Exception as e:
            self.logger.error(f"Error calculating hedge trades: {e}")
            return []
    
    async def _select_optimal_hedge_market(
        self, 
        correlation_matrix: Optional[Dict[str, Dict[str, float]]]
    ) -> Optional[str]:
        """Select the optimal market for hedging based on liquidity and correlation."""
        try:
            # Get liquidity metrics for preferred markets
            market_scores = {}
            
            for market in self._preferred_hedge_markets:
                try:
                    # Get market data
                    market_summary = await self.market_data.get_market_summary(market)
                    if not market_summary or not market_summary.is_active:
                        continue
                    
                    # Get liquidity metrics
                    liquidity_metrics = await self.market_data.get_liquidity_metrics(market)
                    
                    # Calculate market score based on:
                    # 1. Liquidity (40% weight)
                    # 2. Volume (30% weight)  
                    # 3. Spread (20% weight)
                    # 4. Correlation (10% weight)
                    
                    liquidity_score = min(1.0, liquidity_metrics.get('total_liquidity', 0) / self._liquidity_threshold)
                    volume_score = min(1.0, market_summary.volume_24h / 1000000)  # Normalize by $1M
                    spread_score = max(0.0, 1.0 - (liquidity_metrics.get('spread_bps', 100) / 100))  # Penalize wide spreads
                    
                    # Correlation score (prefer lower correlation for diversification)
                    correlation_score = 0.5  # Default neutral score
                    if correlation_matrix:
                        # Calculate average correlation with existing positions
                        correlations = []
                        for other_market in correlation_matrix.keys():
                            if other_market != market and market in correlation_matrix.get(other_market, {}):
                                correlations.append(abs(correlation_matrix[other_market][market]))
                        
                        if correlations:
                            avg_correlation = sum(correlations) / len(correlations)
                            correlation_score = 1.0 - avg_correlation  # Lower correlation = higher score
                    
                    # Weighted total score
                    total_score = (
                        liquidity_score * 0.4 +
                        volume_score * 0.3 +
                        spread_score * 0.2 +
                        correlation_score * 0.1
                    )
                    
                    market_scores[market] = {
                        'total_score': total_score,
                        'liquidity_score': liquidity_score,
                        'volume_score': volume_score,
                        'spread_score': spread_score,
                        'correlation_score': correlation_score
                    }
                    
                except Exception as e:
                    self.logger.warning(f"Error evaluating market {market}: {e}")
                    continue
            
            if not market_scores:
                # Fallback to first preferred market
                return self._preferred_hedge_markets[0] if self._preferred_hedge_markets else None
            
            # Select market with highest score
            best_market = max(market_scores.keys(), key=lambda m: market_scores[m]['total_score'])
            
            self.logger.debug(f"Selected hedge market {best_market} with score {market_scores[best_market]['total_score']:.3f}")
            return best_market
            
        except Exception as e:
            self.logger.error(f"Error selecting optimal hedge market: {e}")
            return self._preferred_hedge_markets[0] if self._preferred_hedge_markets else None
    
    async def _calculate_hedge_ratio(
        self,
        hedge_market: str,
        correlation_matrix: Optional[Dict[str, Dict[str, float]]]
    ) -> float:
        """Calculate hedge ratio based on correlations and volatility."""
        try:
            # Base hedge ratio
            base_ratio = 1.0
            
            if not correlation_matrix:
                return base_ratio
            
            # Calculate weighted average correlation with existing positions
            correlations = []
            for market in correlation_matrix.keys():
                if market != hedge_market and hedge_market in correlation_matrix.get(market, {}):
                    correlation = correlation_matrix[market][hedge_market]
                    correlations.append(abs(correlation))  # Use absolute correlation
            
            if not correlations:
                return base_ratio
            
            # Average correlation
            avg_correlation = sum(correlations) / len(correlations)
            
            # Adjust hedge ratio based on correlation
            # Higher correlation = more effective hedge = lower ratio needed
            correlation_adjustment = 0.5 + (0.5 * avg_correlation)  # 0.5 to 1.0 range
            
            adjusted_ratio = base_ratio * correlation_adjustment
            
            # Ensure ratio is within reasonable bounds
            return max(0.1, min(2.0, adjusted_ratio))
            
        except Exception as e:
            self.logger.error(f"Error calculating hedge ratio: {e}")
            return 1.0
    
    def _determine_hedge_urgency(
        self, 
        delta_deviation: float, 
        portfolio_state: Optional[PortfolioState]
    ) -> HedgeUrgency:
        """Determine hedge execution urgency based on delta deviation and portfolio health."""
        try:
            # Base urgency on delta deviation
            if delta_deviation > 0.1:  # >10% delta deviation
                base_urgency = HedgeUrgency.EMERGENCY
            elif delta_deviation > 0.05:  # >5% delta deviation
                base_urgency = HedgeUrgency.HIGH
            elif delta_deviation > 0.02:  # >2% delta deviation
                base_urgency = HedgeUrgency.NORMAL
            else:
                base_urgency = HedgeUrgency.LOW
            
            # Adjust based on portfolio health
            if portfolio_state:
                if portfolio_state.health_ratio < 0.2:  # Low health ratio
                    if base_urgency == HedgeUrgency.LOW:
                        base_urgency = HedgeUrgency.NORMAL
                    elif base_urgency == HedgeUrgency.NORMAL:
                        base_urgency = HedgeUrgency.HIGH
                
                # High leverage increases urgency
                if portfolio_state.leverage > 3.0:
                    if base_urgency == HedgeUrgency.LOW:
                        base_urgency = HedgeUrgency.NORMAL
            
            return base_urgency
            
        except Exception as e:
            self.logger.error(f"Error determining hedge urgency: {e}")
            return HedgeUrgency.NORMAL
    
    def _get_max_trade_size_for_urgency(self, urgency: HedgeUrgency) -> float:
        """Get maximum trade size based on urgency."""
        urgency_multipliers = {
            HedgeUrgency.LOW: 0.5,      # Smaller trades for low urgency
            HedgeUrgency.NORMAL: 1.0,   # Normal size
            HedgeUrgency.HIGH: 1.5,     # Larger trades for high urgency
            HedgeUrgency.EMERGENCY: 2.0 # Largest trades for emergency
        }
        
        multiplier = urgency_multipliers.get(urgency, 1.0)
        return self._max_hedge_size_usd * multiplier
    
    def _get_slippage_for_urgency(self, urgency: HedgeUrgency) -> float:
        """Get maximum slippage tolerance based on urgency."""
        urgency_slippage = {
            HedgeUrgency.LOW: self._default_slippage * 0.5,      # Lower slippage tolerance
            HedgeUrgency.NORMAL: self._default_slippage,         # Normal slippage
            HedgeUrgency.HIGH: self._default_slippage * 2.0,     # Higher slippage tolerance
            HedgeUrgency.EMERGENCY: self._default_slippage * 5.0 # Much higher tolerance
        }
        
        return urgency_slippage.get(urgency, self._default_slippage)
    
    def _get_order_type_for_urgency(self, urgency: HedgeUrgency) -> str:
        """Get order type based on urgency."""
        if urgency in [HedgeUrgency.HIGH, HedgeUrgency.EMERGENCY]:
            return "market"  # Market orders for urgent hedges
        else:
            return "limit"   # Limit orders for normal hedges
    
    async def _estimate_total_cost(self, hedge_trades: List[HedgeTrade]) -> float:
        """Estimate total cost of executing hedge trades."""
        try:
            total_cost = 0.0
            
            for trade in hedge_trades:
                # Trading fees (estimated)
                trade_value = trade.size * trade.estimated_price
                estimated_fee = trade_value * 0.002  # 0.2% taker fee assumption
                
                # Slippage cost
                slippage_cost = trade_value * trade.max_slippage
                
                total_cost += estimated_fee + slippage_cost
            
            return total_cost
            
        except Exception as e:
            self.logger.error(f"Error estimating total cost: {e}")
            return 0.0
    
    async def _estimate_total_market_impact(self, hedge_trades: List[HedgeTrade]) -> float:
        """Estimate total market impact of hedge trades."""
        try:
            total_impact = 0.0
            
            for trade in hedge_trades:
                # Simplified market impact model
                trade_value = trade.size * trade.estimated_price
                
                # Impact increases with square root of trade size
                impact_factor = (trade_value / 10000.0) ** 0.5  # Normalize by $10k
                estimated_impact = impact_factor * self._impact_coefficient
                
                total_impact += min(0.02, estimated_impact)  # Cap at 2%
            
            return total_impact
            
        except Exception as e:
            self.logger.error(f"Error estimating market impact: {e}")
            return 0.0
    
    async def _calculate_hedge_confidence(self, hedge_trades: List[HedgeTrade]) -> float:
        """Calculate confidence score for hedge strategy."""
        try:
            if not hedge_trades:
                return 0.0
            
            confidence_factors = []
            
            for trade in hedge_trades:
                # Market liquidity factor
                liquidity_metrics = await self.market_data.get_liquidity_metrics(trade.market)
                liquidity_factor = min(1.0, liquidity_metrics.get('total_liquidity', 0) / self._liquidity_threshold)
                
                # Hedge ratio factor (closer to 1.0 = higher confidence)
                ratio_factor = 1.0 - abs(1.0 - trade.hedge_ratio) * 0.5
                
                # Size factor (smaller trades = higher confidence)
                trade_value = trade.size * trade.estimated_price
                size_factor = max(0.5, 1.0 - (trade_value / self._max_hedge_size_usd) * 0.3)
                
                # Combined factor for this trade
                trade_confidence = (liquidity_factor + ratio_factor + size_factor) / 3.0
                confidence_factors.append(trade_confidence)
            
            # Overall confidence is average of individual trade confidences
            overall_confidence = sum(confidence_factors) / len(confidence_factors)
            
            return max(0.0, min(1.0, overall_confidence))
            
        except Exception as e:
            self.logger.error(f"Error calculating hedge confidence: {e}")
            return 0.5