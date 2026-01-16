"""
Property-Based Tests for Delta Neutral Engine Live Mode
========================================================

Tests universal correctness properties using hypothesis.

Feature: delta-neutral-live-mode
"""

import pytest
from hypothesis import given, strategies as st, settings
from src.shared.drivers.virtual_driver import VirtualDriver, VirtualOrder


# Feature: delta-neutral-live-mode, Property 9: Slippage Application in Paper Mode
@settings(max_examples=100)
@given(
    size=st.floats(min_value=0.001, max_value=100.0),
    base_price=st.floats(min_value=1.0, max_value=10000.0),
    side=st.sampled_from(["buy", "sell"])
)
def test_slippage_application_in_paper_mode(size, base_price, side):
    """
    Property 9: Slippage Application in Paper Mode
    
    For any paper mode trade with size S and price P, the executed price should be 
    within the range [P * (1 - slippage), P * (1 + slippage)] where slippage is 
    0.1-0.3% based on size.
    
    Validates: Requirements 1.5
    """
    driver = VirtualDriver("test_engine", {"SOL": 1000.0, "USDC": 10000.0})
    driver.set_price_feed({"TEST-PERP": base_price})
    
    # Calculate expected slippage range
    min_slippage = 0.001  # 0.1%
    max_slippage = 0.003  # 0.3%
    
    # Calculate slippage for this size
    slippage_threshold = 10.0
    if size <= slippage_threshold:
        expected_slippage = min_slippage
    else:
        ratio = min(size / (slippage_threshold * 5), 1.0)
        expected_slippage = min_slippage + (max_slippage - min_slippage) * ratio
    
    # Expected price range
    if side == "buy":
        expected_min = base_price * (1 + expected_slippage * 0.99)  # Allow 1% tolerance
        expected_max = base_price * (1 + expected_slippage * 1.01)
    else:  # sell
        expected_min = base_price * (1 - expected_slippage * 1.01)
        expected_max = base_price * (1 - expected_slippage * 0.99)
    
    # Create and execute order
    order = VirtualOrder(
        engine="test_engine",
        symbol="TEST-PERP",
        side=side,
        size=size,
        order_type="market"
    )
    
    import asyncio
    filled_order = asyncio.run(driver.place_order(order))
    
    # Verify slippage was applied correctly
    if filled_order.status == "filled":
        assert expected_min <= filled_order.filled_price <= expected_max, \
            f"Price {filled_order.filled_price} outside expected range [{expected_min}, {expected_max}]"



# Feature: delta-neutral-live-mode, Property 4: Leverage Limit Enforcement
@settings(max_examples=100)
@given(
    collateral=st.floats(min_value=100.0, max_value=10000.0),
    position_size=st.floats(min_value=0.1, max_value=1000.0),
    price=st.floats(min_value=10.0, max_value=1000.0)
)
def test_leverage_limit_enforcement(collateral, position_size, price):
    """
    Property 4: Leverage Limit Enforcement
    
    For any proposed position size and current collateral, if the resulting leverage 
    would exceed the configured maximum (default 10x for paper), the system should 
    reject the trade.
    
    Validates: Requirements 1.6
    """
    driver = VirtualDriver("test_engine", {"USDC": collateral})
    driver.set_price_feed({"TEST-PERP": price})
    
    # Calculate leverage
    notional = position_size * price
    leverage = notional / collateral
    
    # Create order
    order = VirtualOrder(
        engine="test_engine",
        symbol="TEST-PERP",
        side="buy",
        size=position_size,
        order_type="market"
    )
    
    import asyncio
    filled_order = asyncio.run(driver.place_order(order))
    
    # Verify leverage limit enforcement
    max_leverage = 10.0  # Paper mode limit
    
    if leverage > max_leverage:
        # Should be rejected
        assert filled_order.status == "rejected", \
            f"Order should be rejected for leverage {leverage:.2f}x > {max_leverage}x"
        assert "leverage" in filled_order.metadata.get("error", "").lower(), \
            "Rejection reason should mention leverage"
    else:
        # Should be filled (or rejected for other reasons, but not leverage)
        if filled_order.status == "rejected":
            assert "leverage" not in filled_order.metadata.get("error", "").lower(), \
                f"Order rejected for leverage when {leverage:.2f}x <= {max_leverage}x"



# Feature: delta-neutral-live-mode, Property 2: Health Ratio Bounds
@settings(max_examples=100)
@given(
    total_collateral=st.floats(min_value=0.0, max_value=100000.0),
    maintenance_margin=st.floats(min_value=0.0, max_value=100000.0)
)
def test_health_ratio_bounds(total_collateral, maintenance_margin):
    """
    Property 2: Health Ratio Bounds
    
    For any total collateral and maintenance margin values, the calculated health ratio 
    should be in the range [0, 100], where 0 indicates liquidation and 100 indicates 
    maximum safety.
    
    Validates: Requirements 1.4, 2.3
    """
    # Use unique engine name to avoid cache issues
    import uuid
    engine_name = f"test_engine_{uuid.uuid4().hex[:8]}"
    
    driver = VirtualDriver(engine_name, {"USDC": total_collateral})
    
    # Create a position that requires the given maintenance margin
    if total_collateral > 0 and maintenance_margin > 0:
        # Calculate position size that would result in this maintenance margin
        # maint_margin = size * price * 0.05
        price = 100.0
        size = maintenance_margin / (price * 0.05)
        
        driver.set_price_feed({"TEST-PERP": price})
        
        # Create position manually
        from src.shared.drivers.virtual_driver import VirtualPosition
        driver.positions["TEST-PERP"] = VirtualPosition(
            symbol="TEST-PERP",
            side="short",
            size=size,
            entry_price=price,
            leverage=1.0
        )
    
    # Calculate health ratio
    health = driver.calculate_health_ratio()
    
    # Verify bounds
    assert 0.0 <= health <= 100.0, \
        f"Health ratio {health} outside valid range [0, 100]"
    
    # Verify edge cases
    if total_collateral <= 1e-10:  # Effectively zero (floating point tolerance)
        assert health == 0.0, f"Health should be 0 when collateral is ~0 (got {health}, collateral={total_collateral})"
    
    if maintenance_margin <= 1e-10 and total_collateral > 1e-10:  # No margin, has collateral
        assert health == 100.0, f"Health should be 100 when no margin required (got {health})"
    
    if maintenance_margin >= total_collateral and total_collateral > 1e-10:
        assert health == 0.0, f"Health should be 0 when margin >= collateral (got {health})"
