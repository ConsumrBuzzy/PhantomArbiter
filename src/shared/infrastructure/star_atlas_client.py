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

    ZINK_CHAIN_ID = 57073  # Official z.ink Chain ID
    SDU_MINT = "SDUsgfSZaDhhZ76U3ZgvtFiXsfnHbf2VrzYxjBZ5YbM"  # SDU Mint (Mainnet/Z.ink)
    
    # Authenticated RPC Pool (Failover)
    IRONFORGE_RPC_POOL = []

    def __init__(
        self,
        api_url: str = "https://galaxy.staratlas.com/graphql",
        market_prices_url: str = "https://galaxy.staratlas.com/market/prices",
        rpc_url: str = None,  # Will use pool
        rate_limit_ms: int = 1000  # 1s between requests
    ):
        """
        Initialize Star Atlas client.
        """
        self._load_env_config()
        
        self.api_url = api_url
        self.market_prices_url = market_prices_url
        self.rate_limit_ms = rate_limit_ms
        self.last_request_time = 0
        
        # RPC Failsafe
        self.rpc_index = 0
        if rpc_url:
             self.rpc_url = rpc_url # Manual override
        else:
             self.rpc_url = self._get_current_rpc()

        # Initialize Solana RPC Client for z.ink
        from solana.rpc.api import Client
        self.client = Client(self.rpc_url)
        Logger.info(f"[SA] Connected to z.ink Mainnet (Chain ID: {self.ZINK_CHAIN_ID}) via {self.rpc_url.split('?')[0]}...")

    def _load_env_config(self):
        """Load Ironforge keys from .env or hardcoded fallbacks."""
        import os
        
        # Try to load .env manually if dotenv not installed (common in some envs)
        env_path = ".env"
        if os.path.exists(env_path):
             with open(env_path, 'r') as f:
                 for line in f:
                     if '=' in line and not line.startswith('#'):
                         key, value = line.strip().split('=', 1)
                         os.environ[key] = value

        key1 = os.environ.get("IRONFORGE_KEY_1", "01HZFJ18Q9E3QT62P67P52PC03")
        key2 = os.environ.get("IRONFORGE_KEY_2", "01J7E4JZYVW0KDWRVE1D19KTJS")
        
        self.IRONFORGE_RPC_POOL = [
            f"https://rpc.ironforge.network/mainnet?apiKey={key1}",
            f"https://rpc.ironforge.network/mainnet?apiKey={key2}"
        ]

    def _get_current_rpc(self) -> str:
        if not self.IRONFORGE_RPC_POOL:
             return "https://mainnet.z.ink" # Fallback
        return self.IRONFORGE_RPC_POOL[self.rpc_index % len(self.IRONFORGE_RPC_POOL)]

    def rotate_rpc(self):
        """Failover to next RPC in pool."""
        self.rpc_index += 1
        self.rpc_url = self._get_current_rpc()
        # Re-init client
        from solana.rpc.api import Client
        self.client = Client(self.rpc_url)
        Logger.warning(f"🔄 [Failover] Rotated RPC to: {self.rpc_url.split('?')[0]}...")

    def get_z_xp(self, wallet_address: str) -> float:
        """
        Fetch zXP (Experience Points) from z.ink API.
        Endpoint: https://api.z.ink/v1/profiles/{address}
        """
        url = f"https://api.z.ink/v1/profiles/{wallet_address}"
        try:
            Logger.info(f"[SA] Fetching zXP for {wallet_address[:8]}...")
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                xp = data.get('xp', 0)
                Logger.info(f"   ✨ Current zXP: {xp}")
                return float(xp)
            else:
                 Logger.warning(f"   [!] zXP Fetch Failed: {resp.status_code}")
                 return 0.0
        except Exception as e:
            Logger.error(f"   [X] zXP Error: {e}")
            return 0.0

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

    def get_market_prices_json(self) -> Dict[str, Any]:
        """
        Fetch market prices from the JSON endpoint (User Requested Sensor).
        """
        self._rate_limit()
        try:
            Logger.info(f"[SA] Fetching market prices from {self.market_prices_url}...")
            response = requests.get(self.market_prices_url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.Timeout:
            Logger.warning(f"[!] [StarAtlas] Price fetch timed out (RPC Lag detected)")
            return {}
        except requests.RequestException as e:
            Logger.error(f"[X] [StarAtlas] Price fetch failed: {e}")
            return {}

    def _make_request(self, query: str, variables: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Make GraphQL request to Star Atlas API.
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

        except requests.Timeout:
            Logger.warning(f"[!] [StarAtlas] Request timed out (RPC Lag detected)")
            return {}
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
        Get SDU (Survey Data Unit) marketplace prices via JSON Endpoint.
        """
        Logger.info(f"[SA] Querying SDU prices (Source: market/prices)")
        
        # Use simple JSON endpoint as Primary Sensor
        all_prices = self.get_market_prices_json()
        
        # Mocking the filter logic since we don't know exact JSON schema yet
        # We assume list of dicts with 'symbol' or 'asset'
        sdu_listings = []
        
        if isinstance(all_prices, list):
            for item in all_prices:
                # Flexible matching for SDU
                asset_name = item.get('symbol', '') or item.get('asset', '') or item.get('name', '')
                if 'SDU' in asset_name:
                    # Normalize to our listing structure
                    sdu_listings.append({
                        'id': item.get('id', 'unknown'),
                        'resourceType': 'SDU',
                        'quantity': item.get('quantity', 0),
                        'pricePerUnit': item.get('pricePerUnit', 0),
                        'totalPrice': item.get('totalPrice', 0),
                        'seller': item.get('seller', 'unknown'),
                        'starbase': {
                            'id': item.get('starbase', {}).get('id', 'unknown'),
                            'name': item.get('starbase', {}).get('name', 'unknown'),
                            'coordinates': item.get('starbase', {}).get('coordinates', 'unknown')
                        }
                    })
        
        return sdu_listings
    
    def get_sdu_prices(self) -> List[Dict[str, Any]]:
        """
        Fetch SDU prices.
        Note: Live /nfts endpoint returns metadata. Market data is on-chain or via refined endpoints.
        For simulation, we use the specific mock data generator.
        """
        # For now, default to mock data for the simulation loop as requested by user plan
        # until onsite parsing of the new galaxy.staratlas.com/nfts structure is robust.
        return self._generate_mock_sdu_data()

    def _generate_mock_sdu_data(self) -> List[Dict[str, Any]]:
        """
        Generate mock SDU data for Dry-Run/Simulation.
        Simulate typical z.ink conditions:
        - Wide Spreads (~22% due to liquidity shift)
        - Two Starbases (MUD Station vs ONI Sector)
        """
        import random
        base_price = 0.003

        # Starbase A (Cheap - High Supply)
        price_a = base_price + random.uniform(-0.0002, 0.0002)

        # Starbase B (Expensive - Low Liquidity)
        # User notes: Spreads are wide (22%)
        # Logic: 20-25% markup
        spread_modifier = random.uniform(1.20, 1.25)

        price_b = price_a * spread_modifier

        return [
            {
                'id': 'mock-sdu-sb1',
                'quantity': random.randint(10000, 50000),
                'pricePerUnit': price_a,
                'totalPrice': price_a * 100,
                'seller': 'MockSeller_A',
                'id': 'sb-1',
                'starbase': {'id': 'sb-1', 'name': 'MUD Station'}
            },
            {
                'id': 'mock-sdu-sb2',
                'quantity': random.randint(2000, 10000), # Lower liquidity
                'pricePerUnit': price_b,
                'totalPrice': price_b * 100,
                'seller': 'MockSeller_B',
                'id': 'sb-2',
                'starbase': {'id': 'sb-2', 'name': 'ONI Sector'}
            }
        ]

    def _get_sdu_prices_graphql(self, starbase_id, limit):
        # Original GQL implementation as fallback
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
            Logger.warning("[!] No SDU listings found (GraphQL)")
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

            # Get listings
            if resource == "SDU":
                listings = self.get_sdu_prices()
            else:
                # Use standard GQL for R4 for now, or implement JSON there too
                listings = self.get_resource_listings(resource, limit=50)

            # TODO: Compare prices across starbases
            # For now, just log that we're scanning

            time.sleep(self.rate_limit_ms / 1000.0)

        Logger.success(f"[OK] Scan complete. Found {len(opportunities)} opportunities")

        return opportunities
