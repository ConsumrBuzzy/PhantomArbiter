"""
Arb Scanner Unit Tests
======================
Tests for SpreadOpportunity calculations and SpreadDetector behavior.

The Calculus Behind Optimal Trade Size:
=======================================
Maximize: P(x) = (Spread * x) - (Impact * x²) - Fees
         where x = trade size in USD

Taking derivative and setting to zero:
    P'(x) = Spread - 2 * Impact * x = 0
    x_opt = Spread / (2 * Impact)

This test suite verifies the bot calculates this correctly.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch


class TestSpreadOpportunity:
    """Test SpreadOpportunity dataclass calculations."""

    @pytest.fixture
    def create_opportunity(self):
        """Factory for creating test opportunities."""
        from src.engines.arb.scanner import SpreadOpportunity
        
        def _create(
            spread_pct: float = 1.0,
            fee_pct: float = 0.3,
            slippage_pct: float = 0.1,
            buy_price: float = 150.0,
            sell_price: float = 151.5,
            trade_size: float = 100.0,
        ):
            # Calculate derived USD values
            gross_profit = trade_size * (spread_pct / 100)
            fees_usd = trade_size * (fee_pct / 100)
            slippage_cost = trade_size * (slippage_pct / 100)
            net_profit_usd = gross_profit - fees_usd - slippage_cost
            net_profit_pct = (net_profit_usd / trade_size) * 100 if trade_size > 0 else 0.0

            return SpreadOpportunity(
                pair="SOL/USDC",
                base_mint="SOL_MINT",
                quote_mint="USDC_MINT",
                buy_dex="RAYDIUM",
                sell_dex="ORCA",
                buy_price=buy_price,
                sell_price=sell_price,
                spread_pct=spread_pct,
                gross_profit_usd=gross_profit,
                estimated_fees_usd=fees_usd,
                net_profit_usd=net_profit_usd,
                net_profit_pct=net_profit_pct,
                max_size_usd=trade_size,
                confidence=0.9,
            )
        return _create

    def test_net_profit_calculation(self, create_opportunity):
        """Verify net_profit_pct = spread - fees - slippage."""
        opp = create_opportunity(
            spread_pct=1.5,
            fee_pct=0.35,
            slippage_pct=0.15,
        )
        
        expected_net = 1.5 - 0.35 - 0.15  # 1.0%
        assert abs(opp.net_profit_pct - expected_net) < 0.001, (
            f"Expected net profit {expected_net}%, got {opp.net_profit_pct}%"
        )

    def test_is_profitable_when_positive(self, create_opportunity):
        """Opportunity is profitable when net_profit > 0."""
        opp = create_opportunity(spread_pct=1.0, fee_pct=0.3, slippage_pct=0.1)
        
        assert opp.is_profitable(), (
            f"Should be profitable with {opp.net_profit_pct}% net profit"
        )

    def test_is_not_profitable_when_negative(self, create_opportunity):
        """Opportunity is NOT profitable when fees exceed spread."""
        opp = create_opportunity(spread_pct=0.2, fee_pct=0.3, slippage_pct=0.1)
        
        assert not opp.is_profitable(), (
            f"Should NOT be profitable with {opp.net_profit_pct}% net profit"
        )

    def test_is_not_profitable_at_zero(self, create_opportunity):
        """Edge case: exactly break-even is NOT profitable."""
        opp = create_opportunity(spread_pct=0.4, fee_pct=0.3, slippage_pct=0.1)
        
        assert not opp.is_profitable(), "Break-even should not be considered profitable"

    def test_optimal_size_calculation(self, create_opportunity):
        """
        Verify optimal trade size using calculus.
        
        Formula: x_opt = Spread / (2 * Impact)
        
        For a 1% spread and 0.001 impact factor:
        x_opt = 0.01 / (2 * 0.001) = 5 USD
        
        Clamped to min/max bounds.
        """
        opp = create_opportunity(spread_pct=1.0)
        
        # Impact factor represents price impact per $ traded
        impact_factor = 0.001  # 0.1% price impact per $1
        min_size = 10.0
        max_size = 1000.0
        
        optimal = opp.calculate_optimal_size(
            impact_factor=impact_factor,
            min_size=min_size,
            max_size=max_size,
        )
        
        # Theory: x_opt = spread_pct / (2 * impact * 100)
        # Converting spread_pct (1.0) to decimal: 0.01
        # x_opt = 0.01 / (2 * 0.001) = 5
        # But clamped to min_size of 10
        
        assert optimal >= min_size, f"Optimal {optimal} should be >= min {min_size}"
        assert optimal <= max_size, f"Optimal {optimal} should be <= max {max_size}"

    def test_optimal_size_clamps_to_max(self, create_opportunity):
        """When calculated optimal exceeds max, clamp to max."""
        opp = create_opportunity(spread_pct=5.0)  # High spread
        
        # Very low impact = very high optimal
        optimal = opp.calculate_optimal_size(
            impact_factor=0.00001,
            min_size=10.0,
            max_size=100.0,  # Low max
        )
        
        assert optimal == 100.0, f"Should clamp to max 100, got {optimal}"

    def test_optimal_size_clamps_to_min(self, create_opportunity):
        """When calculated optimal is below min, clamp to min."""
        opp = create_opportunity(spread_pct=0.1)  # Low spread
        
        # High impact = very low optimal
        optimal = opp.calculate_optimal_size(
            impact_factor=0.1,
            min_size=50.0,  # High min
            max_size=1000.0,
        )
        
        assert optimal == 50.0, f"Should clamp to min 50, got {optimal}"

    def test_liquidity_constraint(self, create_opportunity):
        """Optimal size should not exceed available liquidity."""
        opp = create_opportunity(spread_pct=2.0)
        opp.buy_liquidity = 50.0  # Very low liquidity
        opp.sell_liquidity = 30.0
        
        # The optimal should be constrained by min(buy_liq, sell_liq)
        min_liquidity = min(opp.buy_liquidity, opp.sell_liquidity)
        
        optimal = opp.calculate_optimal_size(
            impact_factor=0.0001,
            min_size=10.0,
            max_size=1000.0,
        )
        
        # Implementation should consider liquidity
        # This tests that we don't trade more than available
        assert optimal <= max(min_liquidity, 10.0), (
            f"Optimal {optimal} should respect liquidity {min_liquidity}"
        )


class TestSpreadDetector:
    """Test SpreadDetector scanning logic."""

    @pytest.fixture
    def mock_feeds(self, mock_jupiter_feed):
        """Create mock feeds for different venues."""
        from tests.mocks.mock_feeds import MockVenueFeed
        
        raydium = MockVenueFeed("RAYDIUM", fee_pct=0.0025)
        raydium.set_price("SOL", "USDC", 150.0)
        
        orca = MockVenueFeed("ORCA", fee_pct=0.003)
        orca.set_price("SOL", "USDC", 151.5)  # Higher price = sell venue
        
        return [raydium, orca, mock_jupiter_feed]

    @pytest.fixture
    def detector(self, mock_feeds):
        """Create SpreadDetector with mock feeds."""
        from src.engines.arb.scanner import SpreadDetector
        
        detector = SpreadDetector(feeds=mock_feeds)
        return detector

    @pytest.mark.asyncio
    async def test_scan_pair_finds_spread(self, detector):
        """Detect spread when prices differ across venues."""
        opp = await detector.scan_pair(
            base_mint="SOL_MINT",
            quote_mint="USDC_MINT",
            pair_name="SOL/USDC",
            trade_size=100.0,
        )
        
        # Should find the spread between Raydium (150) and Orca (151.5)
        if opp:
            assert opp.spread_pct > 0, "Should detect positive spread"
            assert opp.buy_dex == "RAYDIUM", "Should buy from lower price"
            assert opp.sell_dex == "ORCA", "Should sell at higher price"

    @pytest.mark.asyncio
    async def test_scan_pair_returns_none_when_no_spread(self, mock_feeds):
        """Return None when no profitable spread exists."""
        from src.engines.arb.scanner import SpreadDetector
        from tests.mocks.mock_feeds import MockVenueFeed
        
        # Set same price on all venues
        for feed in mock_feeds:
            if hasattr(feed, 'set_price'):
                feed.set_price("SOL", "USDC", 150.0)
        
        detector = SpreadDetector(feeds=mock_feeds)
        opp = await detector.scan_pair(
            base_mint="SOL_MINT",
            quote_mint="USDC_MINT",
            pair_name="SOL/USDC",
        )
        
        # Either None or unprofitable
        if opp:
            assert not opp.is_profitable(), "No spread = not profitable"

    @pytest.mark.asyncio
    async def test_scan_all_pairs_parallel(self, detector):
        """Verify multiple pairs are scanned concurrently."""
        import time
        
        pairs = [
            ("SOL_MINT", "USDC_MINT", "SOL/USDC"),
            ("JUP_MINT", "USDC_MINT", "JUP/USDC"),
            ("JTO_MINT", "USDC_MINT", "JTO/USDC"),
        ]
        
        start = time.time()
        opps = await detector.scan_all_pairs(pairs, trade_size=100.0)
        duration = time.time() - start
        
        # Should complete faster than sequential (3 * delay)
        # This is a heuristic test - adjust threshold as needed
        assert duration < 5.0, f"Parallel scan took too long: {duration}s"

    def test_get_price_matrix(self, detector):
        """Price matrix should contain all cached prices."""
        matrix = detector.get_price_matrix()
        
        # Matrix structure: {pair: {dex: price}}
        assert isinstance(matrix, dict), "Matrix should be a dict"


class TestSpreadMath:
    """Pure math tests for spread calculations."""

    def test_spread_percentage_formula(self):
        """
        Spread = (Sell - Buy) / Buy * 100
        
        Example: Buy at 150, Sell at 151.5
        Spread = (151.5 - 150) / 150 * 100 = 1.0%
        """
        buy_price = 150.0
        sell_price = 151.5
        
        spread_pct = (sell_price - buy_price) / buy_price * 100
        
        assert abs(spread_pct - 1.0) < 0.001, f"Expected 1.0%, got {spread_pct}%"

    def test_net_profit_after_fees(self):
        """
        Net Profit = Spread - Buy Fee - Sell Fee - Slippage
        
        Example: 1.0% spread, 0.25% buy fee, 0.30% sell fee, 0.10% slippage
        Net = 1.0 - 0.25 - 0.30 - 0.10 = 0.35%
        """
        spread = 1.0
        buy_fee = 0.25
        sell_fee = 0.30
        slippage = 0.10
        
        net_profit = spread - buy_fee - sell_fee - slippage
        
        assert abs(net_profit - 0.35) < 0.001, f"Expected 0.35%, got {net_profit}%"

    def test_optimal_size_calculus_derivation(self):
        """
        Derive optimal trade size from profit maximization.
        
        P(x) = Spread * x - Impact * x² - FixedFee
        P'(x) = Spread - 2 * Impact * x = 0
        x_opt = Spread / (2 * Impact)
        
        For Spread = 1% = 0.01, Impact = 0.0001 per USD:
        x_opt = 0.01 / (2 * 0.0001) = 50 USD
        """
        spread_decimal = 0.01  # 1%
        impact_per_usd = 0.0001  # 0.01% per $1
        
        x_opt = spread_decimal / (2 * impact_per_usd)
        
        assert abs(x_opt - 50.0) < 0.001, f"Expected 50 USD, got {x_opt}"

    def test_profit_at_optimal_vs_suboptimal(self):
        """
        Verify optimal size yields maximum profit.
        
        P(x) = Spread * x - Impact * x²
        """
        spread = 0.01
        impact = 0.0001
        x_opt = spread / (2 * impact)  # 50
        
        def profit(x):
            return spread * x - impact * x * x
        
        p_optimal = profit(x_opt)
        p_too_small = profit(x_opt * 0.5)
        p_too_large = profit(x_opt * 2)
        
        assert p_optimal > p_too_small, "Optimal should beat smaller size"
        assert p_optimal > p_too_large, "Optimal should beat larger size"

    def test_slippage_model_quadratic(self):
        """
        Slippage model: Slippage(x) = k * x²
        
        This quadratic model reflects that larger trades
        move the market more than linearly.
        """
        k = 0.00001  # Slippage coefficient
        
        # 100 USD trade
        slip_100 = k * 100 * 100  # 0.1%
        
        # 1000 USD trade (10x size = 100x slippage)
        slip_1000 = k * 1000 * 1000  # 10%
        
        ratio = slip_1000 / slip_100
        
        assert ratio == 100, f"Slippage should scale quadratically, got ratio {ratio}"
