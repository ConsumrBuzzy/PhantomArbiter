import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.engine.risk_governor import GlobalRiskGovernor


def test_governor():
    print("🧪 Testing Global Risk Governor...")

    # 1. Init (Capital $1000)
    gov = GlobalRiskGovernor(initial_capital_usd=1000.0)

    # 2. Check Allocations
    # Scalper: 30% ($300). Arbiter: 70% ($700).

    print("   👉 Testing Capital Allocation...")
    # Request $200 for Scalper -> Should PASS
    if gov.can_execute("scalper", 200.0):
        print("   ✅ Scalper Request $200 ALLOWED")
    else:
        print("   ❌ Scalper Request $200 DENIED (Expected Allowed)")

    # 3. Test Daily Drawdown (Kill Switch)
    print("   👉 Testing Kill Switch...")

    # Record Loss of $50 (5%)
    gov.record_trade("scalper", -50.0)
    if not gov.is_halted:
        print("   ✅ -5% Loss: System OK")
    else:
        print("   ❌ -5% Loss: System HALTED (Too Early)")

    # Record Loss of $60 (Cumulative -110 => -11%)
    gov.record_trade("scalper", -60.0)

    if gov.is_halted:
        print("   ✅ -11% Loss: System HALTED")
    else:
        print(f"   ❌ -11% Loss: System LIVE (Expected HALT). PnL: {gov.daily_pnl_usd}")

    # 4. Verify Blocked Trades
    if not gov.can_execute("arbiter", 100.0):
        print("   ✅ Arbiter Trade BLOCKED by Kill Switch")
    else:
        print("   ❌ Arbiter Trade ALLOWED (Should be Blocked)")

    # 5. Reset
    print("   👉 Testing Reset...")
    gov.reset_daily()
    if not gov.is_halted and gov.daily_pnl_usd == 0:
        print("   ✅ Daily Reset Successful")
    else:
        print("   ❌ Reset Failed")


if __name__ == "__main__":
    test_governor()
