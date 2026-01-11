"""
DeltaState Unit Tests
=====================
Tests for delta neutrality monitoring.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock


class TestDeltaState:
    """Test DeltaState dataclass."""

    def test_is_neutral_when_balanced(self):
        """is_neutral should return True when drift < 1%."""
        from src.monitoring.neutrality import DeltaState, HedgeStatus
        
        state = DeltaState(
            spot_qty=1.0,
            perp_qty=-1.0,
            drift_pct=0.5,
            status=HedgeStatus.BALANCED,
        )
        
        assert state.is_neutral

    def test_is_neutral_when_drifted(self):
        """is_neutral should return False when drift >= 1%."""
        from src.monitoring.neutrality import DeltaState, HedgeStatus
        
        state = DeltaState(
            spot_qty=1.0,
            perp_qty=-0.5,
            drift_pct=2.5,
            status=HedgeStatus.UNDERHEDGED,
        )
        
        assert not state.is_neutral

    def test_urgency_levels(self):
        """urgency should return correct level based on drift."""
        from src.monitoring.neutrality import DeltaState
        
        # OK
        ok_state = DeltaState(drift_pct=0.3)
        assert ok_state.urgency == "OK"
        
        # ATTENTION
        attention_state = DeltaState(drift_pct=0.8)
        assert attention_state.urgency == "ATTENTION"
        
        # WARNING
        warning_state = DeltaState(drift_pct=3.0)
        assert warning_state.urgency == "WARNING"
        
        # CRITICAL
        critical_state = DeltaState(drift_pct=6.0)
        assert critical_state.urgency == "CRITICAL"

    def test_to_dict(self):
        """to_dict should include all fields."""
        from src.monitoring.neutrality import DeltaState, HedgeStatus
        
        state = DeltaState(
            spot_qty=1.5,
            perp_qty=-1.5,
            spot_exposure_usd=225.0,
            perp_exposure_usd=-225.0,
            net_delta_usd=0.0,
            drift_pct=0.0,
            status=HedgeStatus.BALANCED,
            sol_price=150.0,
        )
        
        data = state.to_dict()
        
        assert data["spot_qty"] == 1.5
        assert data["perp_qty"] == -1.5
        assert data["status"] == "BALANCED"
        assert data["sol_price"] == 150.0


class TestHedgeStatus:
    """Test HedgeStatus enum."""

    def test_all_statuses_exist(self):
        """All expected statuses should exist."""
        from src.monitoring.neutrality import HedgeStatus
        
        assert HedgeStatus.BALANCED
        assert HedgeStatus.OVERHEDGED
        assert HedgeStatus.UNDERHEDGED
        assert HedgeStatus.CRITICAL
        assert HedgeStatus.UNKNOWN


class TestDeltaCalculator:
    """Test DeltaCalculator functionality."""

    @pytest.fixture
    def mock_wallet(self):
        """Mock wallet."""
        wallet = MagicMock()
        wallet.get_sol_balance.return_value = 1.0
        return wallet

    @pytest.fixture
    def mock_drift(self):
        """Mock Drift adapter."""
        drift = MagicMock()
        drift.get_perp_position.return_value = {"size": -1.0}
        drift.get_funding_rate.return_value = 0.001
        return drift

    @pytest.fixture
    def calculator(self, mock_wallet, mock_drift):
        """Create calculator with mocks."""
        from src.monitoring.neutrality import DeltaCalculator
        return DeltaCalculator(
            wallet=mock_wallet,
            drift_adapter=mock_drift,
        )

    @pytest.mark.asyncio
    async def test_calculate_returns_delta_state(self, calculator):
        """calculate() should return DeltaState."""
        from src.monitoring.neutrality import DeltaState
        
        delta = await calculator.calculate(sol_price=150.0)
        
        assert isinstance(delta, DeltaState)

    @pytest.mark.asyncio
    async def test_calculate_balanced(self, calculator):
        """Should detect balanced hedge."""
        from src.monitoring.neutrality import HedgeStatus
        
        delta = await calculator.calculate(sol_price=150.0)
        
        # 1.0 SOL spot, -1.0 SOL perp = balanced
        assert delta.drift_pct < 1.0
        assert delta.status == HedgeStatus.BALANCED

    @pytest.mark.asyncio
    async def test_calculate_underhedged(self, mock_wallet, mock_drift):
        """Should detect underhedged position."""
        from src.monitoring.neutrality import DeltaCalculator, HedgeStatus
        
        mock_drift.get_perp_position.return_value = {"size": -0.5}  # Only half hedged
        
        calculator = DeltaCalculator(wallet=mock_wallet, drift_adapter=mock_drift)
        delta = await calculator.calculate(sol_price=150.0)
        
        # 1.0 SOL spot, -0.5 SOL perp = underhedged
        assert delta.net_delta_usd > 0
        assert delta.needs_rebalance
        assert delta.suggested_action == "ADD_SHORT"

    @pytest.mark.asyncio
    async def test_calculate_overhedged(self, mock_wallet, mock_drift):
        """Should detect overhedged position."""
        from src.monitoring.neutrality import DeltaCalculator, HedgeStatus
        
        mock_drift.get_perp_position.return_value = {"size": -2.0}  # Too much short
        
        calculator = DeltaCalculator(wallet=mock_wallet, drift_adapter=mock_drift)
        delta = await calculator.calculate(sol_price=150.0)
        
        # 1.0 SOL spot, -2.0 SOL perp = overhedged
        assert delta.net_delta_usd < 0
        assert delta.needs_rebalance
        assert delta.suggested_action == "REDUCE_SHORT"

    def test_avg_drift_tracking(self, calculator):
        """Should track drift history."""
        # Manually add samples
        calculator._drift_history = [1.0, 2.0, 3.0]
        
        assert calculator.get_avg_drift() == 2.0
        assert calculator.get_max_drift() == 3.0


class TestSafetyGateChecker:
    """Test SafetyGateChecker functionality."""

    @pytest.fixture
    def mock_latency(self):
        """Mock latency monitor."""
        latency = MagicMock()
        latency.get_stats.return_value = {"wss_avg_ms": 100}
        return latency

    @pytest.fixture
    def mock_wallet(self):
        """Mock wallet with sufficient balance."""
        wallet = MagicMock()
        wallet.get_sol_balance.return_value = 0.5
        return wallet

    @pytest.mark.asyncio
    async def test_all_clear(self, mock_latency, mock_wallet):
        """Should return all_clear when gates pass."""
        from src.monitoring.neutrality import SafetyGateChecker
        
        checker = SafetyGateChecker(
            latency_monitor=mock_latency,
            wallet=mock_wallet,
        )
        
        status = await checker.check_all()
        
        assert status.all_clear
        assert status.latency_ok
        assert status.balance_ok
        assert len(status.active_blocks) == 0

    @pytest.mark.asyncio
    async def test_latency_block(self, mock_wallet):
        """Should block on high latency."""
        from src.monitoring.neutrality import SafetyGateChecker
        
        slow_latency = MagicMock()
        slow_latency.get_stats.return_value = {"wss_avg_ms": 600}
        
        checker = SafetyGateChecker(
            latency_monitor=slow_latency,
            wallet=mock_wallet,
        )
        
        status = await checker.check_all()
        
        assert not status.all_clear
        assert not status.latency_ok
        assert any("LATENCY" in b for b in status.active_blocks)

    @pytest.mark.asyncio
    async def test_balance_block(self, mock_latency):
        """Should block on low balance."""
        from src.monitoring.neutrality import SafetyGateChecker
        
        poor_wallet = MagicMock()
        poor_wallet.get_sol_balance.return_value = 0.005  # Too low
        
        checker = SafetyGateChecker(
            latency_monitor=mock_latency,
            wallet=poor_wallet,
        )
        
        status = await checker.check_all()
        
        assert not status.all_clear
        assert not status.balance_ok
        assert any("GAS" in b for b in status.active_blocks)
