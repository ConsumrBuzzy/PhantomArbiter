import sys
import os

sys.path.append(os.getcwd())


def main():
    print("🧪 Verifying Shared Token Metadata Layer...")

    try:
        from phantom_core import SharedTokenMetadata, SignalScanner, ScalpSignal
    except ImportError as e:
        print(f"❌ Failed to import phantom_core: {e}")
        print("💡 Hint: Build failed or extension not in path.")
        return

    # 1. Create Metadata
    print("1️⃣ Testing SharedTokenMetadata...")
    meta = SharedTokenMetadata("MINT123")
    meta.symbol = "TEST"
    meta.is_rug_safe = True
    meta.liquidity_usd = 10000.0
    meta.velocity_1m = 0.06  # > 5% threshold
    meta.price_usd = 1.0
    meta.spread_bps = 10
    meta.order_imbalance = 2.0  # Boost
    meta.program_id = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
    meta.last_updated_slot = 1000

    print(f"   ✅ Created Metadata: {meta.mint} (Vel: {meta.velocity_1m})")

    # 2. Scanner
    print("2️⃣ Testing SignalScanner (Rust)...")
    scanner = SignalScanner()
    # Mock current slot close to update so it's not stale
    current_slot = 1005
    signals = scanner.scan_scalp_opportunities([meta], current_slot)

    # 3. Verify
    if len(signals) == 1:
        sig = signals[0]
        print(
            f"   ✅ Signal Detected: {sig.direction} {sig.token} Conf: {sig.confidence:.2f}"
        )
        if sig.confidence > 0.6:
            print("   ✅ Confidence score logic works (Boosts applied).")
        else:
            print(f"   ⚠️ Low confidence: {sig.confidence}")
    else:
        print(f"   ❌ No signal detected! (Expected 1, Got {len(signals)})")

    print("\n🎉 Verification Complete!")


if __name__ == "__main__":
    main()
