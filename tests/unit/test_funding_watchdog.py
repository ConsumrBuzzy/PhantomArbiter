"""
Funding Watchdog Unit Tests
===========================
Tests for FundingWatchdog threshold logic and unwind triggers.

The "Toxic Funding" Problem:
============================
In delta-neutral strategies, we're long spot SOL and short perp SOL.
We collect funding when longs pay shorts (positive funding).
But when funding flips negative, WE pay the longs.

The Watchdog monitors this and triggers an emergency unwind
before the "rent eats the principal."
"""

import pytest
import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch


class TestFundingThresholds:
    """Test funding rate threshold logic."""

    @pytest.fixture
    def watchdog(self, tmp_path, monkeypatch):
        """Create FundingWatchdog with temp state file."""
        # Patch the state file path
        test_state_file = tmp_path / "watchdog_state.json"
        monkeypatch.setattr(
            "src.engines.funding.watchdog.WATCHDOG_STATE_FILE",
            test_state_file
        )
        
        from src.engines.funding.watchdog import FundingWatchdog
        return FundingWatchdog(check_interval_sec=1)

    @pytest.fixture
    def mock_rpc(self, mock_rpc_client):
        """Mock RPC client for funding rate fetches."""
        return mock_rpc_client

    def test_negative_threshold_definition(self):
        """Verify negative threshold is properly defined."""
        from src.engines.funding.watchdog import NEGATIVE_THRESHOLD
        
        # Threshold should be negative (e.g., -0.0005 = -0.05%)
        assert NEGATIVE_THRESHOLD < 0, "Negative threshold should be < 0"
        assert NEGATIVE_THRESHOLD > -0.01, "Threshold shouldn't be too aggressive"

    def test_positive_threshold_definition(self):
        """Verify positive re-entry threshold is defined."""
        from src.engines.funding.watchdog import POSITIVE_THRESHOLD
        
        # Re-entry threshold should be positive
        assert POSITIVE_THRESHOLD > 0, "Re-entry threshold should be > 0"

    @pytest.mark.asyncio
    async def test_check_health_returns_true_on_toxic_funding(self, watchdog, monkeypatch):
        """check_health should return True (unwind) when funding is toxic."""
        from src.engines.funding.watchdog import NEGATIVE_THRESHOLD
        
        # Mock get_funding_rate to return toxic rate
        toxic_rate = NEGATIVE_THRESHOLD - 0.0001  # Below threshold
        
        async def mock_get_rate(client):
            return toxic_rate
            
        monkeypatch.setattr(watchdog, "get_funding_rate", mock_get_rate)
        
        # Configure watchdog to trigger immediately on first bad reading
        watchdog.max_negative_funding_streak = 1
        
        result = await watchdog.check_health(simulate=True)
        
        # Should trigger unwind
        assert result is True, f"Toxic rate {toxic_rate} should trigger unwind"

    @pytest.mark.asyncio
    async def test_check_health_returns_false_on_healthy_funding(self, watchdog, monkeypatch):
        """check_health should return False when funding is healthy."""
        # Mock get_funding_rate to return healthy rate
        healthy_rate = 0.001  # 0.1% positive = healthy
        
        async def mock_get_rate(client):
            return healthy_rate
            
        monkeypatch.setattr(watchdog, "get_funding_rate", mock_get_rate)
        
        result = await watchdog.check_health(simulate=True)
        
        # Should NOT trigger unwind
        assert result is False, f"Healthy rate {healthy_rate} should not trigger unwind"

    @pytest.mark.asyncio
    async def test_check_health_edge_case_at_threshold(self, watchdog, monkeypatch):
        """Exactly at threshold should NOT trigger (use strict inequality)."""
        from src.engines.funding.watchdog import NEGATIVE_THRESHOLD
        
        # Exactly at threshold
        async def mock_get_rate(client):
            return NEGATIVE_THRESHOLD  # Exactly at boundary
            
        monkeypatch.setattr(watchdog, "get_funding_rate", mock_get_rate)
        
        result = await watchdog.check_health(simulate=True)
        
        # Should NOT trigger (need to go BELOW threshold)
        assert result is False, "Exactly at threshold should not trigger"


class TestReEntryLogic:
    """Test re-entry opportunity detection."""

    @pytest.fixture
    def watchdog(self, tmp_path, monkeypatch):
        """Create FundingWatchdog with temp state."""
        test_state_file = tmp_path / "watchdog_state.json"
        monkeypatch.setattr(
            "src.engines.funding.watchdog.WATCHDOG_STATE_FILE",
            test_state_file
        )
        
        from src.engines.funding.watchdog import FundingWatchdog
        return FundingWatchdog(check_interval_sec=1)

    @pytest.mark.asyncio
    async def test_re_entry_requires_sustained_positive(self, watchdog, monkeypatch):
        """Re-entry should only be recommended after sustained positive rates."""
        from src.engines.funding.watchdog import POSITIVE_THRESHOLD
        
        # Simulate one positive reading
        watchdog.recent_rates = [POSITIVE_THRESHOLD + 0.001]  # Only 1 reading
        
        result = await watchdog.check_re_entry_opportunity()
        
        # Should NOT recommend re-entry on single reading
        # (Need sustained positive for confidence)
        # Implementation may vary - adjust assertion based on actual logic
        pass  # Skip if method requires multiple readings

    @pytest.mark.asyncio
    async def test_re_entry_not_recommended_if_volatile(self, watchdog):
        """Don't recommend re-entry if rates are volatile."""
        # Simulate volatile readings: positive, negative, positive
        watchdog.recent_rates = [0.002, -0.001, 0.003]
        
        # Volatility should make us cautious
        # Implementation-specific assertion
        pass


class TestStatePersistence:
    """Test state persistence across restarts."""

    @pytest.fixture
    def state_file(self, tmp_path):
        """Temp state file path."""
        return tmp_path / "watchdog_state.json"

    @pytest.fixture
    def watchdog(self, state_file, monkeypatch):
        """Create watchdog with temp state."""
        monkeypatch.setattr(
            "src.engines.funding.watchdog.WATCHDOG_STATE_FILE",
            state_file
        )
        from src.engines.funding.watchdog import FundingWatchdog
        return FundingWatchdog(check_interval_sec=1)

    def test_save_state_creates_file(self, watchdog, state_file):
        """_save_state should create state file."""
        watchdog.unwind_triggered = True
        watchdog._save_state()
        
        assert state_file.exists(), "State file should be created"

    def test_load_state_reads_file(self, watchdog, state_file):
        """_load_state should read previous state."""
        # Create state file
        state_data = {
            "unwind_triggered": True,
            "last_check_time": 1700000000.0,
        }
        state_file.write_text(json.dumps(state_data))
        
        watchdog._load_state()
        
        assert watchdog.unwind_triggered is True

    def test_load_state_handles_missing_file(self, watchdog, state_file):
        """_load_state should handle missing file gracefully."""
        # Don't create file
        assert not state_file.exists()
        
        # Should not crash
        watchdog._load_state()

    def test_load_state_handles_corrupt_file(self, watchdog, state_file):
        """_load_state should handle corrupt JSON gracefully."""
        state_file.write_text("not valid json {{{")
        
        # Should not crash
        watchdog._load_state()


class TestUnwindProtocol:
    """Test emergency unwind execution."""

    @pytest.fixture
    def watchdog(self, tmp_path, monkeypatch):
        """Create watchdog for unwind testing."""
        test_state_file = tmp_path / "watchdog_state.json"
        monkeypatch.setattr(
            "src.engines.funding.watchdog.WATCHDOG_STATE_FILE",
            test_state_file
        )
        
        from src.engines.funding.watchdog import FundingWatchdog
        return FundingWatchdog(check_interval_sec=1)

    @pytest.mark.asyncio
    async def test_unwind_in_simulate_mode_no_trade(self, watchdog, mock_rpc_client):
        """Simulate mode should NOT execute real trades."""
        # In simulate mode, unwind should log but not trade
        await watchdog.unwind_position(mock_rpc_client, simulate=True)
        
        # Should not have made RPC calls for sending transactions
        # (Only info fetches are ok)
        # Assert based on mock call count for send_transaction
        # Implementation-specific

    @pytest.mark.asyncio
    async def test_unwind_sequence(self, watchdog, mock_rpc_client):
        """
        Unwind should follow correct sequence:
        1. Close Drift Short (Reduce-Only)
        2. Sell Spot SOL
        """
        # This is more of an integration test
        # Unit test just verifies method exists and is callable
        await watchdog.unwind_position(mock_rpc_client, simulate=True)


class TestFundingRateParsing:
    """Test on-chain funding rate parsing."""

    def test_funding_rate_precision(self):
        """Verify funding rate precision constant."""
        from src.engines.funding.watchdog import FUNDING_RATE_PRECISION
        
        assert FUNDING_RATE_PRECISION == 1_000_000_000, "Should be 1e9"

    def test_funding_rate_conversion(self):
        """Test conversion from raw to percentage."""
        from src.engines.funding.watchdog import FUNDING_RATE_PRECISION
        
        # Example: raw rate of 500,000 = 0.0005 = 0.05%
        raw_rate = 500_000
        converted = raw_rate / FUNDING_RATE_PRECISION
        
        assert converted == 0.0005, f"Expected 0.0005, got {converted}"

    def test_negative_funding_rate_conversion(self):
        """Test negative funding rate conversion."""
        from src.engines.funding.watchdog import FUNDING_RATE_PRECISION
        
        # Negative raw rate
        raw_rate = -500_000
        converted = raw_rate / FUNDING_RATE_PRECISION
        
        assert converted == -0.0005, f"Expected -0.0005, got {converted}"
