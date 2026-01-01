"""
Unit Test Configuration
=======================
Fixtures for pure logic tests - NO I/O ALLOWED.

All unit tests should be completely isolated from:
- Network (RPC, HTTP)
- Database (SQLite)
- File system (except tmp_path)
"""

import pytest
from unittest.mock import MagicMock


# ============================================================================
# AUTOUSE: ENFORCE I/O ISOLATION
# ============================================================================


@pytest.fixture(autouse=True)
def isolate_unit_tests(monkeypatch):
    """
    Automatically disable all network I/O for unit tests.
    Any test that accidentally tries to make a network call will fail.
    """
    def block_network(*args, **kwargs):
        raise RuntimeError(
            "Network I/O detected in unit test! "
            "Unit tests must be pure logic with no external dependencies. "
            "Use integration tests for network-dependent code."
        )
    
    # Block common HTTP clients
    try:
        monkeypatch.setattr("httpx.AsyncClient.get", block_network)
        monkeypatch.setattr("httpx.AsyncClient.post", block_network)
    except Exception:
        pass
    
    try:
        monkeypatch.setattr("aiohttp.ClientSession.get", block_network)
        monkeypatch.setattr("aiohttp.ClientSession.post", block_network)
    except Exception:
        pass


# ============================================================================
# LAYER B: EXECUTION LOGIC FIXTURES
# ============================================================================


@pytest.fixture
def mock_portfolio():
    """Mock PortfolioManager for DecisionEngine tests."""
    portfolio = MagicMock()
    portfolio.cash_available = 10000.0
    portfolio.total_positions = 2
    portfolio.max_positions = 5
    portfolio.get_position_value = MagicMock(return_value=0.0)
    portfolio.risk_per_trade = 0.02
    return portfolio


@pytest.fixture
def rsi_scenarios():
    """
    Common RSI scenarios for decision engine testing.
    Returns dict of {scenario_name: (rsi_value, expected_signal_type)}
    """
    return {
        "oversold": (25.0, "BUY"),
        "weak": (40.0, "HOLD"),
        "neutral": (50.0, "HOLD"),
        "strong": (65.0, "HOLD"),
        "overbought": (78.0, "SELL"),
        "extreme_oversold": (15.0, "BUY"),
        "extreme_overbought": (88.0, "SELL"),
    }


@pytest.fixture
def price_scenarios():
    """
    Common price movement scenarios for testing.
    Returns list of price histories representing different market conditions.
    """
    return {
        "rising": [1.0 + i * 0.02 for i in range(20)],  # +40%
        "falling": [1.0 - i * 0.02 for i in range(20)],  # -40%
        "sideways": [1.0 + (i % 3 - 1) * 0.01 for i in range(20)],  # ±1%
        "volatile": [1.0 + ((-1) ** i) * i * 0.03 for i in range(20)],  # Whipsaw
        "pump": [1.0] * 10 + [1.5 + i * 0.1 for i in range(10)],  # Sudden pump
        "dump": [1.5] * 10 + [1.5 - i * 0.1 for i in range(10)],  # Sudden dump
    }


# ============================================================================
# LAYER A: MARKET MONITOR FIXTURES
# ============================================================================


@pytest.fixture
def sample_pool_data():
    """Sample Raydium pool data for cache testing."""
    return {
        "pool_id": "TestPool123",
        "base_mint": "So11111111111111111111111111111111111111112",
        "quote_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "base_reserve": 1000000.0,
        "quote_reserve": 50000.0,
        "lp_supply": 10000.0,
        "fee_bps": 25,
    }


@pytest.fixture
def sample_price_update():
    """Sample price update event."""
    return {
        "mint": "MockMint123456789abcdefghijklmnopqrstuvwx",
        "price": 1.45,
        "source": "jupiter",
        "timestamp": 1704100000,
        "confidence": 0.95,
    }
