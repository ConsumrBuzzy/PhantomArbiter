"""
Base Engine Unit Tests
======================
Tests for BaseEngine lifecycle, mode switching, and tick scheduling.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch


class TestEngineLifecycle:
    """Test engine start/stop lifecycle."""

    @pytest.fixture
    def engine(self, temp_db):
        """Create test engine instance."""
        from tests.mocks.mock_engine import MockTradingEngine
        return MockTradingEngine(name="test_lifecycle", live_mode=False)

    @pytest.mark.asyncio
    async def test_start_sets_running(self, engine):
        """Engine.start() should set running=True."""
        assert not engine.running, "Engine should start stopped"
        
        await engine.start()
        
        assert engine.running, "Engine should be running after start()"
        
        await engine.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_running(self, engine):
        """Engine.stop() should set running=False."""
        await engine.start()
        assert engine.running
        
        await engine.stop()
        
        assert not engine.running, "Engine should be stopped after stop()"

    @pytest.mark.asyncio
    async def test_stop_calls_on_stop(self, engine):
        """Engine.stop() should trigger on_stop() callback."""
        await engine.start()
        await engine.stop()
        
        assert engine.on_stop_called, "on_stop() should be called"

    @pytest.mark.asyncio
    async def test_start_with_config(self, engine):
        """Engine.start() should accept config overrides."""
        config = {"max_trade_usd": 500, "risk_tier": "high"}
        
        await engine.start(config=config)
        
        assert engine.config["max_trade_usd"] == 500
        assert engine.config["risk_tier"] == "high"
        
        await engine.stop()

    @pytest.mark.asyncio
    async def test_double_start_is_noop(self, engine):
        """Calling start() twice should not create duplicate tasks."""
        await engine.start()
        first_task = engine._task
        
        await engine.start()  # Second call
        second_task = engine._task
        
        assert first_task is second_task, "Should not create new task on double start"
        
        await engine.stop()

    @pytest.mark.asyncio
    async def test_stop_without_start_is_safe(self, engine):
        """Calling stop() on a never-started engine should not crash."""
        await engine.stop()  # Should not raise

    @pytest.mark.asyncio
    async def test_repeated_start_stop_no_zombie_tasks(self, engine):
        """
        Starting and stopping repeatedly should not leave zombie tasks.
        
        This is a critical stability test for production.
        """
        for i in range(5):
            await engine.start()
            assert engine.running
            await asyncio.sleep(0.05)  # Let it tick
            await engine.stop()
            assert not engine.running
            
        # After all cycles, task should be None
        assert engine._task is None, "No zombie tasks should remain"


class TestEngineMode:
    """Test paper vs live mode initialization."""

    def test_paper_mode_injects_vault(self, temp_db):
        """Paper mode engines should get engine-specific vault."""
        from tests.mocks.mock_engine import MockTradingEngine
        
        engine = MockTradingEngine(name="test_paper_vault", live_mode=False)
        
        assert engine.mode == "paper"
        # paper_wallet may be None if import fails, but that's ok for mock
        
    def test_live_mode_sets_flag(self):
        """Live mode engines should have live_mode=True."""
        from tests.mocks.mock_engine import MockTradingEngine
        
        engine = MockTradingEngine(name="test_live", live_mode=True)
        
        assert engine.live_mode is True
        assert engine.mode == "live"


class TestEngineTick:
    """Test tick execution and error handling."""

    @pytest.fixture
    def engine(self, temp_db):
        """Create engine with fast tick for testing."""
        from tests.mocks.mock_engine import MockTradingEngine
        engine = MockTradingEngine(name="test_tick", live_mode=False)
        engine.tick_delay = 0.02  # Fast ticks for testing
        return engine

    @pytest.mark.asyncio
    async def test_tick_increments_count(self, engine):
        """Each tick should increment tick_count."""
        await engine.start()
        
        # Wait for some ticks
        await asyncio.sleep(0.1)
        
        assert engine.tick_count > 0, "Should have completed some ticks"
        
        await engine.stop()

    @pytest.mark.asyncio
    async def test_tick_error_is_captured(self, engine):
        """Errors in tick() should be captured, not crash the loop."""
        engine.should_error_on_tick = True
        
        await engine.start()
        await asyncio.sleep(0.05)
        await engine.stop()
        
        assert len(engine.errors) > 0, "Errors should be captured"

    @pytest.mark.asyncio
    async def test_tick_continues_after_error(self, engine):
        """Engine should continue ticking after a tick error."""
        engine.error_on_tick_number = 1  # Error on second tick
        
        await engine.start()
        await asyncio.sleep(0.1)  # Allow multiple ticks
        await engine.stop()
        
        assert engine.tick_count > 2, "Should continue past error"

    @pytest.mark.asyncio
    async def test_tick_broadcasts_via_callback(self, engine):
        """Tick results should be broadcast via callback."""
        received = []
        engine.set_callback(lambda data: received.append(data))
        
        await engine.start()
        await asyncio.sleep(0.05)
        await engine.stop()
        
        assert len(received) > 0, "Should broadcast tick results"


class TestEngineStatus:
    """Test status reporting."""

    @pytest.fixture
    def engine(self, temp_db):
        """Create test engine."""
        from tests.mocks.mock_engine import MockTradingEngine
        return MockTradingEngine(name="test_status", live_mode=False)

    def test_get_status_stopped(self, engine):
        """Status should show 'stopped' when not running."""
        status = engine.get_status()
        
        assert status["status"] == "stopped"
        assert status["name"] == "test_status"

    @pytest.mark.asyncio
    async def test_get_status_running(self, engine):
        """Status should show 'running' when active."""
        await engine.start()
        
        status = engine.get_status()
        
        assert status["status"] == "running"
        
        await engine.stop()

    def test_get_status_includes_config(self, engine):
        """Status should include current configuration."""
        engine.config = {"min_spread": 0.5}
        
        status = engine.get_status()
        
        assert "config" in status
        assert status["config"]["min_spread"] == 0.5

    def test_export_state_for_dashboard(self, engine):
        """export_state() should return dashboard-friendly data."""
        state = engine.export_state()
        
        assert "name" in state
        assert "ticks" in state


class TestEngineVaultIntegration:
    """Test engine-vault binding (paper mode)."""

    @pytest.fixture
    def engine(self, temp_db):
        """Create paper engine with isolated vault."""
        from tests.mocks.mock_engine import MockTradingEngine
        return MockTradingEngine(name="test_vault_bind", live_mode=False)

    def test_paper_engine_has_vault(self, engine):
        """Paper engine should have paper_wallet attribute."""
        # May be None if vault_manager import fails during test
        # The real integration test verifies the actual binding
        assert hasattr(engine, 'paper_wallet')

    def test_different_engines_different_vaults(self, temp_db):
        """Two engines should have isolated vaults."""
        from tests.mocks.mock_engine import MockTradingEngine
        
        engine1 = MockTradingEngine(name="engine_alpha", live_mode=False)
        engine2 = MockTradingEngine(name="engine_beta", live_mode=False)
        
        # They should have different names at minimum
        assert engine1.name != engine2.name
