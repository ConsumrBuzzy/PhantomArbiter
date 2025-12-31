import phantom_core
import base64
import struct


def test_slab_decoder():
    print("🧪 Testing Rust Slab Decoder (Phoenix)...")

    # 1. Mock Phoenix Market Header
    # Layout (Partial):
    # u64 discriminant
    # u64 status
    # ... padding ...

    mock_disc = 123456789
    mock_status = 1  # Active

    # Pack le u64s
    data = struct.pack("<QQ", mock_disc, mock_status)

    # Add padding to reach 128 bytes (size check)
    data += b"\x00" * (128 - 16)

    b64_str = base64.b64encode(data).decode("ascii")

    print(f"   📝 Mock Slab: {len(data)} bytes")

    # 2. Decode in Rust
    res = phantom_core.decode_phoenix_header(b64_str)

    if res:
        disc, status = res
        print(f"   ✅ Decoded: Disc={disc} Status={status}")
        assert disc == mock_disc
        assert status == mock_status
        print("   ✅ Validated Values")
    else:
        print("   ❌ Failed to decode slab")


if __name__ == "__main__":
    test_slab_decoder()
