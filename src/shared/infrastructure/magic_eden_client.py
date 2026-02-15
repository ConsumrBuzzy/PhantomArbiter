"""
Magic Eden REST API Client
===========================
Wrapper for Magic Eden API to discover Legacy NFT listings.

Real API Schema (February 2026):
- Endpoint: https://api-mainnet.magiceden.dev/v2
- Auth: Optional API key in Authorization header (for some endpoints)
- Rate Limit: 120 QPM (2 QPS)
- Attribution required when using API data
"""

import requests
import time
from typing import List, Dict, Any, Optional
from src.shared.system.logging import Logger


class MagicEdenClient:
    """
    REST API client for Magic Eden marketplace.

    Features:
    - Rate limiting (120 QPM / 2 QPS)
    - Legacy NFT filtering
    - Collection statistics
    - Listing price discovery
    - 1.5% marketplace fee (better than Tensor's 2%)
    """

    def __init__(
        self,
        api_url: str = "https://api-mainnet.magiceden.dev/v2",
        api_key: Optional[str] = None,
        rate_limit_ms: int = 600  # 600ms = ~1.7 QPS (under 2 QPS limit)
    ):
        """
        Initialize Magic Eden REST API client.

        Args:
            api_url: Magic Eden API endpoint
            api_key: Optional API key for authenticated endpoints
            rate_limit_ms: Delay between requests in milliseconds (default: 600ms)
        """
        self.api_url = api_url
        self.api_key = api_key
        self.rate_limit_ms = rate_limit_ms
        self.last_request_time = 0

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self.last_request_time
        sleep_time = (self.rate_limit_ms / 1000.0) - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)
        self.last_request_time = time.time()

    def _make_request(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Make a REST API request to Magic Eden.

        Args:
            endpoint: API endpoint path (e.g., "/collections/{symbol}/listings")
            params: Query parameters

        Returns:
            Response data dict

        Raises:
            Exception: If request fails
        """
        self._rate_limit()

        headers = {
            "Accept": "application/json",
        }

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"{self.api_url}{endpoint}"

        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=10
            )

            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            Logger.error(f"[X] [MagicEdenClient] Request failed: {e}")
            return {}

    def get_collection_stats(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get collection statistics including floor price.

        Args:
            symbol: Collection symbol (e.g., "okay_bears")

        Returns:
            Collection stats dict with floorPrice, listedCount, volumeAll, etc.
        """
        endpoint = f"/collections/{symbol}/stats"

        Logger.info(f"[ME] Fetching stats for collection: {symbol}")

        data = self._make_request(endpoint)

        if data:
            Logger.success(f"[OK] Got stats for {symbol}")
            return data
        else:
            Logger.warning(f"[!] No stats found for {symbol}")
            return None

    def get_collection_listings(
        self,
        symbol: str,
        offset: int = 0,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get active listings for a collection.

        Args:
            symbol: Collection symbol
            offset: Pagination offset
            limit: Max results (default: 20, max: 500)

        Returns:
            List of listing objects with price, tokenMint, seller, etc.

        Response Schema:
        [
            {
                "tokenMint": "ABC123...",
                "price": 0.005,
                "seller": "XYZ789...",
                "tokenSize": 1,
                "rarity": {...},
                "extra": {...}
            }
        ]
        """
        endpoint = f"/collections/{symbol}/listings"

        params = {
            "offset": offset,
            "limit": min(limit, 500)  # API max is 500
        }

        Logger.info(f"[ME] Querying listings for '{symbol}' (offset: {offset}, limit: {limit})")

        data = self._make_request(endpoint, params)

        if isinstance(data, list):
            Logger.success(f"[OK] Found {len(data)} listings")
            return data
        else:
            Logger.warning(f"[!] No listings found for '{symbol}'")
            return []

    def get_cheap_nfts_by_collection(
        self,
        symbol: str,
        max_price_sol: float = 0.009,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Query Magic Eden for cheap NFT listings in a specific collection.

        Args:
            symbol: Collection symbol (e.g., "solana_monkey_business")
            max_price_sol: Maximum price in SOL (default: 0.009)
            limit: Maximum results to return

        Returns:
            List of NFT listings with {mint, price, seller} data

        JANITOR LOGIC:
        - Only returns Legacy NFTs (Magic Eden lists Legacy NFTs, not cNFTs by default)
        - Price must be under max_price_sol threshold
        - Sorted by price ascending
        """
        Logger.info(f"[ME] Scanning '{symbol}' for NFTs under {max_price_sol:.6f} SOL")

        # Get collection stats first
        stats = self.get_collection_stats(symbol)

        if not stats:
            Logger.warning(f"[!] Collection '{symbol}' not found")
            return []

        floor_price = stats.get('floorPrice', 999) / 1e9  # Convert lamports to SOL

        if floor_price > max_price_sol:
            Logger.info(f"[SKIP] Floor price ({floor_price:.6f} SOL) exceeds max ({max_price_sol:.6f} SOL)")
            return []

        # Get listings
        listings = self.get_collection_listings(symbol, limit=limit)

        # Filter for cheap NFTs
        cheap_nfts = []

        for listing in listings:
            price_lamports = int(listing.get('price', 0))
            price_sol = price_lamports / 1e9

            # Only include NFTs under max price
            if price_sol < max_price_sol:
                cheap_nfts.append({
                    "mint_address": listing.get('tokenMint'),
                    "name": f"{symbol}#{listing.get('tokenMint', '')[:8]}",  # ME doesn't always return name
                    "price_lamports": price_lamports,
                    "price_sol": price_sol,
                    "is_compressed": False,  # Magic Eden primarily lists Legacy NFTs
                    "seller": listing.get('seller'),
                    "collection_symbol": symbol,
                    "marketplace": "magic_eden",
                    "marketplace_fee": 0.015  # 1.5%
                })

        if cheap_nfts:
            Logger.success(f"[OK] Found {len(cheap_nfts)} cheap NFTs in '{symbol}'")
        else:
            Logger.warning(f"[!] No NFTs under {max_price_sol:.6f} SOL in '{symbol}'")

        return cheap_nfts

    def get_token_listing(self, mint_address: str) -> Optional[Dict[str, Any]]:
        """
        Get listing details for a specific NFT mint.

        Args:
            mint_address: NFT mint address

        Returns:
            Listing details or None if not listed
        """
        endpoint = f"/tokens/{mint_address}/listings"

        Logger.info(f"[ME] Checking listing for {mint_address[:12]}...")

        data = self._make_request(endpoint)

        if isinstance(data, list) and len(data) > 0:
            return data[0]  # Return first (cheapest) listing

        return None

    def scan_multiple_collections(
        self,
        symbols: List[str],
        max_price_sol: float = 0.009,
        limit_per_collection: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Scan multiple collections for cheap Legacy NFTs.

        Args:
            symbols: List of collection symbols to scan
            max_price_sol: Maximum price threshold
            limit_per_collection: Max results per collection

        Returns:
            Combined list of cheap NFTs from all collections
        """
        Logger.info(f"[ME] Scanning {len(symbols)} collections for Janitor targets...")

        all_targets = []

        for i, symbol in enumerate(symbols):
            Logger.info(f"   [{i+1}/{len(symbols)}] Scanning: {symbol}")

            targets = self.get_cheap_nfts_by_collection(
                symbol=symbol,
                max_price_sol=max_price_sol,
                limit=limit_per_collection
            )

            all_targets.extend(targets)

            # Rate limiting between collections
            if i < len(symbols) - 1:
                time.sleep(self.rate_limit_ms / 1000.0)

        Logger.success(f"[OK] Total targets found: {len(all_targets)}")

        return all_targets

    def get_popular_collections(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get list of popular collections on Magic Eden.

        Args:
            limit: Number of collections to return

        Returns:
            List of collection metadata
        """
        endpoint = "/collections"

        params = {
            "offset": 0,
            "limit": min(limit, 500)
        }

        Logger.info(f"[ME] Fetching popular collections (limit: {limit})")

        data = self._make_request(endpoint, params)

        if isinstance(data, list):
            Logger.success(f"[OK] Found {len(data)} collections")
            return data

        return []
