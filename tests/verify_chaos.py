import sys
import os

# Add src to path
sys.path.append(os.path.join(os.getcwd()))

from src.shared.system.chaos_shield import OracleGuard, GasDynamics, JitoGuard

def test_oracle_guard():
    print("🧪 Testing OracleGuard...")
    guard = OracleGuard()
    
    # 1. Test Matching Price (Safe)
    # Mocking internal fetch: In verify, we test check_divergence logic directly
    # Assuming get_oracle_price returns Mock values: SOL=150.0
    
    # Case A: Pool Price = 150.0 (Diff 0%) -> Safe
    is_safe = guard.check_divergence("SOL", 150.0)
    assert is_safe, "OracleGuard failed on matching price!"
    print("   ✅ Match: Safe")
    
    # Case B: Pool Price = 145.0 (Diff 3.3%) -> Safe
    is_safe = guard.check_divergence("SOL", 145.0)
    assert is_safe, "OracleGuard failed on minor divergence!"
    print("   ✅ Minor Diff: Safe")
    
    # Case C: Pool Price = 100.0 (Diff 33%) -> UNSAFE
    is_safe = guard.check_divergence("SOL", 100.0)
    assert not is_safe, "OracleGuard FAILED to catch huge divergence!"
    print("   ✅ Major Diff: CAUGHT (Unsafe)")
    
def test_gas_dynamics():
    print("\n🧪 Testing GasDynamics...")
    gas = GasDynamics()
    base = gas.get_cu_limit()
    print(f"   Base CU: {base}")
    
    # 1. Simulate Failure
    gas.record_outcome(False, "ComputationalBudgetExceeded")
    new_cu = gas.get_cu_limit()
    print(f"   After Fail: {new_cu}")
    assert new_cu > base, "GasDynamics did not increase CU after failure!"
    
    # 2. Simulate Success (Recovery)
    gas.record_outcome(True)
    rec_cu = gas.get_cu_limit()
    print(f"   as Success: {rec_cu}")
    assert rec_cu <= new_cu, "GasDynamics did not decrease CU after success!"

def test_jito_guard():
    print("\n🧪 Testing JitoGuard...")
    jito = JitoGuard("mock_rpc")
    safe = jito.is_safe_slot(12345)
    assert safe, "JitoGuard default mock should be Safe"
    print("   ✅ Slot Check: Passed")

if __name__ == "__main__":
    print("🛡️ STARTING CHAOS SHIELD VERIFICATION 🛡️")
    try:
        test_oracle_guard()
        test_gas_dynamics()
        test_jito_guard()
        print("\n✨ ALL TESTS PASSED. CHAOS SHIELD IS ACTIVE.")
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        sys.exit(1)
