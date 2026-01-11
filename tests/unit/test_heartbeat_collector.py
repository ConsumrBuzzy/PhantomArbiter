"""
HeartbeatDataCollector Unit Tests
=================================
Tests for the extracted data collection service.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch


class TestSystemSnapshot:
    """Test SystemSnapshot dataclass."""

    def test_to_dict_includes_all_fields(self):
        """to_dict should include all required fields."""
        from src.interface.heartbeat_collector import (
            SystemSnapshot, WalletSnapshot, SystemMetrics
        )
        
        snapshot = SystemSnapshot(
            paper_wallet=WalletSnapshot(wallet_type="PAPER"),
            live_wallet=WalletSnapshot(wallet_type="LIVE"),
            sol_price=150.0,
            global_mode="paper",
        )
        
        data = snapshot.to_dict()
        
        assert "paper_wallet" in data
        assert "live_wallet" in data
        assert "wallet" in data  # Legacy compat
        assert "engines" in data
        assert "sol_price" in data
        assert "metrics" in data
        assert "mode" in data

    def test_wallet_snapshot_to_dict(self):
        """WalletSnapshot.to_dict should format assets correctly."""
        from src.interface.heartbeat_collector import WalletSnapshot, AssetBalance
        
        wallet = WalletSnapshot(
            wallet_type="PAPER",
            assets={
                "SOL": AssetBalance("SOL", 1.5, 150.0, 225.0),
                "USDC": AssetBalance("USDC", 100.0, 1.0, 100.0),
            },
            equity=325.0,
            sol_balance=1.5,
        )
        
        data = wallet.to_dict()
        
        assert data["type"] == "PAPER"
        assert data["equity"] == 325.0
        assert "SOL" in data["assets"]
        assert data["assets"]["SOL"]["amount"] == 1.5


class TestHeartbeatDataCollector:
    """Test HeartbeatDataCollector functionality."""

    @pytest.fixture
    def collector(self, temp_db, monkeypatch):
        """Create collector with mocked dependencies."""
        from src.interface.heartbeat_collector import (
            HeartbeatDataCollector, reset_heartbeat_collector
        )
        reset_heartbeat_collector()
        return HeartbeatDataCollector()

    @pytest.fixture
    def mock_paper_wallet(self, monkeypatch):
        """Mock paper wallet."""
        mock_pw = MagicMock()
        mock_pw.balances = {"SOL": 0.5, "USDC": 100.0}
        mock_pw.reload = MagicMock()
        
        monkeypatch.setattr(
            "src.interface.heartbeat_collector.pw",
            mock_pw
        )
        return mock_pw

    @pytest.fixture
    def mock_wallet_manager(self, monkeypatch):
        """Mock wallet manager."""
        mock_wm = MagicMock()
        mock_wm.get_current_live_usd_balance.return_value = {
            "assets": [
                {"symbol": "SOL", "amount": 1.0, "usd_value": 150.0},
            ],
            "breakdown": {"SOL": 1.0, "USDC": 50.0},
            "total_usd": 200.0
        }
        return mock_wm

    @pytest.mark.asyncio
    async def test_collect_returns_snapshot(self, collector, monkeypatch):
        """collect() should return a SystemSnapshot."""
        # Mock all data sources
        async def mock_paper():
            from src.interface.heartbeat_collector import WalletSnapshot
            return WalletSnapshot(wallet_type="PAPER")
        
        async def mock_live():
            from src.interface.heartbeat_collector import WalletSnapshot
            return WalletSnapshot(wallet_type="LIVE")
        
        async def mock_engines():
            return {}
        
        async def mock_sol():
            return 150.0
        
        monkeypatch.setattr(collector, "_collect_paper_wallet", mock_paper)
        monkeypatch.setattr(collector, "_collect_live_wallet", mock_live)
        monkeypatch.setattr(collector, "_collect_engine_status", mock_engines)
        monkeypatch.setattr(collector, "_get_sol_price", mock_sol)
        
        snapshot = await collector.collect()
        
        from src.interface.heartbeat_collector import SystemSnapshot
        assert isinstance(snapshot, SystemSnapshot)
        assert snapshot.paper_wallet.wallet_type == "PAPER"
        assert snapshot.live_wallet.wallet_type == "LIVE"

    @pytest.mark.asyncio
    async def test_collect_tracks_latency(self, collector, monkeypatch):
        """collect() should measure collection latency."""
        # Use fast mocks
        async def instant_wallet():
            from src.interface.heartbeat_collector import WalletSnapshot
            return WalletSnapshot(wallet_type="TEST")
        
        async def instant_engines():
            return {}
        
        async def instant_price():
            return 150.0
        
        monkeypatch.setattr(collector, "_collect_paper_wallet", instant_wallet)
        monkeypatch.setattr(collector, "_collect_live_wallet", instant_wallet)
        monkeypatch.setattr(collector, "_collect_engine_status", instant_engines)
        monkeypatch.setattr(collector, "_get_sol_price", instant_price)
        
        snapshot = await collector.collect()
        
        assert snapshot.collector_latency_ms >= 0
        assert snapshot.collector_latency_ms < 1000  # Should be fast

    @pytest.mark.asyncio
    async def test_fallback_prices_used_when_feed_fails(self, collector):
        """Should use fallback prices when feed unavailable."""
        # Don't set up any price feed
        collector._price_feed = None
        
        price = await collector._get_asset_price("SOL")
        
        assert price == collector.FALLBACK_PRICES["SOL"]

    @pytest.mark.asyncio
    async def test_usdc_always_returns_one(self, collector):
        """USDC should always return 1.0."""
        price = await collector._get_asset_price("USDC")
        
        assert price == 1.0

    def test_system_metrics_collection(self, collector):
        """_collect_system_metrics should return valid metrics."""
        metrics = collector._collect_system_metrics()
        
        from src.interface.heartbeat_collector import SystemMetrics
        assert isinstance(metrics, SystemMetrics)
        assert 0 <= metrics.cpu_percent <= 100
        assert 0 <= metrics.memory_percent <= 100


class TestAssetBalance:
    """Test AssetBalance dataclass."""

    def test_auto_calculates_value(self):
        """value_usd should auto-calculate if not provided."""
        from src.interface.heartbeat_collector import AssetBalance
        
        balance = AssetBalance(
            symbol="SOL",
            amount=2.0,
            price=150.0,
        )
        
        assert balance.value_usd == 300.0

    def test_explicit_value_preserved(self):
        """Explicit value_usd should be preserved."""
        from src.interface.heartbeat_collector import AssetBalance
        
        balance = AssetBalance(
            symbol="SOL",
            amount=2.0,
            price=150.0,
            value_usd=295.0,  # Slightly different (e.g., after fees)
        )
        
        assert balance.value_usd == 295.0


class TestCollectorSingleton:
    """Test singleton access pattern."""

    def test_get_returns_same_instance(self):
        """get_heartbeat_collector should return singleton."""
        from src.interface.heartbeat_collector import (
            get_heartbeat_collector, reset_heartbeat_collector
        )
        
        reset_heartbeat_collector()
        
        c1 = get_heartbeat_collector()
        c2 = get_heartbeat_collector()
        
        assert c1 is c2

    def test_reset_clears_instance(self):
        """reset_heartbeat_collector should clear singleton."""
        from src.interface.heartbeat_collector import (
            get_heartbeat_collector, reset_heartbeat_collector
        )
        
        c1 = get_heartbeat_collector()
        reset_heartbeat_collector()
        c2 = get_heartbeat_collector()
        
        assert c1 is not c2
