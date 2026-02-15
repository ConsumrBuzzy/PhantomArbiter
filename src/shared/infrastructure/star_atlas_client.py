"""
Star Atlas Galactic Marketplace Client
======================================
GraphQL client for Star Atlas marketplace arbitrage on z.ink SVM L1.

Strategy Focus (February 2026):
- z.ink Genesis Event: March 2026
- $ZINK Airdrop weighted by zXP (transaction activity)
- Target: SDU spreads, R4 resource arbitrage
- Fee: 6% marketplace (spread must be >7.5% to profit)

Real API:
- Endpoint: https://galaxy.staratlas.com/graphql
- RPC: https://mainnet.z.ink (z.ink L1, not Solana mainnet)
- Bridge: Automatic 2-way bridge (launches March 2026)
"""

import requests
import time
from typing import List, Dict, Any, Optional
from src.shared.system.logging import Logger


class StarAtlasClient:
    """
    GraphQL client for Star Atlas Galactic Marketplace.

    Features:
    - Resource price tracking (Fuel, Food, Ammo, Toolkits)
    - SDU (Survey Data Unit) arbitrage
    - Starbase price variance detection
    - 6% marketplace fee accounting
    - z.ink RPC integration for low-fee transactions
    """

    def __init__(
        self,
        api_url: str = "https://galaxy.staratlas.com",
        market_prices_url: str = "https://galaxy.staratlas.com/market/prices",
        rpc_url: str = "https://mainnet.z.ink",  # z.ink SVM L1
        rate_limit_ms: int = 1000  # 1s between requests
    ):
        """
        Initialize Star Atlas client.

        Args:
            api_url: Star Atlas Galaxy API base URL (REAL - Feb 2026)
            market_prices_url: Market prices JSON endpoint (REAL - Feb 2026)
            rpc_url: z.ink RPC endpoint (SVM-compatible)
            rate_limit_ms: Delay between requests
        """
        self.api_url = api_url
        self.market_prices_url = market_prices_url
        self.rpc_url = rpc_url
        self.rate_limit_ms = rate_limit_ms
        self.last_request_time = 0

        # Star Atlas marketplace fee
        self.MARKETPLACE_FEE = 0.06  # 6%
        self.MIN_PROFIT_SPREAD = 0.075  # 7.5% minimum to be profitable

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self.last_request_time
        sleep_time = (self.rate_limit_ms / 1000.0) - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)
        self.last_request_time = time.time()

    def _make_request(self, query: str, variables: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Make GraphQL request to Star Atlas API.

        Args:
            query: GraphQL query string
            variables: Query variables

        Returns:
            Response data dict
        """
        self._rate_limit()

        headers = {
            "Content-Type": "application/json",
        }

        payload = {
            "query": query,
            "variables": variables or {}
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
                Logger.error(f"[X] [StarAtlas] GraphQL errors: {data['errors']}")
                return {}

            return data.get("data", {})

        except requests.RequestException as e:
            Logger.error(f"[X] [StarAtlas] Request failed: {e}")
            return {}

    def get_resource_listings(
        self,
        resource_name: str,
        starbase_id: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get marketplace listings for R4 resources.

        Args:
            resource_name: Resource type (e.g., "Fuel", "Food", "Ammo", "Toolkit")
            starbase_id: Optional starbase filter
            limit: Max results

        Returns:
            List of listings with price, seller, quantity

        Schema (needs verification with real API):
        {
          marketplaceListings(
            filters: { resourceType: $resourceName, starbase: $starbaseId }
            limit: $limit
            orderBy: { price: ASC }
          ) {
            id
            resourceType
            quantity
            pricePerUnit
            totalPrice
            seller
            starbase {
              id
              name
              coordinates
            }
          }
        }
        """
        query = """
        query GetResourceListings($resourceName: String!, $starbaseId: String, $limit: Int!) {
          marketplaceListings(
            filters: { resourceType: $resourceName, starbase: $starbaseId }
            limit: $limit
            orderBy: { price: ASC }
          ) {
            id
            resourceType
            quantity
            pricePerUnit
            totalPrice
            seller
            starbase {
              id
              name
            }
          }
        }
        """

        variables = {
            "resourceName": resource_name,
            "starbaseId": starbase_id,
            "limit": limit
        }

        Logger.info(f"[SA] Querying {resource_name} listings (starbase: {starbase_id or 'all'})")

        data = self._make_request(query, variables)

        if not data or "marketplaceListings" not in data:
            Logger.warning(f"[!] No {resource_name} listings found")
            return []

        listings = data["marketplaceListings"]
        Logger.success(f"[OK] Found {len(listings)} {resource_name} listings")

        return listings

    def find_fuel_atlas_spread(
        self,
        max_fuel_price_atlas: float = 0.1,
        min_spread_percent: float = 7.5
    ) -> List[Dict[str, Any]]:
        """
        Find profitable Fuel → $ATLAS arbitrage opportunities.

        Args:
            max_fuel_price_atlas: Maximum Fuel price in $ATLAS to consider
            min_spread_percent: Minimum spread % to flag as opportunity

        Returns:
            List of arbitrage opportunities

        Strategy:
        1. Buy Fuel at low-price starbases
        2. Sell at high-demand starbases
        3. Profit = (sell_price - buy_price - 6% fee)
        4. Only flag if spread > 7.5%
        """
        Logger.info(f"[SA] Scanning for Fuel-to-ATLAS spread opportunities...")

        # This is a placeholder - needs real API schema
        # In production, would query all starbases and compare prices

        opportunities = []

        # TODO: Implement once real API schema is available
        Logger.warning("[!] find_fuel_atlas_spread: Placeholder - needs real API implementation")

        return opportunities

    def get_sdu_prices(
        self,
        starbase_id: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get SDU (Survey Data Unit) marketplace prices.

        SDUs are essential crafting materials that often have price
        variance between starbases, creating arbitrage opportunities.

        Args:
            starbase_id: Optional starbase filter
            limit: Max results

        Returns:
            List of SDU listings with prices
        """
        Logger.info(f"[SA] Querying SDU prices (starbase: {starbase_id or 'all'})")

        # Query for SDU listings
        # NOTE: Schema placeholder - needs verification
        query = """
        query GetSDUListings($starbaseId: String, $limit: Int!) {
          marketplaceListings(
            filters: { assetType: "SDU", starbase: $starbaseId }
            limit: $limit
            orderBy: { price: ASC }
          ) {
            id
            quantity
            pricePerUnit
            totalPrice
            seller
            starbase {
              id
              name
            }
          }
        }
        """

        variables = {
            "starbaseId": starbase_id,
            "limit": limit
        }

        data = self._make_request(query, variables)

        if not data or "marketplaceListings" not in data:
            Logger.warning("[!] No SDU listings found")
            return []

        return data["marketplaceListings"]

    def calculate_arbitrage_profit(
        self,
        buy_price: float,
        sell_price: float,
        quantity: int = 1
    ) -> Dict[str, float]:
        """
        Calculate arbitrage profit accounting for 6% marketplace fee.

        Args:
            buy_price: Purchase price per unit
            sell_price: Sale price per unit
            quantity: Number of units

        Returns:
            {
                'gross_profit': float,
                'marketplace_fee': float,
                'net_profit': float,
                'spread_percent': float,
                'is_profitable': bool
            }
        """
        gross_profit = (sell_price - buy_price) * quantity
        marketplace_fee = sell_price * quantity * self.MARKETPLACE_FEE
        net_profit = gross_profit - marketplace_fee

        spread_percent = ((sell_price - buy_price) / buy_price) * 100 if buy_price > 0 else 0

        return {
            'buy_price': buy_price,
            'sell_price': sell_price,
            'quantity': quantity,
            'gross_profit': gross_profit,
            'marketplace_fee': marketplace_fee,
            'net_profit': net_profit,
            'spread_percent': spread_percent,
            'is_profitable': net_profit > 0 and spread_percent >= self.MIN_PROFIT_SPREAD
        }

    def log_arbitrage_opportunity(
        self,
        asset_type: str,
        buy_starbase: str,
        sell_starbase: str,
        profit_data: Dict[str, float]
    ):
        """
        Log arbitrage opportunity to SAGE_ARBITRAGE_LOGS.csv

        Args:
            asset_type: Resource/asset name
            buy_starbase: Where to buy
            sell_starbase: Where to sell
            profit_data: Output from calculate_arbitrage_profit()
        """
        import csv
        from datetime import datetime

        log_file = "SAGE_ARBITRAGE_LOGS.csv"

        # Create file with headers if doesn't exist
        try:
            with open(log_file, 'x', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp',
                    'asset_type',
                    'buy_starbase',
                    'sell_starbase',
                    'buy_price',
                    'sell_price',
                    'quantity',
                    'gross_profit',
                    'marketplace_fee',
                    'net_profit',
                    'spread_percent',
                    'is_profitable'
                ])
        except FileExistsError:
            pass

        # Append opportunity
        with open(log_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().isoformat(),
                asset_type,
                buy_starbase,
                sell_starbase,
                profit_data['buy_price'],
                profit_data['sell_price'],
                profit_data['quantity'],
                profit_data['gross_profit'],
                profit_data['marketplace_fee'],
                profit_data['net_profit'],
                profit_data['spread_percent'],
                profit_data['is_profitable']
            ])

        Logger.success(f"[LOG] Arbitrage opportunity logged: {asset_type} ({profit_data['spread_percent']:.2f}% spread)")

    def scan_for_opportunities(
        self,
        resources: List[str] = None,
        min_spread: float = 7.5
    ) -> List[Dict[str, Any]]:
        """
        Scan marketplace for arbitrage opportunities across all resources.

        Args:
            resources: List of resource types to scan (default: R4 + SDU)
            min_spread: Minimum spread % to consider

        Returns:
            List of profitable opportunities
        """
        if resources is None:
            resources = ["Fuel", "Food", "Ammo", "Toolkit", "SDU"]

        Logger.info(f"[SA] Starting arbitrage scan across {len(resources)} asset types...")

        opportunities = []

        for resource in resources:
            Logger.info(f"   Scanning: {resource}")

            # Get listings (placeholder - needs real implementation)
            listings = self.get_resource_listings(resource, limit=50)

            # TODO: Compare prices across starbases
            # For now, just log that we're scanning

            time.sleep(self.rate_limit_ms / 1000.0)

        Logger.success(f"[OK] Scan complete. Found {len(opportunities)} opportunities")

        return opportunities
