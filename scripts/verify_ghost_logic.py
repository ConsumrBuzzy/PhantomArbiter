"""
Verify Ghost Validator Logic
============================
Tests the Look-Back validation logic of the GhostValidator.
"""

import sys
import os
import asyncio
from unittest.mock import MagicMock, AsyncMock

# Add src to path
sys.path.append(os.getcwd())

from src.engine.ghost_validator import GhostValidator


async def test_validator():
    print("👻 Testing GhostValidator Logic...")

    # Mock QuoteBuilder
    qb = MagicMock()
    # Mock build_cycle_quotes
    qb.build_cycle_quotes = AsyncMock(return_value=["quote1"])

    # Mock calculate_cycle_profit
    # Case 1: Profitable
    qb.calculate_cycle_profit = MagicMock(return_value={"profit_pct": 1.5})

    validator = GhostValidator(qb)

    print("   Testing Profitable Case...")
    res = await validator.validate_later(
        cycle_id="test_cycle",
        path=["SOL", "USDC", "SOL"],
        original_profit=1.2,
        delay_seconds=0.01,
    )

    print(f"   Result: {res}")
    # Net profit should be 1.5 - fees(0.008 SOL / 1 SOL = 0.8%)
    # 0.008 SOL is roughly $1.60 at $200 SOL.
    # 1 SOL input. 0.8% fee impact.
    # 1.5% - 0.8% = 0.7% net.

    assert res.is_still_profitable, "Should be profitable"
    assert res.current_profit_pct < 1.5, "Fees should reduce profit"

    print("✅ Profitable Case Passed")

    # Case 2: Unprofitable due to fees
    print("   Testing Fee-Loss Case...")
    qb.calculate_cycle_profit = MagicMock(
        return_value={"profit_pct": 0.5}
    )  # 0.5% profit
    # Fees are approx 0.8%. Net should be negative.

    res = await validator.validate_later(
        cycle_id="test_cycle_2",
        path=["SOL", "USDC", "SOL"],
        original_profit=0.5,
        delay_seconds=0.01,
    )

    print(f"   Result: {res}")
    assert not res.is_still_profitable, "Should be rejected due to fees"
    assert res.current_profit_pct < 0, "Net profit should be negative"

    print("✅ Fee-Loss Case Passed")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(test_validator())
        print("\n🎉 GhostValidator Verified")
    except Exception as e:
        print(f"\n❌ VERIFICATION FAILED: {e}")
        sys.exit(1)
    finally:
        loop.close()
