import time
from src.shared.system.db_manager import db_manager
from src.shared.state.app_state import TokenIdentity, TokenRisk
from src.shared.infrastructure.token_registry import get_registry


def test_db_persistence():
    print("🧪 Testing Token DB Persistence...")

    # 1. Direct DBManager Test
    mint = "TEST_MINT_123"
    identity = TokenIdentity(mint=mint, symbol="TEST", name="Test Token", decimals=9)
    risk = TokenRisk(safety_score=95.0, is_mutable=False)

    print(f"   💾 Saving {mint} to DB...")
    db_manager.save_token_metadata(identity, risk)

    time.sleep(0.5)

    print(f"   📖 Reading {mint} from DB...")
    data = db_manager.get_token_metadata(mint)

    if not data:
        print("   ❌ Read failed: No data found")
        return

    loaded_id = data["identity"]
    loaded_risk = data["risk"]

    if loaded_id.symbol == "TEST" and loaded_risk.safety_score == 95.0:
        print("   ✅ Direct DB Save/Load Successful")
    else:
        print(f"   ❌ Data mismatch: {loaded_id.symbol}, {loaded_risk.safety_score}")

    # 2. Registry Integration Test
    print("\n🧪 Testing Registry Integration...")
    registry = get_registry()

    # Ensure cache is empty for this test
    if mint in registry._identity_cache:
        del registry._identity_cache[mint]
    if mint in registry._risk_cache:
        del registry._risk_cache[mint]

    print(f"   🔄 Calling get_full_metadata for {mint} (Targeting DB hit)...")
    meta = registry.get_full_metadata(mint)

    if meta["identity"].symbol == "TEST":
        print("   ✅ Registry successfully loaded from DB")
    else:
        print(f"   ❌ Registry failed to load from DB: {meta}")


if __name__ == "__main__":
    test_db_persistence()
