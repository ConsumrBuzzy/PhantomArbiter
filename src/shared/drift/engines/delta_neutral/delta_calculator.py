"""
Delta Calculator
===============

Component for calculating portfolio and position deltas.
Cohesive with delta-neutral hedging logic.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime

from ...sdk.models.portfolio import PortfolioState, Position
from ...sdk.data.market_data_provider import MarketDataProvider
from src.shared.system.logging import Logger


class DeltaCalculator:
    """
    Delta calculation component for delta-neutral hedging.
    
    Provides sophisticated delta calculations including:
    - Portfolio-level delta
    - Position-level deltas
    - Delta sensitivity analysis
    - Time-decay adjusted deltas
    """
    
    def __init__(self, market_data_provider: MarketDataProvider):
        """
        Initialize delta calculator.
        
        Args:
            market_data_provider: Market data provider for price data
        """
        self.market_data = market_data_provider
        self.logger = Logger
        
        # Delta calculation parameters
        self._price_bump_percentage = 0.01  # 1% price bump for sensitivity
        self._cache = {}
        self._cache_ttl = 60  # 1 minute cache
    
    async def calculate_portfolio_delta(self, portfolio_state: PortfolioState) -> float:
        """
        Calculate total portfolio delta.
        
        Args:
            portfolio_state: Current portfolio state
            
        Returns:
            Total portfolio delta
        """
        try:
            if not portfolio_state.positions:
                return 0.0
            
            total_delta = 0.0
            
            for position in portfolio_state.positions:
                position_delta = await self.calculate_position_delta(position)
                total_delta += position_delta
            
            self.logger.debug(f"Portfolio delta calculated: {total_delta:.4f}")
            return total_delta
            
        except Exception as e:
            self.logger.error(f"Error calculating portfolio delta: {e}")
            return 0.0
    
    async def calculate_position_delta(self, position: Position) -> float:
        """
        Calculate delta for a single position.
        
        Args:
            position: Position to calculate delta for
            
        Returns:
            Position delta
        """
        try:
            # For perpetual futures, delta is approximately position size * price
            # This is a simplified calculation - in practice might need more sophisticated models
            
            if abs(position.size) < 1e-8:
                return 0.0
            
            # Get current market price
            market_summary = await self.market_data.get_market_summary(position.market)
            if not market_summary:
                self.logger.warning(f"No market data for {position.market}")
                return 0.0
            
            current_price = market_summary.mark_price
            
            # For linear instruments (perpetuals), delta ≈ position_size * price
            position_delta = position.size * current_price
            
            # Apply any adjustments for specific market types
            adjusted_delta = self._apply_market_adjustments(position_delta, position.market)
            
            return adjusted_delta
            
        except Exception as e:
            self.logger.error(f"Error calculating position delta for {position.market}: {e}")
            return 0.0
    
    async def calculate_position_deltas(self, positions: List[Position]) -> Dict[str, float]:
        """
        Calculate deltas for multiple positions.
        
        Args:
            positions: List of positions
            
        Returns:
            Dictionary mapping market -> delta
        """
        deltas = {}
        
        for position in positions:
            try:
                delta = await self.calculate_position_delta(position)
                deltas[position.market] = delta
            except Exception as e:
                self.logger.error(f"Error calculating delta for {position.market}: {e}")
                deltas[position.market] = 0.0
        
        return deltas
    
    async def calculate_delta_sensitivity(
        self, 
        portfolio_state: PortfolioState,
        price_scenarios: Optional[Dict[str, float]] = None
    ) -> Dict[str, float]:
        """
        Calculate delta sensitivity to price changes.
        
        Args:
            portfolio_state: Current portfolio state
            price_scenarios: Optional price scenarios {market: price_change_pct}
            
        Returns:
            Dictionary with delta sensitivity analysis
        """
        try:
            if not portfolio_state.positions:
                return {}
            
            # Use default price bump if no scenarios provided
            if not price_scenarios:
                price_scenarios = {}
                for position in portfolio_state.positions:
                    price_scenarios[position.market] = self._price_bump_percentage
            
            sensitivity_results = {}
            
            for market, price_change_pct in price_scenarios.items():
                # Find position for this market
                position = next((p for p in portfolio_state.positions if p.market == market), None)
                if not position:
                    continue
                
                # Calculate delta change for price scenario
                original_delta = await self.calculate_position_delta(position)
                
                # Create modified position with new price
                modified_position = Position(
                    market=position.market,
                    side=position.side,
                    size=position.size,
                    entry_price=position.entry_price,
                    mark_price=position.mark_price * (1 + price_change_pct),
                    unrealized_pnl=position.unrealized_pnl,
                    realized_pnl=position.realized_pnl,
                    margin_requirement=position.margin_requirement,
                    last_updated=position.last_updated
                )
                
                new_delta = await self.calculate_position_delta(modified_position)
                delta_sensitivity = new_delta - original_delta
                
                sensitivity_results[market] = {
                    'price_change_pct': price_change_pct,
                    'original_delta': original_delta,
                    'new_delta': new_delta,
                    'delta_sensitivity': delta_sensitivity,
                    'sensitivity_per_1pct': delta_sensitivity / price_change_pct if price_change_pct != 0 else 0
                }
            
            return sensitivity_results
            
        except Exception as e:
            self.logger.error(f"Error calculating delta sensitivity: {e}")
            return {}
    
    async def calculate_delta_exposure_by_asset(self, portfolio_state: PortfolioState) -> Dict[str, float]:
        """
        Calculate delta exposure grouped by underlying asset.
        
        Args:
            portfolio_state: Current portfolio state
            
        Returns:
            Dictionary mapping asset -> total delta exposure
        """
        try:
            asset_deltas = {}
            
            for position in portfolio_state.positions:
                # Extract asset from market (e.g., "SOL-PERP" -> "SOL")
                asset = position.market.split('-')[0] if '-' in position.market else position.market
                
                position_delta = await self.calculate_position_delta(position)
                
                if asset not in asset_deltas:
                    asset_deltas[asset] = 0.0
                
                asset_deltas[asset] += position_delta
            
            return asset_deltas
            
        except Exception as e:
            self.logger.error(f"Error calculating delta exposure by asset: {e}")
            return {}
    
    async def estimate_hedge_delta_impact(
        self, 
        hedge_market: str, 
        hedge_size: float,
        current_portfolio_delta: float
    ) -> Dict[str, float]:
        """
        Estimate the delta impact of a potential hedge trade.
        
        Args:
            hedge_market: Market for hedge trade
            hedge_size: Size of hedge trade (positive = buy, negative = sell)
            current_portfolio_delta: Current portfolio delta
            
        Returns:
            Dictionary with hedge impact analysis
        """
        try:
            # Get hedge market price
            market_summary = await self.market_data.get_market_summary(hedge_market)
            if not market_summary:
                return {}
            
            hedge_price = market_summary.mark_price
            
            # Calculate hedge delta impact
            hedge_delta_impact = hedge_size * hedge_price
            
            # Calculate resulting portfolio delta
            new_portfolio_delta = current_portfolio_delta + hedge_delta_impact
            
            # Calculate hedge effectiveness
            delta_reduction = abs(new_portfolio_delta) - abs(current_portfolio_delta)
            hedge_effectiveness = -delta_reduction / abs(hedge_delta_impact) if hedge_delta_impact != 0 else 0
            
            return {
                'hedge_market': hedge_market,
                'hedge_size': hedge_size,
                'hedge_price': hedge_price,
                'hedge_delta_impact': hedge_delta_impact,
                'current_portfolio_delta': current_portfolio_delta,
                'new_portfolio_delta': new_portfolio_delta,
                'delta_reduction': delta_reduction,
                'hedge_effectiveness': hedge_effectiveness,
                'hedge_ratio': hedge_delta_impact / current_portfolio_delta if current_portfolio_delta != 0 else 0
            }
            
        except Exception as e:
            self.logger.error(f"Error estimating hedge delta impact: {e}")
            return {}
    
    def calculate_optimal_hedge_size(
        self, 
        current_delta: float, 
        target_delta: float, 
        hedge_price: float,
        hedge_effectiveness: float = 1.0
    ) -> float:
        """
        Calculate optimal hedge size to achieve target delta.
        
        Args:
            current_delta: Current portfolio delta
            target_delta: Target portfolio delta
            hedge_price: Price of hedge instrument
            hedge_effectiveness: Hedge effectiveness ratio (0-1)
            
        Returns:
            Optimal hedge size
        """
        try:
            if hedge_price <= 0 or hedge_effectiveness <= 0:
                return 0.0
            
            # Required delta change
            required_delta_change = target_delta - current_delta
            
            # Calculate hedge size accounting for effectiveness
            optimal_size = required_delta_change / (hedge_price * hedge_effectiveness)
            
            return optimal_size
            
        except Exception as e:
            self.logger.error(f"Error calculating optimal hedge size: {e}")
            return 0.0
    
    def _apply_market_adjustments(self, base_delta: float, market: str) -> float:
        """
        Apply market-specific adjustments to delta calculation.
        
        Args:
            base_delta: Base delta calculation
            market: Market identifier
            
        Returns:
            Adjusted delta
        """
        # Market-specific adjustments could include:
        # - Funding rate impacts
        # - Volatility adjustments
        # - Liquidity considerations
        
        # For now, return base delta (can be enhanced later)
        return base_delta
    
    def get_delta_statistics(self, deltas: Dict[str, float]) -> Dict[str, Any]:
        """
        Calculate statistics for a set of deltas.
        
        Args:
            deltas: Dictionary of market -> delta
            
        Returns:
            Dictionary with delta statistics
        """
        try:
            if not deltas:
                return {}
            
            delta_values = list(deltas.values())
            
            total_delta = sum(delta_values)
            abs_total_delta = sum(abs(d) for d in delta_values)
            
            positive_deltas = [d for d in delta_values if d > 0]
            negative_deltas = [d for d in delta_values if d < 0]
            
            stats = {
                'total_delta': total_delta,
                'absolute_delta': abs_total_delta,
                'net_delta': total_delta,
                'gross_delta': abs_total_delta,
                'long_delta': sum(positive_deltas),
                'short_delta': sum(negative_deltas),
                'position_count': len(deltas),
                'long_positions': len(positive_deltas),
                'short_positions': len(negative_deltas),
                'largest_delta': max(delta_values, key=abs) if delta_values else 0,
                'delta_concentration': max(abs(d) for d in delta_values) / abs_total_delta if abs_total_delta > 0 else 0,
                'calculation_time': datetime.now().isoformat()
            }
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Error calculating delta statistics: {e}")
            return {}