"""
Position Calculator Unit Tests
==============================
Tests for DNEM position sizing and delta math.

All tests are PURE LOGIC - no network or mocks required.
"""

import pytest
from src.delta_neutral.types import (
    DeltaPosition,
    RebalanceDirection,
    RebalanceSignal,
)
from src.delta_neutral.position_calculator import (
    calculate_position_size,
    calculate_position_size_from_equity,
    calculate_delta_drift,
    build_delta_position,
    get_rebalance_qty,
    calculate_rebalance_signal,
    estimate_funding_yield,
    should_enter_funding_arb,
    validate_position_balance,
)


# =============================================================================
# TEST: POSITION SIZING
# =============================================================================


@pytest.mark.unit
class TestPositionSizing:
    """Tests for calculate_position_size()."""

    def test_1x_leverage_splits_evenly(self):
        """$1000 at 1x leverage → $500 spot, $500 short."""
        spot, perp = calculate_position_size(1000, leverage=1.0, spot_price=150)
        
        # Each leg gets $500 worth
        assert pytest.approx(spot, rel=0.001) == 3.333  # $500 / $150
        assert pytest.approx(perp, rel=0.001) == -3.333  # Negative = short
        
        # Verify values
        assert pytest.approx(spot * 150, rel=0.01) == 500
        assert pytest.approx(abs(perp) * 150, rel=0.01) == 500

    def test_2x_leverage_doubles_exposure(self):
        """$1000 at 2x leverage → $1000 spot, $1000 short."""
        spot, perp = calculate_position_size(1000, leverage=2.0, spot_price=150)
        
        assert pytest.approx(spot * 150, rel=0.01) == 1000
        assert pytest.approx(abs(perp) * 150, rel=0.01) == 1000

    def test_exact_user_example_12_usd(self):
        """User example: $12 balance at 1x."""
        spot, perp = calculate_position_size(12, leverage=1.0, spot_price=150)
        
        # $6 spot, $6 short
        assert pytest.approx(spot, rel=0.001) == 0.04  # $6 / $150
        assert pytest.approx(perp, rel=0.001) == -0.04

    def test_zero_balance_returns_zero(self):
        """Edge case: zero balance."""
        spot, perp = calculate_position_size(0, leverage=1.0, spot_price=150)
        
        assert spot == 0.0
        assert perp == 0.0

    def test_invalid_price_raises(self):
        """Invalid price should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid spot price"):
            calculate_position_size(1000, leverage=1.0, spot_price=0)
        
        with pytest.raises(ValueError, match="Invalid spot price"):
            calculate_position_size(1000, leverage=1.0, spot_price=-50)

    def test_invalid_leverage_raises(self):
        """Leverage below 1x should raise."""
        with pytest.raises(ValueError, match="Leverage must be >= 1.0"):
            calculate_position_size(1000, leverage=0.5, spot_price=150)

    def test_from_equity_applies_buffer(self):
        """Position from equity leaves safety buffer."""
        spot, _ = calculate_position_size_from_equity(
            1000, leverage=1.0, spot_price=150, max_position_pct=0.95
        )
        
        # Uses 95% of equity
        expected = calculate_position_size(950, 1.0, 150)[0]
        assert spot == expected


# =============================================================================
# TEST: DELTA DRIFT CALCULATION
# =============================================================================


@pytest.mark.unit
class TestDeltaDrift:
    """Tests for calculate_delta_drift()."""

    def test_perfect_neutral_zero_drift(self):
        """Perfectly balanced position has 0% drift."""
        drift = calculate_delta_drift(1000, -1000)
        assert drift == 0.0

    def test_half_percent_drift(self):
        """0.5% imbalance detection (rebalance threshold)."""
        # $1000 spot, $995 perp → $5 / $1000 = 0.5%
        drift = calculate_delta_drift(1000, -995)
        assert pytest.approx(drift, rel=0.01) == 0.5

    def test_ten_percent_drift(self):
        """Large drift detection."""
        # $1000 spot, $900 perp → $100 / $1000 = 10%
        drift = calculate_delta_drift(1000, -900)
        assert pytest.approx(drift, rel=0.01) == 10.0

    def test_spot_heavy_positive_delta(self):
        """Spot exceeds perp → positive net delta."""
        position = build_delta_position(
            spot_qty=10.0,
            perp_qty=-9.0,  # 10% less
            spot_price=100
        )
        
        assert position.net_delta_usd > 0  # Long bias
        assert position.spot_value_usd == 1000
        assert position.perp_value_usd == 900

    def test_perp_heavy_negative_delta(self):
        """Perp exceeds spot → negative net delta."""
        position = build_delta_position(
            spot_qty=9.0,
            perp_qty=-10.0,  # 10% more short
            spot_price=100
        )
        
        assert position.net_delta_usd < 0  # Short bias

    def test_no_spot_returns_100_drift(self):
        """Edge case: no spot but has perp."""
        drift = calculate_delta_drift(0, -1000)
        assert drift == 100.0

    def test_no_position_zero_drift(self):
        """Edge case: no position at all."""
        drift = calculate_delta_drift(0, 0)
        assert drift == 0.0


# =============================================================================
# TEST: REBALANCING
# =============================================================================


@pytest.mark.unit
class TestRebalancing:
    """Tests for rebalancing calculations."""

    def test_get_rebalance_qty_long_bias(self):
        """Long bias → calculate qty to sell or short."""
        # $50 long bias at $150/SOL
        qty = get_rebalance_qty(50, 150)
        assert pytest.approx(qty, rel=0.001) == 0.333

    def test_get_rebalance_qty_short_bias(self):
        """Short bias → calculate qty to buy."""
        # -$50 short bias at $150/SOL
        qty = get_rebalance_qty(-50, 150)
        assert pytest.approx(qty, rel=0.001) == 0.333

    def test_signal_none_within_threshold(self):
        """No signal when drift < 0.5%."""
        position = build_delta_position(
            spot_qty=10.0,
            perp_qty=-9.97,  # 0.3% drift
            spot_price=100
        )
        
        signal = calculate_rebalance_signal(position, spot_price=100)
        assert signal is None

    def test_signal_generated_above_threshold(self):
        """Signal generated when drift > 0.5%."""
        position = build_delta_position(
            spot_qty=10.0,
            perp_qty=-9.0,  # 10% drift (spot heavy)
            spot_price=100
        )
        
        signal = calculate_rebalance_signal(position, spot_price=100)
        
        assert signal is not None
        assert signal.direction == RebalanceDirection.ADD_SHORT
        assert signal.qty > 0
        assert signal.urgency >= 2  # Elevated for 10% drift

    def test_signal_add_spot_when_perp_heavy(self):
        """Perp heavy → ADD_SPOT signal."""
        position = build_delta_position(
            spot_qty=9.0,
            perp_qty=-10.0,  # Perp heavy
            spot_price=100
        )
        
        signal = calculate_rebalance_signal(position, spot_price=100)
        
        assert signal is not None
        assert signal.direction == RebalanceDirection.ADD_SPOT

    def test_signal_add_short_when_spot_heavy(self):
        """Spot heavy → ADD_SHORT signal."""
        position = build_delta_position(
            spot_qty=10.0,
            perp_qty=-9.0,  # Spot heavy
            spot_price=100
        )
        
        signal = calculate_rebalance_signal(position, spot_price=100)
        
        assert signal is not None
        assert signal.direction == RebalanceDirection.ADD_SHORT

    def test_urgency_levels(self):
        """Urgency scales with drift magnitude."""
        # ~0.6% drift → urgency 1
        pos_low = build_delta_position(10.0, -9.94, 100)
        sig_low = calculate_rebalance_signal(pos_low, 100)
        assert sig_low.urgency == 1
        
        # ~1.5% drift → urgency 2 (10.0 spot, 9.85 perp = 1.5% drift)
        pos_med = build_delta_position(10.0, -9.85, 100)
        sig_med = calculate_rebalance_signal(pos_med, 100)
        assert sig_med.urgency == 2
        
        # ~3% drift → urgency 3 (critical) (10.0 spot, 9.7 perp = 3% drift)
        pos_hi = build_delta_position(10.0, -9.7, 100)
        sig_hi = calculate_rebalance_signal(pos_hi, 100)
        assert sig_hi.urgency == 3


# =============================================================================
# TEST: FUNDING RATE MATH
# =============================================================================


@pytest.mark.unit
class TestFundingMath:
    """Tests for funding rate calculations."""

    def test_estimate_funding_yield(self):
        """Estimate daily and annual yield from funding."""
        # $10,000 position, 0.01% per 8h (0.0001)
        daily, annual = estimate_funding_yield(10000, 0.0001)
        
        # Daily: $10000 * 0.0001 * 3 = $3
        assert pytest.approx(daily, rel=0.01) == 3.0
        
        # Annual: $3/day * 365 / $10000 * 100 = 10.95%
        assert pytest.approx(annual, rel=0.1) == 10.95

    def test_should_enter_profitable_rate(self):
        """Enter position when rate exceeds fees."""
        should_enter, reason = should_enter_funding_arb(0.002)  # 0.2%
        
        assert should_enter is True
        assert "profitable" in reason.lower()

    def test_should_not_enter_low_rate(self):
        """Don't enter when rate below threshold."""
        should_enter, reason = should_enter_funding_arb(0.0005)  # 0.05%
        
        assert should_enter is False
        assert "below" in reason.lower()

    def test_should_not_enter_below_fees(self):
        """Don't enter when rate below trading fees."""
        should_enter, reason = should_enter_funding_arb(
            0.0005, 
            trading_fee_pct=0.001  # 0.1% fees
        )
        
        assert should_enter is False


# =============================================================================
# TEST: VALIDATION
# =============================================================================


@pytest.mark.unit
class TestValidation:
    """Tests for position validation helpers."""

    def test_validate_balanced_position(self):
        """Balanced position passes validation."""
        is_valid, msg = validate_position_balance(10.0, -10.0)
        
        assert is_valid is True
        assert "balanced" in msg.lower()

    def test_validate_missing_spot_leg(self):
        """Missing spot leg fails validation."""
        is_valid, msg = validate_position_balance(0.0, -10.0)
        
        assert is_valid is False
        assert "missing spot" in msg.lower()

    def test_validate_missing_perp_leg(self):
        """Missing perp leg fails validation."""
        is_valid, msg = validate_position_balance(10.0, 0.0)
        
        assert is_valid is False
        assert "missing perp" in msg.lower()

    def test_validate_positive_perp_fails(self):
        """Positive perp (long) fails - should be short."""
        is_valid, msg = validate_position_balance(10.0, 10.0)  # Long perp!
        
        assert is_valid is False
        assert "short" in msg.lower()

    def test_validate_imbalanced_position(self):
        """Imbalanced position fails if beyond tolerance."""
        is_valid, msg = validate_position_balance(10.0, -8.0, tolerance_pct=1.0)
        
        assert is_valid is False
        assert "imbalance" in msg.lower()


# =============================================================================
# TEST: DELTA POSITION DATACLASS
# =============================================================================


@pytest.mark.unit
class TestDeltaPosition:
    """Tests for DeltaPosition dataclass behavior."""

    def test_is_neutral_within_threshold(self):
        """Position with <0.5% drift is neutral."""
        position = build_delta_position(10.0, -9.97, 100)
        
        assert position.is_neutral is True

    def test_is_not_neutral_above_threshold(self):
        """Position with >0.5% drift is not neutral."""
        position = build_delta_position(10.0, -9.0, 100)
        
        assert position.is_neutral is False

    def test_repr_shows_direction(self):
        """String representation shows bias direction."""
        long_bias = build_delta_position(10.0, -8.0, 100)
        assert "LONG BIAS" in repr(long_bias)
        
        short_bias = build_delta_position(8.0, -10.0, 100)
        assert "SHORT BIAS" in repr(short_bias)
        
        neutral = build_delta_position(10.0, -9.98, 100)
        assert "NEUTRAL" in repr(neutral)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
