"""
Verify Privacy Shield Implementation
====================================
Phase 21 Verification Script

Objectives:
1. Simulate a SessionContext with a Mock Wallet Key.
2. Trigger HydrationManager.dehydrate().
3. Inspect the JSON archive to ensure 'wallet_key' is ABSENT.
4. Verify other context params are preserved.
"""

import sys
import os
import json
from dataclasses import dataclass

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.shared.system.hydration_manager import HydrationManager


# Mock Session Context (matches ConfigManager definition)
@dataclass
class MockContext:
    strategy_mode: str
    execution_mode: str
    budget_sol: float
    params: dict
    wallet_key: bytes = None


def run_privacy_audit():
    print("🕵️ Starting Privacy Shield Audit...")

    # 1. Setup Mock Data with SENSITIVE KEY
    # We use a fake key pattern to verify it gets scrubbed
    sensitive_key = b"SENSITIVE_PRIVATE_KEY_DO_NOT_LEAK"

    context = MockContext(
        strategy_mode="TEST_STRATEGY",
        execution_mode="GHOST",
        budget_sol=100.0,
        params={"risk": "HIGH"},
        wallet_key=sensitive_key,
    )

    print(f"   💉 Injected Sensitive Key into Context: {sensitive_key}")

    # 2. Trigger Dehydration
    manager = HydrationManager()

    # Ensure a clean slate for archives (optional, but good for test)
    # We won't delete existing ones, just track the new one

    archive_path = manager.dehydrate(context=context)

    if not archive_path:
        print("❌ Dehydration Logic Failed completely.")
        sys.exit(1)

    print(f"   📦 Archive Created: {archive_path}")

    # 3. Inspect Archive content
    with open(archive_path, "r") as f:
        data = json.load(f)

    archived_context = data["meta"]["context"]

    # 4. Assertions
    print("\n🔍 Inspecting Archive Metadata...")
    print(f"   Context Keys Found: {list(archived_context.keys())}")

    if "wallet_key" in archived_context:
        print("   ❌ CRITICAL FAILURE: 'wallet_key' found in archive!")
        print(f"      Value leaked: {archived_context['wallet_key']}")
        sys.exit(1)
    else:
        print("   ✅ SUCCESS: 'wallet_key' was successfully scrubbed.")

    if archived_context.get("strategy_mode") == "TEST_STRATEGY":
        print("   ✅ SUCCESS: Non-sensitive context data preserved.")
    else:
        print("   ⚠️ WARNING: Context data seems malformed.")

    # Cleanup
    os.remove(archive_path)
    print("\n🛡️ Privacy Audit Passed. Test Archive cleaned up.")


if __name__ == "__main__":
    run_privacy_audit()
