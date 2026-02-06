"""
Zombie Account Repository
==========================
Manages zombie account targets for rent reclamation.

ADR-005 Compliance:
- Stores scan results from SkimmerCore
- Tracks status workflow: PENDING → VERIFIED → CLOSED
- Records failures for retry/audit purposes
"""

import time
from typing import List, Optional, Dict, Any
from src.shared.system.database.repositories.base import BaseRepository
from src.shared.system.logging import Logger


class ZombieRepository(BaseRepository):
    """
    Repository for zombie account tracking and reclamation workflow.
    
    Schema includes safety fields:
    - last_transaction_time: Detect recent activity (False Positive guard)
    - attempts: Track retry count to prevent infinite loops
    - risk_score: LOW/MEDIUM/HIGH based on account characteristics
    """

    def init_table(self):
        """Initialize zombie_targets table with comprehensive schema."""
        with self.db.cursor(commit=True) as c:
            c.execute("""
            CREATE TABLE IF NOT EXISTS zombie_targets (
                address TEXT PRIMARY KEY,
                scanned_at REAL NOT NULL,
                total_transactions INTEGER DEFAULT 0,
                success_rate REAL DEFAULT 0.0,
                estimated_yield_sol REAL NOT NULL,
                risk_score TEXT CHECK(risk_score IN ('LOW', 'MEDIUM', 'HIGH')) DEFAULT 'MEDIUM',
                status TEXT CHECK(status IN ('PENDING', 'VERIFIED', 'CLOSED', 'SKIPPED')) DEFAULT 'PENDING',
                attempts INTEGER DEFAULT 0,
                last_attempt_at REAL,
                last_transaction_time REAL,
                error_message TEXT,
                metadata TEXT,
                created_at REAL DEFAULT (strftime('%s', 'now'))
            )
            """)
            
            # Index for efficient querying
            c.execute("""
            CREATE INDEX IF NOT EXISTS idx_zombie_status 
            ON zombie_targets(status, risk_score)
            """)
            
            Logger.info("📦 [ZombieRepo] Table initialized")

    def add_target(
        self, 
        address: str, 
        estimated_yield_sol: float,
        risk_score: str = 'MEDIUM',
        total_transactions: int = 0,
        success_rate: float = 0.0,
        last_transaction_time: Optional[float] = None,
        metadata: Optional[str] = None
    ) -> None:
        """
        Add a zombie account target.
        
        Args:
            address: Solana account address
            estimated_yield_sol: Expected SOL recovery after fees
            risk_score: LOW/MEDIUM/HIGH (based on activity patterns)
            total_transactions: Historical transaction count
            success_rate: Historical success rate (0-100)
            last_transaction_time: Unix timestamp of last activity
            metadata: JSON-serialized additional data
        
        Note:
            Uses INSERT OR REPLACE for idempotency (re-scans update data)
        """
        with self.db.cursor(commit=True) as c:
            c.execute("""
            INSERT OR REPLACE INTO zombie_targets (
                address, scanned_at, total_transactions, success_rate,
                estimated_yield_sol, risk_score, last_transaction_time, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                address,
                time.time(),
                total_transactions,
                success_rate,
                estimated_yield_sol,
                risk_score,
                last_transaction_time,
                metadata
            ))

    def get_pending_targets(
        self, 
        limit: int = 10,
        max_attempts: int = 3,
        min_yield_sol: float = 0.001
    ) -> List[Dict[str, Any]]:
        """
        Fetch zombie targets ready for closure.
        
        Args:
            limit: Maximum records to return
            max_attempts: Skip targets with >= this many failures
            min_yield_sol: Minimum yield threshold (dust filter)
        
        Returns:
            List of target dictionaries with all fields
        
        Safety:
            Only returns PENDING/VERIFIED status with attempts < max_attempts
        """
        query = """
        SELECT * FROM zombie_targets
        WHERE status IN ('PENDING', 'VERIFIED')
          AND attempts < ?
          AND estimated_yield_sol >= ?
        ORDER BY estimated_yield_sol DESC
        LIMIT ?
        """
        
        return self._fetchall(query, (max_attempts, min_yield_sol, limit))

    def mark_verified(self, address: str) -> None:
        """
        Mark target as VERIFIED (passed all safety checks).
        
        This is an intermediate status before closure execution.
        """
        self._execute(
            "UPDATE zombie_targets SET status = 'VERIFIED' WHERE address = ?",
            (address,),
            commit=True
        )

    def mark_closed(self, address: str, actual_yield_sol: float) -> None:
        """
        Mark target as CLOSED after successful rent reclamation.
        
        Args:
            address: Account that was closed
            actual_yield_sol: Actual SOL recovered (for accuracy tracking)
        """
        with self.db.cursor(commit=True) as c:
            c.execute("""
            UPDATE zombie_targets 
            SET status = 'CLOSED',
                last_attempt_at = ?,
                metadata = json_set(COALESCE(metadata, '{}'), '$.actual_yield_sol', ?)
            WHERE address = ?
            """, (time.time(), actual_yield_sol, address))
        
        Logger.success(f"✅ [ZombieRepo] Closed {address[:8]}... ({actual_yield_sol:.4f} SOL)")

    def mark_failed(self, address: str, error_message: str) -> None:
        """
        Record failed closure attempt.
        
        Args:
            address: Account that failed to close
            error_message: Error description for debugging
        
        Increments attempts counter. After max_attempts, target won't
        be returned by get_pending_targets() until manual reset.
        """
        with self.db.cursor(commit=True) as c:
            c.execute("""
            UPDATE zombie_targets 
            SET attempts = attempts + 1,
                last_attempt_at = ?,
                error_message = ?
            WHERE address = ?
            """, (time.time(), error_message, address))
        
            # Check if we've hit max attempts
            c.execute("SELECT attempts FROM zombie_targets WHERE address = ?", (address,))
            row = c.fetchone()
            if row and row[0] >= 3:
                Logger.warning(f"⚠️ [ZombieRepo] {address[:8]}... reached max attempts, skipping")

    def mark_skipped(self, address: str, reason: str) -> None:
        """
        Mark target as SKIPPED (e.g., LP position detected, recent activity).
        
        Args:
            address: Account to skip
            reason: Human-readable skip reason
        """
        self._execute("""
        UPDATE zombie_targets 
        SET status = 'SKIPPED', error_message = ?
        WHERE address = ?
        """, (reason, address), commit=True)
        
        Logger.debug(f"🚫 [ZombieRepo] Skipped {address[:8]}... ({reason})")

    def get_scan_statistics(self) -> Dict[str, Any]:
        """
        Return aggregate statistics for monitoring/dashboard.
        
        Returns:
            {
                'total_targets': int,
                'pending': int,
                'verified': int,
                'closed': int,
                'skipped': int,
                'failed': int,
                'total_estimated_yield_sol': float,
                'total_actual_yield_sol': float (from metadata)
            }
        """
        with self.db.cursor() as c:
            # Status counts
            c.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'VERIFIED' THEN 1 ELSE 0 END) as verified,
                SUM(CASE WHEN status = 'CLOSED' THEN 1 ELSE 0 END) as closed,
                SUM(CASE WHEN status = 'SKIPPED' THEN 1 ELSE 0 END) as skipped,
                SUM(CASE WHEN attempts >= 3 THEN 1 ELSE 0 END) as failed,
                SUM(estimated_yield_sol) as total_estimated_yield
            FROM zombie_targets
            """)
            
            row = c.fetchone()
            
            return {
                'total_targets': row['total'] or 0,
                'pending': row['pending'] or 0,
                'verified': row['verified'] or 0,
                'closed': row['closed'] or 0,
                'skipped': row['skipped'] or 0,
                'failed': row['failed'] or 0,
                'total_estimated_yield_sol': row['total_estimated_yield'] or 0.0
            }

    def reset_failed_attempts(self, address: str) -> None:
        """
        Reset attempts counter for manual retry.
        
        Use this after investigating and fixing the root cause of failures.
        """
        self._execute(
            "UPDATE zombie_targets SET attempts = 0, error_message = NULL WHERE address = ?",
            (address,),
            commit=True
        )
        Logger.info(f"🔄 [ZombieRepo] Reset attempts for {address[:8]}...")

    def get_target_by_address(self, address: str) -> Optional[Dict[str, Any]]:
        """Fetch a specific target by address."""
        return self._fetchone(
            "SELECT * FROM zombie_targets WHERE address = ?",
            (address,)
        )

    def get_high_risk_targets(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Fetch HIGH risk targets for manual review.
        
        These require human verification before closure due to:
        - Recent transaction activity (< 30 days)
        - High transaction count
        - Potential LP positions
        """
        return self._fetchall("""
        SELECT * FROM zombie_targets
        WHERE risk_score = 'HIGH'
          AND status IN ('PENDING', 'VERIFIED')
        ORDER BY estimated_yield_sol DESC
        LIMIT ?
        """, (limit,))
