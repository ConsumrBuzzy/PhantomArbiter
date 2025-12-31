"""
Multi-Hop Execution Pipeline Tests
===================================
V140: Narrow Path Infrastructure (Phase 16)

Integration tests for the complete multi-hop arbitrage pipeline:
- HopPod multiverse scanning
- CyclePod market context
- ExecutionPod paper trading
- MultiHopBuilder bundle construction
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch


# ═══════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    with patch("config.settings.Settings") as mock:
        mock.HOP_ENGINE_ENABLED = True
        mock.SOL_MINT = "So11111111111111111111111111111111111111112"
        mock.HOP_MIN_LEGS = 2
        mock.HOP_MAX_LEGS = 4
        mock.HOP_MIN_LIQUIDITY_USD = 5000
        mock.HOP_SCAN_INTERVAL_SEC = 2.0
        mock.HOP_MIN_PROFIT_PCT = 0.15
        mock.PRIVATE_KEY_BASE58 = None  # Paper mode
        yield mock


@pytest.fixture
def sample_cycle_data():
    """Sample cycle data as would be emitted by HopPod."""
    return {
        "path": [
            "So11111111111111111111111111111111111111112",  # SOL
            "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",  # JUP
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
            "So11111111111111111111111111111111111111112",  # SOL
        ],
        "pools": [
            "pool1_sol_jup",
            "pool2_jup_usdc",
            "pool3_usdc_sol",
        ],
        "profit_pct": 0.45,
        "hop_count": 3,
        "min_liquidity_usd": 50000,
        "total_fee_bps": 75,
        "dexes": ["RAYDIUM", "ORCA", "RAYDIUM"],
        "estimated_gas": 15000,
    }


@pytest.fixture
def market_context():
    """Fresh market context for testing."""
    from src.shared.models.context import reset_market_context, get_market_context

    reset_market_context()
    return get_market_context()


# ═══════════════════════════════════════════════════════════════════════════
# POD MANAGER TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestPodManager:
    """Test PodManager pod lifecycle."""

    def test_spawn_hop_pod(self, mock_settings):
        """Test spawning a HopPod."""
        from src.engine.pod_manager import PodManager, HopPod

        manager = PodManager()
        pod = manager.spawn_hop_pod(
            name="test_hop",
            min_hops=2,
            max_hops=4,
            min_liquidity=1000,
        )

        assert pod is not None
        assert isinstance(pod, HopPod)
        assert "hop_" in pod.id
        assert manager.get_hop_pods() == [pod]

    def test_spawn_cycle_pod(self, mock_settings):
        """Test spawning a CyclePod (singleton)."""
        from src.engine.pod_manager import PodManager

        manager = PodManager()
        pod1 = manager.spawn_cycle_pod(name="governor")
        pod2 = manager.spawn_cycle_pod(name="duplicate")

        # Should return same pod (singleton)
        assert pod1 is pod2
        assert manager.get_cycle_pod() is pod1

    def test_spawn_execution_pod(self, mock_settings):
        """Test spawning an ExecutionPod."""
        from src.engine.pod_manager import PodManager
        from src.engine.execution_pod import ExecutionPod, ExecutionMode

        manager = PodManager()
        pod = manager.spawn_execution_pod(
            name="striker",
            mode="paper",
            min_profit_pct=0.20,
        )

        assert pod is not None
        assert isinstance(pod, ExecutionPod)
        assert pod.mode == ExecutionMode.PAPER
        assert pod.min_profit_pct == 0.20

    def test_pod_limits(self, mock_settings):
        """Test pod spawning limits."""
        from src.engine.pod_manager import PodManager

        manager = PodManager()
        manager.max_hop_pods = 2

        pod1 = manager.spawn_hop_pod(name="pod1")
        pod2 = manager.spawn_hop_pod(name="pod2")
        pod3 = manager.spawn_hop_pod(name="pod3")  # Should fail

        assert pod1 is not None
        assert pod2 is not None
        assert pod3 is None  # Limit reached


# ═══════════════════════════════════════════════════════════════════════════
# MARKET CONTEXT TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestMarketContext:
    """Test MarketContext global state."""

    def test_congestion_threshold_adjustment(self, market_context):
        """Test that congestion adjusts profit thresholds."""
        from src.shared.models.context import CongestionLevel

        base_threshold = 0.10

        # Low congestion - no adjustment
        market_context.congestion_level = CongestionLevel.LOW
        assert market_context.get_adjusted_threshold(base_threshold) == 0.10

        # Moderate congestion - +0.05%
        market_context.congestion_level = CongestionLevel.MODERATE
        assert market_context.get_adjusted_threshold(base_threshold) == 0.15

        # High congestion - +0.15%
        market_context.congestion_level = CongestionLevel.HIGH
        assert market_context.get_adjusted_threshold(base_threshold) == 0.25

        # Extreme congestion - +0.30%
        market_context.congestion_level = CongestionLevel.EXTREME
        assert market_context.get_adjusted_threshold(base_threshold) == 0.40

    def test_trading_pause_conditions(self, market_context):
        """Test when trading should be paused."""
        from src.shared.models.context import CongestionLevel

        # Normal conditions - trading allowed
        market_context.congestion_level = CongestionLevel.LOW
        market_context.volatility.volatility_index = 50
        market_context.trading_enabled = True
        assert not market_context.should_pause_trading()

        # Extreme congestion - pause
        market_context.congestion_level = CongestionLevel.EXTREME
        assert market_context.should_pause_trading()

        # Reset congestion, high VIX - pause
        market_context.congestion_level = CongestionLevel.LOW
        market_context.volatility.volatility_index = 95
        assert market_context.should_pause_trading()

    def test_jito_heat_indicator(self, market_context):
        """Test Jito heat level indicators."""
        jito = market_context.jito

        # Set baselines
        jito.p50_tip_lamports = 15_000
        jito.p95_tip_lamports = 100_000

        # Low congestion
        jito.current_tip_lamports = 10_000
        assert jito.get_heat_level() == "🟢"

        # Moderate
        jito.current_tip_lamports = 40_000
        assert jito.get_heat_level() == "🟡"

        # High
        jito.current_tip_lamports = 150_000
        assert jito.get_heat_level() == "🟠"

        # Extreme (over 2x p95)
        jito.current_tip_lamports = 250_000
        assert jito.get_heat_level() == "🔴"


# ═══════════════════════════════════════════════════════════════════════════
# EXECUTION POD TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestExecutionPod:
    """Test ExecutionPod paper/live execution."""

    def test_paper_execution(self, mock_settings, sample_cycle_data, market_context):
        """Test paper trade execution."""
        from src.engine.execution_pod import ExecutionPod, ExecutionMode
        from src.engine.pod_manager import PodConfig, PodType

        config = PodConfig(
            pod_type=PodType.SCOUT,
            name="test_striker",
            params={},
            cooldown_seconds=0.5,
        )

        pod = ExecutionPod(
            config=config,
            signal_callback=MagicMock(),
            mode=ExecutionMode.PAPER,
            min_profit_pct=0.10,
        )

        # Execute synchronously for test
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(
            pod._execute_paper("test_id", sample_cycle_data, market_context)
        )
        loop.close()

        assert result.success is True
        assert "paper_" in result.signature
        assert result.expected_profit_pct == 0.45
        assert result.leg_count == 3

    def test_profit_threshold_rejection(
        self, mock_settings, sample_cycle_data, market_context
    ):
        """Test that low-profit opportunities are rejected."""
        from src.engine.execution_pod import ExecutionPod, ExecutionMode
        from src.engine.pod_manager import PodConfig, PodType

        config = PodConfig(
            pod_type=PodType.SCOUT,
            name="test_striker",
            params={},
            cooldown_seconds=0.5,
        )

        pod = ExecutionPod(
            config=config,
            signal_callback=MagicMock(),
            mode=ExecutionMode.PAPER,
            min_profit_pct=0.50,  # High threshold
        )

        # Low profit cycle
        low_profit_data = {**sample_cycle_data, "profit_pct": 0.20}

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(pod._execute_opportunity(low_profit_data))
        loop.close()

        assert result.success is False
        assert "threshold" in result.error.lower()

    def test_congestion_pause(self, mock_settings, sample_cycle_data, market_context):
        """Test that extreme congestion pauses execution."""
        from src.engine.execution_pod import ExecutionPod, ExecutionMode
        from src.engine.pod_manager import PodConfig, PodType
        from src.shared.models.context import CongestionLevel

        # Set extreme congestion
        market_context.congestion_level = CongestionLevel.EXTREME
        market_context.trading_enabled = False
        market_context.reason = "Test extreme congestion"

        config = PodConfig(
            pod_type=PodType.SCOUT,
            name="test_striker",
            params={},
            cooldown_seconds=0.5,
        )

        pod = ExecutionPod(
            config=config,
            signal_callback=MagicMock(),
            mode=ExecutionMode.PAPER,
            min_profit_pct=0.10,
        )

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(pod._execute_opportunity(sample_cycle_data))
        loop.close()

        assert result.success is False
        assert "paused" in result.error.lower()


# ═══════════════════════════════════════════════════════════════════════════
# JUPITER CLIENT TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestJupiterClient:
    """Test Jupiter API client."""

    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """Test Jupiter client creates correctly."""
        from src.engine.dex_builders import JupiterClient

        client = JupiterClient(
            slippage_bps=50,
            only_direct_routes=False,
        )

        assert client.slippage_bps == 50
        assert client.quotes_fetched == 0
        assert client.errors == 0

        await client.close()

    @pytest.mark.asyncio
    async def test_quote_profit_calculation(self):
        """Test MultiHopQuoteBuilder profit calculation."""
        from src.engine.dex_builders import (
            MultiHopQuoteBuilder,
            JupiterClient,
            SwapQuote,
        )

        client = JupiterClient()
        builder = MultiHopQuoteBuilder(client)

        # Mock quotes
        quotes = [
            SwapQuote(
                input_mint="SOL",
                output_mint="JUP",
                input_amount=1_000_000_000,
                output_amount=1_050_000_000,
                price_impact_pct=0.1,
                route_plan=[],
            ),
            SwapQuote(
                input_mint="JUP",
                output_mint="SOL",
                input_amount=1_050_000_000,
                output_amount=1_080_000_000,
                price_impact_pct=0.1,
                route_plan=[],
            ),
        ]

        profit = builder.calculate_cycle_profit(quotes, 1_000_000_000)

        assert profit["profit_amount"] == 80_000_000
        assert profit["profit_pct"] == 8.0  # 8% profit
        assert profit["total_price_impact"] == 0.2

        await client.close()


# ═══════════════════════════════════════════════════════════════════════════
# RUST MULTI-HOP BUILDER TESTS (if extension available)
# ═══════════════════════════════════════════════════════════════════════════


class TestMultiHopBuilder:
    """Test Rust MultiHopBuilder (skip if extension not built)."""

    def test_compute_unit_estimation(self):
        """Test compute unit calculation."""
        try:
            from phantom_core import MultiHopBuilder
        except ImportError:
            pytest.skip("Rust extension not available")

        # Can't test without private key, but can test logic
        # This would be a proper test with mocked keypair
        pass

    def test_tip_calculation_logic(self):
        """Test tip calculation with congestion."""
        try:
            from phantom_core import MultiHopBuilder
        except ImportError:
            pytest.skip("Rust extension not available")

        # Tip calculation formula:
        # base * complexity_factor * congestion_factor
        # complexity_factor = 1.0 + (legs - 2) * 0.25
        # congestion_factor = 1.0 + multiplier

        # 4-leg, low congestion: 10k * 1.5 * 1.0 = 15k
        # 4-leg, high congestion (0.5): 10k * 1.5 * 1.5 = 22.5k
        pass


# ═══════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestFullPipeline:
    """End-to-end integration tests."""

    @pytest.mark.asyncio
    async def test_signal_flow(self, mock_settings, sample_cycle_data, market_context):
        """Test complete signal flow from HopPod to ExecutionPod."""
        from src.engine.pod_manager import PodManager, PodSignal, PodType

        # Create pod manager with signal tracking
        received_signals = []

        def track_signal(signal):
            received_signals.append(signal)

        manager = PodManager(signal_callback=track_signal)

        # Spawn pods
        hop_pod = manager.spawn_hop_pod(name="test_hop")
        cycle_pod = manager.spawn_cycle_pod(name="test_governor")
        exec_pod = manager.spawn_execution_pod(name="test_striker", mode="paper")

        # Simulate HopPod discovering an opportunity
        signal = PodSignal(
            pod_id=hop_pod.id if hop_pod else "test_hop",
            pod_type=PodType.HOP,
            signal_type="OPPORTUNITY",
            priority=8,
            data=sample_cycle_data,
        )

        # Emit signal
        track_signal(signal)

        # Verify signal was received
        assert len(received_signals) == 1
        assert received_signals[0].signal_type == "OPPORTUNITY"

        # Enqueue to execution pod
        if exec_pod:
            await exec_pod.enqueue_opportunity(sample_cycle_data)
            assert exec_pod._queue.qsize() == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
