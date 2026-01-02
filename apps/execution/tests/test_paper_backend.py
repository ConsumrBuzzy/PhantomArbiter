"""
Test Paper Backend

Verifies paper trading execution with slippage and fees.
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from execution.order_bus import TradeSignal, SignalAction
from execution.backends.paper import PaperBackend, PaperConfig


@pytest.fixture
def backend():
    """Create a fresh PaperBackend instance."""
    config = PaperConfig(initial_cash=1000.0, initial_sol=0.1)
    return PaperBackend(config)


def test_buy_execution(backend):
    """Test executing a buy order."""
    signal = TradeSignal(
        symbol="SOL",
        mint="So11111111111111111111111111111111111111112",
        action=SignalAction.BUY,
        size_usd=100.0,
        target_price=150.0,
    )
    
    result = backend.execute(signal)
    
    assert result.status.value == "FILLED"
    assert result.filled_amount > 0
    assert result.filled_price > 0
    assert result.slippage_pct >= 0
    assert backend.get_cash() < 1000.0


def test_insufficient_funds(backend):
    """Test rejection when insufficient funds."""
    signal = TradeSignal(
        symbol="SOL",
        mint="So11111111111111111111111111111111111111112",
        action=SignalAction.BUY,
        size_usd=5000.0,  # More than initial cash
        target_price=150.0,
    )
    
    result = backend.execute(signal)
    
    assert result.status.value == "FAILED"
    assert "Insufficient" in result.error


def test_sell_no_position(backend):
    """Test selling without a position fails."""
    signal = TradeSignal(
        symbol="SOL",
        mint="So11111111111111111111111111111111111111112",
        action=SignalAction.SELL,
        size_usd=50.0,
    )
    
    result = backend.execute(signal)
    
    assert result.status.value == "FAILED"
    assert "No position" in result.error


def test_buy_then_sell(backend):
    """Test buy followed by sell."""
    # Buy
    buy_signal = TradeSignal(
        symbol="JUP",
        mint="JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
        action=SignalAction.BUY,
        size_usd=200.0,
        target_price=1.50,
    )
    buy_result = backend.execute(buy_signal)
    assert buy_result.status.value == "FILLED"
    
    # Sell
    sell_signal = TradeSignal(
        symbol="JUP",
        mint="JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
        action=SignalAction.SELL,
        size_usd=100.0,
    )
    sell_result = backend.execute(sell_signal)
    assert sell_result.status.value == "FILLED"
    
    # Cash should be partially restored
    assert backend.get_cash() > 700  # Some cash back after sell


def test_pnl_tracking(backend):
    """Test PnL is tracked correctly."""
    # Execute some trades
    buy_signal = TradeSignal(
        symbol="TEST",
        mint="TestMint123456789012345678901234567890123",
        action=SignalAction.BUY,
        size_usd=100.0,
        target_price=10.0,
    )
    backend.execute(buy_signal)
    
    pnl = backend.get_pnl()
    assert pnl["trades_count"] == 1


def test_slippage_increases_with_size(backend):
    """Test that larger trades have more slippage."""
    small_slip = backend._calculate_slippage(100)
    large_slip = backend._calculate_slippage(10000)
    
    assert large_slip > small_slip


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
