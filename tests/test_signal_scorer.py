"""
Test suite for Rust SignalScorer integration.
Phase 4: Institutional Realism

Tests the PyO3 bindings for:
- ScorerConfig instantiation
- SignalScorer.score_trade() validation
- Batch scoring functionality
"""

import pytest


class TestSignalScorerImport:
    """Test that Rust module imports correctly."""

    def test_import_scorer_config(self):
        """ScorerConfig should be importable from phantom_core."""
        from phantom_core import ScorerConfig

        config = ScorerConfig()
        assert config is not None
        assert config.min_profit_usd == 0.10
        assert config.max_slippage_bps == 500

    def test_import_signal_scorer(self):
        """SignalScorer should be importable from phantom_core."""
        from phantom_core import SignalScorer, ScorerConfig

        config = ScorerConfig()
        scorer = SignalScorer(config)
        assert scorer is not None

    def test_import_validated_signal(self):
        """ValidatedSignal should be importable from phantom_core."""
        from phantom_core import ValidatedSignal

        # ValidatedSignal is only returned from score_trade, no constructor
        assert ValidatedSignal is not None


class TestScorerConfig:
    """Test ScorerConfig configuration."""

    def test_default_config(self):
        """Default config should have sensible values."""
        from phantom_core import ScorerConfig

        config = ScorerConfig()
        assert config.min_profit_usd == 0.10
        assert config.max_slippage_bps == 500
        assert config.gas_fee_usd == 0.02
        assert config.jito_tip_usd == 0.001
        assert config.dex_fee_bps == 30
        assert config.default_trade_size_usd == 15.0

    def test_custom_config(self):
        """Custom config values should be applied."""
        from phantom_core import ScorerConfig

        config = ScorerConfig(
            min_profit_usd=0.25,
            max_slippage_bps=300,
            gas_fee_usd=0.05,
            jito_tip_usd=0.01,
            dex_fee_bps=50,
            default_trade_size_usd=25.0,
        )
        assert config.min_profit_usd == 0.25
        assert config.max_slippage_bps == 300
        assert config.gas_fee_usd == 0.05
        assert config.dex_fee_bps == 50

    def test_config_repr(self):
        """Config repr should be human-readable."""
        from phantom_core import ScorerConfig

        config = ScorerConfig()
        repr_str = repr(config)
        assert "ScorerConfig" in repr_str
        assert "min_profit" in repr_str


class TestSignalScoring:
    """Test SignalScorer scoring logic."""

    @pytest.fixture
    def scorer(self):
        """Create a scorer with default config."""
        from phantom_core import SignalScorer, ScorerConfig

        return SignalScorer(ScorerConfig())

    @pytest.fixture
    def profitable_metadata(self):
        """Create metadata for a profitable trade scenario."""
        from phantom_core import SharedTokenMetadata

        m = SharedTokenMetadata("TestMint123")
        m.symbol = "TEST"
        m.is_rug_safe = True
        m.has_mint_auth = False
        m.liquidity_usd = 50_000.0
        m.spread_bps = 250  # 2.5% spread
        m.velocity_1m = 0.03
        m.order_imbalance = 1.3
        m.lp_locked_pct = 0.9
        m.transfer_fee_bps = 0
        return m

    def test_score_profitable_trade(self, scorer, profitable_metadata):
        """Profitable trade should return ValidatedSignal."""
        result = scorer.score_trade(profitable_metadata, 15.0)

        assert result is not None, "Expected ValidatedSignal for profitable trade"
        assert result.net_profit > 0.0
        assert result.action == "BUY"  # velocity_1m > 0
        assert 0.0 < result.confidence <= 1.0
        assert result.token == "TestMint123"

    def test_score_unprofitable_trade(self, scorer, profitable_metadata):
        """Unprofitable trade (low spread) should return None."""
        profitable_metadata.spread_bps = 5  # 0.05% - too low

        result = scorer.score_trade(profitable_metadata, 15.0)

        assert result is None, "Expected None for unprofitable trade"

    def test_score_unsafe_token(self, scorer, profitable_metadata):
        """Unsafe token (mint auth active) should return None."""
        profitable_metadata.has_mint_auth = True

        result = scorer.score_trade(profitable_metadata, 15.0)

        assert result is None, "Expected None for unsafe token"

    def test_score_low_liquidity(self, scorer, profitable_metadata):
        """Low liquidity token should return None."""
        profitable_metadata.liquidity_usd = 100.0  # Below $500 floor

        result = scorer.score_trade(profitable_metadata, 15.0)

        assert result is None, "Expected None for low liquidity token"

    def test_validated_signal_fields(self, scorer, profitable_metadata):
        """ValidatedSignal should have all expected fields."""
        result = scorer.score_trade(profitable_metadata, 15.0)

        assert hasattr(result, "net_profit")
        assert hasattr(result, "confidence")
        assert hasattr(result, "token")
        assert hasattr(result, "action")
        assert hasattr(result, "gross_spread")
        assert hasattr(result, "total_frictions")

        # Verify friction breakdown
        assert result.gross_spread > result.net_profit
        assert result.total_frictions > 0


class TestBatchScoring:
    """Test batch scoring functionality."""

    def test_score_batch_mixed(self):
        """Batch scoring should filter out bad trades."""
        from phantom_core import SignalScorer, ScorerConfig, SharedTokenMetadata

        config = ScorerConfig()
        scorer = SignalScorer(config)

        # Create good and bad tokens
        good_token = SharedTokenMetadata("GoodToken")
        good_token.is_rug_safe = True
        good_token.has_mint_auth = False
        good_token.liquidity_usd = 50_000.0
        good_token.spread_bps = 250
        good_token.velocity_1m = 0.03
        good_token.transfer_fee_bps = 0

        bad_token = SharedTokenMetadata("BadToken")
        bad_token.is_rug_safe = True
        bad_token.has_mint_auth = True  # Unsafe!
        bad_token.liquidity_usd = 50_000.0
        bad_token.spread_bps = 250
        bad_token.velocity_1m = 0.03
        bad_token.transfer_fee_bps = 0

        batch = [good_token, bad_token]
        results = scorer.score_batch(batch, 15.0)

        assert len(results) == 1, "Only good token should pass"
        assert results[0].token == "GoodToken"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
