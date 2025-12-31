import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from src.core.shared_cache import SharedPriceCache
from src.shared.state.app_state import state, WalletData, ScalpSignal


async def verify_data_flow():
    print("--- Verifying SharedPriceCache ---")
    SharedPriceCache.write_price("SOL", 160.5, source="TEST")
    price, source = SharedPriceCache.get_price("SOL")
    print(f"Price: {price}, Source: {source}")
    assert price == 160.5

    print("\n--- Verifying AppState Signal Handling ---")
    sig = ScalpSignal(token="SOL", signal_type="RSI", confidence="High", action="BUY")
    state.add_signal(sig)
    print(f"Scalp signals count: {len(state.scalp_signals)}")
    assert len(state.scalp_signals) > 0
    assert state.scalp_signals[0].token == "SOL"

    print("\n--- Verifying AppState Inventory Handling ---")
    # Simulation inventory update
    snapshot = WalletData(
        balance_usdc=50.0, balance_sol=0.06, inventory={"SOL": 0.5, "USDC": 10.0}
    )
    state.update_wallet(is_live=False, data=snapshot)

    inventory = state.inventory
    print(f"Inventory items: {len(inventory)}")
    for item in inventory:
        print(f"  {item.symbol}: {item.amount} (Value: ${item.value_usd:.2f})")

    assert len(inventory) >= 2
    # One of them should have a non-zero value if price cache worked
    valid_value = any(item.value_usd > 0 for item in inventory)
    print(f"Has valid USD values: {valid_value}")
    assert valid_value

    print("\n✅ Verification SUCCESS")


if __name__ == "__main__":
    asyncio.run(verify_data_flow())
