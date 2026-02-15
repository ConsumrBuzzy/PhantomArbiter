"""
Tensor GraphQL API Client
==========================
Wrapper for Tensor Trade API to discover Legacy NFT listings.

Real API Schema (February 2026):
- Endpoint: https://api.tensor.so/graphql
- Auth: X-TENSOR-API-KEY header
- Query: activeListingsV2 with sortBy: PriceAsc
"""

import requests
import time
from typing import List, Dict, Any, Optional
from src.shared.system.logging import Logger


class TensorClient:
    """
    GraphQL client for Tensor Trade API.

    Features:
    - Rate limiting to avoid API throttling (10s between requests)
    - Legacy NFT filtering (isCompressed: false)
    - Price-based sorting (PriceAsc)
    - Pagination support
    """

    def __init__(
        self,
        api_url: str = "https://api.tensor.so/graphql",
        api_key: Optional[str] = None,
        rate_limit_ms: int = 10000  # 10s to avoid rate limiting
    ):
        """
        Initialize Tensor GraphQL client.

        Args:
            api_url: Tensor GraphQL endpoint
            api_key: API key from tensor.trade/developers (optional but recommended)
            rate_limit_ms: Delay between requests in milliseconds (default: 10s)
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

    def _make_request(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make a GraphQL request to Tensor API.

        Args:
            query: GraphQL query string
            variables: Query variables

        Returns:
            Response data dict

        Raises:
            Exception: If request fails
        """
        self._rate_limit()

        headers = {
            "Content-Type": "application/json",
        }

        if self.api_key:
            headers["X-TENSOR-API-KEY"] = self.api_key

        payload = {
            "query": query,
            "variables": variables
        }

        try:
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=10
            )

            response.raise_for_status()
            data = response.json()

            if "errors" in data:
                Logger.error(f"❌ [TensorClient] GraphQL errors: {data['errors']}")
                return {}

            return data.get("data", {})

        except requests.RequestException as e:
            Logger.error(f"❌ [TensorClient] Request failed: {e}")
            return {}

    def get_cheap_nfts_by_collection(
        self,
        collection_slug: str,
        max_price_lamports: int = 10_500_000,  # ~0.0105 SOL with buffer
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Query Tensor for cheap NFT listings in a specific collection.

        Args:
            collection_slug: Collection slug (e.g., "solana_monkey_business")
            max_price_lamports: Maximum price in lamports (default: 10.5M = ~0.0105 SOL)
            limit: Maximum results to return

        Returns:
            List of NFT listings with {mint, price, isCompressed, seller} data

        Schema (REAL from Tensor API Feb 2026):
        {
          activeListingsV2(slug: $slug, sortBy: PriceAsc, limit: $limit) {
            txs {
              mint { address, isCompressed, onchainName }
              tx { sellerId, grossAmount }
            }
          }
        }
        """
        # REAL Tensor GraphQL Schema (Feb 2026)
        query = """
        query ActiveListings($slug: String!, $cursor: String) {
          activeListingsV2(slug: $slug, sortBy: PriceAsc, cursor: $cursor) {
            page {
              endCursor
              hasNextPage
            }
            txs {
              mint {
                onchainName
                mint
                isCompressed
              }
              tx {
                sellerId
                grossAmount
              }
            }
          }
        }
        """

        variables = {
            "slug": collection_slug,
            "cursor": None
        }

        Logger.info(f"🔍 [TensorClient] Querying collection '{collection_slug}' for NFTs under {max_price_lamports / 1e9:.4f} SOL")

        data = self._make_request(query, variables)

        if not data or "activeListingsV2" not in data:
            Logger.warning("⚠️ [TensorClient] No data returned from API")
            return []

        all_txs = data["activeListingsV2"]["txs"]

        # Filter for Legacy NFTs below max price
        cheap_nfts = []
        for tx in all_txs[:limit]:
            price_lamports = int(tx["tx"]["grossAmount"])
            is_compressed = tx["mint"]["isCompressed"]

            # JANITOR LOGIC:
            # 1. Must NOT be compressed (Legacy NFTs have the 0.0121 SOL rent)
            # 2. Price must be lower than max threshold
            if not is_compressed and price_lamports < max_price_lamports:
                cheap_nfts.append({
                    "mint_address": tx["mint"]["mint"],
                    "name": tx["mint"]["onchainName"],
                    "price_lamports": price_lamports,
                    "price_sol": price_lamports / 1e9,
                    "is_compressed": is_compressed,
                    "seller": tx["tx"]["sellerId"],
                    "collection_slug": collection_slug
                })

        if cheap_nfts:
            Logger.success(f"✅ [TensorClient] Found {len(cheap_nfts)} cheap Legacy NFTs")
        else:
            Logger.warning(f"⚠️ [TensorClient] No cheap Legacy NFTs found in '{collection_slug}'")

        return cheap_nfts

    def get_collection_floor_price(self, collection_slug: str) -> Optional[float]:
        """
        Get floor price for a specific collection.

        Args:
            collection_slug: Collection identifier

        Returns:
            Floor price in SOL, or None if not found
        """
        query = """
        query GetCollectionStats($slug: String!) {
          collectionStats(slug: $slug) {
            floorPrice
          }
        }
        """

        variables = {"slug": collection_slug}

        data = self._make_request(query, variables)

        if data and "collectionStats" in data:
            floor_lamports = data["collectionStats"].get("floorPrice")
            if floor_lamports:
                return floor_lamports / 1e9  # Convert to SOL

        return None

    def scan_multiple_collections(
        self,
        collection_slugs: List[str],
        max_price_lamports: int = 10_500_000,
        limit_per_collection: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Scan multiple collections for cheap Legacy NFTs.

        Args:
            collection_slugs: List of collection slugs to scan
            max_price_lamports: Maximum price threshold
            limit_per_collection: Max results per collection

        Returns:
            Combined list of cheap NFTs from all collections
        """
        Logger.info(f"🔍 [TensorClient] Scanning {len(collection_slugs)} collections for Janitor targets...")

        all_targets = []

        for i, slug in enumerate(collection_slugs):
            Logger.info(f"   [{i+1}/{len(collection_slugs)}] Scanning: {slug}")

            targets = self.get_cheap_nfts_by_collection(
                collection_slug=slug,
                max_price_lamports=max_price_lamports,
                limit=limit_per_collection
            )

            all_targets.extend(targets)

            # Rate limiting between collections
            if i < len(collection_slugs) - 1:
                time.sleep(self.rate_limit_ms / 1000.0)

        Logger.success(f"✅ [TensorClient] Total targets found: {len(all_targets)}")

        return all_targets
