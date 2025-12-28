import pytest
from unittest.mock import MagicMock, patch
import sys
import os
sys.path.append(os.getcwd()) # Ensure src is importable

# Mock phantom_core and solders/spl if needed
sys.modules['phantom_core'] = MagicMock()

sys.modules['solders'] = MagicMock()
sys.modules['solders.pubkey'] = MagicMock()
sys.modules['solders.keypair'] = MagicMock()
sys.modules['spl.token.instructions'] = MagicMock()
sys.modules['requests'] = MagicMock() # Mock requests globally

from src.shared.execution.raydium_bridge import RaydiumBridge, RaydiumSwapResult
import requests # Get the mock

# Fake data
POOL_ADDR = "Pool111111111111111111111111111111111111111"
MINT_A = "So11111111111111111111111111111111111111112" # SOL
MINT_B = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v" # USDC

@pytest.fixture
def bridge():
    return RaydiumBridge(bridge_path="dummy")

@patch('src.shared.execution.raydium_bridge.phantom_core')
@patch('src.shared.execution.raydium_bridge.Keypair')
@patch('src.shared.execution.raydium_bridge.get_associated_token_address')
def test_execute_swap_rust_success(mock_gata, mock_keypair, mock_core, bridge):
    """Verify successfully wired execution flow."""
    # 1. Setup Mocks
    mock_requests = sys.modules['requests'] # Access the global mock

    mock_requests.post.side_effect = [
        # Pool Info Response
        MagicMock(json=lambda: {
            "result": {"value": {"data": ["base64data=="]}}
        }),
        # Blockhash Response
        MagicMock(json=lambda: {
            "result": {
                "value": {"blockhash": "hash123"},
                "context": {"slot": 1000}
            }
        }),
        # Send Transaction Response
        MagicMock(json=lambda: {
            "result": "signature_ok_123"
        })
    ]
    
    # Mock Rust Pool Info Parsing
    pool_info_mock = MagicMock()
    pool_info_mock.token_mint_0 = MINT_A
    pool_info_mock.token_mint_1 = MINT_B
    pool_info_mock.token_vault_0 = "VaultA"
    pool_info_mock.token_vault_1 = "VaultB"
    pool_info_mock.amm_config = "Config1"
    pool_info_mock.observation_key = "Obs1"
    pool_info_mock.tick_current = 0
    pool_info_mock.tick_spacing = 10
    pool_info_mock.mint_decimals_0 = 9
    pool_info_mock.mint_decimals_1 = 6
    pool_info_mock.get_price.return_value = 100.0
    
    mock_core.parse_clmm_pool_state.return_value = pool_info_mock
    mock_core.derive_tick_arrays.return_value = ("TickLower", "TickCurr", "TickUpper")
    mock_core.build_raydium_clmm_swap_ix.return_value = b"instruction_bytes"
    mock_core.build_atomic_transaction.return_value = b"transaction_bytes"
    
    # Mock Keys
    mock_kp_instance = MagicMock()
    mock_kp_instance.pubkey.return_value = "PayerPubkey"
    mock_keypair.from_base58_string.return_value = mock_kp_instance
    mock_gata.return_value = "ATA_Addr"

    # 2. Execute
    result = bridge.execute_swap_rust(
        pool_address=POOL_ADDR,
        input_mint=MINT_A, # Selling A -> B
        amount=1.0,
        payer_keypair="SecretKey123"
    )
    
    # 3. Assertions
    assert result.success is True
    assert result.signature == "signature_ok_123"
    
    # Verify Rust calls
    mock_core.parse_clmm_pool_state.assert_called_with(POOL_ADDR, "base64data==")
    
    # Verify Tick Arrays derived
    mock_core.derive_tick_arrays.assert_called_once()
    
    # Verify Instruction Build
    mock_core.build_raydium_clmm_swap_ix.assert_called_once()
    call_kwargs = mock_core.build_raydium_clmm_swap_ix.call_args.kwargs
    
    # Check Plumbing: Vaults for A->B
    assert call_kwargs['input_vault'] == "VaultA"
    assert call_kwargs['output_vault'] == "VaultB"
    assert call_kwargs['amount'] == 1_000_000_000 # 1.0 * 10^9
    
    # Verify Atomic Transaction Build
    mock_core.build_atomic_transaction.assert_called_once()
    assert mock_core.build_atomic_transaction.call_args.kwargs['instruction_payload'] == b"instruction_bytes"
    assert mock_core.build_atomic_transaction.call_args.kwargs['blockhash_b58'] == "hash123"

@patch('src.shared.execution.raydium_bridge.requests')
def test_execute_swap_rust_rpc_failure(mock_requests, bridge):
    """Verify RPC failure handling."""
    mock_requests.post.return_value.json.return_value = {"error": "RPC Fail"}
    
    result = bridge.execute_swap_rust(
        pool_address=POOL_ADDR,
        input_mint=MINT_A,
        amount=1.0,
        payer_keypair="SecretKey123"
    )
    
    assert result.success is False
    assert "Pool account not found" in result.error or "RPC Fail" in str(result.error) # Depends on where it fails

if __name__ == "__main__":
    import unittest
    unittest.main(argv=['first-arg-is-ignored'], exit=False)

