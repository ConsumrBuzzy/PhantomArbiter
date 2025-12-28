import phantom_core
from solders.transaction import VersionedTransaction
from solders.keypair import Keypair
from solders.hash import Hash
import base58

def test_atomic_builder():
    print("🧪 Testing Atomic V0 Builder & Chaos Shield...")

    # 1. Test CU Estimator
    print("\n[1] Testing CU Estimator...")
    ops = ["raydium_swap_v4", "transfer_spl"]
    cu_limit = phantom_core.estimate_compute_units(
        ops, 
        num_accounts=12, 
        num_signers=1, 
        safety_margin_percent=10.0
    )
    print(f"   Ops: {ops}")
    print(f"   Estimated CU: {cu_limit}")
    
    # Expected: ~80k (Raydium) + 4.5k (Transfer) + overhead ~= 95k-100k
    assert cu_limit > 80000, "CU Limit seems too low for Raydium!"
    print("   ✅ CU Estimator Passed")

    # 2. Test Transaction Build
    print("\n[2] Testing Transaction Build...")
    
    # Mock Data
    payer = Keypair()
    # Random valid blockhash
    blockhash_str = "HighSpeedArbitrageExecution1111111111111111" 
    instruction_data = "Memo: Arbitrage Execution"
    rpc_slot = 1000
    jito_slot = 1000 # No gap

    try:
        # Payer needs to be base58 string of the SECRET KEY for our Rust function
        # solders Keypair string representation is the JSON array usually, need explicit base58
        payer_key_b58 = str(payer) # Solders might default to something else, lets be specific
        # Actually, solders.keypair.Keypair does not verify easily to base58 string in one go.
        # Let's manually encode the secret bytes.
        payer_key_b58 = base58.b58encode(bytes(payer.secret())).decode("ascii")
        
        tx_bytes = phantom_core.build_atomic_transaction(
            instruction_data,
            payer_key_b58,
            blockhash_str,
            rpc_slot,
            jito_slot
        )
        print(f"   Tx Raw Output: {len(tx_bytes)} bytes")
        
        # Verify with Solders (Python binding for Solana Rust SDK)
        # If this parses, our manual Bincode serialization in Rust matches the network standard.
        tx = VersionedTransaction.from_bytes(bytes(tx_bytes))
        print("   ✅ Deserialization Successful (Solders verified)")
        print(f"   Num Signatures: {len(tx.signatures)}")
        print(f"   Message Address: {tx.message.account_keys[0]}")
        
    except Exception as e:
        print(f"   ❌ Build Failed: {e}")
        # Re-raise to see trace
        raise e

    # 3. Test Liveness Check (Should Fail)
    print("\n[3] Testing Liveness Check (Stale Data)...")
    try:
        phantom_core.build_atomic_transaction(
            instruction_data,
            payer_pubkey_str,
            blockhash_str,
            rpc_slot=1000,
            jito_slot=1005 # Gap > 2
        )
        print("   ❌ Liveness Check Failed (Should have raised error)")
    except RuntimeError as e:
        print(f"   ✅ Liveness Check Caught Error: {e}")

if __name__ == "__main__":
    test_atomic_builder()
