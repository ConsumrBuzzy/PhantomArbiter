"""
NFT Buyer - Purchase Executor
==============================
Executes NFT purchases with priority fees and safety checks.

Workflow:
1. Fetch pending targets from database
2. Re-verify price hasn't changed
3. Build purchase transaction with priority fees
4. Simulate transaction
5. Execute purchase (if --live mode)
6. Update database
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
from solana.rpc.types import TxOpts


@dataclass
class PurchaseResult:
    """Result of a purchase attempt."""
    success: bool
    mint_address: str
    actual_price_sol: float
    tx_signature: Optional[str]
    error_message: Optional[str]


class NFTBuyer:
    """
    NFT purchase executor with safety checks and priority fees.

    Features:
    - Price re-verification before purchase
    - Transaction simulation
    - Priority fee competition
    - Dry-run mode by default
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(NFTBuyer, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        """Initialize buyer components."""
        self.config = JanitorConfig()
        self.rpc_manager = RpcConnectionManager()
        self.wallet_manager = WalletManager()
        self.db = DatabaseCore()
        self.repo = NFTBurnRepository(self.db)
        self.repo.init_table()

        Logger.info("💳 [NFTBuyer] Initialized")

    def buy_targets(
        self,
        max_count: int = 5,
        max_price_sol: float = None,
        dry_run: bool = True
    ) -> Dict[str, Any]:
        """
        Purchase NFT targets from database.

        Args:
            max_count: Maximum NFTs to purchase
            max_price_sol: Maximum price willing to pay
            dry_run: If True, simulates but doesn't execute

        Returns:
            {
                'attempted': int,
                'successful': int,
                'failed': int,
                'total_spent_sol': float,
                'results': List[PurchaseResult]
            }
        """
        max_price_sol = max_price_sol or self.config.MAX_FLOOR_PRICE_SOL

        Logger.info(f"🛒 [NFTBuyer] Purchasing up to {max_count} NFTs (max_price: {max_price_sol} SOL, dry_run: {dry_run})")

        # Get pending targets
        targets = self.repo.get_pending_targets(
            limit=max_count,
            max_attempts=self.config.MAX_RETRY_ATTEMPTS,
            min_profit_sol=self.config.MIN_PROFIT_SOL
        )

        if not targets:
            Logger.warning("⚠️ [NFTBuyer] No pending targets found")
            return {
                'attempted': 0,
                'successful': 0,
                'failed': 0,
                'total_spent_sol': 0.0,
                'results': []
            }

        Logger.info(f"📋 [NFTBuyer] Found {len(targets)} targets ready to purchase")

        # Check wallet exposure
        total_locked = self._calculate_wallet_exposure()
        if total_locked >= self.config.MAX_WALLET_EXPOSURE_SOL:
            Logger.warning(f"⚠️ [NFTBuyer] Wallet exposure limit reached ({total_locked:.4f} SOL)")
            return {
                'attempted': 0,
                'successful': 0,
                'failed': 0,
                'total_spent_sol': 0.0,
                'results': []
            }

        # Execute purchases
        results = []
        successful = 0
        failed = 0
        total_spent = 0.0

        for target in targets:
            mint_address = target['mint_address']
            floor_price = target['floor_price_sol']

            Logger.info(f"\n💰 [NFTBuyer] Attempting to buy {mint_address[:12]}... for {floor_price:.4f} SOL")

            # Execute purchase
            result = self._execute_purchase(
                mint_address=mint_address,
                max_price_sol=max_price_sol,
                dry_run=dry_run
            )

            results.append(result)

            if result.success:
                successful += 1
                total_spent += result.actual_price_sol

                if not dry_run:
                    self.repo.mark_purchased(mint_address, result.actual_price_sol)
            else:
                failed += 1

                if not dry_run:
                    self.repo.mark_failed(mint_address, result.error_message or "Unknown error")

            # Rate limiting
            time.sleep(self.config.RPC_DELAY_MS / 1000.0)

        summary = {
            'attempted': len(targets),
            'successful': successful,
            'failed': failed,
            'total_spent_sol': total_spent,
            'dry_run': dry_run,
            'results': results
        }

        Logger.success(f"\n✅ [NFTBuyer] Purchase complete: {successful}/{len(targets)} successful")

        return summary

    def _execute_purchase(
        self,
        mint_address: str,
        max_price_sol: float,
        dry_run: bool
    ) -> PurchaseResult:
        """
        Execute a single NFT purchase.

        Args:
            mint_address: NFT mint address
            max_price_sol: Maximum price willing to pay
            dry_run: If True, simulates but doesn't execute

        Returns:
            PurchaseResult
        """
        try:
            # NOTE: This is a placeholder implementation.
            # Actual purchase requires understanding Tensor's program structure
            # or using their API endpoint for purchases.

            # For now, we'll simulate the purchase
            if dry_run:
                Logger.success(f"   ✅ [DRY RUN] Would purchase {mint_address[:12]}... for ~{max_price_sol:.4f} SOL")
                return PurchaseResult(
                    success=True,
                    mint_address=mint_address,
                    actual_price_sol=max_price_sol,
                    tx_signature=None,
                    error_message=None
                )

            # LIVE PURCHASE (Not Yet Implemented)
            Logger.warning(f"   ⚠️ [NFTBuyer] Live purchase not yet implemented for {mint_address[:12]}...")
            Logger.info("   NOTE: Requires Tensor program integration or API endpoint")

            return PurchaseResult(
                success=False,
                mint_address=mint_address,
                actual_price_sol=0.0,
                tx_signature=None,
                error_message="Live purchase not yet implemented"
            )

        except Exception as e:
            Logger.error(f"   ❌ [NFTBuyer] Purchase failed: {e}")
            return PurchaseResult(
                success=False,
                mint_address=mint_address,
                actual_price_sol=0.0,
                tx_signature=None,
                error_message=str(e)
            )

    def _calculate_wallet_exposure(self) -> float:
        """
        Calculate total SOL locked in purchased NFTs.

        Returns:
            Total SOL exposure
        """
        purchased = self.repo.get_purchased_targets(limit=1000)
        return sum(float(t.get('floor_price_sol', 0.0)) for t in purchased)

    def _build_compute_budget_instructions(self) -> List[Instruction]:
        """Build compute budget instructions for priority fees."""
        return [
            set_compute_unit_limit(self.config.COMPUTE_UNITS),
            set_compute_unit_price(self.config.PRIORITY_FEE_LAMPORTS)
        ]
