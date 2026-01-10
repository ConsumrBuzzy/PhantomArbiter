"""
V1.0: Shadow Manager - Dual Execution Auditor
==============================================
Phase 4: Institutional Realism

Runs Paper and Live execution in parallel on the same signal,
compares fill prices, and logs deltas for slippage analysis.
"""

import asyncio
import csv
import os
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from collections import deque

from config.settings import Settings
from src.shared.system.logging import Logger
from src.shared.models.trade_result import TradeResult


@dataclass
class ShadowAudit:
    """
    Result of comparing Paper vs Live execution on the same signal.
    """

    mint: str
    action: str
    paper_fill: float
    live_fill: float
    delta_pct: float  # (Live - Paper) / Paper * 100
    execution_lag_ms: float  # Time difference between fills
    timestamp: float = field(default_factory=time.time)
    paper_slippage: float = 0.0
    live_slippage: float = 0.0
    signal_price: float = 0.0

    @property
    def is_significant(self) -> bool:
        """Check if delta exceeds threshold (1%)."""
        return abs(self.delta_pct) > 1.0

    def to_csv_row(self) -> List:
        """Convert to CSV row format."""
        return [
            self.timestamp,
            self.mint,
            self.action,
            self.signal_price,
            self.paper_fill,
            self.live_fill,
            self.delta_pct,
            self.execution_lag_ms,
            self.paper_slippage,
            self.live_slippage,
        ]

    @staticmethod
    def csv_headers() -> List[str]:
        """CSV column headers."""
        return [
            "timestamp",
            "mint",
            "action",
            "signal_price",
            "paper_fill",
            "live_fill",
            "delta_pct",
            "execution_lag_ms",
            "paper_slippage",
            "live_slippage",
        ]


class ShadowManager:
    """
    Manages parallel Paper/Live execution auditing.

    Key Features:
    - Non-blocking audit via asyncio.create_task()
    - In-memory buffer (capped at 1000 entries)
    - CSV persistence for historical analysis
    - Delta statistics for auto-calibration
    """

    MAX_AUDITS = 1000  # In-memory cap
    CSV_FILE = os.path.join(Settings.DATA_DIR, "shadow_audits.csv")

    def __init__(self, app_state: Optional[Any] = None):
        """
        Initialize ShadowManager.

        Args:
            app_state: Optional AppState for UI alerts
        """
        self.app_state = app_state
        self.audits: deque = deque(maxlen=self.MAX_AUDITS)
        self._ensure_csv_exists()

        # Statistics
        self._total_audits = 0
        self._significant_deltas = 0
        self._sum_delta = 0.0

    def _ensure_csv_exists(self) -> None:
        """Create CSV file with headers if it doesn't exist."""
        if not os.path.exists(self.CSV_FILE):
            os.makedirs(os.path.dirname(self.CSV_FILE), exist_ok=True)
            with open(self.CSV_FILE, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(ShadowAudit.csv_headers())

    async def audit_trade(
        self,
        signal_token: str,
        signal_action: str,
        signal_price: float,
        paper_result: TradeResult,
        live_result: TradeResult,
    ) -> Optional[ShadowAudit]:
        """
        Compare Paper and Live results and log the delta.

        Args:
            signal_token: Token mint/symbol
            signal_action: "BUY" or "SELL"
            signal_price: Original signal price
            paper_result: TradeResult from PaperWallet
            live_result: TradeResult from LiveExecutor

        Returns:
            ShadowAudit if both succeeded, None otherwise
        """
        # Skip if either failed
        if not paper_result.success or not live_result.success:
            Logger.debug(
                f"[SHADOW] Skipping audit - Paper: {paper_result.success}, Live: {live_result.success}"
            )
            return None

        # Calculate Delta
        if paper_result.fill_price <= 0:
            return None

        delta_pct = (
            (live_result.fill_price - paper_result.fill_price) / paper_result.fill_price
        ) * 100

        # Calculate Execution Lag
        lag_ms = (live_result.timestamp - paper_result.timestamp) * 1000

        audit = ShadowAudit(
            mint=signal_token,
            action=signal_action,
            paper_fill=paper_result.fill_price,
            live_fill=live_result.fill_price,
            delta_pct=delta_pct,
            execution_lag_ms=lag_ms,
            paper_slippage=paper_result.slippage_pct,
            live_slippage=live_result.slippage_pct,
            signal_price=signal_price,
        )

        # Store and log
        self._record_audit(audit)

        # Alert if significant
        if audit.is_significant:
            self._alert_significant_delta(audit)

        return audit

    async def audit_trade_from_tasks(
        self,
        signal_token: str,
        signal_action: str,
        signal_price: float,
        paper_task: asyncio.Task,
        live_task: asyncio.Task,
    ) -> Optional[ShadowAudit]:
        """
        Await both execution tasks and perform audit.

        This is the primary entry point for dual-dispatch pattern.

        Args:
            signal_token: Token mint/symbol
            signal_action: "BUY" or "SELL"
            signal_price: Original signal price
            paper_task: asyncio.Task returning TradeResult
            live_task: asyncio.Task returning TradeResult
        """
        try:
            paper_result, live_result = await asyncio.gather(
                paper_task, live_task, return_exceptions=True
            )

            # Handle exceptions
            if isinstance(paper_result, Exception):
                Logger.error(f"[SHADOW] Paper execution failed: {paper_result}")
                paper_result = TradeResult.failed(
                    signal_token, signal_action, str(paper_result), "PAPER"
                )

            if isinstance(live_result, Exception):
                Logger.error(f"[SHADOW] Live execution failed: {live_result}")
                live_result = TradeResult.failed(
                    signal_token, signal_action, str(live_result), "LIVE"
                )

            return await self.audit_trade(
                signal_token, signal_action, signal_price, paper_result, live_result
            )
        except Exception as e:
            Logger.error(f"[SHADOW] Audit failed: {e}")
            return None

    def _record_audit(self, audit: ShadowAudit) -> None:
        """Store audit in memory and persist to CSV."""
        self.audits.append(audit)
        self._total_audits += 1
        self._sum_delta += audit.delta_pct

        if audit.is_significant:
            self._significant_deltas += 1

        # Append to CSV
        try:
            with open(self.CSV_FILE, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(audit.to_csv_row())
        except Exception as e:
            Logger.error(f"[SHADOW] CSV write failed: {e}")

        # Log to console
        emoji = "⚠️" if audit.is_significant else "📊"
        Logger.info(
            f"{emoji} [SHADOW] {audit.mint} {audit.action} | "
            f"Paper: ${audit.paper_fill:.4f} vs Live: ${audit.live_fill:.4f} | "
            f"Delta: {audit.delta_pct:+.2f}%"
        )

    def _alert_significant_delta(self, audit: ShadowAudit) -> None:
        """Alert on significant price delta."""
        if self.app_state:
            try:
                self.app_state.flash_error(
                    f"⚠️ SHADOW ALERT: {audit.mint} Delta > 1% ({audit.delta_pct:+.2f}%)"
                )
            except Exception:
                pass  # UI might not be available

    def get_stats(self) -> Dict[str, float]:
        """Get aggregate statistics."""
        avg_delta = (
            self._sum_delta / self._total_audits if self._total_audits > 0 else 0.0
        )

        return {
            "total_audits": self._total_audits,
            "significant_deltas": self._significant_deltas,
            "avg_delta_pct": avg_delta,
            "max_delta_pct": max((a.delta_pct for a in self.audits), default=0.0),
            "min_delta_pct": min((a.delta_pct for a in self.audits), default=0.0),
        }

    def get_recent_audits(self, n: int = 10) -> List[ShadowAudit]:
        """Get the N most recent audits."""
        return list(self.audits)[-n:]
