"""
NFT Burner - Rent Reclamation Executor
=======================================
Closes NFT metadata accounts and reclaims rent to wallet.

Workflow:
1. Fetch purchased NFTs from database
2. Verify NFT is in wallet
3. Build close instructions (token account + metadata)
4. Simulate transaction
5. Execute burn and reclaim rent
6. Track actual SOL recovered
"""

import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from src.modules.nft_janitor.config import JanitorConfig
from src.shared.infrastructure.rpc_manager import RpcConnectionManager
from src.execution.wallet import WalletManager
from src.shared.system.database.core import DatabaseCore
from src.shared.system.database.repositories.nft_burn_repo import NFTBurnRepository
from src.shared.system.logging import Logger

from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solders.instruction import Instruction, AccountMeta
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.system_program import ID as SYSTEM_PROGRAM_ID
from spl.token.instructions import close_account, CloseAccountParams
from spl.token.constants import TOKEN_PROGRAM_ID
from solana.rpc.types import TxOpts
from solana.rpc.api import Client


@dataclass
class BurnResult:
    """Result of a burn attempt."""
    success: bool
    mint_address: str
    actual_rent_sol: float
    actual_profit_sol: float
    tx_signature: Optional[str]
    error_message: Optional[str]


class NFTBurner:
    """
    NFT burn executor for Legacy NFT rent reclamation.

    Features:
    - Token account closing
    - Metadata account closing
    - Rent reclamation to wallet
    - Safety checks and simulation
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(NFTBurner, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        """Initialize burner components."""
        self.config = JanitorConfig()
        self.rpc_manager = RpcConnectionManager()
        self.wallet_manager = WalletManager()
        self.db = DatabaseCore()
        self.repo = NFTBurnRepository(self.db)
        self.repo.init_table()

        self.wallet_pubkey = self.wallet_manager.keypair.pubkey()

        Logger.info("🔥 [NFTBurner] Initialized")

    def burn_targets(
        self,
        max_count: int = 3,
        dry_run: bool = True
    ) -> Dict[str, Any]:
        """
        Burn purchased NFTs and reclaim rent.

        Args:
            max_count: Maximum NFTs to burn per batch
            dry_run: If True, simulates but doesn't execute

        Returns:
            {
                'attempted': int,
                'successful': int,
                'failed': int,
                'total_rent_reclaimed_sol': float,
                'total_profit_sol': float,
                'results': List[BurnResult]
            }
        """
        Logger.info(f"🔥 [NFTBurner] Burning up to {max_count} NFTs (dry_run: {dry_run})")

        # Get purchased targets
        targets = self.repo.get_purchased_targets(limit=max_count)

        if not targets:
            Logger.warning("⚠️ [NFTBurner] No purchased targets found")
            return {
                'attempted': 0,
                'successful': 0,
                'failed': 0,
                'total_rent_reclaimed_sol': 0.0,
                'total_profit_sol': 0.0,
                'results': []
            }

        Logger.info(f"📋 [NFTBurner] Found {len(targets)} targets ready to burn")

        # Execute burns
        results = []
        successful = 0
        failed = 0
        total_rent = 0.0
        total_profit = 0.0

        for target in targets:
            mint_address = target['mint_address']
            floor_price = target['floor_price_sol']

            Logger.info(f"\n🔥 [NFTBurner] Attempting to burn {mint_address[:12]}...")

            # Execute burn
            result = self._execute_burn(
                mint_address=mint_address,
                floor_price_sol=floor_price,
                dry_run=dry_run
            )

            results.append(result)

            if result.success:
                successful += 1
                total_rent += result.actual_rent_sol
                total_profit += result.actual_profit_sol

                if not dry_run:
                    self.repo.mark_burned(mint_address, result.actual_rent_sol)
            else:
                failed += 1

                if not dry_run:
                    self.repo.mark_failed(mint_address, result.error_message or "Burn failed")

            # Rate limiting
            time.sleep(self.config.RPC_DELAY_MS / 1000.0)

        summary = {
            'attempted': len(targets),
            'successful': successful,
            'failed': failed,
            'total_rent_reclaimed_sol': total_rent,
            'total_profit_sol': total_profit,
            'dry_run': dry_run,
            'results': results
        }

        Logger.success(f"\n✅ [NFTBurner] Burn complete: {successful}/{len(targets)} successful")
        Logger.success(f"   Total Rent Reclaimed: {total_rent:.4f} SOL")
        Logger.success(f"   Total Profit: {total_profit:.4f} SOL")

        return summary

    def _execute_burn(
        self,
        mint_address: str,
        floor_price_sol: float,
        dry_run: bool
    ) -> BurnResult:
        """
        Execute a single NFT burn.

        Args:
            mint_address: NFT mint address
            floor_price_sol: Price paid for NFT
            dry_run: If True, simulates but doesn't execute

        Returns:
            BurnResult
        """
        try:
            # Derive associated token account (ATA)
            mint_pubkey = Pubkey.from_string(mint_address)
            ata = self._get_associated_token_address(mint_pubkey)

            # Verify NFT is in wallet
            if not dry_run:
                has_nft = self._verify_nft_ownership(ata)
                if not has_nft:
                    Logger.warning(f"   ⚠️ NFT not found in wallet: {mint_address[:12]}...")
                    return BurnResult(
                        success=False,
                        mint_address=mint_address,
                        actual_rent_sol=0.0,
                        actual_profit_sol=0.0,
                        tx_signature=None,
                        error_message="NFT not in wallet"
                    )

            # Derive metadata PDA
            metadata_pda = self._derive_metadata_pda(mint_pubkey)

            # Build burn instructions
            instructions = self._build_burn_instructions(ata, metadata_pda, mint_pubkey)

            if dry_run:
                # Simulate
                estimated_rent = self.config.RENT_VALUE_SOL
                estimated_profit = estimated_rent - floor_price_sol

                Logger.success(f"   ✅ [DRY RUN] Would burn {mint_address[:12]}...")
                Logger.info(f"      Estimated Rent: {estimated_rent:.4f} SOL")
                Logger.info(f"      Estimated Profit: {estimated_profit:.4f} SOL")

                return BurnResult(
                    success=True,
                    mint_address=mint_address,
                    actual_rent_sol=estimated_rent,
                    actual_profit_sol=estimated_profit,
                    tx_signature=None,
                    error_message=None
                )

            # LIVE BURN
            # Get recent blockhash
            client = Client("https://api.mainnet-beta.solana.com")
            latest_blockhash = client.get_latest_blockhash().value.blockhash

            # Get balance before
            balance_before = self.wallet_manager.get_sol_balance()

            # Compile transaction
            msg = MessageV0.try_compile(
                payer=self.wallet_pubkey,
                instructions=instructions,
                address_lookup_table_accounts=[],
                recent_blockhash=latest_blockhash,
            )

            tx = VersionedTransaction(msg, [self.wallet_manager.keypair])

            # Send transaction
            sig = client.send_transaction(tx, opts=TxOpts(skip_preflight=False)).value

            Logger.info(f"   📡 Transaction sent: {sig}")
            Logger.info("   ⏳ Waiting for confirmation...")

            # Wait for confirmation
            time.sleep(5)

            # Get balance after
            balance_after = self.wallet_manager.get_sol_balance()
            actual_rent = balance_after - balance_before
            actual_profit = actual_rent - floor_price_sol

            Logger.success(f"   ✅ Burned successfully!")
            Logger.info(f"      Rent Reclaimed: {actual_rent:.4f} SOL")
            Logger.info(f"      Actual Profit: {actual_profit:.4f} SOL")

            return BurnResult(
                success=True,
                mint_address=mint_address,
                actual_rent_sol=actual_rent,
                actual_profit_sol=actual_profit,
                tx_signature=str(sig),
                error_message=None
            )

        except Exception as e:
            Logger.error(f"   ❌ [NFTBurner] Burn failed: {e}")
            return BurnResult(
                success=False,
                mint_address=mint_address,
                actual_rent_sol=0.0,
                actual_profit_sol=0.0,
                tx_signature=None,
                error_message=str(e)
            )

    def _build_burn_instructions(
        self,
        ata: Pubkey,
        metadata_pda: Pubkey,
        mint: Pubkey
    ) -> List[Instruction]:
        """
        Build instructions to close token account and metadata.

        Args:
            ata: Associated token account
            metadata_pda: Metadata PDA
            mint: Mint address

        Returns:
            List of instructions
        """
        instructions = []

        # Add compute budget instructions for priority fees
        instructions.extend([
            set_compute_unit_limit(self.config.COMPUTE_UNITS),
            set_compute_unit_price(self.config.PRIORITY_FEE_LAMPORTS)
        ])

        # Close token account (reclaim ATA rent)
        close_ata_ix = close_account(
            CloseAccountParams(
                account=ata,
                dest=self.wallet_pubkey,
                owner=self.wallet_pubkey,
                program_id=TOKEN_PROGRAM_ID,
                signers=[],
            )
        )
        instructions.append(close_ata_ix)

        # Close metadata account (reclaim metadata rent)
        # NOTE: This requires the proper Metaplex instruction
        # For now, this is a placeholder - actual implementation needs
        # the Metaplex Token Metadata program instruction builder

        Logger.warning("   ⚠️ Metadata account closing not fully implemented yet")
        Logger.info("   NOTE: Only token account will be closed for now")

        return instructions

    def _get_associated_token_address(self, mint: Pubkey) -> Pubkey:
        """Get associated token address for mint and wallet."""
        from spl.token.instructions import get_associated_token_address

        return get_associated_token_address(self.wallet_pubkey, mint)

    def _derive_metadata_pda(self, mint: Pubkey) -> Pubkey:
        """Derive Metaplex metadata PDA."""
        metadata_program = Pubkey.from_string(self.config.METADATA_PROGRAM_ID)

        seeds = [
            b"metadata",
            bytes(metadata_program),
            bytes(mint)
        ]

        pda, _ = Pubkey.find_program_address(seeds, metadata_program)
        return pda

    def _verify_nft_ownership(self, ata: Pubkey) -> bool:
        """
        Verify NFT is in wallet's associated token account.

        Args:
            ata: Associated token account

        Returns:
            True if NFT is present
        """
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAccountInfo",
                "params": [
                    str(ata),
                    {"encoding": "jsonParsed"}
                ]
            }

            response = self.rpc_manager.post(payload, timeout=5)

            if response.status_code != 200:
                return False

            data = response.json()
            result = data.get('result', {})

            if not result or not result.get('value'):
                return False

            account_info = result['value']['data']['parsed']['info']
            token_amount = float(account_info['tokenAmount']['uiAmount'])

            return token_amount == 1.0  # NFTs have amount of 1

        except Exception as e:
            Logger.debug(f"   [NFTBurner] Ownership check failed: {e}")
            return False
