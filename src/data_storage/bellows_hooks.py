"""
Bellows Hooks - Integration between DataBroker and Storage.

Wires TrendEngine and WarmBuffer to the live price feed.
"""

from __future__ import annotations

import time
from typing import Optional, Dict, Any

from src.shared.system.logging import Logger


# Lazy imports to avoid circular dependencies
_trend_engine = None
_warm_buffer = None
_archive_engine = None
_initialized = False


def _ensure_initialized():
    """Lazy initialization of storage components."""
    global _trend_engine, _warm_buffer, _archive_engine, _initialized
    
    if _initialized:
        return
    
    try:
        from src.data_storage.trend_engine import get_trend_engine
        from src.data_storage.warm_buffers import get_warm_buffer
        from src.data_storage.archive_engine import get_archive_engine
        
        _trend_engine = get_trend_engine()
        _warm_buffer = get_warm_buffer()
        _archive_engine = get_archive_engine()
        _initialized = True
        
        Logger.info("🔗 [Bellows] Storage hooks initialized")
    except ImportError as e:
        Logger.warning(f"⚠️ [Bellows] Import failed: {e}")


def on_price_update(
    mint: str,
    symbol: str,
    price: float,
    volume: float = 0.0,
    liquidity: float = 0.0,
    timestamp: Optional[float] = None,
) -> None:
    """
    Hook for price updates from DataBroker.
    
    Call this whenever a new price is received (WSS or HTTP).
    Updates TrendEngine (for archival) and WarmBuffer (for indicators).
    """
    _ensure_initialized()
    
    if price <= 0:
        return
    
    ts = timestamp or time.time()
    
    # Feed TrendEngine (OHLCV aggregation)
    if _trend_engine:
        delta = _trend_engine.add_tick(mint, symbol, price, volume, liquidity, ts)
        
        # If a window closed, archive the delta
        if delta and _archive_engine:
            _archive_engine.append_delta(delta)
    
    # Feed WarmBuffer (indicators)
    if _warm_buffer:
        _warm_buffer.add_price(mint, price, ts, symbol, volume)


def check_window_expiry() -> int:
    """
    Check and close expired windows.
    
    Call this periodically (e.g., every 1 second).
    Returns count of windows closed.
    """
    _ensure_initialized()
    
    if not _trend_engine:
        return 0
    
    deltas = _trend_engine.check_window_expiry()
    
    if deltas and _archive_engine:
        _archive_engine.append_deltas(deltas)
    
    return len(deltas)


def get_regime(mint: str) -> str:
    """Get market regime for a token."""
    _ensure_initialized()
    
    if _warm_buffer:
        return _warm_buffer.get_regime(mint).value
    return "UNKNOWN"


def get_indicators(mint: str) -> Dict[str, Any]:
    """Get all indicators for a token."""
    _ensure_initialized()
    
    if _warm_buffer:
        return _warm_buffer.get_indicators(mint).to_dict()
    return {}


def get_rsi(mint: str, period: int = 14) -> float:
    """Get RSI for a token."""
    _ensure_initialized()
    
    if _warm_buffer:
        return _warm_buffer.get_rsi(mint, period)
    return 50.0


def shutdown_flush() -> Dict[str, Any]:
    """
    Flush all pending data on shutdown.
    
    Returns stats on what was flushed.
    """
    _ensure_initialized()
    
    result = {
        "deltas_flushed": 0,
        "checkpoint_saved": False,
    }
    
    if _trend_engine and _archive_engine:
        deltas = _trend_engine.flush_all()
        if deltas:
            count = _archive_engine.append_deltas(deltas)
            result["deltas_flushed"] = count
            Logger.info(f"💧 [Bellows] Flushed {count} deltas on shutdown")
    
    return result


def get_storage_stats() -> Dict[str, Any]:
    """Get combined storage statistics."""
    _ensure_initialized()
    
    stats = {}
    
    if _trend_engine:
        stats["trend_engine"] = _trend_engine.get_stats()
    
    if _warm_buffer:
        stats["warm_buffer"] = _warm_buffer.get_stats()
    
    if _archive_engine:
        stats["archive"] = _archive_engine.get_stats()
    
    return stats
