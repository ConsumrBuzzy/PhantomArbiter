"""
Shared Price Cache - V7.1
=========================
Atomic file-based cache for cross-process price sharing.
The Data Broker writes, Trading Engines read.
"""

import os
import json
import time

try:
    from filelock import FileLock
except ImportError:
    # V12.1: Robust fallback if filelock is missing (prevents boot crash)
    class FileLock:
        def __init__(self, *args, **kwargs):
            pass

        def acquire(self, *args, **kwargs):
            return self

        def release(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args, **kwargs):
            pass


# Cache file locations
CACHE_DIR = os.path.dirname(__file__)
CACHE_FILE = os.path.join(CACHE_DIR, "../../data/price_cache.json")
CACHE_LOCK = os.path.join(CACHE_DIR, "../../data/.price_cache.lock")

# Ensure data directory exists
os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)


class SharedPriceCache:
    """
    V7.1: File-based price cache for cross-process data sharing.

    - Data Broker writes prices atomically
    - Trading Engines read latest prices
    - Uses file lock to prevent corruption
    """

    _lock = None

    @classmethod
    def _get_lock(cls):
        if cls._lock is None:
            cls._lock = FileLock(CACHE_LOCK)
        return cls._lock

    @classmethod
    def write_price(cls, symbol: str, price: float, source: str = "WSS"):
        """
        Write a single price to cache with history (V7.1.1).

        Args:
            symbol: Token symbol (e.g., "JUP")
            price: Current price in USD
            source: Data source tag ("WSS", "BATCH", etc.)
        """
        lock = cls._get_lock()
        try:
            # V15.2: Timeout to prevent hanging
            with lock.acquire(timeout=0.2):
                data = cls._read_raw()

                # Initialize symbol data if needed
                if symbol not in data["prices"]:
                    data["prices"][symbol] = {
                        "price": 0,
                        "source": "",
                        "timestamp": 0,
                        "history": [],
                    }

                # Update current price
                data["prices"][symbol]["price"] = price
                data["prices"][symbol]["source"] = source
                data["prices"][symbol]["timestamp"] = time.time()

                # V7.1.1: Append to history (max 100 points)
                history = data["prices"][symbol].get("history", [])
                history.append({"price": price, "ts": time.time()})
                if len(history) > 100:
                    history = history[-100:]  # Keep last 100
                data["prices"][symbol]["history"] = history

                data["last_update"] = time.time()
                cls._write_raw(data)
        except Exception:
            pass

    @classmethod
    def write_batch(cls, prices: dict, source: str = "BATCH"):
        """
        Write multiple prices at once with history (V7.1.1).

        Args:
            prices: Dict of {symbol: price}
            source: Data source tag
        """
        lock = cls._get_lock()
        try:
            with lock.acquire(timeout=0.2):
                data = cls._read_raw()
                ts = time.time()

                for symbol, price in prices.items():
                    # Initialize if needed
                    if symbol not in data["prices"]:
                        data["prices"][symbol] = {
                            "price": 0,
                            "source": "",
                            "timestamp": 0,
                            "history": [],
                        }

                    data["prices"][symbol]["price"] = price
                    data["prices"][symbol]["source"] = source
                    data["prices"][symbol]["timestamp"] = ts

                    # V7.2: Store ALL prices (no deduplication) for RSI granularity
                    history = data["prices"][symbol].get("history", [])
                    history.append({"price": price, "ts": ts})
                    if len(history) > 200:  # Increased to 200 for 2-hour window
                        history = history[-200:]
                    data["prices"][symbol]["history"] = history

                data["last_update"] = ts
                cls._write_raw(data)
        except Exception:
            pass

    @classmethod
    def get_price_history(cls, symbol: str, max_age: float = 3600.0) -> list:
        """
        V7.1.1/V7.2c: Get price history for RSI calculation.

        Args:
            symbol: Token symbol
            max_age: Ignored for V7.2 - historical data has old timestamps

        Returns:
            List of prices (floats) for RSI calculation
        """
        lock = cls._get_lock()
        try:
            with lock.acquire(timeout=0.2):
                data = cls._read_raw()
        except:
            return []

        entry = data.get("prices", {}).get(symbol, {})
        history = entry.get("history", [])

        if not history:
            return []

        # V7.2c: Return ALL prices without timestamp filtering
        # CoinGecko backfill data has historical timestamps
        prices = [h["price"] for h in history]

        return prices

    @classmethod
    def get_price(cls, symbol: str, max_age: float = 30.0) -> tuple:
        """
        Get price for a symbol (called by Trading Engines).

        Args:
            symbol: Token symbol
            max_age: Max age in seconds before price is considered stale

        Returns:
            (price, source) or (None, None) if stale/missing
        """
        lock = cls._get_lock()
        try:
            with lock.acquire(timeout=0.2):
                data = cls._read_raw()
        except:
            return None, None

        entry = data.get("prices", {}).get(symbol)
        if not entry:
            return None, None

        age = time.time() - entry.get("timestamp", 0)
        if age > max_age:
            return None, None

        return entry.get("price"), entry.get("source")

    @classmethod
    def get_all_prices(cls, max_age: float = 30.0) -> dict:
        """
        Get all prices (called by Trading Engines).

        Returns:
            Dict of {symbol: {"price": float, "source": str, "age": float}}
        """
        lock = cls._get_lock()
        try:
            with lock.acquire(timeout=0.2):
                data = cls._read_raw()
        except:
            return {}

        result = {}
        now = time.time()

        for symbol, entry in data.get("prices", {}).items():
            age = now - entry.get("timestamp", 0)
            if age <= max_age:
                result[symbol] = {
                    "price": entry.get("price"),
                    "source": entry.get("source"),
                    "age": age,
                }

        return result

    @classmethod
    def get_broker_status(cls) -> dict:
        """Check if broker is running (last update time)."""
        lock = cls._get_lock()
        with lock:
            data = cls._read_raw()

        last_update = data.get("last_update", 0)
        broker_pid = data.get("broker_pid")

        return {
            "last_update": last_update,
            "age": time.time() - last_update,
            "broker_pid": broker_pid,
            # V10.12: Check explicit heartbeat OR last price update
            "broker_alive": (
                time.time() - max(last_update, data.get("broker_heartbeat", 0))
            )
            < 60,
        }

    @classmethod
    def set_broker_info(cls, pid: int):
        """Set broker process info."""
        lock = cls._get_lock()
        try:
            with lock.acquire(timeout=0.2):
                data = cls._read_raw()
                data["broker_pid"] = pid
                data["broker_started"] = time.time()
                # V10.12: Explicit Heartbeat timestamp
                data["broker_heartbeat"] = time.time()
                cls._write_raw(data)
        except:
            pass

    @classmethod
    def _read_raw(cls):
        """Read existing cache or return template."""
        if not os.path.exists(CACHE_FILE):
            return {"prices": {}, "last_update": 0, "active_positions": {}}
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {"prices": {}, "last_update": 0, "active_positions": {}}
        except Exception:
            # Fallback for read errors
            return {"prices": {}, "last_update": 0, "active_positions": {}}

    @classmethod
    def _write_raw(cls, data):
        """
        Write cache atomically using rename.
        V13.4: Added retry logic for WinError 5 (Permission Denied).
        """
        temp_file = CACHE_FILE + ".tmp"
        try:
            with open(temp_file, "w") as f:
                json.dump(data, f)
                f.flush()

            # Atomic swap with retry
            max_retries = 5
            for i in range(max_retries):
                try:
                    os.replace(temp_file, CACHE_FILE)
                    return
                except PermissionError:
                    if i == max_retries - 1:
                        raise  # Give up on last try
                    time.sleep(0.05)
                except Exception:
                    raise

        except Exception:
            # Cleanup temp if failed
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
            # Silent fail to avoid crashing core
            # print(f"Cache Write Error: {e}")
            pass

    # ═══════════════════════════════════════════════════════════════════
    # V7.1.2: Wallet State Caching
    # ═══════════════════════════════════════════════════════════════════

    @classmethod
    def write_wallet_state(
        cls, usdc_balance: float, held_assets: dict, sol_balance: float = 0
    ):
        """
        V7.1.2: Cache wallet state for all engines to read.

        Args:
            usdc_balance: Available USDC (POCKET)
            held_assets: Dict of {symbol: {"balance": float, "value_usd": float}}
            sol_balance: Native SOL for gas
        """
        lock = cls._get_lock()
        with lock:
            data = cls._read_raw()
            data["wallet"] = {
                "usdc": usdc_balance,
                "sol": sol_balance,
                "held_assets": held_assets,
                "timestamp": time.time(),
            }
            cls._write_raw(data)

    @classmethod
    def get_wallet_state(cls, max_age: float = 60.0) -> dict:
        """
        V7.1.2: Get cached wallet state.

        Returns:
            {"usdc": float, "sol": float, "held_assets": dict} or empty dict if stale
        """
        lock = cls._get_lock()
        with lock:
            data = cls._read_raw()

        wallet = data.get("wallet", {})
        if not wallet:
            return {}

        age = time.time() - wallet.get("timestamp", 0)
        if age > max_age:
            return {}

        return wallet

    @classmethod
    def invalidate_wallet_state(cls):
        """
        V9.7: Force wallet state refresh on next read.
        Called after trades to ensure fresh balance data.
        """
        lock = cls._get_lock()
        with lock:
            data = cls._read_raw()
            if "wallet" in data:
                data["wallet"]["timestamp"] = 0  # Mark as stale
                cls._write_raw(data)

    @classmethod
    def write_safety(
        cls, symbol: str, is_safe: bool, liquidity: float = 0.0, reason: str = ""
    ):
        """
        Write safety validation result to cache.

        Args:
            symbol: Token symbol
            is_safe: Whether token passed safety checks
            liquidity: Token liquidity in USD
            reason: Reason for failure (if not safe)
        """
        lock = cls._get_lock()
        with lock:
            data = cls._read_raw()

            if "safety" not in data:
                data["safety"] = {}

            data["safety"][symbol] = {
                "safe": is_safe,
                "liquidity": liquidity,
                "reason": reason,
                "timestamp": time.time(),
            }

            cls._write_raw(data)

    @classmethod
    def get_safety(cls, symbol: str, max_age: float = 3600.0) -> dict:
        """
        Get cached safety validation result.

        Args:
            symbol: Token symbol
            max_age: Max age in seconds (default 1 hour)

        Returns:
            {"safe": bool, "liquidity": float, "reason": str} or empty dict if stale/missing
        """
        lock = cls._get_lock()
        with lock:
            data = cls._read_raw()

        safety = data.get("safety", {}).get(symbol, {})
        if not safety:
            return {}

        age = time.time() - safety.get("timestamp", 0)
        if age > max_age:
            return {}

        return safety

    # ═══════════════════════════════════════════════════════════════════
    # V48.0: Universal Watcher - Rich Market Data Caching
    # ═══════════════════════════════════════════════════════════════════

    @classmethod
    def write_market_data(cls, symbol: str, market_data: dict):
        """
        V48.0: Cache rich market data from Universal Watcher.

        Args:
            symbol: Token symbol
            market_data: Dict with dex_id, liquidity_usd, volume_24h_usd, etc.
        """
        lock = cls._get_lock()
        try:
            with lock.acquire(timeout=0.2):
                data = cls._read_raw()

                if "market_data" not in data:
                    data["market_data"] = {}

                data["market_data"][symbol] = {**market_data, "timestamp": time.time()}

                cls._write_raw(data)
        except Exception:
            pass

    @classmethod
    def write_market_data_batch(cls, market_data_batch: dict):
        """
        V48.0: Batch write rich market data for multiple tokens.

        Args:
            market_data_batch: Dict of {symbol: market_data_dict}
        """
        if not market_data_batch:
            return

        lock = cls._get_lock()
        try:
            with lock.acquire(timeout=0.2):
                data = cls._read_raw()
                ts = time.time()

                if "market_data" not in data:
                    data["market_data"] = {}

                for symbol, mkt_data in market_data_batch.items():
                    data["market_data"][symbol] = {**mkt_data, "timestamp": ts}

                cls._write_raw(data)
        except Exception:
            pass

    @classmethod
    def get_market_data(cls, symbol: str, max_age: float = 300.0) -> dict:
        """
        V48.0: Get cached rich market data for a symbol.

        Returns:
            Dict with dex_id, liquidity_usd, etc. or empty dict if stale/missing
        """
        lock = cls._get_lock()
        try:
            with lock.acquire(timeout=0.2):
                data = cls._read_raw()
        except:
            return {}

        entry = data.get("market_data", {}).get(symbol, {})
        if not entry:
            return {}

        age = time.time() - entry.get("timestamp", 0)
        if age > max_age:
            return {}

        return entry

    @classmethod
    def get_dex_id(cls, symbol: str, max_age: float = 300.0) -> str:
        """
        V48.0: Get cached dex_id for a symbol (convenience method).

        Returns:
            DEX ID string (e.g., 'raydium', 'orca') or 'unknown' if not cached
        """
        mkt_data = cls.get_market_data(symbol, max_age)
        return mkt_data.get("dex_id", "unknown")

    # ═══════════════════════════════════════════════════════════════════
    # V60.0: Market Regime Sharing
    # ═══════════════════════════════════════════════════════════════════

    @classmethod
    def write_market_regime(cls, regime_data: dict):
        """
        Write global market regime to cache.

        Args:
            regime_data: Dict with volatility, trend, quality_score, etc.
        """
        lock = cls._get_lock()
        try:
            with lock.acquire(timeout=0.2):
                data = cls._read_raw()
                data["regime"] = {**regime_data, "timestamp": time.time()}
                cls._write_raw(data)
        except Exception:
            pass

    @classmethod
    def get_market_regime(cls, max_age: float = 300.0) -> dict:
        """
        Get cached market regime.

        Returns:
            Dict or empty if stale.
        """
        lock = cls._get_lock()
        try:
            with lock.acquire(timeout=0.2):
                data = cls._read_raw()
        except:
            return {}

        regime = data.get("regime", {})
        if not regime:
            return {}

        if time.time() - regime.get("timestamp", 0) > max_age:
            return {}

        return regime

    # ═══════════════════════════════════════════════════════════════════
    # V61.0: Smart Money Trust Signals
    # ═══════════════════════════════════════════════════════════════════

    @classmethod
    def write_trust_score(cls, symbol: str, score: float):
        """
        Write Smart Money Trust Score (0.0 - 1.0).
        """
        lock = cls._get_lock()
        try:
            with lock.acquire(timeout=0.2):
                data = cls._read_raw()
                if "trust_scores" not in data:
                    data["trust_scores"] = {}

                data["trust_scores"][symbol] = {
                    "score": score,
                    "timestamp": time.time(),
                }
                cls._write_raw(data)
        except Exception:
            pass

    @classmethod
    def get_trust_score(cls, symbol: str, max_age: float = 600.0) -> float:
        """
        Get Smart Money Trust Score for a symbol.
        Returns 0.0 if stale or not found.
        """
        lock = cls._get_lock()
        try:
            with lock.acquire(timeout=0.2):
                data = cls._read_raw()
        except:
            return 0.0

        scores = data.get("trust_scores", {})
        item = scores.get(symbol)

        if not item:
            return 0.0

        if time.time() - item.get("timestamp", 0) > max_age:
            return 0.0

        return item.get("score", 0.0)

    @classmethod
    def get_all_trust_scores(
        cls, min_score: float = 0.5, max_age: float = 600.0
    ) -> dict:
        """
        Get all active trust scores above threshold.
        Returns: {symbol: score}
        """
        lock = cls._get_lock()
        try:
            with lock.acquire(timeout=0.2):
                data = cls._read_raw()
        except:
            return {}

        scores = data.get("trust_scores", {})
        result = {}
        now = time.time()

        for symbol, item in scores.items():
            if (
                now - item.get("timestamp", 0) <= max_age
                and item.get("score", 0) >= min_score
            ):
                result[symbol] = item.get("score", 0)

        return result

    # ═══════════════════════════════════════════════════════════════════
    # V12.5: Active Positions Sharing
    # ═══════════════════════════════════════════════════════════════════

    @classmethod
    def write_active_positions(cls, positions: list):
        """
        Write list of active positions to cache.

        Args:
            positions: List of dicts [{"symbol": "SOL", "entry": 150.0, "pnl_pct": 5.2, ...}]
        """
        lock = cls._get_lock()
        with lock:
            data = cls._read_raw()
            data["active_positions"] = {
                "positions": positions,
                "timestamp": time.time(),
            }
            cls._write_raw(data)

    @classmethod
    def get_active_positions(cls, max_age: float = 30.0) -> list:
        """
        Get cached active positions.

        Returns:
            List of position dicts.
        """
        lock = cls._get_lock()
        with lock:
            data = cls._read_raw()

        entry = data.get("active_positions", {})
        if not entry:
            return []

        if time.time() - entry.get("timestamp", 0) > max_age:
            # Return old data if stale? No, return empty or stale.
            # Given use case (alert), Stale might be fine or empty.
            # Prompt implied precise data. Let's return empty if > 30s as it's active trading.
            return []

        return entry.get("positions", [])


# Convenience functions for engines
def get_cached_price(symbol: str, max_age: float = 30.0):
    """Get price from shared cache."""
    return SharedPriceCache.get_price(symbol, max_age)


def is_broker_alive() -> bool:
    """Check if data broker is running."""
    return SharedPriceCache.get_broker_status().get("broker_alive", False)
