import phantom_core
import base64
import struct

def test_log_parser():
    print("🧪 Testing Rust Raydium Log Parser...")

    # 1. Create a Fake Raydium Log (Base64)
    # Struct: u8(3), u64(in), u64(out), u64(min_out), u64(direction), ...
    # Let's mock a swap:
    # Type: 3 (Swap)
    # Amount In: 1,000,000 (1 USDC)
    # Amount Out: 500,000,000 (0.5 SOL - unrealistic price but good checks)
    # Min Out: 0
    # Direction: 1 (Buy)
    
    # Pack: <B Q Q Q Q
    data = struct.pack("<BQQQQ", 
        3,              # log_type
        1_000_000,      # amount_in
        500_000_000,    # amount_out
        0,              # min_out
        1               # direction
    )
    
    # Add dummy padding for other fields (user_source etc)
    data += b'\x00' * 30 
    
    b64_str = base64.b64encode(data).decode('ascii')
    log_msg = f"Program log: ray_log: {b64_str}"
    
    print(f"   📝 Mock Log: {log_msg[:40]}...")

    # 2. Parse in Rust
    event = phantom_core.parse_raydium_log(log_msg)
    
    if event:
        print("   ✅ Log Parsed Successfully")
        print(f"      Amount In:  {event.amount_in:_}")
        print(f"      Amount Out: {event.amount_out:_}")
        print(f"      Is Buy:     {event.is_buy}")
        
        assert event.amount_in == 1_000_000
        assert event.amount_out == 500_000_000
        assert event.is_buy == True
        print("   ✅ Validated Values")
    else:
        print("   ❌ Failed to parse log")

if __name__ == "__main__":
    test_log_parser()
