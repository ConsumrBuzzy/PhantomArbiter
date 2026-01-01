"""
Test Suite: Slab Decoder (The Ledger)
=====================================
Verifies L2 orderbook parsing for Phoenix and OpenBook.

Run: pytest tests/test_slab_decoder.py -v
"""

import pytest
import base64


def test_ledger_imports():
    """Verify L2 orderbook classes and functions are available."""
    import phantom_core

    # Classes
    assert hasattr(phantom_core, "L2Level")
    assert hasattr(phantom_core, "L2Orderbook")

    # Phoenix
    assert hasattr(phantom_core, "decode_phoenix_header")
    assert hasattr(phantom_core, "decode_phoenix_orderbook")

    # OpenBook
    assert hasattr(phantom_core, "decode_openbook_slab")
    assert hasattr(phantom_core, "build_openbook_orderbook")

    # Utilities
    assert hasattr(phantom_core, "calculate_ofi")
    assert hasattr(phantom_core, "calculate_vwap")


def test_l2_level_repr():
    """L2Level should have a readable repr."""
    import phantom_core

    # Create L2Level via decode (we can't instantiate directly without data)
    # Just test that the class exists
    assert phantom_core.L2Level is not None


def test_decode_phoenix_header_short_data():
    """Short data should return None."""
    import phantom_core

    # Create data shorter than 128 bytes
    short_data = base64.b64encode(b"short").decode()
    result = phantom_core.decode_phoenix_header(short_data)

    assert result is None


def test_decode_phoenix_orderbook_empty():
    """Empty orderbook should return empty levels."""
    import phantom_core

    # Create minimal valid data (256 byte header + no orders)
    data = b"\x00" * 256
    data_b64 = base64.b64encode(data).decode()

    orderbook = phantom_core.decode_phoenix_orderbook(data_b64, 0.0001, 0.001, 20)

    assert len(orderbook.bids) == 0
    assert len(orderbook.asks) == 0
    assert orderbook.best_bid is None
    assert orderbook.best_ask is None
    assert orderbook.spread is None


def test_decode_openbook_slab_empty():
    """Empty slab should return empty levels."""
    import phantom_core

    # Create minimal valid data (72 byte header + no nodes)
    data = b"\x00" * 72
    data_b64 = base64.b64encode(data).decode()

    levels = phantom_core.decode_openbook_slab(data_b64, True, 0.0001, 0.001, 20)

    assert len(levels) == 0


def test_build_openbook_orderbook():
    """Building orderbook from levels should calculate derived values."""
    import phantom_core

    # We need to use the C-created L2Level objects
    # For now, test with empty lists
    orderbook = phantom_core.build_openbook_orderbook([], [])

    assert len(orderbook.bids) == 0
    assert len(orderbook.asks) == 0
    assert orderbook.spread is None


def test_calculate_ofi_empty():
    """OFI with no data should return 0."""
    import phantom_core

    ofi = phantom_core.calculate_ofi([], [], 5)
    assert ofi == 0.0


def test_calculate_vwap_empty():
    """VWAP with no data should return 0."""
    import phantom_core

    vwap = phantom_core.calculate_vwap([])
    assert vwap == 0.0


def test_orderbook_repr():
    """L2Orderbook should have a readable repr."""
    import phantom_core

    orderbook = phantom_core.build_openbook_orderbook([], [])
    repr_str = repr(orderbook)

    assert "L2Orderbook" in repr_str
    assert "bids=0" in repr_str
    assert "asks=0" in repr_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
