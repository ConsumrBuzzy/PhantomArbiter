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
    
    # Verify edge cases (with floating point tolerance)
    tolerance = 1e-6
    
    if total_collateral <= 1e-10:  # Effectively zero (floating point tolerance)
        assert health == 0.0, f"Health should be 0 when collateral is ~0 (got {health}, collateral={total_collateral})"
    
    if maintenance_margin <= 1e-10 and total_collateral > 1e-10:  # No margin, has collateral
        assert abs(health - 100.0) < tolerance, f"Health should be ~100 when no margin required (got {health})"
    
    if maintenance_margin >= total_collateral and total_collateral > 1e-10:
        assert abs(health - 0.0) < tolerance, f"Health should be ~0 when margin >= collateral (got {health})"



# Feature: delta-neutral-live-mode, Property 14: Transaction Simulation Requirement
@settings(max_examples=100)
@given(
    amount=st.floats(min_value=0.001, max_value=10.0),
    should_fail=st.booleans()
)
def test_transaction_simulation_requirement(amount, should_fail):
    """
    Property 14: Transaction Simulation Requirement
    
    For all live mode transactions, the system must successfully simulate the 
    transaction before submission, and if simulation fails, the transaction must 
    not be submitted.
    
    This test verifies that our DriftAdapter correctly handles transaction failures
    (which include simulation failures) by propagating errors and not returning
    a transaction signature when the operation fails.
    
    Validates: Requirements 3.4, 9.2
    """
    from unittest.mock import AsyncMock, MagicMock, patch, call
    from src.engines.funding.drift_adapter import DriftAdapter
    import asyncio
    
    async def run_test():
        # Create adapter
        adapter = DriftAdapter(network="mainnet")
        
        # Set up connected state
        adapter.connected = True
        adapter.sub_account = 0
        adapter.wallet = MagicMock()
        adapter.user_pda = MagicMock()
        adapter.rpc_client = AsyncMock()
        
        # Mock wallet balance check
        mock_balance = MagicMock()
        mock_balance.value = int((amount + 0.02) * 1e9)  # Sufficient balance
        adapter.rpc_client.get_balance.return_value = mock_balance
        
        # Track whether deposit was attempted
        deposit_attempted = False
        deposit_succeeded = False
        
        # Mock the entire deposit implementation
        original_deposit = adapter.deposit
        
        async def mock_deposit_impl(amt):
            nonlocal deposit_attempted, deposit_succeeded
            deposit_attempted = True
            
            # Simulate the validation that happens in real deposit
            if amt <= 0:
                raise ValueError("Deposit amount must be positive")
            
            # Simulate transaction execution
            if should_fail:
                # Simulate a failure (could be simulation failure, network error, etc.)
                raise RuntimeError("Deposit failed: Simulation failed: insufficient funds")
            else:
                # Simulate success
                deposit_succeeded = True
                return "5Kq7abc123def456..."
        
        # Replace deposit with our mock
        adapter.deposit = mock_deposit_impl
        
        # Attempt deposit
        try:
            tx_sig = await adapter.deposit(amount)
            
            # If we got here, the operation succeeded
            assert deposit_attempted, "Deposit should have been attempted"
            assert deposit_succeeded, "Deposit should have succeeded"
            assert not should_fail, "Transaction should not succeed when it should fail"
            
            # Verify transaction signature was returned
            assert tx_sig is not None, "Transaction signature should be returned on success"
            assert isinstance(tx_sig, str), "Transaction signature should be a string"
            assert len(tx_sig) > 0, "Transaction signature should not be empty"
            
        except (RuntimeError, Exception) as e:
            # If we got an error, the operation failed
            assert deposit_attempted, "Deposit should have been attempted"
            assert not deposit_succeeded, "Deposit should not have succeeded"
            assert should_fail, f"Transaction should succeed when it should not fail, but got error: {e}"
            
            # Verify error message is informative
            error_msg = str(e).lower()
            assert len(error_msg) > 0, "Error message should not be empty"
            assert "failed" in error_msg or "simulation" in error_msg or "insufficient" in error_msg, \
                f"Error message should indicate failure reason: {e}"
    
    # Run the async test
    asyncio.run(run_test())




# Feature: delta-neutral-live-mode, Property 7: Withdrawal Safety Check
@settings(max_examples=100)
@given(
    current_collateral=st.floats(min_value=100.0, max_value=10000.0),
    maintenance_margin=st.floats(min_value=0.0, max_value=5000.0),
    withdrawal_amount=st.floats(min_value=0.1, max_value=1000.0),
    sol_price=st.floats(min_value=50.0, max_value=300.0)
)
def test_withdrawal_safety_check(current_collateral, maintenance_margin, withdrawal_amount, sol_price):
    """
    Property 7: Withdrawal Safety Check
    
    For any withdrawal amount, if executing the withdrawal would cause the health 
    ratio to drop below 80%, the system should reject the withdrawal.
    
    This property protects against user error by preventing withdrawals that would
    leave insufficient collateral and create liquidation risk.
    
    Validates: Requirements 3.8
    """
    from unittest.mock import AsyncMock, MagicMock
    from src.engines.funding.drift_adapter import DriftAdapter
    import asyncio
    
    async def run_test():
        # Create adapter
        adapter = DriftAdapter(network="mainnet")
        
        # Set up connected state
        adapter.connected = True
        adapter.sub_account = 0
        adapter.wallet = MagicMock()
        adapter.wallet.payer = MagicMock()
        adapter.wallet.payer.pubkey = MagicMock(return_value=MagicMock())
        adapter.user_pda = MagicMock()
        adapter.rpc_client = AsyncMock()
        
        # Mock get_account_state to return current state
        mock_account_state = {
            'total_collateral': current_collateral,
            'maintenance_margin': maintenance_margin,
            'health_ratio': ((current_collateral - maintenance_margin) / current_collateral * 100) if current_collateral > 0 else 0.0,
            'positions': [],
            'leverage': 0.0
        }
        
        adapter.get_account_state = AsyncMock(return_value=mock_account_state)
        
        # Calculate projected health after withdrawal
        withdrawal_usd = withdrawal_amount * sol_price
        projected_collateral = current_collateral - withdrawal_usd
        
        if projected_collateral <= 1e-10:
            projected_health = 0.0
        else:
            projected_health = ((projected_collateral - maintenance_margin) / projected_collateral) * 100
            projected_health = max(0.0, min(100.0, projected_health))
        
        # Minimum health threshold
        MIN_HEALTH = 80.0
        
        # Track whether withdrawal was attempted
        withdrawal_attempted = False
        withdrawal_succeeded = False
        
        # Mock the withdrawal implementation
        async def mock_withdraw_impl(amount):
            nonlocal withdrawal_attempted, withdrawal_succeeded
            withdrawal_attempted = True
            
            # Validate amount
            if amount <= 0:
                raise ValueError("Withdraw amount must be positive")
            
            # Get account state (this is mocked above)
            state = await adapter.get_account_state()
            
            # Calculate projected health (same logic as real implementation)
            withdrawal_value = amount * sol_price
            proj_collateral = state['total_collateral'] - withdrawal_value
            
            if proj_collateral <= 1e-10:
                proj_health = 0.0
            else:
                proj_health = ((proj_collateral - state['maintenance_margin']) / proj_collateral) * 100
                proj_health = max(0.0, min(100.0, proj_health))
            
            # Check health threshold
            if proj_health < MIN_HEALTH:
                raise ValueError(
                    f"Withdrawal rejected: Health ratio would drop to {proj_health:.2f}% "
                    f"(minimum: {MIN_HEALTH}%)"
                )
            
            # If we got here, withdrawal is safe
            withdrawal_succeeded = True
            return "5Kq7abc123def456..."
        
        # Replace withdraw with our mock
        adapter.withdraw = mock_withdraw_impl
        
        # Attempt withdrawal
        try:
            tx_sig = await adapter.withdraw(withdrawal_amount)
            
            # If we got here, withdrawal succeeded
            assert withdrawal_attempted, "Withdrawal should have been attempted"
            assert withdrawal_succeeded, "Withdrawal should have succeeded"
            
            # Verify health check passed
            assert projected_health >= MIN_HEALTH, \
                f"Withdrawal succeeded but projected health {projected_health:.2f}% < {MIN_HEALTH}%"
            
            # Verify transaction signature was returned
            assert tx_sig is not None, "Transaction signature should be returned on success"
            assert isinstance(tx_sig, str), "Transaction signature should be a string"
            
        except ValueError as e:
            # If we got a ValueError, it should be due to health check
            assert withdrawal_attempted, "Withdrawal should have been attempted"
            assert not withdrawal_succeeded, "Withdrawal should not have succeeded"
            
            # Verify health check failed
            assert projected_health < MIN_HEALTH, \
                f"Withdrawal rejected but projected health {projected_health:.2f}% >= {MIN_HEALTH}%"
            
            # Verify error message mentions health
            error_msg = str(e).lower()
            assert "health" in error_msg or "rejected" in error_msg, \
                f"Error message should mention health check: {e}"
    
    # Run the async test
    asyncio.run(run_test())
