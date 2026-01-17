"""
Drift Portfolio Data Provider
============================

Concrete implementation of PortfolioDataProvider for Drift Protocol.
Integrates with Drift's account and position APIs.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from .portfolio_data_provider import PortfolioDataProvider
from ..models.portfolio import PortfolioState, Position
from ..models.trading import TradeResult, OrderSide, ExecutionQuality
from src.shared.system.logging import Logger


class DriftPortfolioDataProvider(PortfolioDataProvider):
    """
    Concrete portfolio data provider for Drift Protocol.
    
    Integrates with Drift's account APIs to provide real-time portfolio
    state, position data, and trade history.
    """
    
    def __init__(self, drift_adapter):
        """
        Initialize Drift portfolio data provider.
        
        Args:
            drift_adapter: DriftAdapter instance for API access
        """
        super().__init__()
        self.drift_adapter = drift_adapter
        self.logger = Logger
        
        # Portfolio data cache with shorter TTL for real-time data
        self.set_cache_ttl(15)  # 15 seconds for portfolio data
        
        self.logger.info("Drift Portfolio Data Provider initialized")
    
    async def get_portfolio_state(self) -> Optional[PortfolioState]:
        """
        Get current portfolio state from Drift Protocol.
        
        Returns:
            Current PortfolioState or None if unavailable
        """
        try:
            cache_key = self._get_cache_key("portfolio_state")
            
            # Check cache first
            if self._is_cache_valid(cache_key):
                cached_data = self._get_from_cache(cache_key)
                if cached_data:
                    return cached_data
            
            # Get account data from Drift
            account_data = await self.drift_adapter.get_user_account()
            
            if not account_data:
                return None
            
            # Get positions
            positions = await self.get_positions()
            
            # Extract portfolio metrics from account data
            total_collateral = float(account_data.get('total_collateral', 0))
            unrealized_pnl = float(account_data.get('unrealized_pnl', 0))
            total_value = total_collateral + unrealized_pnl
            
            # Calculate margin metrics
            margin_used = float(account_data.get('total_position_value', 0))
            margin_available = float(account_data.get('free_collateral', 0))
            
            # Calculate health and leverage
            health_ratio = float(account_data.get('health', 1.0))
            leverage = margin_used / total_collateral if total_collateral > 0 else 0.0
            buying_power = margin_available * 5  # Assuming 5x max leverage
            
            # Create portfolio state
            portfolio_state = PortfolioState(
                total_value=total_value,
                total_collateral=total_collateral,
                unrealized_pnl=unrealized_pnl,
                realized_pnl=float(account_data.get('settled_pnl', 0)),
                margin_used=margin_used,
                margin_available=margin_available,
                health_ratio=health_ratio,
                leverage=leverage,
                buying_power=buying_power,
                positions=positions,
                position_count=len(positions),
                last_updated=datetime.now(),
                account_id=str(account_data.get('authority', '')),
                subaccount_id=str(account_data.get('sub_account_id', 0)),
                daily_pnl=float(account_data.get('pnl_pool', {}).get('scaled_balance', 0)),
                funding_payments=float(account_data.get('cumulative_funding_rate_delta', 0)),
                fees_paid=0.0  # Would need separate API call for fees
            )
            
            # Cache the result
            self._set_cache(cache_key, portfolio_state)
            
            return portfolio_state
            
        except Exception as e:
            self.logger.error(f"Error getting portfolio state: {e}")
            return None
    
    async def get_positions(self) -> List[Position]:
        """
        Get all current positions from Drift Protocol.
        
        Returns:
            List of current positions
        """
        try:
            cache_key = self._get_cache_key("positions")
            
            # Check cache
            if self._is_cache_valid(cache_key):
                cached_data = self._get_from_cache(cache_key)
                if cached_data:
                    return cached_data
            
            # Get positions from Drift
            positions_data = await self.drift_adapter.get_positions()
            
            if not positions_data:
                return []
            
            positions = []
            for pos_data in positions_data:
                # Skip zero positions
                base_asset_amount = float(pos_data.get('base_asset_amount', 0))
                if abs(base_asset_amount) < 1e-8:
                    continue
                
                # Get market info
                market_index = pos_data.get('market_index', 0)
                market_name = await self._get_market_name(market_index)
                
                # Calculate position metrics
                mark_price = float(pos_data.get('mark_price', 0))
                entry_price = float(pos_data.get('average_entry_price', 0))
                
                # Determine side
                side = "long" if base_asset_amount > 0 else "short"
                
                # Calculate PnL
                unrealized_pnl = float(pos_data.get('unrealized_pnl', 0))
                realized_pnl = float(pos_data.get('realized_pnl', 0))
                
                # Calculate margin requirement
                margin_requirement = float(pos_data.get('margin_requirement', 0))
                
                position = Position(
                    market=market_name,
                    side=side,
                    size=base_asset_amount,
                    entry_price=entry_price,
                    mark_price=mark_price,
                    unrealized_pnl=unrealized_pnl,
                    realized_pnl=realized_pnl,
                    margin_requirement=margin_requirement,
                    last_updated=datetime.now(),
                    position_id=str(pos_data.get('position_index', '')),
                    funding_payments=float(pos_data.get('last_cumulative_funding_rate', 0))
                )
                
                positions.append(position)
            
            # Cache the result
            self._set_cache(cache_key, positions)
            
            return positions
            
        except Exception as e:
            self.logger.error(f"Error getting positions: {e}")
            return []
    
    async def get_position(self, market: str) -> Optional[Position]:
        """
        Get position for a specific market.
        
        Args:
            market: Market identifier
            
        Returns:
            Position or None if no position exists
        """
        try:
            positions = await self.get_positions()
            
            for position in positions:
                if position.market == market:
                    return position
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting position for {market}: {e}")
            return None
    
    async def get_trade_history(
        self, 
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[TradeResult]:
        """
        Get trade history from Drift Protocol.
        
        Args:
            start_time: Start time for history
            end_time: End time for history
            limit: Maximum number of trades to return
            
        Returns:
            List of trade results
        """
        try:
            # Set default time range if not provided
            if not end_time:
                end_time = datetime.now()
            if not start_time:
                start_time = end_time - timedelta(days=7)  # Default 7 days
            
            cache_key = self._get_cache_key("trade_history", start_time.isoformat(), end_time.isoformat(), limit)
            
            # Check cache
            cached_data = self._get_from_cache(cache_key)
            if cached_data:
                return cached_data
            
            # Get trade history from Drift
            trades_data = await self.drift_adapter.get_trade_history(
                start_time=start_time,
                end_time=end_time,
                limit=limit
            )
            
            if not trades_data:
                return []
            
            trade_results = []
            for trade_data in trades_data:
                # Get market name
                market_index = trade_data.get('market_index', 0)
                market_name = await self._get_market_name(market_index)
                
                # Parse trade data
                base_asset_amount = float(trade_data.get('base_asset_amount', 0))
                side = OrderSide.BUY if base_asset_amount > 0 else OrderSide.SELL
                
                executed_size = abs(base_asset_amount)
                price = float(trade_data.get('price', 0))
                
                # Calculate metrics
                notional_value = executed_size * price
                fees = float(trade_data.get('fee', 0))
                
                # Parse timestamps
                execution_time = self._parse_timestamp(trade_data.get('ts'))
                
                # Create trade result
                trade_result = TradeResult(
                    trade_id=str(trade_data.get('order_id', '')),
                    market=market_name,
                    side=side,
                    requested_size=executed_size,  # Assume fully filled
                    executed_size=executed_size,
                    average_price=price,
                    notional_value=notional_value,
                    total_fees=fees,
                    estimated_pnl=0.0,  # Would need additional calculation
                    slippage=0.0,  # Would need order price vs execution price
                    execution_time_ms=0.0,  # Would need order submission time
                    execution_quality=ExecutionQuality.GOOD,  # Default assumption
                    market_impact_bps=0.0,  # Would need market data
                    execution_start=execution_time or datetime.now(),
                    execution_end=execution_time or datetime.now(),
                    success=True,
                    partial_fill=False
                )
                
                trade_results.append(trade_result)
            
            # Sort by execution time (most recent first)
            trade_results.sort(key=lambda x: x.execution_end, reverse=True)
            
            # Cache the result
            self._set_cache(cache_key, trade_results)
            
            return trade_results
            
        except Exception as e:
            self.logger.error(f"Error getting trade history: {e}")
            return []
    
    async def get_portfolio_value_history(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        resolution: str = "1h"
    ) -> List[Dict[str, Any]]:
        """
        Get portfolio value history from Drift Protocol.
        
        Args:
            start_time: Start time for history
            end_time: End time for history
            resolution: Data resolution ("1m", "5m", "1h", "1d")
            
        Returns:
            List of portfolio value snapshots
        """
        try:
            # Set default time range if not provided
            if not end_time:
                end_time = datetime.now()
            if not start_time:
                start_time = end_time - timedelta(days=30)  # Default 30 days
            
            cache_key = self._get_cache_key("portfolio_value_history", start_time.isoformat(), end_time.isoformat(), resolution)
            
            # Check cache
            cached_data = self._get_from_cache(cache_key)
            if cached_data:
                return cached_data
            
            # Get portfolio value history from Drift
            # Note: This might not be directly available and may need to be constructed
            # from position history and market data
            
            value_history_data = await self.drift_adapter.get_portfolio_value_history(
                start_time=start_time,
                end_time=end_time,
                resolution=resolution
            )
            
            if not value_history_data:
                # Fallback: construct from current state
                current_state = await self.get_portfolio_state()
                if current_state:
                    return [{
                        'timestamp': datetime.now(),
                        'total_value': current_state.total_value,
                        'total_collateral': current_state.total_collateral,
                        'unrealized_pnl': current_state.unrealized_pnl,
                        'realized_pnl': current_state.realized_pnl,
                        'estimated_delta': current_state.get_portfolio_delta()
                    }]
                return []
            
            # Convert to standard format
            value_history = []
            for data_point in value_history_data:
                value_snapshot = {
                    'timestamp': self._parse_timestamp(data_point.get('timestamp')),
                    'total_value': float(data_point.get('total_value', 0)),
                    'total_collateral': float(data_point.get('total_collateral', 0)),
                    'unrealized_pnl': float(data_point.get('unrealized_pnl', 0)),
                    'realized_pnl': float(data_point.get('realized_pnl', 0)),
                    'margin_used': float(data_point.get('margin_used', 0)),
                    'health_ratio': float(data_point.get('health_ratio', 1.0)),
                    'leverage': float(data_point.get('leverage', 0)),
                    'estimated_delta': float(data_point.get('estimated_delta', 0))
                }
                value_history.append(value_snapshot)
            
            # Cache the result
            self._set_cache(cache_key, value_history)
            
            return value_history
            
        except Exception as e:
            self.logger.error(f"Error getting portfolio value history: {e}")
            return []
    
    # ==========================================================================
    # DRIFT-SPECIFIC METHODS
    # ==========================================================================
    
    async def get_account_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive account summary.
        
        Returns:
            Dictionary with account summary
        """
        try:
            account_data = await self.drift_adapter.get_user_account()
            
            if not account_data:
                return {}
            
            # Get additional data
            positions = await self.get_positions()
            recent_trades = await self.get_trade_history(limit=10)
            
            summary = {
                'account_id': str(account_data.get('authority', '')),
                'subaccount_id': str(account_data.get('sub_account_id', 0)),
                'total_collateral': float(account_data.get('total_collateral', 0)),
                'free_collateral': float(account_data.get('free_collateral', 0)),
                'unrealized_pnl': float(account_data.get('unrealized_pnl', 0)),
                'health_ratio': float(account_data.get('health', 1.0)),
                'leverage': float(account_data.get('leverage', 0)),
                'position_count': len(positions),
                'recent_trades_count': len(recent_trades),
                'last_updated': datetime.now().isoformat()
            }
            
            return summary
            
        except Exception as e:
            self.logger.error(f"Error getting account summary: {e}")
            return {}
    
    async def get_funding_payments(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get funding payment history.
        
        Args:
            days: Number of days of history
            
        Returns:
            List of funding payments
        """
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)
            
            funding_data = await self.drift_adapter.get_funding_payments(
                start_time=start_time,
                end_time=end_time
            )
            
            if not funding_data:
                return []
            
            funding_payments = []
            for payment_data in funding_data:
                market_index = payment_data.get('market_index', 0)
                market_name = await self._get_market_name(market_index)
                
                payment = {
                    'timestamp': self._parse_timestamp(payment_data.get('ts')),
                    'market': market_name,
                    'funding_rate': float(payment_data.get('funding_rate', 0)),
                    'payment_amount': float(payment_data.get('funding_payment', 0)),
                    'position_size': float(payment_data.get('base_asset_amount', 0))
                }
                funding_payments.append(payment)
            
            return funding_payments
            
        except Exception as e:
            self.logger.error(f"Error getting funding payments: {e}")
            return []
    
    async def get_order_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get order history.
        
        Args:
            limit: Maximum number of orders to return
            
        Returns:
            List of order history
        """
        try:
            orders_data = await self.drift_adapter.get_order_history(limit=limit)
            
            if not orders_data:
                return []
            
            orders = []
            for order_data in orders_data:
                market_index = order_data.get('market_index', 0)
                market_name = await self._get_market_name(market_index)
                
                order = {
                    'order_id': str(order_data.get('order_id', '')),
                    'market': market_name,
                    'side': 'buy' if float(order_data.get('base_asset_amount', 0)) > 0 else 'sell',
                    'size': abs(float(order_data.get('base_asset_amount', 0))),
                    'price': float(order_data.get('price', 0)),
                    'order_type': order_data.get('order_type', 'market'),
                    'status': order_data.get('status', 'unknown'),
                    'timestamp': self._parse_timestamp(order_data.get('ts')),
                    'filled_size': float(order_data.get('base_asset_amount_filled', 0)),
                    'fees': float(order_data.get('fee', 0))
                }
                orders.append(order)
            
            return orders
            
        except Exception as e:
            self.logger.error(f"Error getting order history: {e}")
            return []
    
    # ==========================================================================
    # UTILITY METHODS
    # ==========================================================================
    
    async def _get_market_name(self, market_index: int) -> str:
        """Get market name from market index."""
        try:
            # This would typically involve a lookup table or API call
            # For now, use a simple mapping
            market_map = {
                0: 'SOL-PERP',
                1: 'BTC-PERP',
                2: 'ETH-PERP',
                # Add more markets as needed
            }
            
            return market_map.get(market_index, f'MARKET-{market_index}')
            
        except Exception:
            return f'MARKET-{market_index}'
    
    def _parse_timestamp(self, timestamp_data: Any) -> Optional[datetime]:
        """Parse timestamp from various formats."""
        if not timestamp_data:
            return None
        
        try:
            if isinstance(timestamp_data, datetime):
                return timestamp_data
            elif isinstance(timestamp_data, (int, float)):
                # Unix timestamp (handle both seconds and microseconds)
                if timestamp_data > 1e10:  # Microseconds
                    return datetime.fromtimestamp(timestamp_data / 1e6)
                else:  # Seconds
                    return datetime.fromtimestamp(timestamp_data)
            elif isinstance(timestamp_data, str):
                # ISO format string
                return datetime.fromisoformat(timestamp_data.replace('Z', '+00:00'))
            else:
                return None
        except Exception:
            return None