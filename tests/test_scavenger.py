"""
Test Scavenger Intelligence
============================
Phase 17: Battle Testing

Tests for FailureTracker and BridgePod signal detection:
1. Failure spike detection
2. Recoil detection after spike
3. Bridge inflow whale detection
4. Dashboard panel updates
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock


class TestFailureTracker:
    """Test the FailureTracker for spike and recoil detection."""
    
    def test_failure_spike_detection(self):
        """Verify that 5+ failures in 30s triggers a SPIKE signal."""
        from src.shared.infrastructure.log_harvester import FailureTracker
        
        tracker = FailureTracker(
            window_seconds=30.0,
            failure_threshold=5,
            recoil_silence_seconds=3.0,
        )
        
        pool = "675kPX9MCyJsD5ippTu671dKKkCtSE5v4RBmZJtHNv9v"
        
        # Record 4 failures - should NOT trigger alert
        for i in range(4):
            tracker.record_failure(pool, "SLIPPAGE_EXCEEDED")
        
        assert tracker.alerts_emitted == 0
        
        # 5th failure should trigger alert
        tracker.record_failure(pool, "SLIPPAGE_EXCEEDED")
        
        assert tracker.alerts_emitted == 1
        assert tracker.total_failures_tracked == 5
    
    def test_recoil_detection(self):
        """Verify recoil is detected when failures stop after spike."""
        from src.shared.infrastructure.log_harvester import FailureTracker
        
        tracker = FailureTracker(
            window_seconds=30.0,
            failure_threshold=5,
            recoil_silence_seconds=0.1,  # Short for testing
        )
        
        pool = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
        
        # Trigger spike
        for i in range(5):
            tracker.record_failure(pool, "SLIPPAGE_EXCEEDED")
        
        assert tracker.alerts_emitted == 1
        assert tracker.recoils_detected == 0
        
        # Wait for silence period
        time.sleep(0.15)
        
        # Record success - should detect recoil
        tracker.record_success(pool)
        
        assert tracker.recoils_detected == 1
    
    def test_hot_pools_list(self):
        """Verify get_hot_pools returns pools under pressure."""
        from src.shared.infrastructure.log_harvester import FailureTracker
        
        tracker = FailureTracker(
            window_seconds=30.0,
            failure_threshold=5,
        )
        
        # Create pressure on two pools
        pool1 = "pool1_address_here_with_44_chars_total_ok"
        pool2 = "pool2_address_here_with_44_chars_total_ok"
        
        for i in range(6):
            tracker.record_failure(pool1, "SLIPPAGE")
        
        for i in range(3):
            tracker.record_failure(pool2, "SLIPPAGE")
        
        hot = tracker.get_hot_pools(min_failures=3)
        
        assert len(hot) == 2
        assert hot[0]["pool"] == pool1  # Most failures first
        assert hot[0]["failures"] == 6
    
    def test_cooldown_prevents_spam(self):
        """Verify alert cooldown prevents spam."""
        from src.shared.infrastructure.log_harvester import FailureTracker
        
        tracker = FailureTracker(
            window_seconds=30.0,
            failure_threshold=5,
        )
        tracker._alert_cooldown = 0.5  # Short for testing
        
        pool = "test_pool_address_44_chars_here_for_test"
        
        # First spike
        for i in range(5):
            tracker.record_failure(pool, "SLIPPAGE")
        assert tracker.alerts_emitted == 1
        
        # More failures immediately - should NOT alert (cooldown)
        for i in range(3):
            tracker.record_failure(pool, "SLIPPAGE")
        assert tracker.alerts_emitted == 1  # Still 1
        
        # Wait for cooldown
        time.sleep(0.6)
        
        # Now should alert again
        tracker.record_failure(pool, "SLIPPAGE")
        assert tracker.alerts_emitted == 2


class TestBridgePod:
    """Test the BridgePod for whale detection."""
    
    def test_whale_detection(self):
        """Verify whale threshold triggers LIQUIDITY_INFLOW signal."""
        from src.engine.bridge_pod import BridgePod, BridgeEvent
        from src.engine.pod_manager import PodConfig, PodType
        
        signals = []
        
        def capture_signal(signal):
            signals.append(signal)
        
        config = PodConfig(
            pod_type=PodType.WHALE,
            name="test_sniffer",
            params={},
            cooldown_seconds=1.0,
        )
        
        pod = BridgePod(
            config=config,
            signal_callback=capture_signal,
            whale_threshold_usd=250_000.0,
        )
        
        # Below threshold - should NOT emit
        pod.handle_bridge_event({
            "protocol": "CCTP",
            "signature": "sig1",
            "amount_usd": 100_000,
            "mint": "USDC",
            "recipient": "wallet1",
        })
        
        assert len(signals) == 0
        assert pod.whale_count == 0
        
        # Above threshold - should emit
        pod.handle_bridge_event({
            "protocol": "CCTP",
            "signature": "sig2",
            "amount_usd": 500_000,
            "mint": "USDC",
            "recipient": "wallet2",
        })
        
        assert len(signals) == 1
        assert pod.whale_count == 1
        assert signals[0].signal_type == "LIQUIDITY_INFLOW"
        assert signals[0].data["amount_usd"] == 500_000
    
    def test_inflow_aggregation(self):
        """Verify 1-hour inflow aggregation."""
        from src.engine.bridge_pod import BridgePod
        from src.engine.pod_manager import PodConfig, PodType
        
        config = PodConfig(
            pod_type=PodType.WHALE,
            name="test_sniffer",
            params={},
            cooldown_seconds=1.0,
        )
        
        pod = BridgePod(
            config=config,
            signal_callback=lambda x: None,
            whale_threshold_usd=1_000_000,  # High threshold to avoid alerts
        )
        
        # Add multiple events
        for i in range(5):
            pod.handle_bridge_event({
                "protocol": "WORMHOLE",
                "signature": f"sig{i}",
                "amount_usd": 100_000,
                "mint": "ETH",
                "recipient": f"wallet{i}",
            })
        
        assert pod.total_events == 5
        assert len(pod.recent_events) == 5
    
    def test_stats_output(self):
        """Verify stats dictionary format."""
        from src.engine.bridge_pod import BridgePod
        from src.engine.pod_manager import PodConfig, PodType
        
        config = PodConfig(
            pod_type=PodType.WHALE,
            name="test_sniffer",
            params={},
            cooldown_seconds=1.0,
        )
        
        pod = BridgePod(
            config=config,
            signal_callback=lambda x: None,
        )
        
        stats = pod.get_stats()
        
        assert "pod_id" in stats
        assert "status" in stats
        assert "whale_count" in stats
        assert "inflow_1h_usd" in stats


class TestLogHarvesterIntegration:
    """Test LogHarvester integration with FailureTracker."""
    
    def test_failure_tracker_attached(self):
        """Verify LogHarvester has FailureTracker attached."""
        from src.shared.infrastructure.log_harvester import LogHarvester
        
        harvester = LogHarvester()
        
        assert hasattr(harvester, 'failure_tracker')
        assert harvester.failure_tracker is not None
    
    def test_hot_pools_method(self):
        """Verify get_hot_pools delegates to FailureTracker."""
        from src.shared.infrastructure.log_harvester import LogHarvester
        
        harvester = LogHarvester()
        
        hot = harvester.get_hot_pools()
        
        assert isinstance(hot, list)


class TestDashboardPanels:
    """Test that dashboard panels render correctly."""
    
    def test_scavenger_panel_empty(self):
        """Verify Scavenger panel renders with no hot pools."""
        from src.arbiter.ui.pulsed_dashboard import PulsedDashboard
        
        dashboard = PulsedDashboard()
        
        panel = dashboard.generate_scavenger_panel(None)
        
        assert panel is not None
        assert "Scavenger" in str(panel.title)
    
    def test_scavenger_panel_with_data(self):
        """Verify Scavenger panel renders with hot pools."""
        from src.arbiter.ui.pulsed_dashboard import PulsedDashboard
        
        dashboard = PulsedDashboard()
        
        hot_pools = [
            {"pool": "675kPX9MCyJsD5ippTu671dKKkCtSE5v4RBmZJtHNv9v", "failures": 8, "recoil": False},
            {"pool": "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc", "failures": 5, "recoil": True},
        ]
        
        panel = dashboard.generate_scavenger_panel(hot_pools)
        
        assert panel is not None
    
    def test_flow_panel_empty(self):
        """Verify Flow panel renders with no data."""
        from src.arbiter.ui.pulsed_dashboard import PulsedDashboard
        
        dashboard = PulsedDashboard()
        
        panel = dashboard.generate_flow_panel(None)
        
        assert panel is not None
        assert "Flow" in str(panel.title)
    
    def test_flow_panel_with_data(self):
        """Verify Flow panel renders with bridge stats."""
        from src.arbiter.ui.pulsed_dashboard import PulsedDashboard
        
        dashboard = PulsedDashboard()
        
        bridge_stats = {
            "inflow_1h_usd": 1_250_000,
            "whale_count": 3,
        }
        
        panel = dashboard.generate_flow_panel(bridge_stats)
        
        assert panel is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
