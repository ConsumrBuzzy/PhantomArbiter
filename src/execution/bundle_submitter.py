"""
Bundle Submitter
================
Jito bundle submission and confirmation handling.

The "Pilot" of the execution pipeline.
Handles the messy real-world interaction with Solana.

Responsibilities:
- Assemble versioned transactions
- Submit bundles to Jito Block Engine
- Poll for confirmation
- Handle retries and timeouts
"""

from __future__ import annotations

import base64
import asyncio
import time
from typing import List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solders.instruction import Instruction
from solders.pubkey import Pubkey
from solders.keypair import Keypair

from src.shared.system.logging import Logger
from src.shared.execution.execution_result import (
    ExecutionResult, ExecutionStatus, ErrorCode,
    success_result, failure_result,
)


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class SubmitterConfig:
    """Configuration for bundle submission."""
    
    # Confirmation
    confirmation_timeout_sec: float = 30.0
    poll_interval_sec: float = 0.5
    
    # Retries
    max_retries: int = 2
    retry_delay_sec: float = 1.0
    
    # Blockhash
    blockhash_refresh_threshold_sec: float = 5.0


class BundleStatus(Enum):
    """Status of a submitted bundle."""
    PENDING = "PENDING"
    LANDED = "LANDED"
    FAILED = "FAILED"
    DROPPED = "DROPPED"
    TIMEOUT = "TIMEOUT"


@dataclass
class SubmissionResult:
    """Result of a bundle submission attempt."""
    
    bundle_id: Optional[str] = None
    status: BundleStatus = BundleStatus.PENDING
    tx_signatures: List[str] = field(default_factory=list)
    submitted_slot: int = 0
    confirmed_slot: Optional[int] = None
    latency_ms: float = 0.0
    error: Optional[str] = None
    
    @property
    def success(self) -> bool:
        return self.status == BundleStatus.LANDED


# ═══════════════════════════════════════════════════════════════════════════════
# BUNDLE SUBMITTER
# ═══════════════════════════════════════════════════════════════════════════════

class BundleSubmitter:
    """
    Handles bundle submission to Jito Block Engine.
    
    Manages:
    - Transaction assembly and signing
    - Blockhash management
    - Bundle submission with retries
    - Confirmation polling
    
    Usage:
        submitter = BundleSubmitter(rpc_client, jito_client, keypair)
        result = await submitter.submit_and_confirm(instructions)
    """
    
    def __init__(
        self,
        rpc_client: Any,
        jito_client: Any,
        keypair: Keypair,
        config: Optional[SubmitterConfig] = None,
    ):
        """
        Initialize submitter.
        
        Args:
            rpc_client: Solana RPC client
            jito_client: Jito Block Engine client
            keypair: Signing keypair
            config: Submission configuration
        """
        self.rpc = rpc_client
        self.jito = jito_client
        self.keypair = keypair
        self.payer = keypair.pubkey()
        self.config = config or SubmitterConfig()
        
        # Blockhash cache
        self._cached_blockhash: Optional[str] = None
        self._blockhash_time: float = 0.0
        
        # Statistics
        self._submissions = 0
        self._confirmations = 0
        self._failures = 0
        self._timeouts = 0
    
    async def submit_and_confirm(
        self,
        instructions: List[Instruction],
        simulate_first: bool = True,
    ) -> SubmissionResult:
        """
        Submit instructions as a Jito bundle and wait for confirmation.
        
        Args:
            instructions: List of instructions to bundle
            simulate_first: Whether to simulate before submitting
            
        Returns:
            SubmissionResult with status and details
        """
        start_time = time.time()
        self._submissions += 1
        
        try:
            # Step 1: Build transaction
            tx = await self._build_transaction(instructions)
            if tx is None:
                return SubmissionResult(
                    status=BundleStatus.FAILED,
                    error="Transaction build failed",
                    latency_ms=(time.time() - start_time) * 1000,
                )
            
            # Step 2: Simulate (optional)
            if simulate_first:
                sim_ok, sim_error = await self._simulate_transaction(tx)
                if not sim_ok:
                    return SubmissionResult(
                        status=BundleStatus.FAILED,
                        error=f"Simulation failed: {sim_error}",
                        latency_ms=(time.time() - start_time) * 1000,
                    )
            
            # Step 3: Submit bundle
            bundle_id = await self._submit_bundle(tx)
            if not bundle_id:
                self._failures += 1
                return SubmissionResult(
                    status=BundleStatus.FAILED,
                    error="Bundle submission rejected",
                    latency_ms=(time.time() - start_time) * 1000,
                )
            
            # Step 4: Wait for confirmation
            confirmed, confirmed_slot = await self._wait_for_confirmation(bundle_id)
            
            latency_ms = (time.time() - start_time) * 1000
            
            if confirmed:
                self._confirmations += 1
                return SubmissionResult(
                    bundle_id=bundle_id,
                    status=BundleStatus.LANDED,
                    confirmed_slot=confirmed_slot,
                    latency_ms=latency_ms,
                )
            else:
                self._timeouts += 1
                return SubmissionResult(
                    bundle_id=bundle_id,
                    status=BundleStatus.TIMEOUT,
                    error="Confirmation timeout",
                    latency_ms=latency_ms,
                )
                
        except Exception as e:
            self._failures += 1
            Logger.error(f"[BundleSubmitter] Submission error: {e}")
            return SubmissionResult(
                status=BundleStatus.FAILED,
                error=str(e),
                latency_ms=(time.time() - start_time) * 1000,
            )
    
    async def _build_transaction(
        self,
        instructions: List[Instruction],
    ) -> Optional[VersionedTransaction]:
        """Build and sign a versioned transaction."""
        try:
            blockhash = await self._get_recent_blockhash()
            
            message = MessageV0.try_compile(
                payer=self.payer,
                instructions=instructions,
                address_lookup_table_accounts=[],
                recent_blockhash=blockhash,
            )
            
            tx = VersionedTransaction(message, [self.keypair])
            
            Logger.debug(f"[BundleSubmitter] TX built: {len(instructions)} ixs")
            return tx
            
        except Exception as e:
            Logger.error(f"[BundleSubmitter] TX build failed: {e}")
            return None
    
    async def _get_recent_blockhash(self) -> str:
        """Get recent blockhash with caching."""
        now = time.time()
        
        if (
            self._cached_blockhash is None or
            now - self._blockhash_time > self.config.blockhash_refresh_threshold_sec
        ):
            resp = self.rpc.get_latest_blockhash()
            self._cached_blockhash = str(resp.value.blockhash)
            self._blockhash_time = now
            Logger.debug(f"[BundleSubmitter] Fresh blockhash: {self._cached_blockhash[:16]}...")
        
        return self._cached_blockhash
    
    async def _simulate_transaction(
        self,
        tx: VersionedTransaction,
    ) -> Tuple[bool, Optional[str]]:
        """Simulate transaction before submission."""
        try:
            # Serialize for simulation
            encoded = base64.b64encode(bytes(tx)).decode("utf-8")
            
            resp = self.rpc.simulate_transaction(tx)
            
            if resp.value.err:
                return False, str(resp.value.err)
            
            Logger.debug("[BundleSubmitter] Simulation passed")
            return True, None
            
        except Exception as e:
            return False, str(e)
    
    async def _submit_bundle(
        self,
        tx: VersionedTransaction,
    ) -> Optional[str]:
        """Submit transaction as Jito bundle."""
        try:
            # Serialize transaction
            encoded = base64.b64encode(bytes(tx)).decode("utf-8")
            
            # Submit to Jito
            bundle_id = await self.jito.submit_bundle(
                [encoded],
                simulate=False,
            )
            
            if bundle_id:
                Logger.info(f"[BundleSubmitter] 🚀 Bundle submitted: {bundle_id[:16]}...")
            
            return bundle_id
            
        except Exception as e:
            Logger.error(f"[BundleSubmitter] Submit failed: {e}")
            return None
    
    async def _wait_for_confirmation(
        self,
        bundle_id: str,
    ) -> Tuple[bool, Optional[int]]:
        """Poll for bundle confirmation."""
        deadline = time.time() + self.config.confirmation_timeout_sec
        
        while time.time() < deadline:
            try:
                status = await self.jito.get_bundle_status(bundle_id)
                
                if status == "landed":
                    slot = await self._get_current_slot()
                    return True, slot
                elif status in ("failed", "dropped"):
                    return False, None
                    
            except Exception as e:
                Logger.debug(f"[BundleSubmitter] Status check error: {e}")
            
            await asyncio.sleep(self.config.poll_interval_sec)
        
        return False, None
    
    async def _get_current_slot(self) -> int:
        """Get current slot."""
        try:
            return self.rpc.get_slot().value
        except Exception:
            return 0
    
    def get_stats(self) -> dict:
        """Get submission statistics."""
        success_rate = (
            self._confirmations / self._submissions * 100
            if self._submissions > 0
            else 0
        )
        
        return {
            "submissions": self._submissions,
            "confirmations": self._confirmations,
            "failures": self._failures,
            "timeouts": self._timeouts,
            "success_rate_pct": round(success_rate, 2),
        }
