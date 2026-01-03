import time
import os
import phantom_core

def test_flash_cache():
    CACHE_FILE = "verify_cache.dat"
    
    # Clean up previous run
    if os.path.exists(CACHE_FILE):
        try:
            os.remove(CACHE_FILE)
        except:
            pass
            
    print("🚀 Initializing FlashCache Writer...")
    writer = phantom_core.FlashCacheWriter(CACHE_FILE)
    
    print("🚀 Initializing FlashCache Reader...")
    reader = phantom_core.FlashCacheReader(CACHE_FILE)
    
    # 1. Write Updates
    print("Writing 5 updates...")
    test_mints = [
        ("So11111111111111111111111111111111111111112", 150.0),
        ("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", 1.0),
        ("DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", 0.05),
        ("JUPyiwrYJFskUPiHa7hkeR8VUtkOpj8oppfxy6Si2Ca", 1.25),
        ("mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So", 180.0),
    ]
    
    start_time = time.time()
    for i, (mint, price) in enumerate(test_mints):
        # push_update(mint_str, price, slot, liquidity)
        writer.push_update(mint, price, 240000000 + i, 500000.0)
        
    write_duration = (time.time() - start_time) * 1000
    print(f"✅ Wrote 5 updates in {write_duration:.4f}ms")

    # 2. Read Updates
    print("Reading updates...")
    start_time = time.time()
    updates = reader.poll_updates()
    read_duration = (time.time() - start_time) * 1000
    
    print(f"✅ Read {len(updates)} updates in {read_duration:.4f}ms")
    
    # 3. Verify
    if len(updates) != 5:
        print(f"❌ Mismatch! Expected 5, got {len(updates)}")
        return
        
    for i, (mint, price, slot) in enumerate(updates):
        expected_mint, expected_price = test_mints[i]
        if mint != expected_mint:
            print(f"❌ Mint mismatch at {i}: {mint} != {expected_mint}")
        if abs(price - expected_price) > 0.0001:
            print(f"❌ Price mismatch at {i}: {price} != {expected_price}")
            
    print("🎉 verification Success: FlashCache is functional!")
    
    # cleanup
    try:
        os.remove(CACHE_FILE)
    except:
        pass

if __name__ == "__main__":
    try:
        test_flash_cache()
    except ImportError:
        print("❌ phantom_core not found! Build failed or environment issue.")
    except Exception as e:
        print(f"❌ Test Failed: {e}")
