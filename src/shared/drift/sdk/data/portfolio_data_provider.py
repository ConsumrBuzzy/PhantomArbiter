"""
Portfolio Data Provider
======================

Shared portfolio data interface for all trading engines.
Provides consistent access to portfolio state and position data.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from ..models.portfolio import PortfolioState, Position, PositionSummary
from ..models.trading import TradeResult, OrderResponse
from src.shared.system.logging import Logger


class PortfolioDataProvider(ABC):
    """
    Abstract base class for portfolio data providers.
    
    Provides a consistent interface for accessing portfolio data
    across different sources and trading engines.
    """
    
    def __init__(self):
        self.logger = Logger
        self._cache = {}
        self._cache_ttl = 30  # 30 seconds for portfolio data
    
    # ==========================================================================
    # ABSTRACT METHODS - Must be implemented by concrete providers
    # ==========================================================================
    
    @abstractmethod
    async def get_portfolio_state(self) -> Optional[PortfolioState]:
        """
        Get current portfolio state.
        
        Returns:
            Current PortfolioState or None if unavailable
        """
        pass
    
    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """
        Get all current positions.
        
        Returns:
            List of current positions
        """
        pass
    
    @abstractmethod
    async def get_position(self, market: str) -> Optional[Position]:
        """
        Get position for a specific market.
        
        Args:
            market: Market identifier
            
        Returns:
            Position or None if no position exists
        """
        pass
    
    @abstractmethod
    async def get_trade_history(
        self, 
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[TradeResult]:
        """
        Get trade history.
        
        Args:
            start_time: Start time for history
            end_time: End time for history
            limit: Maximum number of trades to return
            
        Returns:
            List of trade results
        """
        pass
    
    @abstractmethod
    async def get_portfolio_value_history(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        resolution: str = "1h"
    ) -> List[Dict[str, Any]]:
        """
        Get portfolio value history.
        
        Args:
            start_time: Start time for history
            end_time: End time for history
            resolution: Data resolution ("1m", "5m", "1h", "1d")
            
        Returns:
            List of portfolio value snapshots
        """
        pass
    
    # ==========================================================================
    # CONCRETE METHODS - Built on abstract methods
    # ==========================================================================
    
    async def get_portfolio_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive portfolio summary.
        
        Returns:
            Dictionary with portfolio summary statistics
        """
        try:
            portfolio_state = await self.get_portfolio_state()
            
            if not portfolio_state:
                return {}
            
            # Get position summaries
            position_summaries = portfolio_state.get_position_summary_by_asset()
            
            # Calculate additional metrics
            total_positions = len(portfolio_state.positions)
            long_positions = len([p for p in portfolio_state.positions if p.is_long])
            short_positions = len([p for p in portfolio_state.positions if p.is_short])
            
            # Get largest positions
            largest_positions = portfolio_state.get_largest_positions(5)
            most_profitable = portfolio_state.get_most_profitable_positions(5)
            
            summary = {
                'portfolio_value': portfolio_state.total_value,
                'total_collateral': portfolio_state.total_collateral,
                'unrealized_pnl': portfolio_state.unrealized_pnl,
                'realized_pnl': portfolio_state.realized_pnl,
                'daily_pnl': portfolio_state.daily_pnl,
                'health_ratio': portfolio_state.health_ratio,
                'leverage': portfolio_state.leverage,
                'margin_utilization': portfolio_state.utilization_ratio,
                'total_positions': total_positions,
                'long_positions': long_positions,
                'short_positions': short_positions,
                'position_summaries': {
                    asset: summary.to_dict() if hasattr(summary, 'to_dict') else summary.__dict__
                    for asset, summary in position_summaries.items()
                },
                'largest_positions': [
                    {
                        'market': pos.market,
                        'notional_value': pos.notional_value,
                        'unrealized_pnl': pos.unrealized_pnl,
                        'pnl_percentage': pos.pnl_percentage
                    }
                    for pos in largest_positions
                ],
                'most_profitable': [
                    {
                        'market': pos.market,
                        'unrealized_pnl': pos.unrealized_pnl,
                        'pnl_percentage': pos.pnl_percentage
                    }
                    for pos in most_profitable
                ],
                'portfolio_delta': portfolio_state.get_portfolio_delta(),
                'is_healthy': portfolio_state.is_healthy,
                'is_at_risk': portfolio_state.is_at_risk,
                'last_updated': portfolio_state.last_updated.isoformat()
            }
            
            return summary
            
        except Exception as e:
            self.logger.error(f"Error getting portfolio summary: {e}")
            return {}
    
    async def get_position_performance(self, market: str, days: int = 30) -> Dict[str, Any]:
        """
        Get performance metrics for a specific position.
        
        Args:
            market: Market identifier
            days: Number of days for performance calculation
            
        Returns:
            Dictionary with position performance metrics
        """
        try:
            position = await self.get_position(market)
            
            if not position:
                return {}
            
            # Get trade history for this market
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)
            
            all_trades = await self.get_trade_history(start_time, end_time)
            position_trades = [trade for trade in all_trades if trade.market == market]
            
            # Calculate performance metrics
            total_trades = len(position_trades)
            winning_trades = len([t for t in position_trades if t.estimated_pnl > 0])
            losing_trades = total_trades - winning_trades
            
            win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
            
            total_pnl = sum(trade.estimated_pnl for trade in position_trades)
            total_fees = sum(trade.total_fees for trade in position_trades)
            
            # Average trade metrics
            avg_win = 0.0
            avg_loss = 0.0
            
            if winning_trades > 0:
                winning_pnls = [t.estimated_pnl for t in position_trades if t.estimated_pnl > 0]
                avg_win = sum(winning_pnls) / len(winning_pnls)
            
            if losing_trades > 0:
                losing_pnls = [t.estimated_pnl for t in position_trades if t.estimated_pnl < 0]
                avg_loss = sum(losing_pnls) / len(losing_pnls)
            
            # Profit factor
            gross_profit = sum(t.estimated_pnl for t in position_trades if t.estimated_pnl > 0)
            gross_loss = abs(sum(t.estimated_pnl for t in position_trades if t.estimated_pnl < 0))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
            
            performance = {
                'market': market,
                'current_position': {
                    'size': position.size,
                    'notional_value': position.notional_value,
                    'unrealized_pnl': position.unrealized_pnl,
                    'realized_pnl': position.realized_pnl,
                    'pnl_percentage': position.pnl_percentage,
                    'entry_price': position.entry_price,
                    'mark_price': position.mark_price
                },
                'trading_performance': {
                    'total_trades': total_trades,
                    'winning_trades': winning_trades,
                    'losing_trades': losing_trades,
                    'win_rate': win_rate,
                    'total_pnl': total_pnl,
                    'total_fees': total_fees,
                    'net_pnl': total_pnl - total_fees,
                    'avg_win': avg_win,
                    'avg_loss': avg_loss,
                    'profit_factor': profit_factor,
                    'largest_win': max([t.estimated_pnl for t in position_trades], default=0.0),
                    'largest_loss': min([t.estimated_pnl for t in position_trades], default=0.0)
                },
                'period_days': days,
                'calculation_time': datetime.now().isoformat()
            }
            
            return performance
            
        except Exception as e:
            self.logger.error(f"Error getting position performance for {market}: {e}")
            return {}
    
    async def get_portfolio_returns(self, days: int = 252) -> List[float]:
        """
        Calculate portfolio returns from value history.
        
        Args:
            days: Number of days of returns to calculate
            
        Returns:
            List of daily portfolio returns
        """
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days + 1)  # Extra day for first return
            
            value_history = await self.get_portfolio_value_history(
                start_time=start_time,
                end_time=end_time,
                resolution="1d"
            )
            
            if len(value_history) < 2:
                return []
            
            returns = []
            for i in range(1, len(value_history)):
                prev_value = value_history[i-1].get('total_value', 0)
                curr_value = value_history[i].get('total_value', 0)
                
                if prev_value > 0:
                    ret = (curr_value - prev_value) / prev_value
                    returns.append(ret)
            
            return returns[-days:] if len(returns) > days else returns
            
        except Exception as e:
            self.logger.error(f"Error calculating portfolio returns: {e}")
            return []
    
    async def get_position_exposure_analysis(self) -> Dict[str, Any]:
        """
        Analyze portfolio exposure across different dimensions.
        
        Returns:
            Dictionary with exposure analysis
        """
        try:
            portfolio_state = await self.get_portfolio_state()
            
            if not portfolio_state or not portfolio_state.positions:
                return {}
            
            total_exposure = sum(abs(pos.notional_value) for pos in portfolio_state.positions)
            
            if total_exposure == 0:
                return {}
            
            # Asset exposure
            asset_exposure = {}
            for position in portfolio_state.positions:
                asset = position.market.split('-')[0] if '-' in position.market else position.market
                exposure = abs(position.notional_value) / total_exposure
                asset_exposure[asset] = asset_exposure.get(asset, 0.0) + exposure
            
            # Side exposure (long vs short)
            long_exposure = sum(pos.notional_value for pos in portfolio_state.positions if pos.is_long)
            short_exposure = sum(abs(pos.notional_value) for pos in portfolio_state.positions if pos.is_short)
            
            # Market type exposure
            perp_exposure = 0.0
            spot_exposure = 0.0
            
            for position in portfolio_state.positions:
                exposure = abs(position.notional_value) / total_exposure
                if 'PERP' in position.market:
                    perp_exposure += exposure
                else:
                    spot_exposure += exposure
            
            # Concentration metrics
            sorted_exposures = sorted(asset_exposure.values(), reverse=True)
            top_3_concentration = sum(sorted_exposures[:3]) if len(sorted_exposures) >= 3 else sum(sorted_exposures)
            
            # Calculate Herfindahl-Hirschman Index
            hhi = sum(exposure ** 2 for exposure in asset_exposure.values())
            
            analysis = {
                'total_exposure': total_exposure,
                'asset_exposure': asset_exposure,
                'side_exposure': {
                    'long_notional': long_exposure,
                    'short_notional': short_exposure,
                    'net_exposure': long_exposure - short_exposure,
                    'long_percentage': long_exposure / total_exposure if total_exposure > 0 else 0,
                    'short_percentage': short_exposure / total_exposure if total_exposure > 0 else 0
                },
                'market_type_exposure': {
                    'perpetual': perp_exposure,
                    'spot': spot_exposure
                },
                'concentration_metrics': {
                    'top_3_concentration': top_3_concentration,
                    'herfindahl_index': hhi,
                    'effective_positions': 1 / hhi if hhi > 0 else 0,
                    'concentration_level': 'high' if hhi > 0.25 else 'moderate' if hhi > 0.15 else 'low'
                },
                'diversification_score': 1 - hhi,
                'position_count': len(portfolio_state.positions),
                'calculation_time': datetime.now().isoformat()
            }
            
            return analysis
            
        except Exception as e:
            self.logger.error(f"Error analyzing position exposure: {e}")
            return {}
    
    async def get_trading_statistics(self, days: int = 30) -> Dict[str, Any]:
        """
        Get comprehensive trading statistics.
        
        Args:
            days: Number of days for statistics calculation
            
        Returns:
            Dictionary with trading statistics
        """
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)
            
            trades = await self.get_trade_history(start_time, end_time)
            
            if not trades:
                return {}
            
            # Basic statistics
            total_trades = len(trades)
            winning_trades = len([t for t in trades if t.estimated_pnl > 0])
            losing_trades = len([t for t in trades if t.estimated_pnl < 0])
            breakeven_trades = total_trades - winning_trades - losing_trades
            
            # PnL statistics
            total_pnl = sum(trade.estimated_pnl for trade in trades)
            total_fees = sum(trade.total_fees for trade in trades)
            net_pnl = total_pnl - total_fees
            
            # Win/Loss metrics
            win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
            
            winning_pnls = [t.estimated_pnl for t in trades if t.estimated_pnl > 0]
            losing_pnls = [t.estimated_pnl for t in trades if t.estimated_pnl < 0]
            
            avg_win = sum(winning_pnls) / len(winning_pnls) if winning_pnls else 0.0
            avg_loss = sum(losing_pnls) / len(losing_pnls) if losing_pnls else 0.0
            
            largest_win = max(winning_pnls) if winning_pnls else 0.0
            largest_loss = min(losing_pnls) if losing_pnls else 0.0
            
            # Profit factor
            gross_profit = sum(winning_pnls) if winning_pnls else 0.0
            gross_loss = abs(sum(losing_pnls)) if losing_pnls else 0.0
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
            
            # Execution quality
            avg_slippage = sum(abs(t.slippage) for t in trades) / total_trades if total_trades > 0 else 0.0
            avg_execution_time = sum(t.execution_time_ms for t in trades) / total_trades if total_trades > 0 else 0.0
            
            fill_rates = [t.fill_rate for t in trades if hasattr(t, 'fill_rate')]
            avg_fill_rate = sum(fill_rates) / len(fill_rates) if fill_rates else 100.0
            
            # Market breakdown
            market_stats = {}
            for trade in trades:
                market = trade.market
                if market not in market_stats:
                    market_stats[market] = {
                        'trades': 0,
                        'pnl': 0.0,
                        'fees': 0.0,
                        'volume': 0.0
                    }
                
                market_stats[market]['trades'] += 1
                market_stats[market]['pnl'] += trade.estimated_pnl
                market_stats[market]['fees'] += trade.total_fees
                market_stats[market]['volume'] += trade.notional_value
            
            statistics = {
                'period_days': days,
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'breakeven_trades': breakeven_trades,
                'win_rate': win_rate,
                'pnl_metrics': {
                    'total_pnl': total_pnl,
                    'total_fees': total_fees,
                    'net_pnl': net_pnl,
                    'avg_win': avg_win,
                    'avg_loss': avg_loss,
                    'largest_win': largest_win,
                    'largest_loss': largest_loss,
                    'profit_factor': profit_factor,
                    'expectancy': total_pnl / total_trades if total_trades > 0 else 0.0
                },
                'execution_quality': {
                    'avg_slippage': avg_slippage,
                    'avg_execution_time_ms': avg_execution_time,
                    'avg_fill_rate': avg_fill_rate
                },
                'market_breakdown': market_stats,
                'calculation_time': datetime.now().isoformat()
            }
            
            return statistics
            
        except Exception as e:
            self.logger.error(f"Error calculating trading statistics: {e}")
            return {}
    
    # ==========================================================================
    # UTILITY METHODS
    # ==========================================================================
    
    async def is_position_open(self, market: str) -> bool:
        """
        Check if a position is open in a specific market.
        
        Args:
            market: Market identifier
            
        Returns:
            True if position exists and has non-zero size
        """
        try:
            position = await self.get_position(market)
            return position is not None and abs(position.size) > 1e-8
        except Exception as e:
            self.logger.error(f"Error checking position for {market}: {e}")
            return False
    
    async def get_net_exposure(self, asset: str) -> float:
        """
        Get net exposure for a specific asset across all markets.
        
        Args:
            asset: Asset identifier (e.g., "SOL")
            
        Returns:
            Net exposure (positive = long, negative = short)
        """
        try:
            positions = await self.get_positions()
            
            net_exposure = 0.0
            for position in positions:
                if asset in position.market:
                    net_exposure += position.size * position.mark_price
            
            return net_exposure
            
        except Exception as e:
            self.logger.error(f"Error calculating net exposure for {asset}: {e}")
            return 0.0
    
    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
    
    def set_cache_ttl(self, ttl_seconds: int) -> None:
        """Set cache TTL in seconds."""
        self._cache_ttl = ttl_seconds