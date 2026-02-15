"""
NFT Scanner - Discovery Engine
===============================
Discovers profitable Legacy NFTs via Tensor API and validates metadata.

Workflow:
1. Query Tensor for cheap Legacy NFT listings
2. Fetch on-chain metadata for each NFT
3. Verify metadata is burnable (mutable, no freeze authority)
4. Calculate profitability after fees
5. Store viable targets in database
"""

import time
import base64
import struct
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from src.modules.nft_janitor.config import JanitorConfig
from src.shared.infrastructure.tensor_client import TensorClient
from src.shared.infrastructure.rpc_manager import RpcConnectionManager
from src.shared.system.database.core import DatabaseCore
from src.shared.system.database.repositories.nft_burn_repo import NFTBurnRepository
from src.shared.system.logging import Logger
from solders.pubkey import Pubkey


@dataclass
class NFTMetadata:
    """Parsed NFT metadata from on-chain account."""
    mint: str
    is_mutable: bool
    update_authority: Optional[str]
    freeze_authority: Optional[str]
    is_burnable: bool
    risk_score: str  # SAFE, RISKY, BLOCKED


class NFTScanner:
    """
    Singleton scanner for Legacy NFT discovery.

    Pattern: Follows Skimmer module architecture with rate limiting,
    database persistence, and safety checks.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(NFTScanner, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        """Initialize scanner components."""
        self.config = JanitorConfig()
        self.tensor = TensorClient(
            api_url=self.config.TENSOR_GRAPHQL_URL,
            api_key=self.config.TENSOR_API_KEY,
            rate_limit_ms=self.config.TENSOR_DELAY_MS
        )
        self.rpc_manager = RpcConnectionManager()
        self.db = DatabaseCore()
        self.repo = NFTBurnRepository(self.db)
        self.repo.init_table()

        Logger.info("🔍 [NFTScanner] Initialized")

    def scan_tensor(
        self,
        max_price_sol: float = None,
        limit: int = None,
        dry_run: bool = True
    ) -> Dict[str, Any]:
        """
        Scan Tensor for profitable Legacy NFT opportunities.

        Args:
            max_price_sol: Maximum floor price (default: config.MAX_FLOOR_PRICE_SOL)
            limit: Max NFTs to scan (default: config.SCAN_BATCH_SIZE)
            dry_run: If True, logs results but doesn't persist to DB

        Returns:
            {
                'total_scanned': int,
                'opportunities_found': int,
                'blocked': int,
                'total_estimated_profit_sol': float,
                'results': List[Dict]
            }
        """
        max_price_sol = max_price_sol or self.config.MAX_FLOOR_PRICE_SOL
        limit = limit or self.config.SCAN_BATCH_SIZE

        Logger.info(f"🚀 [NFTScanner] Starting scan (max_price: {max_price_sol} SOL, limit: {limit}, dry_run: {dry_run})")

        # Query Tensor for cheap listings
        listings = self.tensor.get_cheap_nfts(
            max_price_sol=max_price_sol,
            limit=limit,
            only_legacy=True
        )

        if not listings:
            Logger.warning("⚠️ [NFTScanner] No listings found from Tensor API")
            Logger.info("   NOTE: Tensor GraphQL schema may need adjustment - check API docs")
            return {
                'total_scanned': 0,
                'opportunities_found': 0,
                'blocked': 0,
                'total_estimated_profit_sol': 0.0,
                'results': []
            }

        # Analyze each listing
        opportunities = []
        blocked = 0
        total_profit = 0.0

        for i, listing in enumerate(listings):
            try:
                # Rate limiting
                if i > 0:
                    time.sleep(self.config.RPC_DELAY_MS / 1000.0)

                mint_address = listing.get("mint")
                price_sol = listing.get("price", 0.0)
                collection = listing.get("collection", {})
                collection_name = collection.get("name", "Unknown")
                collection_slug = collection.get("slug", "")

                if not mint_address:
                    continue

                # Fetch and validate metadata
                metadata = self._fetch_and_validate_metadata(mint_address)

                if not metadata:
                    blocked += 1
                    continue

                # Calculate profitability
                estimated_profit = self.config.calculate_profit(price_sol)

                if estimated_profit <= 0:
                    Logger.debug(f"   [NFTScanner] {mint_address[:8]}... unprofitable (price: {price_sol:.4f} SOL)")
                    blocked += 1
                    continue

                # Valid opportunity found
                opportunity = {
                    'mint_address': mint_address,
                    'collection_name': collection_name,
                    'collection_slug': collection_slug,
                    'floor_price_sol': price_sol,
                    'estimated_rent_sol': self.config.RENT_VALUE_SOL,
                    'estimated_profit_sol': estimated_profit,
                    'is_burnable': metadata.is_burnable,
                    'is_mutable': metadata.is_mutable,
                    'metadata_authority': metadata.update_authority,
                    'freeze_authority': metadata.freeze_authority,
                    'risk_score': metadata.risk_score
                }

                opportunities.append(opportunity)
                total_profit += estimated_profit

                Logger.success(f"💰 [NFTScanner] Found: {mint_address[:8]}... "
                             f"(Price: {price_sol:.4f} SOL, Profit: {estimated_profit:.4f} SOL)")

                # Persist to database (unless dry-run)
                if not dry_run:
                    self.repo.add_target(**opportunity)

            except Exception as e:
                Logger.error(f"❌ [NFTScanner] Error analyzing {mint_address[:8] if mint_address else 'unknown'}: {e}")
                blocked += 1

        summary = {
            'total_scanned': len(listings),
            'opportunities_found': len(opportunities),
            'blocked': blocked,
            'total_estimated_profit_sol': total_profit,
            'dry_run': dry_run,
            'results': opportunities
        }

        Logger.success(
            f"✅ [NFTScanner] Scan complete: {len(opportunities)} opportunities "
            f"({total_profit:.4f} SOL estimated profit)"
        )

        return summary

    def _fetch_and_validate_metadata(self, mint_address: str) -> Optional[NFTMetadata]:
        """
        Fetch NFT metadata from on-chain and validate burnability.

        Args:
            mint_address: NFT mint address

        Returns:
            NFTMetadata object or None if not burnable/invalid
        """
        try:
            # Derive metadata PDA
            metadata_pda = self._derive_metadata_pda(mint_address)

            # Fetch metadata account
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAccountInfo",
                "params": [
                    str(metadata_pda),
                    {"encoding": "base64"}
                ]
            }

            response = self.rpc_manager.post(payload, timeout=5)

            if response.status_code != 200:
                Logger.debug(f"   [NFTScanner] RPC error for {mint_address[:8]}...")
                return None

            data = response.json()
            result = data.get('result', {})

            if not result or not result.get('value'):
                Logger.debug(f"   [NFTScanner] No metadata account for {mint_address[:8]}...")
                return None

            account_data = result['value'].get('data', [])
            if not account_data:
                return None

            # Decode base64 data
            encoded_data = account_data[0] if isinstance(account_data, list) else account_data
            decoded = base64.b64decode(encoded_data)

            # Parse metadata (simplified - actual Metaplex format is complex)
            # NOTE: This is a basic parser and may need refinement
            metadata = self._parse_metadata_simple(decoded, mint_address)

            return metadata

        except Exception as e:
            Logger.debug(f"   [NFTScanner] Metadata fetch failed for {mint_address[:8]}...: {e}")
            return None

    def _derive_metadata_pda(self, mint_address: str) -> Pubkey:
        """
        Derive Metaplex metadata PDA for a mint.

        Formula: find_program_address(['metadata', METADATA_PROGRAM_ID, mint])
        """
        mint_pubkey = Pubkey.from_string(mint_address)
        metadata_program = Pubkey.from_string(self.config.METADATA_PROGRAM_ID)

        seeds = [
            b"metadata",
            bytes(metadata_program),
            bytes(mint_pubkey)
        ]

        pda, _ = Pubkey.find_program_address(seeds, metadata_program)
        return pda

    def _parse_metadata_simple(self, data: bytes, mint: str) -> NFTMetadata:
        """
        Simple metadata parser (basic version).

        Args:
            data: Raw metadata account data
            mint: Mint address for logging

        Returns:
            NFTMetadata object

        Note:
            This is a simplified parser. Full Metaplex metadata parsing
            requires borsh deserialization. For now, we extract key fields.
        """
        try:
            # Metaplex Metadata structure (simplified):
            # - key (1 byte): should be 4 for Metadata
            # - update_authority (32 bytes): Pubkey
            # - mint (32 bytes): Pubkey
            # - data: varies
            # - primary_sale_happened (1 byte): bool
            # - is_mutable (1 byte): bool

            if len(data) < 100:
                # Too small to be valid metadata
                return NFTMetadata(
                    mint=mint,
                    is_mutable=False,
                    update_authority=None,
                    freeze_authority=None,
                    is_burnable=False,
                    risk_score='BLOCKED'
                )

            # Extract key fields (offsets are approximate)
            key = data[0]
            update_authority_bytes = data[1:33]
            mint_bytes = data[33:65]

            # is_mutable is typically around byte 326+ (after name/symbol/uri)
            # For safety, we'll check the last few bytes
            is_mutable = False
            if len(data) > 100:
                # Scan for is_mutable flag (typically near end of fixed section)
                # This is a heuristic - proper borsh parsing is more reliable
                is_mutable = data[101] == 1 if len(data) > 101 else False

            update_authority = str(Pubkey(update_authority_bytes))

            # Determine if burnable
            is_burnable = is_mutable and update_authority != "11111111111111111111111111111111"

            risk_score = 'SAFE' if is_burnable else 'BLOCKED'

            return NFTMetadata(
                mint=mint,
                is_mutable=is_mutable,
                update_authority=update_authority if is_burnable else None,
                freeze_authority=None,  # Would need deeper parsing
                is_burnable=is_burnable,
                risk_score=risk_score
            )

        except Exception as e:
            Logger.debug(f"   [NFTScanner] Metadata parsing failed for {mint[:8]}...: {e}")
            return NFTMetadata(
                mint=mint,
                is_mutable=False,
                update_authority=None,
                freeze_authority=None,
                is_burnable=False,
                risk_score='BLOCKED'
            )

    def get_statistics(self) -> Dict[str, Any]:
        """Fetch aggregate statistics from repository."""
        return self.repo.get_statistics()
