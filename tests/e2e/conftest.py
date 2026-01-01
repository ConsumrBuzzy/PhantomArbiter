"""
End-to-End Test Configuration
=============================
Fixtures for full system tests with mocked chaos parameters.

E2E tests verify the complete mission:
Signal Discovery → Decision → Execution → Audit

These tests use "Chaos Mocks" to simulate real-world conditions
without requiring devnet or mainnet connectivity.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
import random
import time


# ============================================================================
# CHAOS SIMULATION FIXTURES
# ============================================================================


@pytest.fixture
def chaos_config():
    """
    Chaos configuration for realistic E2E testing.
    Simulates network conditions, MEV competition, and slippage.
    """
    return {
        # Network conditions
        "rpc_latency_ms": (20, 150),       # Range of latencies
        "rpc_failure_rate": 0.05,          # 5% chance of RPC timeout
        
        # MEV / Jito conditions
        "bundle_inclusion_rate": 0.85,     # 85% of bundles land
        "bundle_latency_ms": (100, 500),   # Bundle confirmation time
        
        # Market conditions
        "slippage_base_pct": 0.5,          # Base slippage
        "slippage_variance_pct": 0.3,      # Additional random slippage
        "price_drift_per_second": 0.001,   # 0.1% drift per second
        
        # Congestion
        "congestion_multiplier": 1.5,      # Fee multiplier during congestion
        "priority_fee_lamports": 10000,    # Base priority fee
    }


@pytest.fixture
def chaos_rpc(chaos_config):
    """
    Chaos RPC client that randomly fails or delays based on config.
    """
    config = chaos_config
    
    async def maybe_fail():
        if random.random() < config["rpc_failure_rate"]:
            raise TimeoutError("Simulated RPC timeout")
        
        # Simulate latency
        latency = random.uniform(*config["rpc_latency_ms"]) / 1000
        await asyncio.sleep(latency)
    
    rpc = MagicMock()
    rpc.get_account_info = AsyncMock(side_effect=maybe_fail)
    rpc.send_transaction = AsyncMock(side_effect=maybe_fail)
    return rpc


@pytest.fixture
def chaos_jito(chaos_config):
    """
    Chaos Jito bundle submitter that randomly fails bundles.
    """
    config = chaos_config
    
    async def submit_bundle(bundle):
        # Random inclusion
        if random.random() > config["bundle_inclusion_rate"]:
            return {"status": "dropped", "reason": "MEV competition"}
        
        # Simulate confirmation delay
        delay = random.uniform(*config["bundle_latency_ms"]) / 1000
        await asyncio.sleep(delay)
        
        return {
            "status": "landed",
            "slot": 123456789,
            "tx_signatures": ["chaos_tx_" + str(random.randint(1000, 9999))],
        }
    
    jito = MagicMock()
    jito.submit_bundle = AsyncMock(side_effect=submit_bundle)
    return jito


# ============================================================================
# FULL SYSTEM FIXTURES
# ============================================================================


@pytest.fixture
def e2e_system_state():
    """
    Complete system state for E2E testing.
    Represents a fully initialized PhantomArbiter ready for a mission.
    """
    return {
        "wallet": {
            "pubkey": "TestWallet123456789abcdefghijklmnopqrstuvwx",
            "sol_balance": 5.0,
            "usdc_balance": 1000.0,
        },
        "paper_mode": True,
        "watchers": {
            "SOL": {"in_position": False, "price": 100.0},
            "BONK": {"in_position": False, "price": 0.00001234},
        },
        "signals_pending": [],
        "trades_executed": [],
        "start_time": time.time(),
    }


@pytest.fixture
def mock_full_tactical_strategy(mock_capital_manager, mock_execution_backend):
    """
    Mock TacticalStrategy for E2E testing.
    Pre-wired with mock backends.
    """
    strategy = MagicMock()
    strategy.capital_mgr = mock_capital_manager
    strategy.execution_backend = mock_execution_backend
    strategy.engine_name = "E2E_TEST"
    strategy.paper_mode = True
    
    # Simulate scan_signals returning a BUY signal
    strategy.scan_signals = MagicMock(return_value=[
        {
            "action": "BUY",
            "watcher": MagicMock(symbol="BONK", mint="DezX..."),
            "price": 0.00001234,
            "reason": "RSI oversold",
            "confidence": 0.75,
            "size_usd": 10.0,
        }
    ])
    
    strategy.execute_signal = AsyncMock(return_value={
        "success": True,
        "tx_id": "e2e_trade_001",
    })
    
    return strategy


# ============================================================================
# SOAK TEST FIXTURES
# ============================================================================


@pytest.fixture
def soak_duration_seconds():
    """Duration for soak tests (default: 60 seconds for CI, can override)."""
    return int(os.environ.get("SOAK_DURATION", 60))


@pytest.fixture
def soak_metrics():
    """Collector for soak test metrics."""
    return {
        "signals_generated": 0,
        "signals_executed": 0,
        "signals_rejected": 0,
        "errors": [],
        "latencies_ms": [],
        "memory_samples_mb": [],
        "start_time": None,
        "end_time": None,
    }


import asyncio
import os
