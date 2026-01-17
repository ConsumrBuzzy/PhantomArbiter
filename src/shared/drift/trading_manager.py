"""
Drift Trading Manager
====================

Comprehensive trading operations manager for Drift Protocol.
Provides advanced order types, order management, and trading analytics.

Features:
- All order types (market, limit, stop, conditional)
- Order lifecycle management (place, modify, cancel)
- Advanced order options (post-only, time-in-force, reduce-only)
- Order history and analytics
- Risk-aware position sizing
- Automated order management

Usage:
    trading_manager = DriftTradingManager(drift_adapter)
    
    # Place limit order
    order_id = await trading_manager.place_limit_order(
        market="SOL-PERP",
        side="buy", 
        size=1.0,
        price=150.0,
        post_only=True
    )
    
    # Place stop-loss
    await trading_manager.place_stop_order(
        market="SOL-PERP",
        side="sell",
        size=1.0, 
        trigger_price=140.0
    )
"""

import asyncio
import time
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime, timedelta

from src.shared.system.logging import Logger


# =============================================================================
# ENUMS AND DATA STRUCTURES
# =============================================================================

class OrderType(Enum):
    """Order type enumeration."""
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"
    TAKE_PROFIT_MARKET = "take_profit_market"
    TAKE_PROFIT_LIMIT = "take_profit_limit"


class OrderSide(Enum):
    """Order side enumeration."""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """Order status enumeration."""
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class TimeInForce(Enum):
    """Time in force enumeration."""
    GTC = "gtc"  # Good Till Cancelled
    IOC = "ioc"  # Immediate Or Cancel
    FOK = "fok"  # Fill Or Kill
    GTT = "gtt"  # Good Till Time


@dataclass
class OrderCondition:
    """Conditional order trigger condition."""
    market: str
    condition_type: str  # "price_above", "price_below", "funding_rate_above", etc.
    threshold: float
    operator: str = "gte"  # "gte", "lte", "eq"


@dataclass
class Order:
    """Order data structure."""
    id: str
    market: str
    type: OrderType
    side: OrderSide
    size: float
    price: Optional[float]
    trigger_price: Optional[float]
    status: OrderStatus
    filled_size: float
    remaining_size: float
    average_fill_price: Optional[float]
    time_in_force: TimeInForce
    post_only: bool
    reduce_only: bool
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime]
    conditions: List[OrderCondition]
    metadata: Dict[str, Any]


@dataclass
class OrderParams:
    """Order parameters for placement."""
    market: str
    type: OrderType
    side: OrderSide
    size: float
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    time_in_force: TimeInForce = TimeInForce.GTC
    post_only: bool = False
    reduce_only: bool = False
    expires_at: Optional[datetime] = None
    conditions: List[OrderCondition] = None
    client_order_id: Optional[str] = None


@dataclass
class TradingStats:
    """Trading statistics and analytics."""
    total_orders: int
    filled_orders: int
    cancelled_orders: int
    total_volume: float
    total_fees: float
    average_fill_time: float
    fill_rate: float
    win_rate: float
    profit_factor: float
    sharpe_ratio: float


# =============================================================================
# DRIFT TRADING MANAGER
# =============================================================================

class DriftTradingManager:
    """
    Comprehensive trading operations manager for Drift Protocol.
    
    Provides advanced order types, order management, and trading analytics
    built on top of the DriftAdapter singleton pattern.
    """
    
    def __init__(self, drift_adapter):
        """
        Initialize trading manager.
        
        Args:
            drift_adapter: DriftAdapter instance (singleton-enabled)
        """
        self.drift_adapter = drift_adapter
        self._orders: Dict[str, Order] = {}
        self._order_callbacks: Dict[str, List[Callable]] = {}
        self._next_order_id = 1
        
        # Trading statistics
        self._stats = TradingStats(
            total_orders=0,
            filled_orders=0,
            cancelled_orders=0,
            total_volume=0.0,
            total_fees=0.0,
            average_fill_time=0.0,
            fill_rate=0.0,
            win_rate=0.0,
            profit_factor=0.0,
            sharpe_ratio=0.0
        )
    
    # =========================================================================
    # ORDER PLACEMENT METHODS
    # =========================================================================
    
    async def place_market_order(
        self,
        market: str,
        side: str,
        size: float,
        reduce_only: bool = False,
        client_order_id: Optional[str] = None
    ) -> str:
        """
        Place market order for immediate execution.
        
        Args:
            market: Market symbol (e.g., "SOL-PERP")
            side: Order side ("buy" or "sell")
            size: Order size in base asset
            reduce_only: Only reduce existing position
            client_order_id: Optional client-provided order ID
        
        Returns:
            Order ID string
        
        Raises:
            ValueError: Invalid parameters
            RuntimeError: Order placement failed
        """
        Logger.info(f"[TradingManager] Placing market order: {side} {size} {market}")
        
        # Validate parameters
        self._validate_order_params(market, side, size)
        
        try:
            # Use existing DriftAdapter market order functionality
            if side.lower() == "buy":
                tx_sig = await self.drift_adapter.open_position(
                    market=market,
                    direction="long",
                    size=size
                )
            else:
                tx_sig = await self.drift_adapter.open_position(
                    market=market,
                    direction="short", 
                    size=size
                )
            
            # Create order record
            order_id = self._generate_order_id(client_order_id)
            order = Order(
                id=order_id,
                market=market,
                type=OrderType.MARKET,
                side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
                size=size,
                price=None,
                trigger_price=None,
                status=OrderStatus.FILLED,  # Market orders fill immediately
                filled_size=size,
                remaining_size=0.0,
                average_fill_price=None,  # Will be updated from transaction
                time_in_force=TimeInForce.IOC,
                post_only=False,
                reduce_only=reduce_only,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                expires_at=None,
                conditions=[],
                metadata={"tx_signature": tx_sig}
            )
            
            # Store order
            self._orders[order_id] = order
            self._update_stats(order)
            
            Logger.success(f"[TradingManager] ✅ Market order placed: {order_id}")
            return order_id
            
        except Exception as e:
            Logger.error(f"[TradingManager] Market order failed: {e}")
            raise RuntimeError(f"Market order placement failed: {e}")
    
    async def place_limit_order(
        self,
        market: str,
        side: str,
        size: float,
        price: float,
        time_in_force: str = "GTC",
        post_only: bool = False,
        reduce_only: bool = False,
        expires_at: Optional[datetime] = None,
        client_order_id: Optional[str] = None
    ) -> str:
        """
        Place limit order with specified price.
        
        Args:
            market: Market symbol (e.g., "SOL-PERP")
            side: Order side ("buy" or "sell")
            size: Order size in base asset
            price: Limit price
            time_in_force: Time in force ("GTC", "IOC", "FOK", "GTT")
            post_only: Only place as maker order
            reduce_only: Only reduce existing position
            expires_at: Expiration time (required for GTT)
            client_order_id: Optional client-provided order ID
        
        Returns:
            Order ID string
        
        Raises:
            ValueError: Invalid parameters
            RuntimeError: Order placement failed
        """
        Logger.info(f"[TradingManager] Placing limit order: {side} {size} {market} @ ${price}")
        
        # Validate parameters
        self._validate_order_params(market, side, size, price)
        self._validate_time_in_force(time_in_force, expires_at)
        
        try:
            # TODO: Implement actual Drift SDK limit order placement
            # For now, create pending order that will be managed by order engine
            
            order_id = self._generate_order_id(client_order_id)
            order = Order(
                id=order_id,
                market=market,
                type=OrderType.LIMIT,
                side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
                size=size,
                price=price,
                trigger_price=None,
                status=OrderStatus.OPEN,
                filled_size=0.0,
                remaining_size=size,
                average_fill_price=None,
                time_in_force=TimeInForce(time_in_force.lower()),
                post_only=post_only,
                reduce_only=reduce_only,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                expires_at=expires_at,
                conditions=[],
                metadata={}
            )
            
            # Store order
            self._orders[order_id] = order
            self._update_stats(order)
            
            # TODO: Submit to Drift Protocol
            # For now, simulate order management
            asyncio.create_task(self._monitor_limit_order(order_id))
            
            Logger.success(f"[TradingManager] ✅ Limit order placed: {order_id}")
            return order_id
            
        except Exception as e:
            Logger.error(f"[TradingManager] Limit order failed: {e}")
            raise RuntimeError(f"Limit order placement failed: {e}")
    
    async def place_stop_order(
        self,
        market: str,
        side: str,
        size: float,
        trigger_price: float,
        limit_price: Optional[float] = None,
        reduce_only: bool = True,
        client_order_id: Optional[str] = None
    ) -> str:
        """
        Place stop-loss or take-profit order.
        
        Args:
            market: Market symbol (e.g., "SOL-PERP")
            side: Order side ("buy" or "sell")
            size: Order size in base asset
            trigger_price: Price that triggers the order
            limit_price: Limit price (if None, becomes stop-market order)
            reduce_only: Only reduce existing position (default: True)
            client_order_id: Optional client-provided order ID
        
        Returns:
            Order ID string
        
        Raises:
            ValueError: Invalid parameters
            RuntimeError: Order placement failed
        """
        order_type = OrderType.STOP_LIMIT if limit_price else OrderType.STOP_MARKET
        Logger.info(f"[TradingManager] Placing {order_type.value} order: {side} {size} {market} @ trigger ${trigger_price}")
        
        # Validate parameters
        self._validate_order_params(market, side, size, limit_price, trigger_price)
        
        try:
            order_id = self._generate_order_id(client_order_id)
            order = Order(
                id=order_id,
                market=market,
                type=order_type,
                side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
                size=size,
                price=limit_price,
                trigger_price=trigger_price,
                status=OrderStatus.OPEN,
                filled_size=0.0,
                remaining_size=size,
                average_fill_price=None,
                time_in_force=TimeInForce.GTC,
                post_only=False,
                reduce_only=reduce_only,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                expires_at=None,
                conditions=[],
                metadata={}
            )
            
            # Store order
            self._orders[order_id] = order
            self._update_stats(order)
            
            # Start monitoring for trigger
            asyncio.create_task(self._monitor_stop_order(order_id))
            
            Logger.success(f"[TradingManager] ✅ Stop order placed: {order_id}")
            return order_id
            
        except Exception as e:
            Logger.error(f"[TradingManager] Stop order failed: {e}")
            raise RuntimeError(f"Stop order placement failed: {e}")
    
    async def place_conditional_order(
        self,
        market: str,
        conditions: List[OrderCondition],
        order_params: OrderParams
    ) -> str:
        """
        Place conditional order with multiple triggers.
        
        Args:
            market: Market symbol (e.g., "SOL-PERP")
            conditions: List of conditions that must be met
            order_params: Order parameters to execute when triggered
        
        Returns:
            Order ID string
        
        Raises:
            ValueError: Invalid parameters
            RuntimeError: Order placement failed
        """
        Logger.info(f"[TradingManager] Placing conditional order: {len(conditions)} conditions")
        
        # Validate parameters
        if not conditions:
            raise ValueError("At least one condition required for conditional order")
        
        try:
            order_id = self._generate_order_id(order_params.client_order_id)
            order = Order(
                id=order_id,
                market=market,
                type=order_params.type,
                side=order_params.side,
                size=order_params.size,
                price=order_params.price,
                trigger_price=order_params.trigger_price,
                status=OrderStatus.PENDING,
                filled_size=0.0,
                remaining_size=order_params.size,
                average_fill_price=None,
                time_in_force=order_params.time_in_force,
                post_only=order_params.post_only,
                reduce_only=order_params.reduce_only,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                expires_at=order_params.expires_at,
                conditions=conditions,
                metadata={}
            )
            
            # Store order
            self._orders[order_id] = order
            self._update_stats(order)
            
            # Start monitoring conditions
            asyncio.create_task(self._monitor_conditional_order(order_id))
            
            Logger.success(f"[TradingManager] ✅ Conditional order placed: {order_id}")
            return order_id
            
        except Exception as e:
            Logger.error(f"[TradingManager] Conditional order failed: {e}")
            raise RuntimeError(f"Conditional order placement failed: {e}")
    
    # =========================================================================
    # ORDER MANAGEMENT METHODS
    # =========================================================================
    
    async def modify_order(
        self,
        order_id: str,
        new_price: Optional[float] = None,
        new_size: Optional[float] = None
    ) -> bool:
        """
        Modify existing order price or size.
        
        Args:
            order_id: Order ID to modify
            new_price: New limit price (optional)
            new_size: New order size (optional)
        
        Returns:
            True if modification successful
        
        Raises:
            ValueError: Order not found or invalid parameters
            RuntimeError: Modification failed
        """
        Logger.info(f"[TradingManager] Modifying order: {order_id}")
        
        if order_id not in self._orders:
            raise ValueError(f"Order not found: {order_id}")
        
        order = self._orders[order_id]
        
        if order.status not in [OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]:
            raise ValueError(f"Cannot modify order in status: {order.status}")
        
        try:
            # Update order parameters
            if new_price is not None:
                if order.type not in [OrderType.LIMIT, OrderType.STOP_LIMIT, OrderType.TAKE_PROFIT_LIMIT]:
                    raise ValueError("Cannot modify price for non-limit order")
                order.price = new_price
            
            if new_size is not None:
                if new_size <= order.filled_size:
                    raise ValueError("New size must be greater than filled size")
                order.size = new_size
                order.remaining_size = new_size - order.filled_size
            
            order.updated_at = datetime.now()
            
            # TODO: Submit modification to Drift Protocol
            
            Logger.success(f"[TradingManager] ✅ Order modified: {order_id}")
            return True
            
        except Exception as e:
            Logger.error(f"[TradingManager] Order modification failed: {e}")
            raise RuntimeError(f"Order modification failed: {e}")
    
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel specific order.
        
        Args:
            order_id: Order ID to cancel
        
        Returns:
            True if cancellation successful
        
        Raises:
            ValueError: Order not found
            RuntimeError: Cancellation failed
        """
        Logger.info(f"[TradingManager] Cancelling order: {order_id}")
        
        if order_id not in self._orders:
            raise ValueError(f"Order not found: {order_id}")
        
        order = self._orders[order_id]
        
        if order.status not in [OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED, OrderStatus.PENDING]:
            Logger.warning(f"[TradingManager] Order {order_id} already in final state: {order.status}")
            return True
        
        try:
            # Update order status
            order.status = OrderStatus.CANCELLED
            order.updated_at = datetime.now()
            
            # TODO: Submit cancellation to Drift Protocol
            
            self._stats.cancelled_orders += 1
            
            Logger.success(f"[TradingManager] ✅ Order cancelled: {order_id}")
            return True
            
        except Exception as e:
            Logger.error(f"[TradingManager] Order cancellation failed: {e}")
            raise RuntimeError(f"Order cancellation failed: {e}")
    
    async def cancel_all_orders(self, market: Optional[str] = None) -> int:
        """
        Cancel all orders, optionally filtered by market.
        
        Args:
            market: Optional market filter (e.g., "SOL-PERP")
        
        Returns:
            Number of orders cancelled
        
        Raises:
            RuntimeError: Cancellation failed
        """
        Logger.info(f"[TradingManager] Cancelling all orders" + (f" for {market}" if market else ""))
        
        try:
            cancelled_count = 0
            
            for order_id, order in self._orders.items():
                # Filter by market if specified
                if market and order.market != market:
                    continue
                
                # Only cancel active orders
                if order.status in [OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED, OrderStatus.PENDING]:
                    await self.cancel_order(order_id)
                    cancelled_count += 1
            
            Logger.success(f"[TradingManager] ✅ Cancelled {cancelled_count} orders")
            return cancelled_count
            
        except Exception as e:
            Logger.error(f"[TradingManager] Bulk cancellation failed: {e}")
            raise RuntimeError(f"Bulk cancellation failed: {e}")
    
    # =========================================================================
    # ORDER QUERY METHODS
    # =========================================================================
    
    async def get_order(self, order_id: str) -> Optional[Order]:
        """
        Get specific order by ID.
        
        Args:
            order_id: Order ID to retrieve
        
        Returns:
            Order object or None if not found
        """
        return self._orders.get(order_id)
    
    async def get_open_orders(self, market: Optional[str] = None) -> List[Order]:
        """
        Get all open orders, optionally filtered by market.
        
        Args:
            market: Optional market filter (e.g., "SOL-PERP")
        
        Returns:
            List of open orders
        """
        open_orders = []
        
        for order in self._orders.values():
            # Filter by market if specified
            if market and order.market != market:
                continue
            
            # Only include active orders
            if order.status in [OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED, OrderStatus.PENDING]:
                open_orders.append(order)
        
        return open_orders
    
    async def get_order_history(
        self,
        market: Optional[str] = None,
        limit: int = 100,
        status_filter: Optional[OrderStatus] = None
    ) -> List[Order]:
        """
        Get order history with optional filtering.
        
        Args:
            market: Optional market filter (e.g., "SOL-PERP")
            limit: Maximum number of orders to return
            status_filter: Optional status filter
        
        Returns:
            List of historical orders
        """
        filtered_orders = []
        
        for order in self._orders.values():
            # Apply filters
            if market and order.market != market:
                continue
            
            if status_filter and order.status != status_filter:
                continue
            
            filtered_orders.append(order)
        
        # Sort by creation time (newest first) and limit
        filtered_orders.sort(key=lambda x: x.created_at, reverse=True)
        return filtered_orders[:limit]
    
    async def get_trading_stats(self) -> TradingStats:
        """
        Get comprehensive trading statistics.
        
        Returns:
            TradingStats object with current metrics
        """
        return self._stats
    
    # =========================================================================
    # PRIVATE HELPER METHODS
    # =========================================================================
    
    def _generate_order_id(self, client_order_id: Optional[str] = None) -> str:
        """Generate unique order ID."""
        if client_order_id:
            return f"client_{client_order_id}_{int(time.time())}"
        
        order_id = f"order_{self._next_order_id}_{int(time.time())}"
        self._next_order_id += 1
        return order_id
    
    def _validate_order_params(
        self,
        market: str,
        side: str,
        size: float,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None
    ):
        """Validate order parameters."""
        if not market:
            raise ValueError("Market is required")
        
        if side.lower() not in ["buy", "sell"]:
            raise ValueError("Side must be 'buy' or 'sell'")
        
        if size <= 0:
            raise ValueError("Size must be positive")
        
        if price is not None and price <= 0:
            raise ValueError("Price must be positive")
        
        if trigger_price is not None and trigger_price <= 0:
            raise ValueError("Trigger price must be positive")
    
    def _validate_time_in_force(self, time_in_force: str, expires_at: Optional[datetime]):
        """Validate time in force parameters."""
        if time_in_force.upper() == "GTT" and not expires_at:
            raise ValueError("expires_at is required for GTT orders")
        
        if expires_at and expires_at <= datetime.now():
            raise ValueError("expires_at must be in the future")
    
    def _update_stats(self, order: Order):
        """Update trading statistics."""
        self._stats.total_orders += 1
        
        if order.status == OrderStatus.FILLED:
            self._stats.filled_orders += 1
            self._stats.total_volume += order.size
        elif order.status == OrderStatus.CANCELLED:
            self._stats.cancelled_orders += 1
        
        # Update derived metrics
        if self._stats.total_orders > 0:
            self._stats.fill_rate = self._stats.filled_orders / self._stats.total_orders
    
    # =========================================================================
    # ORDER MONITORING TASKS
    # =========================================================================
    
    async def _monitor_limit_order(self, order_id: str):
        """Monitor limit order for execution."""
        # TODO: Implement limit order monitoring
        # This would check market price against limit price
        # and execute when conditions are met
        pass
    
    async def _monitor_stop_order(self, order_id: str):
        """Monitor stop order for trigger."""
        # TODO: Implement stop order monitoring
        # This would check market price against trigger price
        # and convert to market order when triggered
        pass
    
    async def _monitor_conditional_order(self, order_id: str):
        """Monitor conditional order for trigger conditions."""
        # TODO: Implement conditional order monitoring
        # This would check all conditions and execute order when met
        pass