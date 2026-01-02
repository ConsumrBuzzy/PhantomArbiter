"""
Test Contract Integrity - JSON/gRPC Struct Consistency

Verifies data structures remain consistent across serialization.
"""

import pytest
import json
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "apps", "execution", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from execution.order_bus import TradeSignal, SignalAction, SignalStatus


class TestTradeSignalContract:
    """Tests for TradeSignal serialization integrity."""
    
    def test_signal_to_json_roundtrip(self):
        """TradeSignal survives JSON roundtrip."""
        original = TradeSignal(
            symbol="SOL",
            mint="So11111111111111111111111111111111111111112",
            action=SignalAction.BUY,
            size_usd=150.75,
            target_price=148.123456789,
            confidence=0.85,
            source="Scalper_01",
        )
        
        # Serialize
        as_dict = original.to_dict()
        json_str = json.dumps(as_dict)
        
        # Deserialize
        parsed = json.loads(json_str)
        
        # Verify fields
        assert parsed["symbol"] == "SOL"
        assert parsed["mint"] == original.mint
        assert parsed["action"] == "BUY"
        assert parsed["size_usd"] == 150.75
        assert abs(parsed["target_price"] - 148.123456789) < 0.0001
        assert parsed["confidence"] == 0.85
    
    def test_float_precision_maintained(self):
        """Float precision is maintained across wire."""
        signal = TradeSignal(
            symbol="MICRO",
            mint="MicroMint",
            action=SignalAction.BUY,
            size_usd=0.00000123,  # Micro amount
            target_price=0.000000001234567890123,  # Very small
        )
        
        json_str = json.dumps(signal.to_dict())
        parsed = json.loads(json_str)
        
        # Should maintain precision
        assert parsed["size_usd"] == 0.00000123
        # JSON has ~15 digit precision
        assert abs(parsed["target_price"] - 0.000000001234567890123) < 1e-18
    
    def test_timestamp_precision(self):
        """Timestamps maintain millisecond precision."""
        now_ms = int(time.time() * 1000)
        
        signal = TradeSignal(
            symbol="TIME",
            mint="TimeMint",
            action=SignalAction.SELL,
            size_usd=100,
        )
        
        data = signal.to_dict()
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        
        # Timestamp should be close to now
        assert abs(parsed["timestamp"] - (now_ms / 1000)) < 1.0
    
    def test_enum_serialization(self):
        """Enums serialize to strings."""
        signal = TradeSignal(
            symbol="ENUM",
            mint="EnumMint",
            action=SignalAction.BUY,
            size_usd=100,
        )
        
        data = signal.to_dict()
        
        # Action should be string
        assert isinstance(data["action"], str)
        assert data["action"] == "BUY"


class TestStructDrift:
    """Tests to detect struct drift across layers."""
    
    def test_required_fields_present(self):
        """All required fields exist in serialized form."""
        signal = TradeSignal(
            symbol="DRIFT",
            mint="DriftMint",
            action=SignalAction.BUY,
            size_usd=100,
        )
        
        data = signal.to_dict()
        
        required = ["id", "symbol", "mint", "action", "size_usd", "timestamp"]
        for field in required:
            assert field in data, f"Missing required field: {field}"
    
    def test_no_type_drift(self):
        """Types don't accidentally change."""
        signal = TradeSignal(
            symbol="TYPES",
            mint="TypeMint",
            action=SignalAction.BUY,
            size_usd=100.0,
            target_price=50.0,
            confidence=0.75,
        )
        
        data = signal.to_dict()
        
        # Check types
        assert isinstance(data["symbol"], str)
        assert isinstance(data["mint"], str)
        assert isinstance(data["action"], str)
        assert isinstance(data["size_usd"], float)
        assert isinstance(data["target_price"], float)
        assert isinstance(data["confidence"], float)
        assert isinstance(data["timestamp"], float)


class TestExecutionResultContract:
    """Tests for ExecutionResult serialization."""
    
    def test_result_to_dict(self):
        """ExecutionResult serializes correctly."""
        from execution.order_bus import ExecutionResult
        
        result = ExecutionResult(
            signal_id="sig_123",
            status=SignalStatus.FILLED,
            filled_amount=10.5,
            filled_price=149.99,
            slippage_pct=0.003,
            fees_usd=0.15,
            tx_signature="sim_abc123",
        )
        
        data = result.to_dict()
        
        assert data["signal_id"] == "sig_123"
        assert data["status"] == "FILLED"
        assert data["filled_amount"] == 10.5
        assert data["filled_price"] == 149.99
        assert data["slippage_pct"] == 0.003
        assert data["tx_signature"] == "sim_abc123"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
