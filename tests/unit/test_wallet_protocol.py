"""
SharedWalletProtocol Unit Tests
===============================
Tests for unified wallet interface.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock


class TestTransactionResult:
    """Test TransactionResult dataclass."""

    def test_success_debit_factory(self):
        """success_debit should create successful result."""
        from src.shared.state.wallet_protocol import TransactionResult, TransactionStatus
        
        result = TransactionResult.success_debit(
            asset="SOL",
            amount=1.0,
            before=2.0,
            after=1.0,
            fee=0.001,
        )
        
        assert result.success
        assert result.status == TransactionStatus.SUCCESS
        assert result.balance_before == 2.0
        assert result.balance_after == 1.0

    def test_insufficient_balance_factory(self):
        """insufficient_balance should create failure result."""
        from src.shared.state.wallet_protocol import TransactionResult, TransactionStatus
        
        result = TransactionResult.insufficient_balance(
            asset="SOL",
            requested=2.0,
            available=1.0,
        )
        
        assert not result.success
        assert result.status == TransactionStatus.INSUFFICIENT_BALANCE
        assert "Insufficient" in result.error_message


class TestVirtualDriver:
    """Test VirtualDriver (paper trading)."""

    @pytest.fixture
    def driver(self, temp_db):
        """Create driver with temp database."""
        from src.shared.state.wallet_protocol import VirtualDriver
        return VirtualDriver(initial_balances={"SOL": 1.0, "USDC": 100.0})

    def test_mode_is_paper(self, driver):
        """mode should be 'paper'."""
        assert driver.mode == "paper"

    def test_get_balance(self, driver):
        """get_balance should return correct balance."""
        assert driver.get_balance("SOL") == 1.0
        assert driver.get_balance("USDC") == 100.0
        assert driver.get_balance("UNKNOWN") == 0.0

    def test_get_all_balances(self, driver):
        """get_all_balances should return all assets."""
        balances = driver.get_all_balances()
        
        assert "SOL" in balances
        assert "USDC" in balances

    def test_get_equity_usd(self, driver):
        """get_equity_usd should calculate total value."""
        prices = {"SOL": 150.0, "USDC": 1.0}
        equity = driver.get_equity_usd(prices)
        
        # 1.0 SOL * 150 + 100 USDC = 250
        assert equity == 250.0

    @pytest.mark.asyncio
    async def test_debit_success(self, driver):
        """debit should reduce balance."""
        result = await driver.debit("SOL", 0.5, reason="TEST")
        
        assert result.success
        assert result.balance_after == 0.5
        assert driver.get_balance("SOL") == 0.5

    @pytest.mark.asyncio
    async def test_debit_insufficient(self, driver):
        """debit should fail if insufficient balance."""
        result = await driver.debit("SOL", 5.0, reason="TEST")
        
        assert not result.success
        assert "Insufficient" in result.error_message
        # Balance unchanged
        assert driver.get_balance("SOL") == 1.0

    @pytest.mark.asyncio
    async def test_credit(self, driver):
        """credit should increase balance."""
        result = await driver.credit("SOL", 0.5, reason="TEST")
        
        assert result.success
        assert result.balance_after == 1.5
        assert driver.get_balance("SOL") == 1.5

    @pytest.mark.asyncio
    async def test_swap(self, driver):
        """swap should atomically exchange assets."""
        # Swap 1 SOL for 150 USDC
        result = await driver.swap(
            from_asset="SOL",
            to_asset="USDC",
            from_amount=0.5,
            to_amount=75.0,
            fee_amount=0.001,
            reason="TEST_SWAP",
        )
        
        assert result.success
        assert driver.get_balance("SOL") == pytest.approx(0.499, rel=0.01)
        assert driver.get_balance("USDC") == 175.0

    def test_reset(self, driver):
        """reset should restore initial state."""
        driver._balances["SOL"] = 0.1  # Modify
        
        driver.reset({"SOL": 2.0, "USDC": 200.0})
        
        assert driver.get_balance("SOL") == 2.0
        assert driver.get_balance("USDC") == 200.0

    def test_transaction_history(self, driver):
        """get_transaction_history should return recent transactions."""
        # Create some transactions
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            driver.debit("SOL", 0.1, reason="TEST1")
        )
        asyncio.get_event_loop().run_until_complete(
            driver.credit("USDC", 10.0, reason="TEST2")
        )
        
        history = driver.get_transaction_history()
        
        assert len(history) >= 2


class TestSolanaDriver:
    """Test SolanaDriver (live trading)."""

    @pytest.fixture
    def mock_wallet_manager(self):
        """Mock WalletManager."""
        wm = MagicMock()
        wm.get_current_live_usd_balance.return_value = {
            "breakdown": {"SOL": 1.5, "USDC": 50.0},
            "assets": [],
        }
        return wm

    @pytest.fixture
    def driver(self, mock_wallet_manager):
        """Create driver with mock."""
        from src.shared.state.wallet_protocol import SolanaDriver
        return SolanaDriver(wallet_manager=mock_wallet_manager)

    def test_mode_is_live(self, driver):
        """mode should be 'live'."""
        assert driver.mode == "live"

    def test_get_balance_from_chain(self, driver):
        """get_balance should fetch from chain."""
        assert driver.get_balance("SOL") == 1.5
        assert driver.get_balance("USDC") == 50.0

    @pytest.mark.asyncio
    async def test_debit_updates_cache(self, driver):
        """debit should update cached balance."""
        _ = driver.get_balance("SOL")  # Prime cache
        
        result = await driver.debit("SOL", 0.5, reason="TEST")
        
        assert result.success
        assert driver._cached_balances["SOL"] == 1.0


class TestWalletFactory:
    """Test wallet factory function."""

    def test_get_paper_wallet(self, temp_db):
        """get_wallet('paper') should return VirtualDriver."""
        from src.shared.state.wallet_protocol import get_wallet, reset_wallets
        
        reset_wallets()
        wallet = get_wallet("paper")
        
        assert wallet.mode == "paper"

    def test_get_live_wallet(self):
        """get_wallet('live') should return SolanaDriver."""
        from src.shared.state.wallet_protocol import get_wallet, reset_wallets
        
        reset_wallets()
        mock_wm = MagicMock()
        mock_wm.get_current_live_usd_balance.return_value = {"breakdown": {}}
        
        wallet = get_wallet("live", wallet_manager=mock_wm)
        
        assert wallet.mode == "live"

    def test_singleton_behavior(self, temp_db):
        """Should return same instance on repeated calls."""
        from src.shared.state.wallet_protocol import get_wallet, reset_wallets
        
        reset_wallets()
        
        w1 = get_wallet("paper")
        w2 = get_wallet("paper")
        
        assert w1 is w2


class TestSystemicParity:
    """Test that paper and live have identical interfaces."""

    @pytest.fixture
    def paper_driver(self, temp_db):
        """Paper driver."""
        from src.shared.state.wallet_protocol import VirtualDriver
        return VirtualDriver({"SOL": 1.0, "USDC": 100.0})

    @pytest.fixture
    def live_driver(self):
        """Live driver with mock."""
        from src.shared.state.wallet_protocol import SolanaDriver
        mock = MagicMock()
        mock.get_current_live_usd_balance.return_value = {
            "breakdown": {"SOL": 1.0, "USDC": 100.0}
        }
        return SolanaDriver(wallet_manager=mock)

    def test_same_interface(self, paper_driver, live_driver):
        """Both drivers should have identical methods."""
        paper_methods = set(m for m in dir(paper_driver) if not m.startswith("_"))
        live_methods = set(m for m in dir(live_driver) if not m.startswith("_"))
        
        # Core methods should match
        core_methods = {"mode", "get_balance", "get_all_balances", "get_equity_usd", 
                       "debit", "credit", "swap", "reset", "get_transaction_history"}
        
        assert core_methods.issubset(paper_methods)
        assert core_methods.issubset(live_methods)

    @pytest.mark.asyncio
    async def test_same_debit_behavior(self, paper_driver, live_driver):
        """Debit should work identically."""
        paper_result = await paper_driver.debit("SOL", 0.5)
        live_result = await live_driver.debit("SOL", 0.5)
        
        assert paper_result.success == live_result.success
        assert paper_result.amount == live_result.amount
