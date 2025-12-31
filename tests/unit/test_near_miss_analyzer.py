"""
Unit Tests: Near-Miss Analyzer
==============================
Tests for the NearMissAnalyzer module.

Run with: pytest tests/unit/test_near_miss_analyzer.py -v
"""

import pytest
from typing import NamedTuple

# Import the module under test
from src.arbiter.core.near_miss_analyzer import (
    NearMissAnalyzer,
    NearMissMetrics,
    analyze_near_miss,
)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════


class MockOpportunity(NamedTuple):
    """Mock opportunity for testing."""

    net_profit_usd: float
    spread_pct: float
    max_size_usd: float = 30.0


@pytest.fixture
def viable_opp() -> MockOpportunity:
    """Profitable opportunity: +$0.05 net profit."""
    return MockOpportunity(net_profit_usd=0.05, spread_pct=0.80)


@pytest.fixture
def near_miss_opp() -> MockOpportunity:
    """Near-miss: -$0.03 (within $0.05 threshold)."""
    return MockOpportunity(net_profit_usd=-0.03, spread_pct=0.62)


@pytest.fixture
def warm_opp() -> MockOpportunity:
    """Warm opportunity: -$0.08 (within $0.10 threshold)."""
    return MockOpportunity(net_profit_usd=-0.08, spread_pct=0.55)


@pytest.fixture
def far_opp() -> MockOpportunity:
    """Far from profitable: -$0.50."""
    return MockOpportunity(net_profit_usd=-0.50, spread_pct=0.20)


# ═══════════════════════════════════════════════════════════════════════════════
# STATUS CLASSIFICATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestClassifyStatus:
    """Tests for NearMissAnalyzer.classify_status()."""

    def test_positive_profit_is_viable(self):
        """Positive net profit → VIABLE."""
        assert NearMissAnalyzer.classify_status(0.01) == "VIABLE"
        assert NearMissAnalyzer.classify_status(1.00) == "VIABLE"
        assert NearMissAnalyzer.classify_status(0.001) == "VIABLE"

    def test_zero_profit_is_near_miss(self):
        """Zero net profit → NEAR_MISS (not viable, but closest)."""
        assert NearMissAnalyzer.classify_status(0.0) == "NEAR_MISS"

    def test_within_5_cents_is_near_miss(self):
        """Loss within $0.05 → NEAR_MISS."""
        assert NearMissAnalyzer.classify_status(-0.01) == "NEAR_MISS"
        assert NearMissAnalyzer.classify_status(-0.03) == "NEAR_MISS"
        assert NearMissAnalyzer.classify_status(-0.05) == "NEAR_MISS"

    def test_within_10_cents_is_warm(self):
        """Loss between $0.05 and $0.10 → WARM."""
        assert NearMissAnalyzer.classify_status(-0.06) == "WARM"
        assert NearMissAnalyzer.classify_status(-0.08) == "WARM"
        assert NearMissAnalyzer.classify_status(-0.10) == "WARM"

    def test_beyond_10_cents_is_far(self):
        """Loss greater than $0.10 → FAR."""
        assert NearMissAnalyzer.classify_status(-0.11) == "FAR"
        assert NearMissAnalyzer.classify_status(-0.50) == "FAR"
        assert NearMissAnalyzer.classify_status(-5.00) == "FAR"


# ═══════════════════════════════════════════════════════════════════════════════
# METRICS CALCULATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestCalculateMetrics:
    """Tests for NearMissAnalyzer.calculate_metrics()."""

    def test_viable_opportunity(self, viable_opp):
        """Profitable opportunity returns VIABLE status and zero gap."""
        metrics = NearMissAnalyzer.calculate_metrics(viable_opp)

        assert metrics.status == "VIABLE"
        assert metrics.status_icon == "✅ READY"
        assert metrics.gap_to_profit_usd == 0.0
        assert metrics.gap_display == "READY"

    def test_near_miss_opportunity(self, near_miss_opp):
        """Near-miss returns correct gap calculation."""
        metrics = NearMissAnalyzer.calculate_metrics(near_miss_opp)

        assert metrics.status == "NEAR_MISS"
        assert metrics.status_icon == "⚡ NEAR"
        assert metrics.gap_to_profit_usd == pytest.approx(0.03, abs=0.001)
        assert metrics.gap_display == "+$0.030"

    def test_warm_opportunity(self, warm_opp):
        """Warm opportunity returns WARM status."""
        metrics = NearMissAnalyzer.calculate_metrics(warm_opp)

        assert metrics.status == "WARM"
        assert metrics.status_icon == "🔸 WARM"
        assert metrics.gap_to_profit_usd == pytest.approx(0.08, abs=0.001)

    def test_far_opportunity(self, far_opp):
        """Far opportunity returns FAR status."""
        metrics = NearMissAnalyzer.calculate_metrics(far_opp)

        assert metrics.status == "FAR"
        assert metrics.status_icon == "❌"
        assert metrics.gap_to_profit_usd == pytest.approx(0.50, abs=0.001)

    def test_required_spread_calculation(self, near_miss_opp):
        """Required spread should be higher than current spread for non-viable."""
        metrics = NearMissAnalyzer.calculate_metrics(near_miss_opp)

        # Required spread must be >= current spread to close the gap
        assert metrics.required_spread_pct >= near_miss_opp.spread_pct

    def test_custom_trade_size(self, near_miss_opp):
        """Trade size override affects required spread calculation."""
        metrics_30 = NearMissAnalyzer.calculate_metrics(
            near_miss_opp, trade_size_usd=30.0
        )
        metrics_100 = NearMissAnalyzer.calculate_metrics(
            near_miss_opp, trade_size_usd=100.0
        )

        # Larger trade size → lower required spread to cover fixed costs
        # (Relative difference should be noticeable)
        assert metrics_30.required_spread_pct != metrics_100.required_spread_pct


# ═══════════════════════════════════════════════════════════════════════════════
# IS_ACTIONABLE TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestIsActionable:
    """Tests for NearMissAnalyzer.is_actionable()."""

    def test_viable_is_actionable(self, viable_opp):
        """Viable opportunities are actionable."""
        assert NearMissAnalyzer.is_actionable(viable_opp) is True

    def test_near_miss_is_actionable(self, near_miss_opp):
        """Near-miss opportunities are actionable (worth watching)."""
        assert NearMissAnalyzer.is_actionable(near_miss_opp) is True

    def test_warm_is_not_actionable(self, warm_opp):
        """Warm opportunities are not immediately actionable."""
        assert NearMissAnalyzer.is_actionable(warm_opp) is False

    def test_far_is_not_actionable(self, far_opp):
        """Far opportunities are not actionable."""
        assert NearMissAnalyzer.is_actionable(far_opp) is False


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestConvenienceFunction:
    """Tests for the module-level analyze_near_miss() function."""

    def test_analyze_near_miss_returns_metrics(self, viable_opp):
        """analyze_near_miss() returns NearMissMetrics."""
        result = analyze_near_miss(viable_opp)

        assert isinstance(result, NearMissMetrics)
        assert result.status == "VIABLE"


# ═══════════════════════════════════════════════════════════════════════════════
# EDGE CASE TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge case and boundary condition tests."""

    def test_exact_threshold_boundary_near(self):
        """Exactly -$0.05 is still NEAR_MISS (inclusive)."""
        opp = MockOpportunity(net_profit_usd=-0.05, spread_pct=0.50)
        assert NearMissAnalyzer.classify_status(opp.net_profit_usd) == "NEAR_MISS"

    def test_exact_threshold_boundary_warm(self):
        """Exactly -$0.10 is still WARM (inclusive)."""
        opp = MockOpportunity(net_profit_usd=-0.10, spread_pct=0.40)
        assert NearMissAnalyzer.classify_status(opp.net_profit_usd) == "WARM"

    def test_tiny_profit_is_viable(self):
        """Even $0.001 profit counts as VIABLE."""
        opp = MockOpportunity(net_profit_usd=0.001, spread_pct=0.65)
        metrics = NearMissAnalyzer.calculate_metrics(opp)

        assert metrics.status == "VIABLE"
        assert metrics.gap_display == "READY"

    def test_zero_trade_size_handles_gracefully(self):
        """Zero trade size doesn't cause division by zero."""
        opp = MockOpportunity(net_profit_usd=-0.05, spread_pct=0.50, max_size_usd=0.0)

        # Should not raise
        metrics = NearMissAnalyzer.calculate_metrics(opp, trade_size_usd=0.0)
        assert metrics.required_spread_pct == 0.0
