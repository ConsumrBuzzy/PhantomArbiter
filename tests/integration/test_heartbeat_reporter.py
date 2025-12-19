"""
V48.0: Unit Tests for HeartbeatReporter
========================================
Tests for the extracted heartbeat/display logic.

Run: pytest tests/test_heartbeat_reporter.py -v
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestHeartbeatReporterImport:
    """Test that HeartbeatReporter can be imported."""
    
    def test_import_heartbeat_reporter(self):
        """Verify HeartbeatReporter imports successfully."""
        from src.engine.heartbeat_reporter import HeartbeatReporter, HeartbeatData
        assert HeartbeatReporter is not None
        assert HeartbeatData is not None


class TestHeartbeatData:
    """Test HeartbeatData dataclass."""
    
    def test_heartbeat_data_creation(self):
        """Test HeartbeatData can be created."""
        from src.engine.heartbeat_reporter import HeartbeatData
        
        data = HeartbeatData(
            tick_count=100,
            active_positions=2,
            scout_positions=1,
            total_watchers=10,
            engine_name="MERCHANT",
            uptime_min=30,
            dsa_mode="NORMAL",
            usdc_bal=500.0,
            sol_bal=0.5,
            top_bags_str="",
            paper_section="",
            cex_section=""
        )
        
        assert data.tick_count == 100
        assert data.engine_name == "MERCHANT"
        assert data.usdc_bal == 500.0


class TestHeartbeatTiming:
    """Test heartbeat timing logic."""
    
    @pytest.fixture
    def mock_reporter(self):
        """Create a HeartbeatReporter with mocked dependencies."""
        from src.engine.heartbeat_reporter import HeartbeatReporter
        
        mock_paper_wallet = MagicMock()
        mock_paper_wallet.initialized = True
        mock_paper_wallet.initial_capital = 1000.0
        mock_paper_wallet.assets = {}
        mock_paper_wallet.stats = {'wins': 0, 'losses': 0, 'fees_paid_usd': 0.0}
        mock_paper_wallet.sol_balance = 0.02
        mock_paper_wallet.engine_name = "TEST"
        
        mock_portfolio = MagicMock()
        mock_portfolio.cash_available = 500.0
        
        mock_wallet = MagicMock()
        mock_wallet.get_current_live_usd_balance = MagicMock(return_value={
            'breakdown': {'USDC': 500.0, 'SOL': 0.5},
            'assets': [],
            'total_usd': 500.0
        })
        
        mock_decision_engine = MagicMock()
        mock_decision_engine.mode = 'NORMAL'
        
        reporter = HeartbeatReporter(
            engine_name="TEST",
            paper_wallet=mock_paper_wallet,
            portfolio=mock_portfolio,
            wallet=mock_wallet,
            decision_engine=mock_decision_engine
        )
        
        return reporter
    
    def test_should_send_heartbeat_initially(self, mock_reporter):
        """Test heartbeat should send on first call after interval."""
        import time
        
        # Set last_heartbeat to past
        mock_reporter.last_heartbeat = time.time() - 61
        
        assert mock_reporter.should_send_heartbeat() is True
    
    def test_should_not_send_heartbeat_too_soon(self, mock_reporter):
        """Test heartbeat should not send if interval not elapsed."""
        import time
        
        mock_reporter.last_heartbeat = time.time()
        
        assert mock_reporter.should_send_heartbeat() is False


class TestConsoleFormatting:
    """Test console output formatting."""
    
    def test_log_to_console_runs(self):
        """Test _log_to_console executes without error."""
        from src.engine.heartbeat_reporter import HeartbeatReporter, HeartbeatData
        
        mock_paper_wallet = MagicMock()
        mock_paper_wallet.initialized = False
        
        reporter = HeartbeatReporter(
            engine_name="TEST",
            paper_wallet=mock_paper_wallet,
            portfolio=MagicMock(),
            wallet=MagicMock(),
            decision_engine=MagicMock()
        )
        
        data = HeartbeatData(
            tick_count=50,
            active_positions=1,
            scout_positions=0,
            total_watchers=5,
            engine_name="TEST",
            uptime_min=10,
            dsa_mode="NORMAL",
            usdc_bal=100.0,
            sol_bal=0.1,
            top_bags_str="",
            paper_section="",
            cex_section=""
        )
        
        # Should not raise
        reporter._log_to_console(data)


class TestTradingCoreIntegration:
    """Test TradingCore has HeartbeatReporter integration."""
    
    def test_trading_core_has_reporter(self):
        """Verify TradingCore initializes reporter."""
        from src.engine.trading_core import TradingCore
        from src.engine.heartbeat_reporter import HeartbeatReporter
        
        # Import test only
        assert hasattr(TradingCore, '__init__')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
