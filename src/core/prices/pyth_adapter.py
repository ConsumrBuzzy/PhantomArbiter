"""
V48.0: Pyth Network Price Adapter
=================================
Ultra-low-latency price oracle via Pyth Hermes API.

Features:
- ~400ms latency (vs seconds for DexScreener)
- Confidence interval for data quality assessment
- First-party data from exchanges/market makers

API: https://hermes.pyth.network/v2/updates/price/latest
"""

import time
import requests
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from src.core.prices.base import PriceProvider


@dataclass
class PythPrice:
    """
    Pyth price data with confidence interval.

    The confidence interval indicates data quality - tighter = more reliable.
    Use confidence_pct for ML features.
    """

    price: float  # USD price
    confidence: float  # +/- USD uncertainty
    expo: int  # Price exponent (for raw conversion)
    publish_time: int  # Unix timestamp of update
    confidence_pct: float  # confidence/price * 100 (for ML)

    @property
    def is_stale(self) -> bool:
        """Check if price is stale (>5 seconds old)."""
        return time.time() - self.publish_time > 5


class PythAdapter(PriceProvider):
    """
    V48.0: Ultra-low-latency price oracle via Pyth Hermes API.

    Provides:
    - Fast price updates (~400ms)
    - Confidence intervals for data quality
    - First-party data from exchanges

    Usage:
        adapter = PythAdapter()
        prices = adapter.fetch_with_confidence(["SOL", "ETH"])
        if prices["SOL"].confidence_pct < 0.5:
            # High confidence data
            execute_trade()
    """

    HERMES_URL = "https://hermes.pyth.network"
    API_VERSION = "v2"

    # Rate limiting
    REQUEST_TIMEOUT = 5  # seconds
    MIN_REQUEST_INTERVAL = 0.1  # 100ms between requests

    # Pyth Price Feed IDs (Solana mainnet)
    # Source: https://pyth.network/price-feeds
    FEED_IDS: Dict[str, str] = {
        # Major tokens
        "SOL": "0xef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d",
        "ETH": "0xff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
        "BTC": "0xe62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43",
        # Stablecoins
        "USDC": "0xeaa020c61cc479712813461ce153894a96a6c00b21ed0cfc2798d1f9a9e9c94a",
        "USDT": "0x2b89b9dc8fdf9f34709a5b106b472f0f39bb6ca9ce04b0fd7f2e971688e2e53b",
        # LST (for yield strategy)
        "JITOSOL": "0x67be9f519b95cf24338801051f9a808eff0a578ccb388db73b7f6fe1de019ffb",
        # Solana ecosystem
        "RAY": "0x91568baa8beb53db23c6e42b9a3b1d54b3dafbc4c6a57b0e2d5dc3d0e43c8a1f",
        "JUP": "0x0a0408d619e9380abad35060f9192039ed5042fa6f82301d0e48bb52be830996",
    }

    def __init__(self):
        """Initialize Pyth adapter."""
        self._last_request_time = 0
        self._cache: Dict[
            str, Tuple[float, PythPrice]
        ] = {}  # symbol -> (timestamp, price)
        self._cache_ttl = 1.0  # 1 second cache

    def get_name(self) -> str:
        """Return provider name."""
        return "Pyth"

    def fetch_prices(self, mints: list) -> dict:
        """
        Fetch prices for a list of mints.

        Note: Pyth uses symbols, not mints. This method converts where possible.
        For full functionality, use fetch_with_confidence().

        Returns:
            Dict {mint: price_usd} - only for tokens with Pyth feeds
        """
        # This implementation is limited - Pyth uses symbols not mints
        # For now, return empty and use fetch_with_confidence() for full data
        return {}

    def fetch_with_confidence(self, symbols: List[str]) -> Dict[str, PythPrice]:
        """
        Fetch prices with confidence intervals for multiple symbols.

        Args:
            symbols: List of symbols (e.g., ["SOL", "ETH"])

        Returns:
            Dict {symbol: PythPrice} for available feeds
        """
        results: Dict[str, PythPrice] = {}

        # Filter to symbols with known feed IDs
        known_symbols = [s.upper() for s in symbols if s.upper() in self.FEED_IDS]

        if not known_symbols:
            return results

        # Check cache first
        now = time.time()
        uncached_symbols = []
        for symbol in known_symbols:
            if symbol in self._cache:
                cache_time, cached_price = self._cache[symbol]
                if now - cache_time < self._cache_ttl:
                    results[symbol] = cached_price
                else:
                    uncached_symbols.append(symbol)
            else:
                uncached_symbols.append(symbol)

        if not uncached_symbols:
            return results

        # Rate limiting
        time_since_last = now - self._last_request_time
        if time_since_last < self.MIN_REQUEST_INTERVAL:
            time.sleep(self.MIN_REQUEST_INTERVAL - time_since_last)

        # Build request URL with multiple feed IDs
        feed_ids = [self.FEED_IDS[s] for s in uncached_symbols]

        try:
            # Use the v2 API
            url = f"{self.HERMES_URL}/{self.API_VERSION}/updates/price/latest"
            params = {"ids[]": feed_ids}

            self._last_request_time = time.time()
            response = requests.get(url, params=params, timeout=self.REQUEST_TIMEOUT)

            if response.status_code != 200:
                print(f"      ⚠️ Pyth API error: {response.status_code}")
                return results

            data = response.json()

            # Parse response
            parsed = data.get("parsed", [])
            for item in parsed:
                feed_id = item.get("id", "")
                price_data = item.get("price", {})

                # Find symbol for this feed
                symbol = self._feed_id_to_symbol(feed_id)
                if not symbol:
                    continue

                # Parse price (handle exponent)
                raw_price = int(price_data.get("price", 0))
                raw_conf = int(price_data.get("conf", 0))
                expo = int(price_data.get("expo", 0))
                publish_time = int(price_data.get("publish_time", 0))

                # Convert using exponent
                price = raw_price * (10**expo)
                confidence = raw_conf * (10**expo)

                # Calculate confidence percentage
                conf_pct = (confidence / price * 100) if price > 0 else 100.0

                pyth_price = PythPrice(
                    price=price,
                    confidence=confidence,
                    expo=expo,
                    publish_time=publish_time,
                    confidence_pct=conf_pct,
                )

                results[symbol] = pyth_price
                self._cache[symbol] = (time.time(), pyth_price)

        except requests.exceptions.Timeout:
            print("      ⚠️ Pyth API timeout")
        except requests.exceptions.ConnectionError:
            print("      ⚠️ Pyth API connection error")
        except Exception as e:
            print(f"      ⚠️ Pyth API error: {e}")

        return results

    def fetch_single(self, symbol: str) -> Optional[PythPrice]:
        """
        Fetch price for a single symbol.

        Args:
            symbol: Token symbol (e.g., "SOL")

        Returns:
            PythPrice or None if not available
        """
        results = self.fetch_with_confidence([symbol])
        return results.get(symbol.upper())

    def _feed_id_to_symbol(self, feed_id: str) -> Optional[str]:
        """Convert feed ID back to symbol."""
        # Normalize feed_id (sometimes with/without 0x prefix)
        normalized = feed_id.lower()
        if not normalized.startswith("0x"):
            normalized = "0x" + normalized

        for symbol, fid in self.FEED_IDS.items():
            if fid.lower() == normalized:
                return symbol
        return None

    def has_feed(self, symbol: str) -> bool:
        """Check if symbol has a Pyth feed."""
        return symbol.upper() in self.FEED_IDS

    def get_supported_symbols(self) -> List[str]:
        """Get list of supported symbols."""
        return list(self.FEED_IDS.keys())


# ═══════════════════════════════════════════════════════════════════
# TEST SCRIPT
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("Pyth Network Adapter Test")
    print("=" * 60)

    adapter = PythAdapter()

    # Test fetching SOL price
    print("\n1. Fetching SOL price...")
    sol_price = adapter.fetch_single("SOL")
    if sol_price:
        print(f"   SOL: ${sol_price.price:.4f}")
        print(
            f"   Confidence: +/- ${sol_price.confidence:.6f} ({sol_price.confidence_pct:.4f}%)"
        )
        print(f"   Stale: {sol_price.is_stale}")
    else:
        print("   Failed to fetch SOL price")

    # Test batch fetch
    print("\n2. Batch fetching SOL, ETH, BTC...")
    prices = adapter.fetch_with_confidence(["SOL", "ETH", "BTC"])
    for symbol, price in prices.items():
        print(f"   {symbol}: ${price.price:.2f} (+/- {price.confidence_pct:.4f}%)")

    # Test unsupported token
    print("\n3. Testing unsupported token (BONK)...")
    bonk_price = adapter.fetch_single("BONK")
    print(f"   BONK available: {bonk_price is not None}")

    print("\n" + "=" * 60)
    print("Test complete!")
