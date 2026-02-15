"""
NFT Burn Repository
===================
Manages NFT burn targets for Legacy NFT rent reclamation.

Schema Workflow: DISCOVERED → PURCHASED → BURNED
Risk Scoring: SAFE / RISKY / BLOCKED
"""

import time
from typing import List, Optional, Dict, Any
from src.shared.system.database.repositories.base import BaseRepository
from src.shared.system.logging import Logger


class NFTBurnRepository(BaseRepository):
    """
    Repository for NFT burn target tracking and reclamation workflow.

    Schema includes safety fields:
    - is_burnable: Pre-flight metadata check result
    - risk_score: SAFE/RISKY/BLOCKED based on metadata characteristics
    - status: DISCOVERED/PURCHASED/BURNED/FAILED/SKIPPED
    - attempts: Track retry count to prevent infinite loops
    """

    def init_table(self):
        """Initialize nft_burn_targets table with comprehensive schema."""
        with self.db.cursor(commit=True) as c:
            c.execute("""
            CREATE TABLE IF NOT EXISTS nft_burn_targets (
                mint_address TEXT PRIMARY KEY,
                collection_name TEXT,
                collection_slug TEXT,
                floor_price_sol REAL NOT NULL,
                estimated_rent_sol REAL NOT NULL,
                estimated_profit_sol REAL NOT NULL,
                is_burnable BOOLEAN DEFAULT 0,
                is_mutable BOOLEAN DEFAULT 0,
                metadata_authority TEXT,
                freeze_authority TEXT,
                status TEXT CHECK(status IN ('DISCOVERED', 'PURCHASED', 'BURNED', 'FAILED', 'SKIPPED')) DEFAULT 'DISCOVERED',
                risk_score TEXT CHECK(risk_score IN ('SAFE', 'RISKY', 'BLOCKED')) DEFAULT 'SAFE',
                discovered_at REAL NOT NULL,
                purchased_at REAL,
                burned_at REAL,
                actual_profit_sol REAL,
                actual_rent_sol REAL,
                attempts INTEGER DEFAULT 0,
                last_attempt_at REAL,
                error_message TEXT,
                metadata TEXT,
                created_at REAL DEFAULT (strftime('%s', 'now'))
            )
            """)

            # Indexes for efficient querying
            c.execute("""
            CREATE INDEX IF NOT EXISTS idx_nft_burn_status
            ON nft_burn_targets(status, risk_score)
            """)

            c.execute("""
            CREATE INDEX IF NOT EXISTS idx_nft_burn_profit
            ON nft_burn_targets(estimated_profit_sol DESC)
            """)

            Logger.info("📦 [NFTBurnRepo] Table initialized")

    def add_target(
        self,
        mint_address: str,
        collection_name: str,
        collection_slug: str,
        floor_price_sol: float,
        estimated_rent_sol: float,
        estimated_profit_sol: float,
        is_burnable: bool = False,
        is_mutable: bool = False,
        metadata_authority: Optional[str] = None,
        freeze_authority: Optional[str] = None,
        risk_score: str = 'SAFE',
        metadata: Optional[str] = None
    ) -> None:
        """
        Add an NFT burn target.

        Args:
            mint_address: Solana mint address
            collection_name: Collection name
            collection_slug: Collection slug (for tracking)
            floor_price_sol: Current floor price
            estimated_rent_sol: Expected rent recovery
            estimated_profit_sol: Expected profit after fees
            is_burnable: Whether metadata is burnable
            is_mutable: Whether metadata is mutable
            metadata_authority: Update authority address
            freeze_authority: Freeze authority (if any)
            risk_score: SAFE/RISKY/BLOCKED
            metadata: JSON-serialized additional data

        Note:
            Uses INSERT OR REPLACE for idempotency (re-scans update data)
        """
        with self.db.cursor(commit=True) as c:
            c.execute("""
            INSERT OR REPLACE INTO nft_burn_targets (
                mint_address, collection_name, collection_slug,
                floor_price_sol, estimated_rent_sol, estimated_profit_sol,
                is_burnable, is_mutable, metadata_authority, freeze_authority,
                risk_score, discovered_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                mint_address,
                collection_name,
                collection_slug,
                floor_price_sol,
                estimated_rent_sol,
                estimated_profit_sol,
                is_burnable,
                is_mutable,
                metadata_authority,
                freeze_authority,
                risk_score,
                time.time(),
                metadata
            ))

    def get_pending_targets(
        self,
        limit: int = 10,
        max_attempts: int = 3,
        min_profit_sol: float = 0.002
    ) -> List[Dict[str, Any]]:
        """
        Fetch NFT targets ready for purchase.

        Args:
            limit: Maximum records to return
            max_attempts: Skip targets with >= this many failures
            min_profit_sol: Minimum profit threshold

        Returns:
            List of target dictionaries with all fields

        Safety:
            Only returns DISCOVERED status with is_burnable=1 and attempts < max_attempts
        """
        query = """
        SELECT * FROM nft_burn_targets
        WHERE status = 'DISCOVERED'
          AND is_burnable = 1
          AND risk_score IN ('SAFE', 'RISKY')
          AND attempts < ?
          AND estimated_profit_sol >= ?
        ORDER BY estimated_profit_sol DESC
        LIMIT ?
        """

        return self._fetchall(query, (max_attempts, min_profit_sol, limit))

    def get_purchased_targets(
        self,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Fetch NFTs that have been purchased and are ready to burn.

        Returns:
            List of purchased NFT targets
        """
        query = """
        SELECT * FROM nft_burn_targets
        WHERE status = 'PURCHASED'
        ORDER BY purchased_at ASC
        LIMIT ?
        """

        return self._fetchall(query, (limit,))

    def mark_purchased(self, mint_address: str, actual_price_sol: float) -> None:
        """
        Mark target as PURCHASED after successful purchase.

        Args:
            mint_address: NFT mint address
            actual_price_sol: Actual purchase price (may differ from floor)
        """
        with self.db.cursor(commit=True) as c:
            c.execute("""
            UPDATE nft_burn_targets
            SET status = 'PURCHASED',
                purchased_at = ?,
                metadata = json_set(COALESCE(metadata, '{}'), '$.actual_price_sol', ?)
            WHERE mint_address = ?
            """, (time.time(), actual_price_sol, mint_address))

        Logger.success(f"✅ [NFTBurnRepo] Purchased {mint_address[:8]}... for {actual_price_sol:.4f} SOL")

    def mark_burned(self, mint_address: str, actual_rent_sol: float) -> None:
        """
        Mark target as BURNED after successful rent reclamation.

        Args:
            mint_address: NFT that was burned
            actual_rent_sol: Actual SOL recovered (for accuracy tracking)
        """
        with self.db.cursor(commit=True) as c:
            # Calculate actual profit
            c.execute("""
            SELECT floor_price_sol, metadata
            FROM nft_burn_targets
            WHERE mint_address = ?
            """, (mint_address,))

            row = c.fetchone()
            if row:
                floor_price = row[0]
                actual_profit = actual_rent_sol - floor_price

                c.execute("""
                UPDATE nft_burn_targets
                SET status = 'BURNED',
                    burned_at = ?,
                    actual_rent_sol = ?,
                    actual_profit_sol = ?
                WHERE mint_address = ?
                """, (time.time(), actual_rent_sol, actual_profit, mint_address))

                Logger.success(f"🔥 [NFTBurnRepo] Burned {mint_address[:8]}... "
                             f"(Recovered: {actual_rent_sol:.4f} SOL, Profit: {actual_profit:.4f} SOL)")

    def mark_failed(self, mint_address: str, error_message: str) -> None:
        """
        Record failed operation.

        Args:
            mint_address: NFT that failed
            error_message: Error description for debugging

        Increments attempts counter. After max_attempts, target won't
        be returned by get_pending_targets() until manual reset.
        """
        with self.db.cursor(commit=True) as c:
            c.execute("""
            UPDATE nft_burn_targets
            SET attempts = attempts + 1,
                last_attempt_at = ?,
                error_message = ?
            WHERE mint_address = ?
            """, (time.time(), error_message, mint_address))

            # Check if we've hit max attempts
            c.execute("SELECT attempts FROM nft_burn_targets WHERE mint_address = ?", (mint_address,))
            row = c.fetchone()
            if row and row[0] >= 3:
                c.execute("UPDATE nft_burn_targets SET status = 'FAILED' WHERE mint_address = ?", (mint_address,))
                Logger.warning(f"⚠️ [NFTBurnRepo] {mint_address[:8]}... reached max attempts, marked as FAILED")

    def mark_skipped(self, mint_address: str, reason: str) -> None:
        """
        Mark target as SKIPPED (e.g., metadata not burnable, freeze authority set).

        Args:
            mint_address: NFT to skip
            reason: Human-readable skip reason
        """
        self._execute("""
        UPDATE nft_burn_targets
        SET status = 'SKIPPED', risk_score = 'BLOCKED', error_message = ?
        WHERE mint_address = ?
        """, (reason, mint_address), commit=True)

        Logger.debug(f"🚫 [NFTBurnRepo] Skipped {mint_address[:8]}... ({reason})")

    def get_statistics(self) -> Dict[str, Any]:
        """
        Return aggregate statistics for monitoring/dashboard.

        Returns:
            {
                'total_targets': int,
                'discovered': int,
                'purchased': int,
                'burned': int,
                'failed': int,
                'skipped': int,
                'total_estimated_profit_sol': float,
                'total_actual_profit_sol': float,
                'success_rate': float (percentage)
            }
        """
        with self.db.cursor() as c:
            # Status counts
            c.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'DISCOVERED' THEN 1 ELSE 0 END) as discovered,
                SUM(CASE WHEN status = 'PURCHASED' THEN 1 ELSE 0 END) as purchased,
                SUM(CASE WHEN status = 'BURNED' THEN 1 ELSE 0 END) as burned,
                SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'SKIPPED' THEN 1 ELSE 0 END) as skipped,
                SUM(estimated_profit_sol) as total_estimated_profit,
                SUM(actual_profit_sol) as total_actual_profit
            FROM nft_burn_targets
            """)

            row = c.fetchone()

            total = row['total'] or 0
            burned = row['burned'] or 0
            success_rate = (burned / total * 100) if total > 0 else 0.0

            return {
                'total_targets': total,
                'discovered': row['discovered'] or 0,
                'purchased': row['purchased'] or 0,
                'burned': burned,
                'failed': row['failed'] or 0,
                'skipped': row['skipped'] or 0,
                'total_estimated_profit_sol': row['total_estimated_profit'] or 0.0,
                'total_actual_profit_sol': row['total_actual_profit'] or 0.0,
                'success_rate': success_rate
            }

    def get_target_by_mint(self, mint_address: str) -> Optional[Dict[str, Any]]:
        """Fetch a specific target by mint address."""
        return self._fetchone(
            "SELECT * FROM nft_burn_targets WHERE mint_address = ?",
            (mint_address,)
        )

    def get_top_opportunities(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Fetch top NFT opportunities by profit potential.

        Returns:
            List of highest-profit NFT targets
        """
        return self._fetchall("""
        SELECT * FROM nft_burn_targets
        WHERE status = 'DISCOVERED'
          AND is_burnable = 1
          AND risk_score != 'BLOCKED'
        ORDER BY estimated_profit_sol DESC
        LIMIT ?
        """, (limit,))

    def reset_failed_attempts(self, mint_address: str) -> None:
        """
        Reset attempts counter for manual retry.

        Use this after investigating and fixing the root cause of failures.
        """
        self._execute("""
        UPDATE nft_burn_targets
        SET attempts = 0, error_message = NULL, status = 'DISCOVERED'
        WHERE mint_address = ?
        """, (mint_address,), commit=True)

        Logger.info(f"🔄 [NFTBurnRepo] Reset attempts for {mint_address[:8]}...")
