"""
Virtual Driver
==============
Paper trading execution layer for the Phantom Arbiter Trading OS.

Intercepts trade orders and simulates fills using live market prices,
recording everything to the SQLite paper_trades table instead of
executing on-chain.

Features:
- Uses live price feeds for realistic simulation
- Tracks simulated P&L in paper_wallet
- Full order lifecycle (fills, partials, rejects)
- Slippage simulation (0.1-0.3% based on size)
- Fee calculation
- Settled vs unsettled PnL tracking
- Funding rate accrual (8-hour cycles)
- Leverage limits (10x for paper mode)
- Maintenance margin calculation (5% for SOL-PERP)
"""

import time
import asyncio
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import uuid

from src.shared.system.persistence import get_db
from src.shared.system.logging import Logger
from src.shared.state.vault_manager import get_engine_vault


class ExecutionMode(Enum):
    """Engine execution mode."""
    PAPER = "paper"
    LIVE = "live"


@dataclass
class VirtualPosition:
    """Represents a simulated position with PnL tracking."""
    symbol: str
    side: str  # "long" or "short"
    size: float
    entry_price: float
    leverage: float
    settled_pnl: float = 0.0
    unsettled_pnl: float = 0.0
    last_funding_time: float = field(default_factory=time.time)
    opened_at: float = field(default_factory=time.time)
    
    def calculate_unrealized_pnl(self, current_price: float) -> float:
        """Calculate unrealized PnL based on current price."""
        if self.side == "long":
            return (current_price - self.entry_price) * self.size
        else:  # short
            return (self.entry_price - current_price) * self.size
    
    def calculate_maintenance_margin(self, current_price: float, margin_rate: float = 0.05) -> float:
        """Calculate maintenance margin requirement."""
        notional = self.size * current_price
        return notional * margin_rate


@dataclass
class VirtualOrder:
    """Represents a simulated order."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    engine: str = ""
    symbol: str = ""
    side: str = ""  # "buy" or "sell"
    size: float = 0.0
    order_type: str = "market"  # "market" or "limit"
    limit_price: Optional[float] = None
    status: str = "pending"
    filled_size: float = 0.0
    filled_price: float = 0.0
    fee: float = 0.0
    created_at: float = field(default_factory=time.time)
    executed_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class VirtualDriver:
    """
    Paper trading execution driver.
    
    Simulates order execution using live market prices but records
    trades to the paper_trades table instead of executing on-chain.
    
    Enhanced features:
    - Settled vs unsettled PnL tracking
    - Funding rate accrual (8-hour cycles)
    - Realistic slippage (0.1-0.3% based on size)
    - Leverage limits (10x for paper mode)
    - Maintenance margin calculation (5% for SOL-PERP)
    """
    
    # Default fee rate (0.1% = 10 bps)
    DEFAULT_FEE_RATE = 0.001
    
    # Slippage simulation (size-based)
    MIN_SLIPPAGE = 0.001  # 0.1% for small trades
    MAX_SLIPPAGE = 0.003  # 0.3% for large trades
    SLIPPAGE_SIZE_THRESHOLD = 10.0  # SOL
    
    # Leverage limits
    MAX_LEVERAGE_PAPER = 10.0
    
    # Maintenance margin rate (5% for SOL-PERP)
    MAINTENANCE_MARGIN_RATE = 0.05
    
    # Funding rate cycle (8 hours in seconds)
    FUNDING_CYCLE_SECONDS = 8 * 60 * 60
    
    def __init__(self, engine_name: str, initial_balances: Dict[str, float] = None):
        """
        Initialize the virtual driver.
        
        Args:
            engine_name: Name of the engine using this driver
            initial_balances: Starting paper wallet balances
        """
        self.engine_name = engine_name
        self.db = get_db()
        
        # Initialize paper wallet if provided
        if initial_balances:
            self._init_paper_wallet(initial_balances)
        
        # Order callback for notifications
        self._on_fill_callback: Optional[Callable] = None
        
        # Price feed (set externally)
        self._current_prices: Dict[str, float] = {}
        
        # Position tracking (in-memory for performance)
        self.positions: Dict[str, VirtualPosition] = {}
        
        # Funding rate tracking
        self._funding_rates: Dict[str, float] = {}  # symbol -> rate per 8h
    
    def _init_paper_wallet(self, balances: Dict[str, float]):
        """Initialize paper wallet via EngineVault."""
        vault = get_engine_vault(self.engine_name)
        # Clear existing balances
        vault._clear_vault()
        # Set new balances
        vault.balances = dict(balances)
        vault._save_state()
            
        Logger.info(f"[PAPER] Initialized engine vault [{self.engine_name}]: {balances}")
    
    def set_price_feed(self, prices: Dict[str, float]):
        """Update current prices for execution."""
        self._current_prices.update(prices)
    
    def set_funding_rates(self, rates: Dict[str, float]):
        """Update funding rates (per 8-hour cycle)."""
        self._funding_rates.update(rates)
    
    def set_on_fill_callback(self, callback: Callable):
        """Set callback for fill notifications."""
        self._on_fill_callback = callback
    
    def _calculate_slippage(self, size: float) -> float:
        """Calculate slippage based on trade size (0.1-0.3%)."""
        if size <= self.SLIPPAGE_SIZE_THRESHOLD:
            return self.MIN_SLIPPAGE
        
        # Linear interpolation between min and max
        ratio = min(size / (self.SLIPPAGE_SIZE_THRESHOLD * 5), 1.0)
        return self.MIN_SLIPPAGE + (self.MAX_SLIPPAGE - self.MIN_SLIPPAGE) * ratio
    
    def _check_leverage_limit(self, new_position_size: float, current_price: float) -> bool:
        """Check if new position would exceed leverage limit."""
        vault = get_engine_vault(self.engine_name)
        total_collateral = sum(vault.balances.values())  # Simplified
        
        if total_collateral <= 0:
            return False
        
        notional = new_position_size * current_price
        leverage = notional / total_collateral
        
        return leverage <= self.MAX_LEVERAGE_PAPER
    
    def calculate_health_ratio(self) -> float:
        """
        Calculate health ratio: (total_collateral - maint_margin) / total_collateral * 100.
        
        Returns:
            Health ratio in range [0, 100]
        """
        vault = get_engine_vault(self.engine_name)
        total_collateral = sum(vault.balances.values())
        
        # Calculate total maintenance margin
        total_maint_margin = 0.0
        for symbol, position in self.positions.items():
            current_price = self._current_prices.get(symbol, position.entry_price)
            total_maint_margin += position.calculate_maintenance_margin(
                current_price, self.MAINTENANCE_MARGIN_RATE
            )
        
        # Edge case: no collateral = liquidated
        if total_collateral <= 1e-10:  # Floating point tolerance
            return 0.0
        
        # Normal case
        health = ((total_collateral - total_maint_margin) / total_collateral) * 100
        return max(0.0, min(100.0, health))
    
    def apply_funding_rate(self, symbol: str, rate_8h: float):
        """
        Apply funding rate to position (simulates 8-hour funding payment).
        
        Args:
            symbol: Market symbol (e.g., "SOL-PERP")
            rate_8h: Funding rate for 8-hour period (e.g., 0.0001 = 0.01%)
        """
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        current_price = self._current_prices.get(symbol, position.entry_price)
        
        # Calculate funding payment
        notional = position.size * current_price
        funding_payment = notional * rate_8h
        
        # For shorts, we receive funding if rate is positive
        if position.side == "short":
            funding_payment = -funding_payment
        
        # Add to unsettled PnL
        position.unsettled_pnl += funding_payment
        position.last_funding_time = time.time()
        
        Logger.debug(f"[PAPER] Funding applied to {symbol}: ${funding_payment:.4f}")
    
    def settle_pnl(self, symbol: str):
        """Move unsettled PnL to settled PnL."""
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        position.settled_pnl += position.unsettled_pnl
        position.unsettled_pnl = 0.0
        
        Logger.debug(f"[PAPER] PnL settled for {symbol}: ${position.settled_pnl:.4f}")
    
    def get_balances(self) -> Dict[str, float]:
        """Get current paper wallet balances."""
        vault = get_engine_vault(self.engine_name)
        return vault.balances.copy()
    
    def set_balance(self, asset: str, amount: float):
        """Set balance for an asset."""
        vault = get_engine_vault(self.engine_name)
        current = vault.balances.get(asset, 0.0)
        diff = amount - current
        
        if diff > 0:
            vault.credit(asset, diff)
        elif diff < 0:
            vault.debit(asset, abs(diff))
    
    # ═══════════════════════════════════════════════════════════════
    # ORDER EXECUTION
    # ═══════════════════════════════════════════════════════════════
    
    async def place_order(self, order: VirtualOrder) -> VirtualOrder:
        """
        Simulate placing an order.
        
        For market orders, fills immediately at current price + slippage.
        For limit orders, checks if limit price is met.
        
        Returns:
            Updated order with fill details
        """
        order.engine = self.engine_name
        
        # Get current price
        current_price = self._current_prices.get(order.symbol)
        if current_price is None:
            order.status = "rejected"
            order.metadata["error"] = f"No price feed for {order.symbol}"
            Logger.warning(f"[PAPER] Order rejected: no price for {order.symbol}")
            return order
        
        # For market orders, simulate fill
        if order.order_type == "market":
            return await self._fill_order(order, current_price)
        
        # For limit orders, check if price is met
        if order.order_type == "limit" and order.limit_price:
            if order.side == "buy" and current_price <= order.limit_price:
                return await self._fill_order(order, order.limit_price)
            elif order.side == "sell" and current_price >= order.limit_price:
                return await self._fill_order(order, order.limit_price)
            else:
                order.status = "pending"
                Logger.debug(f"[PAPER] Limit order pending: {order.id}")
                return order
        
        return order
    
    async def _fill_order(self, order: VirtualOrder, base_price: float) -> VirtualOrder:
        """Execute a fill at the given price with size-based slippage."""
        now = time.time()
        
        # Check leverage limit before fill
        if not self._check_leverage_limit(order.size, base_price):
            order.status = "rejected"
            order.metadata["error"] = f"Leverage limit exceeded (max {self.MAX_LEVERAGE_PAPER}x)"
            Logger.warning(f"[PAPER] Order rejected: leverage limit")
            return order
        
        # Apply size-based slippage (worse for taker)
        slippage = self._calculate_slippage(order.size)
        if order.side == "buy":
            fill_price = base_price * (1 + slippage)
        else:
            fill_price = base_price * (1 - slippage)
        
        # Calculate fee
        notional = order.size * fill_price
        fee = notional * self.DEFAULT_FEE_RATE
        
        # Update order
        order.filled_size = order.size
        order.filled_price = fill_price
        order.fee = fee
        order.status = "filled"
        order.executed_at = now
        
        # Update paper wallet
        await self._update_paper_wallet(order)
        
        # Update position tracking
        self._update_position_tracking(order)
        
        # Record paper trade
        await self._record_paper_trade(order)
        
        Logger.info(
            f"[PAPER] ✅ {order.side.upper()} {order.size:.4f} {order.symbol} "
            f"@ {fill_price:.2f} (slippage: {slippage*100:.2f}%)"
        )
        
        # Notify via callback
        if self._on_fill_callback:
            await self._on_fill_callback(order)
        
        return order
    
    def _update_position_tracking(self, order: VirtualOrder):
        """Update in-memory position tracking."""
        symbol = order.symbol
        
        if symbol not in self.positions:
            # New position
            side = "long" if order.side == "buy" else "short"
            self.positions[symbol] = VirtualPosition(
                symbol=symbol,
                side=side,
                size=order.filled_size,
                entry_price=order.filled_price,
                leverage=1.0  # Simplified
            )
        else:
            # Modify existing position
            position = self.positions[symbol]
            
            if order.side == "buy":
                if position.side == "short":
                    # Reducing short
                    position.size -= order.filled_size
                    if position.size <= 0:
                        # Position closed or flipped
                        del self.positions[symbol]
                else:
                    # Adding to long
                    # Weighted average entry price
                    total_cost = (position.size * position.entry_price + 
                                 order.filled_size * order.filled_price)
                    position.size += order.filled_size
                    position.entry_price = total_cost / position.size
            else:  # sell
                if position.side == "long":
                    # Reducing long
                    position.size -= order.filled_size
                    if position.size <= 0:
                        # Position closed or flipped
                        del self.positions[symbol]
                else:
                    # Adding to short
                    total_cost = (position.size * position.entry_price + 
                                 order.filled_size * order.filled_price)
                    position.size += order.filled_size
                    position.entry_price = total_cost / position.size
    
    async def _update_paper_wallet(self, order: VirtualOrder):
        """Update engine vault balances after fill."""
        vault = get_engine_vault(self.engine_name)
        
        # Parse symbol (e.g., "SOL-PERP" -> "SOL", "USDC")
        base_asset = order.symbol.split("-")[0]
        quote_asset = "USDC"
        
        # Calculate totals
        notional = order.filled_size * order.filled_price
        
        if order.side == "buy":
            # Buying: spend USDC, receive base asset
            debit_amt = notional + order.fee
            vault.debit(quote_asset, debit_amt)
            vault.credit(base_asset, order.filled_size)
        else:
            # Selling: spend base asset, receive USDC
            vault.debit(base_asset, order.filled_size)
            credit_amt = notional - order.fee
            vault.credit(quote_asset, credit_amt)
            
        Logger.debug(f"[PAPER] Vault [{self.engine_name}] updated via VirtualDriver")
    
    async def _record_paper_trade(self, order: VirtualOrder):
        """Record trade to paper_trades table."""
        conn = self.db._get_connection()
        
        conn.execute("""
            INSERT INTO paper_trades (engine, symbol, side, size, entry_price, 
                                      fee, status, opened_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order.engine, order.symbol, order.side, order.filled_size,
            order.filled_price, order.fee, "filled", order.executed_at,
            "{}"
        ))
        conn.commit()
    
    # ═══════════════════════════════════════════════════════════════
    # POSITION MANAGEMENT
    # ═══════════════════════════════════════════════════════════════
    
    async def open_position(self, symbol: str, side: str, size: float,
                           leverage: float = 1.0) -> Optional[VirtualOrder]:
        """Open a new paper position."""
        order = VirtualOrder(
            engine=self.engine_name,
            symbol=symbol,
            side=side,
            size=size,
            order_type="market"
        )
        
        filled_order = await self.place_order(order)
        
        if filled_order.status == "filled":
            # Position tracking handled in _update_position_tracking
            Logger.info(f"[PAPER] Position opened: {symbol} {side} {size}")
        
        return filled_order
    
    async def close_position(self, symbol: str) -> Optional[VirtualOrder]:
        """Close an existing paper position."""
        if symbol not in self.positions:
            Logger.warning(f"[PAPER] No position to close: {symbol}")
            return None
        
        position = self.positions[symbol]
        
        # Determine close side
        close_side = "sell" if position.side == "long" else "buy"
        
        order = VirtualOrder(
            engine=self.engine_name,
            symbol=symbol,
            side=close_side,
            size=position.size,
            order_type="market"
        )
        
        filled_order = await self.place_order(order)
        
        if filled_order.status == "filled":
            # Calculate realized P&L
            current_price = filled_order.filled_price
            pnl = position.calculate_unrealized_pnl(current_price)
            pnl += position.settled_pnl + position.unsettled_pnl
            pnl -= filled_order.fee
            
            Logger.info(f"[PAPER] Position closed: {symbol} PnL: ${pnl:.2f}")
        
        return filled_order
    
    def _update_paper_position(self, symbol: str, side: str, size: float,
                               entry_price: float, leverage: float):
        """Update paper position in database."""
        conn = self.db._get_connection()
        now = time.time()
        
        conn.execute("""
            INSERT INTO paper_positions (engine, symbol, side, size, entry_price,
                                        leverage, opened_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(engine, symbol) DO UPDATE SET
                side = excluded.side,
                size = excluded.size,
                entry_price = excluded.entry_price,
                updated_at = excluded.updated_at
        """, (
            self.engine_name, symbol, side, size, entry_price, leverage, now, now
        ))
        conn.commit()
    
    def _close_paper_position(self, symbol: str, exit_price: float, pnl: float):
        """Mark paper position as closed."""
        conn = self.db._get_connection()
        now = time.time()
        
        # Update position
        conn.execute("""
            UPDATE paper_positions 
            SET size = 0, side = 'flat', current_price = ?, unrealized_pnl = 0, updated_at = ?
            WHERE engine = ? AND symbol = ?
        """, (exit_price, now, self.engine_name, symbol))
        
        # Update paper trade with exit
        conn.execute("""
            UPDATE paper_trades 
            SET exit_price = ?, realized_pnl = ?, status = 'closed', closed_at = ?
            WHERE engine = ? AND symbol = ? AND status = 'filled'
            ORDER BY opened_at DESC LIMIT 1
        """, (exit_price, pnl, now, self.engine_name, symbol))
        
        conn.commit()
    
    # ═══════════════════════════════════════════════════════════════
    # BALANCE QUERIES
    # ═══════════════════════════════════════════════════════════════
    
    def get_paper_balance(self, asset: str) -> float:
        """Get current paper balance for an asset via EngineVault."""
        vault = get_engine_vault(self.engine_name)
        return vault.balances.get(asset, 0.0)
    
    def get_all_paper_balances(self) -> Dict[str, float]:
        """Get all paper wallet balances via EngineVault."""
        vault = get_engine_vault(self.engine_name)
        return vault.balances.copy()
    
    def get_paper_positions(self) -> list:
        """Get all open paper positions for this engine."""
        positions_list = []
        for symbol, position in self.positions.items():
            current_price = self._current_prices.get(symbol, position.entry_price)
            unrealized_pnl = position.calculate_unrealized_pnl(current_price)
            
            positions_list.append({
                "symbol": symbol,
                "side": position.side,
                "size": position.size,
                "entry_price": position.entry_price,
                "current_price": current_price,
                "leverage": position.leverage,
                "settled_pnl": position.settled_pnl,
                "unsettled_pnl": position.unsettled_pnl,
                "unrealized_pnl": unrealized_pnl,
                "total_pnl": position.settled_pnl + position.unsettled_pnl + unrealized_pnl,
                "opened_at": position.opened_at,
                "last_funding_time": position.last_funding_time
            })
        
        return positions_list
    
    def get_paper_pnl(self, since: float = None) -> Dict[str, float]:
        """Get paper trading P&L statistics for this engine."""
        # Calculate from in-memory positions
        settled = sum(p.settled_pnl for p in self.positions.values())
        unsettled = sum(p.unsettled_pnl for p in self.positions.values())
        
        unrealized = 0.0
        for symbol, position in self.positions.items():
            current_price = self._current_prices.get(symbol, position.entry_price)
            unrealized += position.calculate_unrealized_pnl(current_price)
        
        return {
            "settled": settled,
            "unsettled": unsettled,
            "unrealized": unrealized,
            "total": settled + unsettled + unrealized
        }
    
    def reset_paper_wallet(self, balances: Dict[str, float]):
        """Reset paper wallet to initial state."""
        conn = self.db._get_connection()
        
        # Clear positions and trades
        conn.execute("DELETE FROM paper_positions WHERE engine = ?", (self.engine_name,))
        conn.execute("DELETE FROM paper_trades WHERE engine = ?", (self.engine_name,))
        conn.commit()
        
        # Clear in-memory positions
        self.positions.clear()
        
        # Reset wallet via Vault
        self._init_paper_wallet(balances)
        
        Logger.info(f"[PAPER] Wallet reset: {balances}")
