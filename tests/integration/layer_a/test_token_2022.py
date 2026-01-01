"""
V48.0: Unit Tests for Token-2022 Detection
===========================================
Tests for the Token-2022 program detection safety check.

Run: pytest tests/test_token_2022.py -v
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestToken2022Import:
    """Test that Token-2022 constants can be imported."""

    def test_import_program_ids(self):
        """Verify program ID constants are defined."""
        from src.core.validator import TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID

        assert TOKEN_PROGRAM_ID == "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
        assert TOKEN_2022_PROGRAM_ID == "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

    def test_is_token_2022_method_exists(self):
        """Verify is_token_2022 method exists on TokenValidator."""
        from src.core.validator import TokenValidator

        validator = TokenValidator()
        assert hasattr(validator, "is_token_2022")
        assert callable(validator.is_token_2022)


class TestToken2022Detection:
    """Test Token-2022 detection logic."""

    @pytest.fixture
    def mock_validator(self):
        """Create a TokenValidator with mocked RPC."""
        from src.core.validator import TokenValidator

        return TokenValidator()

    def test_standard_spl_token_returns_false(self, mock_validator):
        """Test that standard SPL tokens return False (safe)."""
        from src.core.validator import TOKEN_PROGRAM_ID

        # Mock the RPC response for a standard SPL token
        mock_response = {"result": {"value": {"owner": TOKEN_PROGRAM_ID}}}

        with patch("requests.post") as mock_post:
            mock_post.return_value.json.return_value = mock_response

            result = mock_validator.is_token_2022(
                "So11111111111111111111111111111111111111112"
            )

            assert result is False  # Standard SPL = safe

    def test_token_2022_returns_true(self, mock_validator):
        """Test that Token-2022 tokens return True (blocked)."""
        from src.core.validator import TOKEN_2022_PROGRAM_ID

        # Mock the RPC response for a Token-2022 token
        mock_response = {"result": {"value": {"owner": TOKEN_2022_PROGRAM_ID}}}

        with patch("requests.post") as mock_post:
            mock_post.return_value.json.return_value = mock_response

            result = mock_validator.is_token_2022("SomeToken2022Mint123")

            assert result is True  # Token-2022 = blocked

    def test_rpc_failure_returns_false(self, mock_validator):
        """Test that RPC failures return False (fail open)."""
        with patch("requests.post") as mock_post:
            mock_post.side_effect = Exception("RPC Connection Failed")

            result = mock_validator.is_token_2022("SomeMint123")

            assert result is False  # Fail open = assume safe


class TestPreflightIntegration:
    """Test Token-2022 integration in pre-flight checks."""

    def test_preflight_blocks_token_2022(self):
        """Test that pre-flight check blocks Token-2022 tokens."""
        from src.engine.trade_executor import TradeExecutor
        from src.core.validator import TokenValidator

        # Create executor with mocked dependencies
        mock_validator = MagicMock(spec=TokenValidator)
        mock_validator.is_token_2022 = MagicMock(return_value=True)  # Token-2022

        executor = TradeExecutor(
            engine_name="TEST",
            capital_mgr=MagicMock(),
            paper_wallet=MagicMock(),
            swapper=MagicMock(),
            portfolio=MagicMock(),
            validator=mock_validator,
        )

        # Mock watcher with mint
        mock_watcher = MagicMock()
        mock_watcher.mint = "SomeToken2022Mint"

        can_execute, reason = executor._check_preflight_buy(mock_watcher, 50.0)

        assert can_execute is False
        assert "Token-2022" in reason

    def test_preflight_allows_standard_spl(self):
        """Test that pre-flight allows standard SPL tokens."""
        from src.engine.trade_executor import TradeExecutor
        from src.core.validator import TokenValidator

        # Create executor with mocked dependencies
        mock_validator = MagicMock(spec=TokenValidator)
        mock_validator.is_token_2022 = MagicMock(return_value=False)  # Standard SPL

        mock_paper_wallet = MagicMock()
        mock_paper_wallet.cash_balance = 100.0
        mock_paper_wallet.sol_balance = 0.02
        mock_paper_wallet.assets = {}

        executor = TradeExecutor(
            engine_name="TEST",
            capital_mgr=MagicMock(),
            paper_wallet=mock_paper_wallet,
            swapper=MagicMock(),
            portfolio=MagicMock(),
            validator=mock_validator,
        )

        # Mock watcher
        mock_watcher = MagicMock()
        mock_watcher.mint = "StandardSPLMint"
        mock_watcher.get_liquidity = MagicMock(return_value=500000)  # High liquidity

        can_execute, reason = executor._check_preflight_buy(mock_watcher, 50.0)

        # Token-2022 check should pass, may fail on other checks but not this one
        assert "Token-2022" not in reason


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
