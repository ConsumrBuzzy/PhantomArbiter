"""
Test Friction Feedback - Market Volatility → Slippage

Verifies that the FrictionCalculator responds to market conditions.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "apps", "execution", "src"))

from execution.friction_calculator import FrictionCalculator, FrictionConfig


class TestFrictionBasics:
    """Basic friction calculation tests."""
    
    @pytest.fixture
    def calculator(self):
        return FrictionCalculator()
    
    def test_base_slippage(self, calculator):
        """Small trade on large pool has base slippage."""
        result = calculator.calculate(
            size_usd=100.0,
            price=150.0,
            liquidity_usd=1_000_000.0,
            is_volatile=False,
        )
        
        # Should be close to base (0.3%)
        assert 0.002 < result.slippage_pct < 0.01
        assert result.slippage_usd > 0
    
    def test_size_impact(self, calculator):
        """Larger trades have more slippage."""
        small = calculator.calculate(size_usd=100, price=100, liquidity_usd=10000)
        large = calculator.calculate(size_usd=5000, price=100, liquidity_usd=10000)
        
        # Large trade should have more slippage
        assert large.slippage_pct > small.slippage_pct
    
    def test_volatility_multiplier(self, calculator):
        """Volatile markets have 3x slippage."""
        calm = calculator.calculate(
            size_usd=100, price=100, liquidity_usd=10000, is_volatile=False
        )
        choppy = calculator.calculate(
            size_usd=100, price=100, liquidity_usd=10000, is_volatile=True
        )
        
        # Choppy should be ~3x (minus base)
        assert choppy.slippage_pct > calm.slippage_pct * 2
    
    def test_slippage_cap(self, calculator):
        """Slippage capped at 10%."""
        result = calculator.calculate(
            size_usd=100000,  # Huge trade
            price=100,
            liquidity_usd=1000,  # Tiny pool
            is_volatile=True,
        )
        
        # Cap at 10%
        assert result.slippage_pct <= 0.10


class TestFrictionImpact:
    """Tests for friction impact on effective price."""
    
    @pytest.fixture
    def calculator(self):
        return FrictionCalculator()
    
    def test_buy_price_higher(self, calculator):
        """Buy effective price is higher than market."""
        result = calculator.calculate(
            size_usd=100, price=100.0, liquidity_usd=10000, is_buy=True
        )
        
        assert result.effective_price > 100.0
    
    def test_sell_price_lower(self, calculator):
        """Sell effective price is lower than market."""
        result = calculator.calculate(
            size_usd=100, price=100.0, liquidity_usd=10000, is_buy=False
        )
        
        assert result.effective_price < 100.0
    
    def test_gas_fees_included(self, calculator):
        """Gas fees are calculated."""
        result = calculator.calculate(size_usd=100, price=100, liquidity_usd=10000)
        
        assert result.gas_fee_sol > 0
        assert result.gas_fee_usd > 0


class TestLowLiquidityPools:
    """Tests for low liquidity scenarios."""
    
    @pytest.fixture
    def calculator(self):
        return FrictionCalculator()
    
    def test_small_pool_high_impact(self, calculator):
        """$1000 trade on $1000 pool = massive slippage."""
        result = calculator.calculate(
            size_usd=1000,
            price=1.0,
            liquidity_usd=1000,
        )
        
        # 100% of pool = very high impact
        assert result.slippage_pct > 0.05  # >5%
    
    def test_comparing_pools(self, calculator):
        """Same trade, different pools, different slippage."""
        tiny_pool = calculator.calculate(
            size_usd=100, price=1.0, liquidity_usd=500
        )
        big_pool = calculator.calculate(
            size_usd=100, price=1.0, liquidity_usd=1_000_000
        )
        
        # Ratio should be significant
        assert tiny_pool.slippage_pct > big_pool.slippage_pct * 5


class TestMEVRisk:
    """Tests for MEV simulation."""
    
    def test_mev_sometimes_applies(self):
        """MEV risk applies stochastically."""
        calculator = FrictionCalculator()
        
        mev_count = 0
        iterations = 100
        
        for _ in range(iterations):
            result = calculator.calculate(
                size_usd=100, price=100, liquidity_usd=10000
            )
            if result.mev_applied:
                mev_count += 1
        
        # Should apply roughly 5% of the time (with variance)
        assert 0 < mev_count < 30  # Allow wide variance


class TestConfigurable:
    """Tests for custom friction config."""
    
    def test_custom_base_spread(self):
        """Custom base spread is applied."""
        config = FrictionConfig(base_spread_pct=0.01)  # 1%
        calculator = FrictionCalculator(config)
        
        result = calculator.calculate(
            size_usd=100, price=100, liquidity_usd=1_000_000
        )
        
        # Should be close to 1%
        assert result.slippage_pct >= 0.01
    
    def test_custom_gas_fees(self):
        """Custom gas fees are applied."""
        config = FrictionConfig(gas_fee_sol=0.001)  # 10x normal
        calculator = FrictionCalculator(config)
        
        result = calculator.calculate(size_usd=100, price=100, liquidity_usd=10000)
        
        assert result.gas_fee_sol >= 0.001


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
