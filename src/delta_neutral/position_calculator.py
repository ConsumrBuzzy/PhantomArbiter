"""
DNEM Position Calculator
========================
Pure math functions for delta neutral position sizing and rebalancing.

All functions are PURE LOGIC - no network or state dependencies.
This enables comprehensive unit testing without mocks.

Key formulas:
- Position Size: For $X at 1x leverage → $X/2 spot, $X/2 short
- Delta Drift: |(Spot Value) - |Perp Notional|| / Spot Value × 100
- Rebalance Qty: |current_delta_usd| / price
"""

from __future__ import annotations

from typing import Tuple, Optional
from src.delta_neutral.types import (
    DeltaPosition,
    RebalanceSignal,
    RebalanceDirection,
)


# =============================================================================
# POSITION SIZING
# =============================================================================


def calculate_position_size(
    total_balance_usd: float,
    leverage: float = 1.0,
    spot_price: float = 150.0,
) -> Tuple[float, float]:
    """
    Calculate spot and perp quantities for a delta-neutral position.
    
    For a 1x leveraged delta-neutral position:
    - Half the capital goes to Spot (long SOL)
    - Half the capital goes to Perp (short SOL-PERP)
    
    For 2x leverage:
    - Full capital as Spot
    - Full capital as Short (2x notional exposure)
    
    Args:
        total_balance_usd: Total capital to deploy
        leverage: Position leverage (1.0 = 1x, 2.0 = 2x)
        spot_price: Current SOL/USD price
    
    Returns:
        Tuple of (spot_qty, perp_qty) where perp_qty is negative (short)
    
    Example:
        >>> calculate_position_size(1000, leverage=1.0, spot_price=150)
        (3.333..., -3.333...)  # $500 spot, $500 short
        
        >>> calculate_position_size(1000, leverage=2.0, spot_price=150)
        (6.666..., -6.666...)  # $1000 spot, $1000 short
    """
    if total_balance_usd <= 0:
        return (0.0, 0.0)
    
    if spot_price <= 0:
        raise ValueError(f"Invalid spot price: {spot_price}")
    
    if leverage < 1.0:
        raise ValueError(f"Leverage must be >= 1.0, got {leverage}")
    
    # At 1x leverage: each leg gets half the capital
    # At 2x leverage: each leg gets full capital (2x notional)
    notional_per_leg = (total_balance_usd * leverage) / 2
    qty = notional_per_leg / spot_price
    
    return (qty, -qty)  # Positive spot, negative (short) perp


def calculate_position_size_from_equity(
    equity_usd: float,
    leverage: float = 1.0,
    spot_price: float = 150.0,
    max_position_pct: float = 0.95,
) -> Tuple[float, float]:
    """
    Calculate position size with safety margin for fees and slippage.
    
    Leaves 5% buffer by default for:
    - Trading fees (~0.1% per leg)
    - Slippage (~0.1-0.5%)
    - Gas costs (~0.001 SOL)
    
    Args:
        equity_usd: Total account equity
        leverage: Position leverage
        spot_price: Current SOL price
        max_position_pct: Maximum % of equity to use (default 95%)
    
    Returns:
        Tuple of (spot_qty, perp_qty)
    """
    deployable = equity_usd * max_position_pct
    return calculate_position_size(deployable, leverage, spot_price)


# =============================================================================
# DELTA CALCULATION
# =============================================================================


def calculate_delta_drift(
    spot_value_usd: float,
    perp_notional_usd: float,
) -> float:
    """
    Calculate the delta drift percentage.
    
    Formula:
        Drift % = |Spot Value - |Perp Notional|| / Spot Value × 100
    
    Args:
        spot_value_usd: USD value of spot holdings
        perp_notional_usd: USD notional of perp position (can be negative)
    
    Returns:
        Drift as percentage (0.5 = 0.5% drift)
    
    Example:
        >>> calculate_delta_drift(1000, -995)  # Almost balanced
        0.5
        
        >>> calculate_delta_drift(1000, -900)  # 10% drift
        10.0
    """
    if spot_value_usd <= 0:
        # Edge case: no spot position
        return 100.0 if perp_notional_usd != 0 else 0.0
    
    perp_abs = abs(perp_notional_usd)
    delta = abs(spot_value_usd - perp_abs)
    drift_pct = (delta / spot_value_usd) * 100
    
    return drift_pct


def build_delta_position(
    spot_qty: float,
    perp_qty: float,
    spot_price: float,
    entry_price_spot: float = 0.0,
    entry_price_perp: float = 0.0,
    timestamp_ms: int = 0,
) -> DeltaPosition:
    """
    Build a DeltaPosition from raw quantities and current price.
    
    Args:
        spot_qty: SOL quantity in spot wallet
        perp_qty: SOL size of perp position (negative = short)
        spot_price: Current SOL/USD price
        entry_price_spot: Average entry for spot leg
        entry_price_perp: Average entry for perp leg
        timestamp_ms: Position timestamp
    
    Returns:
        Fully calculated DeltaPosition with drift
    """
    spot_value = spot_qty * spot_price
    perp_value = abs(perp_qty) * spot_price  # Absolute notional
    
    drift = calculate_delta_drift(spot_value, -perp_value)
    
    return DeltaPosition(
        spot_qty=spot_qty,
        perp_qty=perp_qty,
        spot_value_usd=spot_value,
        perp_value_usd=perp_value,
        entry_price_spot=entry_price_spot or spot_price,
        entry_price_perp=entry_price_perp or spot_price,
        delta_drift_pct=drift,
        timestamp_ms=timestamp_ms,
    )


# =============================================================================
# REBALANCING
# =============================================================================


def get_rebalance_qty(current_delta_usd: float, price: float) -> float:
    """
    Calculate exactly how much SOL to trade to achieve zero delta.
    
    Args:
        current_delta_usd: Net USD exposure (Spot - |Perp|)
                          Positive = long bias, need to add short or sell spot
                          Negative = short bias, need to buy spot or reduce short
        price: Current SOL/USD price
    
    Returns:
        Quantity of SOL to trade (always positive, direction from delta sign)
    
    Example:
        >>> get_rebalance_qty(50, 150)  # $50 long bias
        0.333...  # Sell 0.33 SOL spot OR short 0.33 perp
        
        >>> get_rebalance_qty(-50, 150)  # $50 short bias
        0.333...  # Buy 0.33 SOL spot OR close 0.33 short
    """
    if price <= 0:
        raise ValueError(f"Invalid price: {price}")
    
    return abs(current_delta_usd) / price


def calculate_rebalance_signal(
    position: DeltaPosition,
    spot_price: float,
    drift_threshold_pct: float = 0.5,
) -> Optional[RebalanceSignal]:
    """
    Determine if rebalancing is needed and generate signal.
    
    Args:
        position: Current DeltaPosition
        spot_price: Current SOL/USD price
        drift_threshold_pct: Trigger threshold (default 0.5%)
    
    Returns:
        RebalanceSignal if drift exceeds threshold, None otherwise
    """
    drift = position.delta_drift_pct
    
    if abs(drift) <= drift_threshold_pct:
        return None  # Within tolerance
    
    # Calculate net delta
    net_delta_usd = position.net_delta_usd
    qty = get_rebalance_qty(net_delta_usd, spot_price)
    qty_usd = qty * spot_price
    
    # Determine direction based on imbalance
    if net_delta_usd > 0:
        # Spot heavy → need to increase short
        direction = RebalanceDirection.ADD_SHORT
        reason = f"Spot heavy by ${net_delta_usd:.2f}, adding short"
    else:
        # Perp heavy → need to buy more spot
        direction = RebalanceDirection.ADD_SPOT
        reason = f"Perp heavy by ${abs(net_delta_usd):.2f}, buying spot"
    
    # Urgency based on drift magnitude
    if drift > 2.0:
        urgency = 3  # Critical
    elif drift > 1.0:
        urgency = 2  # Elevated
    else:
        urgency = 1  # Normal
    
    return RebalanceSignal(
        direction=direction,
        qty=qty,
        qty_usd=qty_usd,
        current_drift_pct=drift,
        reason=reason,
        urgency=urgency,
    )


# =============================================================================
# FUNDING RATE MATH
# =============================================================================


def estimate_funding_yield(
    position_notional_usd: float,
    funding_rate_8h: float,
    periods_per_day: int = 3,
) -> Tuple[float, float]:
    """
    Estimate funding income from a delta-neutral position.
    
    In delta-neutral, you RECEIVE funding when:
    - Funding is POSITIVE and you're SHORT perp
    - Funding is NEGATIVE and you're LONG perp (rare)
    
    Args:
        position_notional_usd: Perp position size in USD
        funding_rate_8h: 8-hour funding rate as decimal (0.01 = 1%)
        periods_per_day: Funding payment frequency (default 3 = every 8h)
    
    Returns:
        Tuple of (daily_yield_usd, annualized_yield_pct)
    """
    # Per-period income
    period_income = position_notional_usd * abs(funding_rate_8h)
    
    # Daily income
    daily_income = period_income * periods_per_day
    
    # Annualized as percentage
    annual_pct = (daily_income / position_notional_usd) * 365 * 100
    
    return (daily_income, annual_pct)


def should_enter_funding_arb(
    funding_rate_8h: float,
    min_rate_threshold: float = 0.001,  # 0.1% minimum
    trading_fee_pct: float = 0.001,     # 0.1% round trip
) -> Tuple[bool, str]:
    """
    Determine if funding rate justifies entering a delta-neutral position.
    
    Break-even requires funding to exceed trading costs.
    For a single 8h period, funding must exceed entry + exit fees.
    
    Args:
        funding_rate_8h: Current 8-hour funding rate
        min_rate_threshold: Minimum rate to consider
        trading_fee_pct: Estimated round-trip fee (entry + exit)
    
    Returns:
        Tuple of (should_enter, reason)
    """
    rate = abs(funding_rate_8h)
    
    if rate < trading_fee_pct:
        return (
            False,
            f"Rate {rate:.4%} below trading fees {trading_fee_pct:.4%}"
        )
    
    if rate < min_rate_threshold:
        return (
            False,
            f"Rate {rate:.4%} below minimum threshold {min_rate_threshold:.4%}"
        )
    
    # Calculate how many periods to break even
    net_per_period = rate - (trading_fee_pct / 3)  # Amortize fees
    periods_to_breakeven = trading_fee_pct / net_per_period if net_per_period > 0 else float('inf')
    
    return (
        True,
        f"Rate {rate:.4%} profitable. Break-even in {periods_to_breakeven:.1f} periods"
    )


# =============================================================================
# VALIDATION HELPERS
# =============================================================================


def validate_position_balance(
    spot_qty: float,
    perp_qty: float,
    tolerance_pct: float = 1.0,
) -> Tuple[bool, str]:
    """
    Validate that spot and perp legs are within acceptable balance.
    
    Args:
        spot_qty: Spot SOL quantity
        perp_qty: Perp SOL size (should be negative for short)
        tolerance_pct: Maximum imbalance percentage
    
    Returns:
        Tuple of (is_valid, message)
    """
    if perp_qty > 0:
        return (False, "Perp position should be negative (short) for delta-neutral")
    
    perp_abs = abs(perp_qty)
    
    if spot_qty == 0 and perp_abs == 0:
        return (True, "No position")
    
    if spot_qty == 0:
        return (False, "Missing spot leg")
    
    if perp_abs == 0:
        return (False, "Missing perp leg")
    
    imbalance = abs(spot_qty - perp_abs) / spot_qty * 100
    
    if imbalance > tolerance_pct:
        return (
            False,
            f"Position imbalance {imbalance:.2f}% exceeds tolerance {tolerance_pct}%"
        )
    
    return (True, f"Position balanced (imbalance {imbalance:.2f}%)")
