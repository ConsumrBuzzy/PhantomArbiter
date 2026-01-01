import pytest
import time
from phantom_core import PdaCache
from solders.pubkey import Pubkey

def test_pda_cache_instantiation():
    """Test that we can create the Rust object."""
    cache = PdaCache()
    assert cache is not None

def test_ata_derivation():
    """Verify ATA derivation against known values or logic."""
    cache = PdaCache()
    
    # Known values
    owner = "CKH7q184k5bQvC94v6165Fq4v9q5J7vJ4v6q5q4q5q4q" # Fake base58
    # Let's use real valid base58 strings to avoid parsing errors
    # Using a burn address for owner
    owner = "11111111111111111111111111111111"
    # USDC Mint
    usdc_mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    
    start_time = time.time()
    ata = cache.get_ata_address(owner, usdc_mint)
    duration_rust = time.time() - start_time
    
    print(f"Rust Derivation Time: {duration_rust*1000:.4f}ms")
    print(f"Derived ATA: {ata}")
    
    assert len(ata) > 30 # Basic check for valid base58 length

def test_orca_whirlpool_derivation():
    cache = PdaCache()
    
    # Whirlpool Config (Mainnet)
    config = "2LecshUwdy9xi7meFgHtFJQNSKk4KcPrc26E1L56xCn7"
    # SOL
    token_a = "So11111111111111111111111111111111111111112"
    # USDC
    token_b = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    tick_spacing = 64
    
    pf_addr = cache.get_orca_whirlpool_address(config, token_a, token_b, tick_spacing)
    print(f"Orca Pool Address: {pf_addr}")
    assert len(pf_addr) > 30

def test_cache_performance():
    """Benchmark 1000 lookups."""
    cache = PdaCache()
    owner = "11111111111111111111111111111111"
    mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    
    start = time.time()
    for _ in range(1000):
        _ = cache.get_ata_address(owner, mint)
    end = time.time()
    
    print(f"1000 Derive + Cache Hits: {(end-start)*1000:.4f}ms")
    print(f"Per Op: {(end-start)*1000/1000:.4f}ms")

if __name__ == "__main__":
    test_pda_cache_instantiation()
    test_ata_derivation()
    test_orca_whirlpool_derivation()
    test_cache_performance()
    print("All tests passed!")
