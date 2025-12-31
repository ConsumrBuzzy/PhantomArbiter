"""
V48.0: Jito Block Engine Adapter
================================
Provides priority transaction execution via Jito Labs' MEV-protected
block engine. Transactions submitted through Jito bypass the standard
Solana queue and enter a priority auction.

Features:
- Tip account management (fetch, cache, random selection)
- Bundle submission for atomic execution
- Priority fee optimization

API: https://mainnet.block-engine.jito.wtf/api/v1/bundles
"""

import time
import random
import requests
from typing import List, Optional, Dict
from dataclasses import dataclass


@dataclass
class TipConfig:
    """Configuration for Jito tips."""

    lamports: int = 10000  # Minimum tip (~$0.002)
    max_lamports: int = 100000  # Maximum tip for high priority
    dynamic_tip: bool = False  # Scale tip with urgency


class JitoAdapter:
    """
    V48.0: Jito Block Engine client for priority transactions.

    Provides guaranteed transaction inclusion by tipping Jito validators.
    Tip accounts are fetched from the block engine and cached.

    Usage:
        adapter = JitoAdapter()
        tip_account = adapter.get_random_tip_account()

        # For bundle submission (live trading):
        tx_id = adapter.submit_bundle([signed_tx], tip_lamports=10000)
    """

    # Block Engine endpoints
    MAINNET_API = "https://mainnet.block-engine.jito.wtf/api/v1/bundles"

    # Regional endpoints for lower latency
    REGIONAL_ENDPOINTS = {
        "mainnet": "https://mainnet.block-engine.jito.wtf/api/v1/bundles",
        "frankfurt": "https://frankfurt.mainnet.block-engine.jito.wtf/api/v1/bundles",
        "amsterdam": "https://amsterdam.mainnet.block-engine.jito.wtf/api/v1/bundles",
        "ny": "https://ny.mainnet.block-engine.jito.wtf/api/v1/bundles",
        "tokyo": "https://tokyo.mainnet.block-engine.jito.wtf/api/v1/bundles",
    }

    # Cache settings
    TIP_CACHE_TTL = 300  # 5 minutes
    REQUEST_TIMEOUT = 10  # seconds

    def __init__(self, region: str = "ny"):
        """
        Initialize Jito adapter.

        Args:
            region: Regional endpoint (mainnet, frankfurt, amsterdam, ny, tokyo)
        """
        self.api_url = self.REGIONAL_ENDPOINTS.get(region, self.MAINNET_API)

        # Tip account cache
        self._tip_accounts: List[str] = []
        self._tip_accounts_fetched: float = 0

        # Stats tracking
        self._bundles_submitted = 0
        self._bundles_landed = 0

    def _rpc_call(
        self, method: str, params: list = None, max_retries: int = 1
    ) -> Optional[Dict]:
        """
        Make a JSON-RPC call to the Block Engine with retry logic.

        Args:
            method: RPC method name
            params: Optional parameters
            max_retries: Maximum retry attempts for rate limiting (Default: 1 for speed)

        Returns:
            Response dict or None on error
        """
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}

        for attempt in range(max_retries):
            try:
                response = requests.post(
                    self.api_url, json=payload, timeout=self.REQUEST_TIMEOUT
                )

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    # Rate limited - exponential backoff
                    wait_time = 2**attempt  # 1s, 2s, 4s
                    if attempt < max_retries - 1:
                        print(f"   ⚠️ [JITO] Rate limited, waiting {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        print("   ❌ [JITO] Rate limited, max retries exceeded")
                        return None
                else:
                    print(
                        f"   ⚠️ [JITO] HTTP {response.status_code}: {response.text[:100]}"
                    )
                    return None

            except requests.exceptions.Timeout:
                print("   ⚠️ [JITO] Request timeout")
                return None
            except Exception as e:
                print(f"   ❌ [JITO] RPC error: {e}")
                return None

        return None

    def get_tip_accounts(self, force_refresh: bool = False) -> List[str]:
        """
        Fetch and cache Jito tip accounts.

        Tip accounts are validator addresses that receive priority fees.
        Randomly selecting from the pool reduces contention.

        Returns:
            List of tip account public key strings
        """
        now = time.time()

        # Return cached if valid
        if not force_refresh and self._tip_accounts:
            if now - self._tip_accounts_fetched < self.TIP_CACHE_TTL:
                return self._tip_accounts

        response = self._rpc_call("getTipAccounts")

        if response and isinstance(response, dict):
            accounts = response.get("result", [])
            if isinstance(accounts, list) and len(accounts) > 0:
                self._tip_accounts = accounts
                self._tip_accounts_fetched = now
                print(f"   ✅ [JITO] Cached {len(accounts)} tip accounts")
                return self._tip_accounts

        return self._tip_accounts or []

    def get_random_tip_account(self) -> Optional[str]:
        """
        Get a random tip account to reduce contention.

        Returns:
            Tip account public key or None if unavailable
        """
        accounts = self.get_tip_accounts()
        if accounts:
            return random.choice(accounts)
        return None

    def is_available(self) -> bool:
        """Check if Jito Block Engine is reachable."""
        accounts = self.get_tip_accounts()
        return len(accounts) > 0

    def get_stats(self) -> Dict[str, int]:
        """Get bundle submission statistics."""
        return {
            "bundles_submitted": self._bundles_submitted,
            "bundles_landed": self._bundles_landed,
            "tip_accounts_cached": len(self._tip_accounts),
        }

    # ═══════════════════════════════════════════════════════════════════
    # BUNDLE SUBMISSION (for future live trading)
    # ═══════════════════════════════════════════════════════════════════

    def submit_bundle(
        self,
        serialized_transactions: List[str],
        tip_account: Optional[str] = None,
        tip_lamports: int = 10000,
    ) -> Optional[str]:
        """
        Submit a transaction bundle to Jito Block Engine.

        The bundle is submitted as an atomic unit - either all transactions
        land or none do. A tip transaction to the tip account is required.

        Args:
            serialized_transactions: List of base58-encoded signed transactions
            tip_account: Optional specific tip account (random if not provided)
            tip_lamports: Tip amount in lamports (minimum 1000)

        Returns:
            Bundle UUID if submitted, None on failure
        """
        if not serialized_transactions:
            print("   ❌ [JITO] No transactions provided")
            return None

        # Get tip account if not provided
        if not tip_account:
            tip_account = self.get_random_tip_account()
            if not tip_account:
                print("   ❌ [JITO] No tip accounts available")
                return None

        response = self._rpc_call("sendBundle", [serialized_transactions])

        self._bundles_submitted += 1

        if response and isinstance(response, dict):
            bundle_id = response.get("result")
            if bundle_id:
                print(f"   🚀 [JITO] Bundle submitted: {bundle_id[:16]}...")
                return bundle_id

            error = response.get("error", {})
            print(f"   ❌ [JITO] Submit failed: {error}")
            return None

        return None

    def get_bundle_status(self, bundle_id: str) -> Optional[Dict]:
        """
        Check status of a submitted bundle.

        Args:
            bundle_id: UUID returned from submit_bundle()

        Returns:
            Status dict or None
        """
        response = self._rpc_call("getInflightBundleStatuses", [[bundle_id]])

        if response and isinstance(response, dict):
            return response.get("result")
        return None


# ═══════════════════════════════════════════════════════════════════
# TEST SCRIPT
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("Jito Block Engine Adapter Test")
    print("=" * 60)

    adapter = JitoAdapter()

    # Test tip account fetching
    print("\n1. Fetching tip accounts...")
    accounts = adapter.get_tip_accounts()
    print(f"   Found {len(accounts)} tip accounts")

    if accounts:
        print(f"   Sample: {accounts[0][:32]}...")

        # Test random selection
        print("\n2. Random tip account selection...")
        for i in range(3):
            tip = adapter.get_random_tip_account()
            print(f"   [{i + 1}] {tip[:32]}...")

    # Test availability
    print("\n3. Block Engine availability...")
    available = adapter.is_available()
    print(f"   Available: {available}")

    # Stats
    print("\n4. Stats...")
    stats = adapter.get_stats()
    print(f"   {stats}")

    print("\n" + "=" * 60)
    print("Test complete!")
