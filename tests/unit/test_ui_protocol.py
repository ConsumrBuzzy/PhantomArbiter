"""
UI Protocol Unit Tests
======================
Tests for headless UI architecture.
"""

import pytest


class TestEngineUIState:
    """Test EngineUIState dataclass."""

    def test_arb_engine_factory(self):
        """for_arb_engine should create correct state."""
        from src.interface.ui_protocol import EngineUIState, TradingMode, UrgencyLevel
        
        state = EngineUIState.for_arb_engine(
            spread_pct=0.75,
            is_running=True,
            mode=TradingMode.PAPER,
            pnl=5.50,
        )
        
        assert state.engine_id == "arb"
        assert state.primary_metric == 0.75
        assert state.urgency == UrgencyLevel.OPPORTUNITY
        assert state.pnl_session == 5.50

    def test_funding_engine_factory(self):
        """for_funding_engine should create correct state."""
        from src.interface.ui_protocol import EngineUIState, TradingMode
        
        state = EngineUIState.for_funding_engine(
            net_apy=15.5,
            drift_pct=0.3,
            is_running=True,
        )
        
        assert state.engine_id == "funding"
        assert state.primary_metric == 15.5
        assert "APY" in state.status_text

    def test_scalp_engine_factory(self):
        """for_scalp_engine should create correct state."""
        from src.interface.ui_protocol import EngineUIState
        
        state = EngineUIState.for_scalp_engine(
            active_positions=3,
            unrealized_pnl=-2.50,
            is_running=True,
        )
        
        assert state.engine_id == "scalp"
        assert state.primary_metric == 3.0

    def test_to_dict(self):
        """to_dict should serialize all fields."""
        from src.interface.ui_protocol import EngineUIState, EngineType, TradingMode
        
        state = EngineUIState(
            engine_id="test",
            engine_type=EngineType.ARB,
            display_name="Test Engine",
            is_running=True,
            mode=TradingMode.LIVE,
        )
        
        data = state.to_dict()
        
        assert data["engine_id"] == "test"
        assert data["engine_type"] == "ARB"
        assert data["mode"] == "LIVE"
        assert data["is_running"] == True


class TestOpportunitySnapshot:
    """Test OpportunitySnapshot dataclass."""

    def test_creation(self):
        """Should create opportunity snapshot."""
        from src.interface.ui_protocol import OpportunitySnapshot, EngineType
        
        opp = OpportunitySnapshot(
            opportunity_id="arb_001",
            source_engine=EngineType.ARB,
            asset_pair="SOL/USDC",
            opportunity_type="ARB",
            profit_estimate_usd=1.50,
            profit_estimate_pct=0.015,
        )
        
        assert opp.asset_pair == "SOL/USDC"
        assert opp.profit_estimate_usd == 1.50

    def test_to_dict(self):
        """to_dict should serialize."""
        from src.interface.ui_protocol import OpportunitySnapshot, EngineType
        
        opp = OpportunitySnapshot(
            opportunity_id="test",
            source_engine=EngineType.FUNDING,
            asset_pair="jitoSOL/SOL",
            opportunity_type="DEPEG",
        )
        
        data = opp.to_dict()
        
        assert data["source_engine"] == "FUNDING"
        assert data["asset_pair"] == "jitoSOL/SOL"


class TestRenderPayload:
    """Test RenderPayload dataclass."""

    def test_to_dict(self):
        """to_dict should serialize entire payload."""
        from src.interface.ui_protocol import RenderPayload, TradingMode
        
        payload = RenderPayload(
            global_mode=TradingMode.PAPER,
            paper_equity_usd=100.50,
            sol_price=150.0,
        )
        
        data = payload.to_dict()
        
        assert data["global_mode"] == "PAPER"
        assert data["paper_equity_usd"] == 100.50
        assert data["sol_price"] == 150.0

    def test_to_console_summary(self):
        """to_console_summary should format for terminal."""
        from src.interface.ui_protocol import (
            RenderPayload, TradingMode, EngineUIState
        )
        
        payload = RenderPayload(
            engines=[
                EngineUIState.for_arb_engine(spread_pct=0.5, is_running=True)
            ],
            global_mode=TradingMode.PAPER,
            paper_equity_usd=100.0,
            sol_price=150.0,
        )
        
        summary = payload.to_console_summary()
        
        assert "PAPER" in summary
        assert "$150.00" in summary
        assert "Arbitrage" in summary


class TestRenderBuilder:
    """Test RenderBuilder functionality."""

    def test_frame_counter_increments(self):
        """Frame counter should increment."""
        from src.interface.ui_protocol import RenderBuilder
        
        # Create mock snapshot
        class MockSnapshot:
            global_mode = "paper"
            paper_wallet = type('obj', (object,), {'equity': 100.0})()
            live_wallet = type('obj', (object,), {'equity': 50.0})()
            engines = {}
            sol_price = 150.0
            delta_state = None
            metrics = type('obj', (object,), {
                'cpu_percent': 10.0,
                'memory_percent': 20.0
            })()
            collector_latency_ms = 5.0
        
        payload1 = RenderBuilder.from_snapshot(MockSnapshot())
        payload2 = RenderBuilder.from_snapshot(MockSnapshot())
        
        assert payload2.frame_id > payload1.frame_id


class TestTradingModeAndUrgency:
    """Test enums."""

    def test_trading_mode_values(self):
        """TradingMode should have expected values."""
        from src.interface.ui_protocol import TradingMode
        
        assert TradingMode.PAPER.value == "PAPER"
        assert TradingMode.LIVE.value == "LIVE"

    def test_urgency_level_values(self):
        """UrgencyLevel should have all levels."""
        from src.interface.ui_protocol import UrgencyLevel
        
        assert UrgencyLevel.IDLE.value == "IDLE"
        assert UrgencyLevel.NORMAL.value == "NORMAL"
        assert UrgencyLevel.OPPORTUNITY.value == "OPPORTUNITY"
        assert UrgencyLevel.CRITICAL.value == "CRITICAL"
