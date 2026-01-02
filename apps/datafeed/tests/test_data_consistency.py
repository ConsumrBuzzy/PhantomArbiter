"""
Test Data Consistency - Serialization and Precision

Verifies data remains consistent across serialization boundaries.
"""

import pytest
import json
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from datafeed.price_aggregator import PricePoint, PriceSource


class TestPricePointSerialization:
    """Tests for PricePoint serialization."""
    
    def test_to_dict_roundtrip(self):
        """PricePoint survives dict roundtrip."""
        original = PricePoint(
            mint="TokenMint123456789012345678901234567890123",
            symbol="TKN",
            price=123.456789012345,
            source=PriceSource.HELIUS,
            timestamp=time.time(),
            volume=100000.5,
            liquidity=5000000.75,
        )
        
        data = original.to_dict()
        
        assert data["mint"] == original.mint
        assert data["symbol"] == "TKN"
        assert abs(data["price"] - 123.456789012345) < 1e-10
        assert data["source"] == "HELIUS"
    
    def test_json_roundtrip(self):
        """PricePoint survives JSON roundtrip."""
        original = PricePoint(
            mint="SOL123",
            symbol="SOL",
            price=150.123456,
            source=PriceSource.DEXSCREENER,
            timestamp=1704214800.123,
        )
        
        json_str = json.dumps(original.to_dict())
        parsed = json.loads(json_str)
        
        assert parsed["mint"] == "SOL123"
        assert parsed["price"] == 150.123456
        assert parsed["timestamp"] == 1704214800.123


class TestFloatPrecision:
    """Tests for floating point precision."""
    
    def test_micro_price_precision(self):
        """Micro prices maintain precision."""
        point = PricePoint(
            mint="MICRO",
            symbol="MCR",
            price=0.00000000123456789,  # Very small
            source=PriceSource.HELIUS,
        )
        
        data = point.to_dict()
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        
        # Should maintain precision to ~15 digits
        assert abs(parsed["price"] - 0.00000000123456789) < 1e-20
    
    def test_large_volume_precision(self):
        """Large volumes don't lose precision."""
        point = PricePoint(
            mint="WHALE",
            symbol="WHL",
            price=1.0,
            source=PriceSource.HELIUS,
            volume=123456789012345.67,  # Large
        )
        
        data = point.to_dict()
        
        # Check no integer overflow or precision loss
        assert data["volume"] == 123456789012345.67


class TestTimestampPrecision:
    """Tests for timestamp handling."""
    
    def test_millisecond_precision(self):
        """Timestamps maintain millisecond precision."""
        ts = 1704214800.123456  # With microseconds
        
        point = PricePoint(
            mint="TIME",
            symbol="TM",
            price=1.0,
            source=PriceSource.HELIUS,
            timestamp=ts,
        )
        
        data = point.to_dict()
        
        # Should maintain at least millisecond precision
        assert abs(data["timestamp"] - ts) < 0.001
    
    def test_timestamp_in_past(self):
        """Past timestamps are preserved."""
        past = time.time() - 3600  # 1 hour ago
        
        point = PricePoint(
            mint="PAST",
            symbol="PST",
            price=1.0,
            source=PriceSource.HELIUS,
            timestamp=past,
        )
        
        assert point.timestamp == past


class TestMintMapping:
    """Tests for symbol/mint mapping."""
    
    def test_full_mint_preserved(self):
        """Full 44-char mint addresses are preserved."""
        full_mint = "So11111111111111111111111111111111111111112"
        
        point = PricePoint(
            mint=full_mint,
            symbol="SOL",
            price=150.0,
            source=PriceSource.HELIUS,
        )
        
        assert len(point.mint) == 44
        assert point.mint == full_mint
    
    def test_symbol_case_preserved(self):
        """Symbol case is preserved."""
        point = PricePoint(
            mint="TEST",
            symbol="BonK",  # Mixed case
            price=0.001,
            source=PriceSource.HELIUS,
        )
        
        assert point.symbol == "BonK"


class TestStaleDataDetection:
    """Tests for stale data handling."""
    
    def test_fresh_data_not_stale(self):
        """Recent data is not marked stale."""
        point = PricePoint(
            mint="FRESH",
            symbol="FRS",
            price=1.0,
            source=PriceSource.HELIUS,
            timestamp=time.time(),
        )
        
        assert point.is_stale(max_age_seconds=60) is False
    
    def test_old_data_is_stale(self):
        """Old data is marked stale."""
        point = PricePoint(
            mint="OLD",
            symbol="OLD",
            price=1.0,
            source=PriceSource.HELIUS,
            timestamp=time.time() - 120,  # 2 minutes ago
        )
        
        assert point.is_stale(max_age_seconds=60) is True
    
    def test_stale_threshold_configurable(self):
        """Stale threshold can be adjusted."""
        point = PricePoint(
            mint="EDGE",
            symbol="EDG",
            price=1.0,
            source=PriceSource.HELIUS,
            timestamp=time.time() - 30,  # 30 seconds ago
        )
        
        # 20s threshold = stale
        assert point.is_stale(max_age_seconds=20) is True
        
        # 60s threshold = fresh
        assert point.is_stale(max_age_seconds=60) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
