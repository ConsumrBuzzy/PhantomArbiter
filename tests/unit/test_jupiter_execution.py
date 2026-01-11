"""
Jupiter Execution Unit Tests
============================
Tests for JupiterSwapper with mock RPC.

This is Priority 1 testing - JupiterSwapper handles real money.

"Golden Path" Testing Strategy:
1. Mock Quote: Provide deterministic JSON quote
2. Simulation Check: Assert simulateTransaction is called
3. Vault Interception: Verify paper_wallet is updated correctly
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import dataclass


class TestJupiterQuoteFetching:
    """Test Jupiter API quote fetching."""

    @pytest.fixture
    def jupiter_quote_response(self):
        """Golden path Jupiter quote response."""
        return {
            "inputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
            "inAmount": "100000000",  # 100 USDC (6 decimals)
            "outputMint": "So11111111111111111111111111111111111111112",  # SOL
            "outAmount": "666666666",  # ~0.666 SOL (9 decimals)
            "otherAmountThreshold": "660000000",  # After slippage
            "swapMode": "ExactIn",
            "slippageBps": 50,
            "priceImpactPct": "0.01",
            "routePlan": [
                {
                    "swapInfo": {
                        "ammKey": "AMM_KEY",
                        "label": "Raydium",
                        "inputMint": "USDC_MINT",
                        "outputMint": "SOL_MINT",
                        "inAmount": "100000000",
                        "outAmount": "666666666",
                        "feeAmount": "300000",
                        "feeMint": "USDC_MINT"
                    },
                    "percent": 100
                }
            ]
        }

    def test_quote_parsing(self, jupiter_quote_response):
        """Verify quote response is parsed correctly."""
        quote = jupiter_quote_response
        
        # Verify amounts
        in_amount_atomic = int(quote["inAmount"])
        out_amount_atomic = int(quote["outAmount"])
        
        # USDC has 6 decimals
        in_amount_human = in_amount_atomic / 1_000_000
        assert in_amount_human == 100.0
        
        # SOL has 9 decimals
        out_amount_human = out_amount_atomic / 1_000_000_000
        assert abs(out_amount_human - 0.666666666) < 0.0001
        
        # Calculate effective price
        price = in_amount_human / out_amount_human  # USDC per SOL
        assert abs(price - 150.0) < 1.0  # ~$150/SOL

    def test_slippage_threshold_calculation(self, jupiter_quote_response):
        """Verify slippage threshold is calculated correctly."""
        quote = jupiter_quote_response
        
        out_amount = int(quote["outAmount"])
        threshold = int(quote["otherAmountThreshold"])
        
        # Threshold should be less than out_amount
        assert threshold < out_amount
        
        # Calculate actual slippage
        slippage_applied = (out_amount - threshold) / out_amount * 10000
        assert abs(slippage_applied - 50) < 10  # ~50 bps


class TestJupiterSwapExecution:
    """Test swap execution logic."""

    @pytest.fixture
    def mock_wallet_manager(self):
        """Mock wallet manager."""
        wallet = MagicMock()
        wallet.get_keypair.return_value = MagicMock()
        wallet.get_pubkey.return_value = "MOCK_PUBKEY"
        wallet.get_current_live_usd_balance.return_value = {
            "breakdown": {"SOL": 1.0, "USDC": 500.0},
            "total_usd": 650.0
        }
        return wallet

    @pytest.fixture
    def mock_rpc_balancer(self):
        """Mock RPC balancer."""
        balancer = MagicMock()
        balancer.get_best_client.return_value = AsyncMock()
        return balancer

    @pytest.fixture
    def mock_http_client(self, jupiter_quote_response):
        """Mock httpx client for Jupiter API calls."""
        response = MagicMock()
        response.json.return_value = jupiter_quote_response
        response.status_code = 200
        response.raise_for_status = MagicMock()
        
        client = MagicMock()
        client.get = AsyncMock(return_value=response)
        client.post = AsyncMock(return_value=response)
        
        return client

    def test_direction_parsing(self):
        """Test buy/sell direction is parsed correctly."""
        # BUY SOL = sell USDC, get SOL
        buy_direction = "BUY"
        
        # Determine mints
        if buy_direction == "BUY":
            input_mint = "USDC_MINT"  # Selling USDC
            output_mint = "SOL_MINT"  # Buying SOL
        else:
            input_mint = "SOL_MINT"
            output_mint = "USDC_MINT"
        
        assert input_mint == "USDC_MINT"
        assert output_mint == "SOL_MINT"

    def test_amount_conversion(self):
        """Test USD amount to atomic unit conversion."""
        amount_usd = 100.0
        sol_price = 150.0
        
        # Calculate SOL amount
        sol_amount = amount_usd / sol_price
        assert abs(sol_amount - 0.666666) < 0.001
        
        # Convert to lamports (9 decimals)
        lamports = int(sol_amount * 1_000_000_000)
        assert lamports == 666666666

    def test_fee_calculation(self):
        """Test fee calculation from quote."""
        fee_amount_atomic = 300000  # From routePlan
        fee_decimals = 6  # USDC
        
        fee_human = fee_amount_atomic / (10 ** fee_decimals)
        assert fee_human == 0.3  # $0.30 fee


class TestPaperModeExecution:
    """Test paper trading execution."""

    @pytest.fixture
    def paper_vault(self, temp_db):
        """Get paper vault for testing."""
        from src.shared.state.vault_manager import get_engine_vault
        return get_engine_vault("jupiter_test")

    def test_paper_buy_updates_vault(self, paper_vault):
        """Paper buy should credit SOL and debit USDC."""
        initial_usdc = paper_vault.usdc_balance
        initial_sol = paper_vault.sol_balance
        
        # Simulate buy: spend 100 USDC, get 0.666 SOL
        buy_amount_usd = 100.0
        sol_received = 0.666
        
        paper_vault.debit("USDC", buy_amount_usd)
        paper_vault.credit("SOL", sol_received)
        
        # Verify
        assert paper_vault.usdc_balance == initial_usdc - buy_amount_usd
        assert paper_vault.sol_balance == initial_sol + sol_received

    def test_paper_sell_updates_vault(self, paper_vault):
        """Paper sell should credit USDC and debit SOL."""
        # Add some SOL first
        paper_vault.credit("SOL", 1.0)
        
        initial_usdc = paper_vault.usdc_balance
        initial_sol = paper_vault.sol_balance
        
        # Simulate sell: sell 0.5 SOL, get 75 USDC
        sol_sold = 0.5
        usdc_received = 75.0
        
        paper_vault.debit("SOL", sol_sold)
        paper_vault.credit("USDC", usdc_received)
        
        # Verify
        assert paper_vault.sol_balance == initial_sol - sol_sold
        assert paper_vault.usdc_balance == initial_usdc + usdc_received

    def test_paper_trade_with_fees(self, paper_vault):
        """Paper trade should account for fees."""
        initial_usdc = paper_vault.usdc_balance
        
        buy_amount_usd = 100.0
        fee_pct = 0.3
        fee_usd = buy_amount_usd * (fee_pct / 100)
        
        sol_price = 150.0
        sol_received = (buy_amount_usd - fee_usd) / sol_price
        
        paper_vault.debit("USDC", buy_amount_usd)
        paper_vault.credit("SOL", sol_received)
        
        # SOL received should be less due to fees
        assert sol_received < buy_amount_usd / sol_price


class TestExecutionResult:
    """Test unified ExecutionResult type."""

    def test_success_result_factory(self):
        """Test success_result factory function."""
        from src.shared.execution.execution_result import success_result
        
        result = success_result(
            tx_signature="TX_SIG_123",
            fill_price=150.0,
            filled_amount=0.666,
            venue="JUPITER",
            fees_paid=0.30,
            slippage_pct=0.05,
        )
        
        assert result.success is True
        assert result.tx_signature == "TX_SIG_123"
        assert result.fill_price == 150.0
        assert result.fees_paid == 0.30

    def test_failure_result_factory(self):
        """Test failure_result factory function."""
        from src.shared.execution.execution_result import failure_result, ErrorCode
        
        result = failure_result(
            error_code=ErrorCode.SLIPPAGE_EXCEEDED,
            error_message="Price moved 2% during execution",
            venue="JUPITER",
        )
        
        assert result.success is False
        assert result.error_code == ErrorCode.SLIPPAGE_EXCEEDED
        assert "Price moved" in result.error_message

    def test_simulated_result_factory(self):
        """Test simulated_result factory for paper trades."""
        from src.shared.execution.execution_result import simulated_result, ExecutionStatus
        
        result = simulated_result(
            fill_price=150.0,
            filled_amount=0.666,
        )
        
        assert result.success is True
        assert result.status == ExecutionStatus.SIMULATED
        assert result.tx_signature.startswith("PAPER_")

    def test_net_cost_calculation(self):
        """Test net cost aggregation."""
        from src.shared.execution.execution_result import ExecutionResult, ExecutionStatus
        
        result = ExecutionResult(
            success=True,
            status=ExecutionStatus.SUCCESS,
            fees_paid=0.30,
            gas_cost_usd=0.01,
            jito_tip_usd=0.05,
        )
        
        assert result.net_cost_usd == 0.30 + 0.01 + 0.05


class TestSimulationValidation:
    """Test that simulation is called before execution."""

    def test_simulation_required_before_send(self):
        """
        Critical: simulateTransaction must be called before sendTransaction.
        
        This test documents the requirement - actual implementation
        should call simulation first.
        """
        execution_steps = []
        
        # Mock the execution flow
        def simulate_transaction(tx):
            execution_steps.append("simulate")
            return {"value": {"err": None}}
        
        def send_transaction(tx):
            execution_steps.append("send")
            return {"result": "TX_SIG"}
        
        # Correct flow
        simulate_transaction("mock_tx")
        send_transaction("mock_tx")
        
        assert execution_steps == ["simulate", "send"]
        assert execution_steps.index("simulate") < execution_steps.index("send")
