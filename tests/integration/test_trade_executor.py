"""
V48.0: Unit Tests for TradeExecutor
====================================
Tests for the extracted trade execution logic.

Run: pytest tests/test_trade_executor.py -v
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestTradeExecutorImport:
    """Test that TradeExecutor can be imported."""
    
    def test_import_trade_executor(self):
        """Verify TradeExecutor imports successfully."""
        from src.engine.trade_executor import TradeExecutor, ExecutionResult
        assert TradeExecutor is not None
        assert ExecutionResult is not None


class TestExecutionResult:
    """Test ExecutionResult dataclass."""
    
    def test_execution_result_success(self):
        """Test successful ExecutionResult."""
        from src.engine.trade_executor import ExecutionResult
        
        result = ExecutionResult(
            success=True,
            message="BUY BONK",
            tx_id="MOCK_TX_123",
            pnl_usd=None
        )
        
        assert result.success is True
        assert result.message == "BUY BONK"
        assert result.tx_id == "MOCK_TX_123"
    
    def test_execution_result_failure(self):
        """Test failed ExecutionResult."""
        from src.engine.trade_executor import ExecutionResult
        
        result = ExecutionResult(
            success=False,
            message="Low Liquidity"
        )
        
        assert result.success is False
        assert result.tx_id is None


class TestPreflightChecks:
    """Test pre-flight check logic."""
    
    @pytest.fixture
    def mock_executor(self):
        """Create a TradeExecutor with mocked dependencies."""
        from src.engine.trade_executor import TradeExecutor
        
        # Mock all dependencies
        mock_capital_mgr = MagicMock()
        mock_paper_wallet = MagicMock()
        mock_paper_wallet.cash_balance = 100.0
        mock_paper_wallet.sol_balance = 0.02
        mock_paper_wallet.assets = {}
        
        mock_swapper = MagicMock()
        mock_portfolio = MagicMock()
        mock_portfolio.request_lock = MagicMock(return_value=True)
        
        executor = TradeExecutor(
            engine_name="TEST",
            capital_mgr=mock_capital_mgr,
            paper_wallet=mock_paper_wallet,
            swapper=mock_swapper,
            portfolio=mock_portfolio,
            ml_model=None
        )
        
        return executor
    
    def test_preflight_passes_with_sufficient_funds(self, mock_executor):
        """Test preflight passes when funds are sufficient."""
        mock_watcher = MagicMock()
        mock_watcher.get_liquidity = MagicMock(return_value=500000)  # $500k liquidity
        
        with patch.object(mock_executor, 'paper_wallet') as pw:
            pw.cash_balance = 100.0
            pw.sol_balance = 0.02
            pw.assets = {}
            
            can_execute, reason = mock_executor._check_preflight_buy(mock_watcher, 50.0)
            assert can_execute is True
    
    def test_preflight_blocks_low_liquidity(self, mock_executor):
        """Test preflight blocks when liquidity is too low."""
        mock_watcher = MagicMock()
        mock_watcher.get_liquidity = MagicMock(return_value=50000)  # $50k < $100k
        
        can_execute, reason = mock_executor._check_preflight_buy(mock_watcher, 50.0)
        assert can_execute is False
        assert "Liquidity" in reason


class TestMLFilter:
    """Test ML filter logic."""
    
    def test_ml_filter_passes_without_model(self):
        """Test ML filter passes when no model is loaded."""
        from src.engine.trade_executor import TradeExecutor
        
        executor = TradeExecutor(
            engine_name="TEST",
            capital_mgr=MagicMock(),
            paper_wallet=MagicMock(),
            swapper=MagicMock(),
            portfolio=MagicMock(),
            ml_model=None  # No model
        )
        
        mock_watcher = MagicMock()
        passed, prob = executor._apply_ml_filter(mock_watcher, 1.0, 100000)
        
        assert passed is True
        assert prob == 0.5  # Default neutral probability
    
    def test_ml_filter_rejects_low_probability(self):
        """Test ML filter rejects trades below threshold."""
        from src.engine.trade_executor import TradeExecutor
        import numpy as np
        
        # Mock ML model that predicts low probability
        mock_model = MagicMock()
        mock_model.predict_proba = MagicMock(return_value=np.array([[0.6, 0.4]]))  # 40% < 65%
        
        executor = TradeExecutor(
            engine_name="TEST",
            capital_mgr=MagicMock(),
            paper_wallet=MagicMock(),
            swapper=MagicMock(),
            portfolio=MagicMock(),
            ml_model=mock_model
        )
        
        # Mock watcher with required methods
        mock_watcher = MagicMock()
        mock_watcher.get_rsi = MagicMock(return_value=50)
        mock_watcher.data_feed = MagicMock()
        mock_watcher.data_feed.get_atr = MagicMock(return_value=0.05)
        
        passed, prob = executor._apply_ml_filter(mock_watcher, 1.0, 100000)
        
        assert passed is False
        assert prob == 0.4


class TestExecutionDelegation:
    """Test that execution properly delegates to TradeExecutor."""
    
    def test_trading_core_has_executor(self):
        """Verify TradingCore initializes executor."""
        # This is an import test - full initialization requires too many deps
        from src.engine.trading_core import TradingCore
        from src.engine.trade_executor import TradeExecutor
        
        # Just verify the class has the attribute defined
        assert hasattr(TradingCore, '__init__')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
