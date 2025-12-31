"""
Verify Scavenger Logic (Standalone)
===================================
Phase 17: Battle Testing

Independent verification script to test FailureTracker and BridgePod
without relying on pytest infrastructure.
"""

import sys
import time
from typing import Dict, Any

# Add project root to path
sys.path.insert(0, ".")

def test_failure_tracker():
    """Test FailureTracker logic."""
    print("\n🔬 Testing FailureTracker (Recoil Signal)...")
    from src.shared.infrastructure.log_harvester import FailureTracker
    
    # 1. Initialize
    tracker = FailureTracker(
        window_seconds=1.0,  # Short window
        failure_threshold=3, # Low threshold
        recoil_silence_seconds=0.1 # Fast recoil
    )
    pool = "PoolA_Test_Address"
    print("   [1/4] Loaded FailureTracker")

    # 2. Test Spike
    for i in range(2):
        tracker.record_failure(pool, "FAIL")
    assert tracker.alerts_emitted == 0, "Premature alert emitted"
    
    tracker.record_failure(pool, "FAIL")
    assert tracker.alerts_emitted == 1, "Alert NOT emitted on threshold"
    print("   [2/4] Spike Detection: ✅ PASS")

    # 3. Test Cooldown
    tracker.record_failure(pool, "FAIL")
    assert tracker.alerts_emitted == 1, "Cooldown failed (duplicate alert)"
    print("   [3/4] Alert Cooldown: ✅ PASS")

    # 4. Test Recoil
    time.sleep(0.15) # Wait for silence
    tracker.record_success(pool) # Trigger recoil check via success or next tick
    assert tracker.recoils_detected == 1, "Recoil NOT detected"
    print("   [4/4] Recoil Detection: ✅ PASS")
    
    return True

def test_bridge_pod():
    """Test BridgePod logic."""
    print("\n🔬 Testing BridgePod (The Sniffer)...")
    from src.engine.bridge_pod import BridgePod
    from src.engine.pod_manager import PodConfig, PodType
    
    captured_signals = []
    def callback(signal):
        captured_signals.append(signal)

    # 1. Initialize
    config = PodConfig(
        pod_type=PodType.WHALE,
        name="test_sniffer",
        params={},
        cooldown_seconds=0.1,
    )
    pod = BridgePod(
        config=config,
        signal_callback=callback,
        whale_threshold_usd=100_000,
    )
    print("   [1/3] Loaded BridgePod")

    # 2. Test Ignored Event (Below Threshold)
    pod.handle_bridge_event({
        "protocol": "CCTP",
        "signature": "sig1",
        "amount_usd": 50_000,
        "mint": "USDC",
        "recipient": "walletA",
    })
    assert len(captured_signals) == 0, "Signal emitted for small fish"
    print("   [2/3] Ignore Small Fish: ✅ PASS")

    # 3. Test Whale Event
    pod.handle_bridge_event({
        "protocol": "CCTP",
        "signature": "sig2",
        "amount_usd": 500_000,
        "mint": "USDC",
        "recipient": "walletB",
    })
    assert len(captured_signals) == 1, "Whale signal NOT emitted"
    sig = captured_signals[0]
    assert sig.signal_type == "LIQUIDITY_INFLOW", "Wrong signal type"
    assert sig.data['amount_usd'] == 500_000, "Wrong amount data"
    print("   [3/3] Whale Detection: ✅ PASS")

    return True

def main():
    print("="*40)
    print("🧪 SCAVENGER VERIFICATION")
    print("="*40)
    
    try:
        f_success = test_failure_tracker()
        b_success = test_bridge_pod()
        
        if f_success and b_success:
            print("\n✅ ALL TESTS PASSED")
            sys.exit(0)
        else:
            print("\n❌ SOME TESTS FAILED")
            sys.exit(1)
            
    except AssertionError as e:
        print(f"\n❌ ASSERTION FAILED: {str(e)}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ EXCEPTION: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
