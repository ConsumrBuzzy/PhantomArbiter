"""
RecoveryManager Unit Tests
==========================
Tests for partial fill detection and recovery paths.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock


class TestPositionState:
    """Test PositionState dataclass."""

    def test_neutral_check_true(self):
        """is_neutral should return True when balanced."""
        from src.execution.recovery_manager import PositionState
        
        state = PositionState(
            sol_balance=1.0,
            perp_size=-1.0,  # Short 1 SOL
        )
        
        assert state.is_neutral()

    def test_neutral_check_false(self):
        """is_neutral should return False when unbalanced."""
        from src.execution.recovery_manager import PositionState
        
        state = PositionState(
            sol_balance=1.0,
            perp_size=-0.5,  # Only half hedged
        )
        
        assert not state.is_neutral()

    def test_neutral_with_tolerance(self):
        """is_neutral should respect tolerance."""
        from src.execution.recovery_manager import PositionState
        
        state = PositionState(
            sol_balance=1.0,
            perp_size=-1.005,  # 0.5% off
        )
        
        # Should pass with default 0.01 tolerance
        assert state.is_neutral(tolerance=0.01)


class TestPartialFillAnalysis:
    """Test partial fill detection."""

    def test_spot_only_classification(self):
        """SPOT_ONLY when only spot executed."""
        from src.execution.recovery_manager import PartialFillAnalysis, PartialFillType
        
        analysis = PartialFillAnalysis(
            fill_type=PartialFillType.SPOT_ONLY,
            is_partial_fill=True,
            spot_executed=True,
            perp_executed=False,
            spot_delta=1.0,
            perp_delta=0.0,
        )
        
        assert analysis.is_partial_fill
        assert analysis.spot_executed
        assert not analysis.perp_executed

    def test_perp_only_classification(self):
        """PERP_ONLY when only perp executed."""
        from src.execution.recovery_manager import PartialFillAnalysis, PartialFillType
        
        analysis = PartialFillAnalysis(
            fill_type=PartialFillType.PERP_ONLY,
            is_partial_fill=True,
            spot_executed=False,
            perp_executed=True,
            spot_delta=0.0,
            perp_delta=-1.0,
        )
        
        assert analysis.is_partial_fill
        assert not analysis.spot_executed
        assert analysis.perp_executed

    def test_both_is_not_partial(self):
        """BOTH should not be marked as partial."""
        from src.execution.recovery_manager import PartialFillAnalysis, PartialFillType
        
        analysis = PartialFillAnalysis(
            fill_type=PartialFillType.BOTH,
            is_partial_fill=False,
            spot_executed=True,
            perp_executed=True,
        )
        
        assert not analysis.is_partial_fill


class TestRecoveryPath:
    """Test RecoveryPath calculation."""

    def test_recovery_path_description(self):
        """RecoveryPath should have human-readable description."""
        from src.execution.recovery_manager import RecoveryPath
        
        path = RecoveryPath(
            action="SELL_SPOT",
            asset="SOL",
            size=1.5,
            urgency="IMMEDIATE",
            reason="Perp leg failed",
            estimated_cost_usd=11.25,
        )
        
        assert "SELL_SPOT" in path.description
        assert "1.5" in path.description
        assert "SOL" in path.description


class TestRecoveryManager:
    """Test RecoveryManager functionality."""

    @pytest.fixture
    def mock_wallet(self):
        """Mock wallet manager."""
        wallet = MagicMock()
        wallet.get_sol_balance.return_value = 0.5
        wallet.get_current_live_usd_balance.return_value = {
            "breakdown": {"USDC": 100.0}
        }
        return wallet

    @pytest.fixture
    def mock_drift(self):
        """Mock Drift adapter."""
        drift = MagicMock()
        drift.get_perp_position.return_value = {
            "size": -0.5,
            "entry_price": 150.0,
        }
        return drift

    @pytest.fixture
    def recovery_manager(self, mock_wallet, mock_drift):
        """Create RecoveryManager with mocks."""
        from src.execution.recovery_manager import RecoveryManager
        return RecoveryManager(mock_wallet, mock_drift)

    @pytest.mark.asyncio
    async def test_capture_pre_trade(self, recovery_manager):
        """capture_pre_trade should return snapshot key."""
        key = await recovery_manager.capture_pre_trade()
        
        assert key is not None
        assert key.startswith("snapshot_")

    @pytest.mark.asyncio
    async def test_analyze_no_snapshot(self, recovery_manager):
        """analyze_post_trade should handle missing snapshot."""
        # Don't capture pre-trade
        analysis = await recovery_manager.analyze_post_trade()
        
        assert not analysis.is_partial_fill

    def test_calculate_recovery_spot_only(self, recovery_manager):
        """Should calculate SELL_SPOT path for spot-only fill."""
        from src.execution.recovery_manager import PartialFillAnalysis, PartialFillType
        
        analysis = PartialFillAnalysis(
            fill_type=PartialFillType.SPOT_ONLY,
            is_partial_fill=True,
            spot_executed=True,
            perp_executed=False,
            spot_delta=1.0,
            perp_delta=0.0,
            net_exposure=1.0,
            recovery_needed=True,
            recovery_action="SELL_SPOT",
            recovery_size=1.0,
        )
        
        path = recovery_manager.calculate_recovery_path(analysis)
        
        assert path is not None
        assert path.action == "SELL_SPOT"
        assert path.asset == "SOL"
        assert path.size == 1.0

    def test_calculate_recovery_perp_only(self, recovery_manager):
        """Should calculate CLOSE_SHORT path for perp-only fill."""
        from src.execution.recovery_manager import PartialFillAnalysis, PartialFillType
        
        analysis = PartialFillAnalysis(
            fill_type=PartialFillType.PERP_ONLY,
            is_partial_fill=True,
            spot_executed=False,
            perp_executed=True,
            spot_delta=0.0,
            perp_delta=-1.0,  # Short opened
            net_exposure=-1.0,
            recovery_needed=True,
            recovery_action="CLOSE_PERP",
            recovery_size=1.0,
        )
        
        path = recovery_manager.calculate_recovery_path(analysis)
        
        assert path is not None
        assert path.action == "CLOSE_SHORT"
        assert path.asset == "SOL-PERP"

    def test_no_recovery_when_not_needed(self, recovery_manager):
        """Should return None when no recovery needed."""
        from src.execution.recovery_manager import PartialFillAnalysis, PartialFillType
        
        analysis = PartialFillAnalysis(
            fill_type=PartialFillType.BOTH,
            is_partial_fill=False,
            recovery_needed=False,
        )
        
        path = recovery_manager.calculate_recovery_path(analysis)
        
        assert path is None

    def test_stats_tracking(self, recovery_manager):
        """get_stats should return statistics."""
        stats = recovery_manager.get_stats()
        
        assert "partials_detected" in stats
        assert "recoveries_executed" in stats
        assert "recoveries_failed" in stats
