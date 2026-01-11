"""
Test Suite: Raydium Bridge Rust Execution (Phase 20.2)
======================================================
Verifies the plumbing of execute_swap_rust:
- ATA Derivation
- Vault Resolution
- Rust Instruction Building Call
- Atomic Transaction Signing
"""

import sys
import os
import pytest
from unittest.mock import MagicMock

import sys
import os
import pytest
from unittest.mock import MagicMock, patch
import importlib

@pytest.fixture(scope="function")
def mock_rust_deps():
    """Setup mocked environment for RaydiumBridge."""
    # Create mocks
    mock_phantom = MagicMock()
    mock_solders = MagicMock()
    mock_solders.pubkey.Pubkey = MagicMock()
    mock_solders.keypair.Keypair = MagicMock()
    
    mock_spl_instructions = MagicMock()
    
    mock_requests = MagicMock()
    mock_logger = MagicMock()

    # Dictionary of modules to patch
    modules = {
        "phantom_core": mock_phantom,
        "solders": mock_solders,
        "solders.pubkey": mock_solders, # simplified
        "solders.keypair": mock_solders, # simplified
        "spl": MagicMock(),
        "spl.token": MagicMock(),
        "spl.token.instructions": mock_spl_instructions,
        "requests": mock_requests,
        "src.shared.system.logging": mock_logger,
    }

    # Apply patch
    with patch.dict(sys.modules, modules):
        # We must import/reload RaydiumBridge while mocks are active
        if "src.shared.execution.raydium_bridge" in sys.modules:
            import src.shared.execution.raydium_bridge
            importlib.reload(src.shared.execution.raydium_bridge)
        else:
            import src.shared.execution.raydium_bridge
        
        from src.shared.execution.raydium_bridge import RaydiumBridge
        
        yield {
            "phantom": mock_phantom,
            "requests": mock_requests,
            "bridge_cls": RaydiumBridge,
            "spl_ix": mock_spl_instructions
        }

# Fake data

# Fake data

POOL_ADDR = "Pool111111111111111111111111111111111111111"
MINT_A = "So11111111111111111111111111111111111111112"  # SOL
MINT_B = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # USDC


@pytest.fixture
def bridge(mock_rust_deps):
    RaydiumBridge = mock_rust_deps["bridge_cls"]
    return RaydiumBridge(bridge_path="dummy")


def test_execute_swap_rust_success(bridge, mock_rust_deps):
    """Verify successfully wired execution flow."""
    mock_requests = mock_rust_deps["requests"]
    mock_phantom = mock_rust_deps["phantom"]
    mock_spl_instructions = mock_rust_deps["spl_ix"]
    
    # Reset mocks
    mock_requests.reset_mock()
    mock_phantom.reset_mock()
    mock_spl_instructions.get_associated_token_address.reset_mock()

    # Setup Mocks logic
    mock_requests.post.side_effect = [
        # Pool Info Response
        MagicMock(json=lambda: {"result": {"value": {"data": ["base64data=="]}}}),
        # Blockhash Response
        MagicMock(
            json=lambda: {
                "result": {"value": {"blockhash": "hash123"}, "context": {"slot": 1000}}
            }
        ),
        # Send Transaction Response
        MagicMock(json=lambda: {"result": "signature_ok_123"}),
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

    mock_phantom.parse_clmm_pool_state.return_value = pool_info_mock
    mock_phantom.derive_tick_arrays.return_value = (
        "TickLower",
        "TickCurr",
        "TickUpper",
    )
    mock_phantom.build_raydium_clmm_swap_ix.return_value = b"instruction_bytes"
    mock_phantom.build_atomic_transaction.return_value = b"transaction_bytes"

    # Mock Keys
    # Keypair mocking simplified in fixture
    mock_spl_instructions.get_associated_token_address.return_value = "ATA_Addr"

    # Execute
    result = bridge.execute_swap_rust(
        pool_address=POOL_ADDR,
        input_mint=MINT_A,  # Selling A -> B
        amount=1.0,
        payer_keypair="SecretKey123",
    )

    if not result.success:
        with open("bridge_error.log", "w") as f:
            f.write(f"Result Error: {result.error}")

    # Assertions
    assert result.success is True
    assert result.signature == "signature_ok_123"

    # ... rest of verify ...

    # Verify Rust calls
    mock_phantom.parse_clmm_pool_state.assert_called_with(POOL_ADDR, "base64data==")

    # Verify Tick Arrays derived
    mock_phantom.derive_tick_arrays.assert_called_once()

    # Verify Instruction Build
    mock_phantom.build_raydium_clmm_swap_ix.assert_called_once()
    call_kwargs = mock_phantom.build_raydium_clmm_swap_ix.call_args.kwargs

    # Check Plumbing: Vaults for A->B
    assert call_kwargs["input_vault"] == "VaultA"
    assert call_kwargs["output_vault"] == "VaultB"
    assert call_kwargs["amount"] == 1_000_000_000  # 1.0 * 10^9

    # Verify Atomic Transaction Build
    mock_phantom.build_atomic_transaction.assert_called_once()
    assert (
        mock_phantom.build_atomic_transaction.call_args.kwargs["instruction_payload"]
        == b"instruction_bytes"
    )
    assert (
        mock_phantom.build_atomic_transaction.call_args.kwargs["blockhash_b58"]
        == "hash123"
    )


def test_execute_swap_rust_rpc_failure(bridge, mock_rust_deps):
    """Verify RPC failure handling."""
    mock_requests = mock_rust_deps["requests"]
    mock_requests.reset_mock()
    mock_requests.post.side_effect = None  # Clear previous side effect
    mock_requests.post.return_value.json.return_value = {"error": "RPC Fail"}

    result = bridge.execute_swap_rust(
        pool_address=POOL_ADDR,
        input_mint=MINT_A,
        amount=1.0,
        payer_keypair="SecretKey123",
    )

    assert result.success is False
    assert "Pool account not found" in result.error or "RPC Fail" in str(result.error)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
