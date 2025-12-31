import sys
import os
import time
from unittest.mock import MagicMock

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.scraper.agents.sniper_agent import SniperAgent
from src.shared.system.signal_bus import intent_registry


def verify_graduation():
    print("🧪 Testing Graduation Sniper Logic...")

    # Setup Agent
    agent = SniperAgent()
    agent.running = True  # Manually start for sync test

    # Mock dependencies
    agent.scraper.lookup = MagicMock(return_value={"symbol": "GRAD", "liquidity": 5000})

    mint = "GRAD_TOKEN_MINT_123"

    # 1. Test Watchlist Addition (Curve update)
    print("   👉 Testing Bonding Curve Trigger...")
    agent.on_bonding_curve_update(mint, 0.98)  # 98% complete

    if mint in agent.graduation_watchlist:
        print(f"   ✅ Token {mint[:8]} added to Graduation Watchlist")
    else:
        print(f"   ❌ Token NOT in watchlist (Size: {len(agent.graduation_watchlist)})")
        return

    # 2. Test Graduation Event (Raydium Init)
    print("   👉 Testing Raydium Pool Creation...")
    agent.on_raydium_pool_created(mint)

    if mint not in agent.graduation_watchlist:
        print("   ✅ Token removed from Watchlist")
    else:
        print("   ❌ Token still in Watchlist")

    pending = [p for p in agent.pending_snipes if p["mint"] == mint]
    if pending and pending[0]["source"] == "GRADUATION":
        print("   ✅ Token PROMOTED to Pending Queue (Source: GRADUATION)")
    else:
        print("   ❌ Token missing from Queue or wrong source")
        return

    # 3. Test Intent Lock (Success Case)
    print("   👉 Testing Lock Acquisition...")
    signal = agent.on_tick({})

    if signal and signal.metadata["is_graduation"]:
        print("   ✅ SNIPE Signal Fired")
        owner = intent_registry.check_owner(mint)
        if owner == "SNIPER":
            print(f"   ✅ Lock Held by: {owner}")
        else:
            print(f"   ❌ Lock Check Failed: {owner}")
    else:
        print("   ❌ No Signal Fired")

    # 4. Test Lock Collision (Fail Case)
    print("   👉 Testing Lock Collision...")
    mint_locked = "LOCKED_TOKEN_456"

    # Queue manually
    agent.pending_snipes.append(
        {"mint": mint_locked, "source": "Manual", "discovered_at": time.time()}
    )

    # Arbiter locks it first
    intent_registry.claim(mint_locked, "ARBITER", ttl=60)

    # Try to snipe
    signal_blocked = agent.on_tick({})

    if signal_blocked is None:
        print("   ✅ Snipe BLOCKED by ARBITER lock")
    else:
        print(f"   ❌ Snipe fired despite lock! {signal_blocked}")


if __name__ == "__main__":
    verify_graduation()
