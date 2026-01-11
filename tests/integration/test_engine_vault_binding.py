"""
Engine-Vault Integration Tests
==============================
Verify paper trades correctly debit engine-specific vaults.

This is the critical "Isolation Test" - ensuring that:
1. A $1.00 loss in the Scalp Vault cannot affect the Funding Vault
2. Each engine's PnL is independently tracked
3. Vault state persists correctly
"""

import pytest
import asyncio


class TestVaultIsolation:
    """Test vault isolation between engines."""

    @pytest.fixture(autouse=True)
    def reset_registry(self):
        """Reset VaultRegistry singleton before and after each test."""
        from src.shared.state.vault_manager import VaultRegistry
        VaultRegistry._instance = None
        yield
        VaultRegistry._instance = None

    @pytest.fixture
    def vault_registry(self, temp_db, reset_registry):
        """Get clean vault registry."""
        from src.shared.state.vault_manager import get_vault_registry
        return get_vault_registry()

    def test_different_engines_have_separate_vaults(self, vault_registry):
        """Two engines should have completely isolated vaults."""
        arb_vault = vault_registry.get_vault("arb")
        scalp_vault = vault_registry.get_vault("scalp")
        
        # Modify arb vault
        initial_arb = arb_vault.usdc_balance
        initial_scalp = scalp_vault.usdc_balance
        
        arb_vault.credit("USDC", 1000.0)
        
        # Scalp should be unchanged
        assert scalp_vault.usdc_balance == initial_scalp, (
            "Scalp vault should not change when Arb vault is credited"
        )
        
        # Arb should be updated
        assert arb_vault.usdc_balance == initial_arb + 1000.0

    def test_debit_only_affects_target_vault(self, vault_registry):
        """Debiting one vault should not affect others."""
        funding_vault = vault_registry.get_vault("funding")
        lst_vault = vault_registry.get_vault("lst")
        
        # Credit both
        funding_vault.credit("SOL", 10.0)
        lst_vault.credit("SOL", 5.0)
        
        # Debit only funding
        funding_vault.debit("SOL", 3.0)
        
        # LST should still have full balance
        assert lst_vault.sol_balance == 5.0 + 0.25  # +default
        
        # Funding should be debited
        assert funding_vault.sol_balance == 10.0 + 0.25 - 3.0

    def test_reset_only_affects_target_vault(self, vault_registry):
        """Resetting one vault should not affect others."""
        vault_a = vault_registry.get_vault("engine_alpha")
        vault_b = vault_registry.get_vault("engine_beta")
        
        # Modify both
        vault_a.credit("USDC", 500.0)
        vault_b.credit("USDC", 300.0)
        
        initial_b = vault_b.usdc_balance
        
        # Reset only A
        vault_registry.reset_vault("engine_alpha")
        
        # B should be unchanged
        assert vault_b.usdc_balance == initial_b


class TestPaperTradeExecution:
    """Test paper trade execution debits correct vault."""

    @pytest.fixture
    def mock_engine_with_vault(self, temp_db):
        """Create mock engine with real vault binding."""
        from tests.mocks.mock_engine import MockTradingEngine
        from src.shared.state.vault_manager import get_engine_vault
        
        engine = MockTradingEngine(name="trade_test", live_mode=False)
        engine.paper_wallet = get_engine_vault("trade_test")
        
        return engine

    def test_buy_debits_quote_credits_base(self, mock_engine_with_vault):
        """Buying SOL should debit USDC and credit SOL."""
        vault = mock_engine_with_vault.paper_wallet
        
        # Initial state
        initial_usdc = vault.usdc_balance
        initial_sol = vault.sol_balance
        
        # Simulate buy: spend 100 USDC, get 0.66 SOL (at $150)
        vault.debit("USDC", 100.0)
        vault.credit("SOL", 0.66)
        
        assert vault.usdc_balance == initial_usdc - 100.0
        assert vault.sol_balance == initial_sol + 0.66

    def test_sell_credits_quote_debits_base(self, mock_engine_with_vault):
        """Selling SOL should credit USDC and debit SOL."""
        vault = mock_engine_with_vault.paper_wallet
        
        # Add some SOL first
        vault.credit("SOL", 1.0)
        
        initial_usdc = vault.usdc_balance
        initial_sol = vault.sol_balance
        
        # Simulate sell: sell 0.5 SOL, get 75 USDC (at $150)
        vault.debit("SOL", 0.5)
        vault.credit("USDC", 75.0)
        
        assert vault.sol_balance == initial_sol - 0.5
        assert vault.usdc_balance == initial_usdc + 75.0

    def test_failed_trade_no_vault_change(self, mock_engine_with_vault):
        """Failed trade should not modify vault."""
        vault = mock_engine_with_vault.paper_wallet
        
        initial_usdc = vault.usdc_balance
        
        # Try to debit more than available
        success = vault.debit("USDC", initial_usdc + 1000.0)
        
        assert success is False
        assert vault.usdc_balance == initial_usdc, "Failed debit should not change balance"


class TestCrossEngineOperations:
    """Test operations involving multiple engines."""

    @pytest.fixture
    def multi_engine_setup(self, temp_db):
        """Set up multiple engines with vaults."""
        from src.shared.state.vault_manager import get_vault_registry
        
        registry = get_vault_registry()
        
        engines = {
            "arb": registry.get_vault("arb"),
            "funding": registry.get_vault("funding"),
            "scalp": registry.get_vault("scalp"),
        }
        
        # Give each engine different initial capital
        engines["arb"].credit("USDC", 1000.0)
        engines["funding"].credit("USDC", 5000.0)
        engines["scalp"].credit("USDC", 500.0)
        
        return engines

    def test_global_snapshot_aggregates_correctly(self, multi_engine_setup, temp_db):
        """Global snapshot should sum all vault balances."""
        from src.shared.state.vault_manager import get_vault_registry
        
        registry = get_vault_registry()
        snapshot = registry.get_global_snapshot(sol_price=150.0)
        
        # Total USDC should include all engines + defaults
        total_usdc = snapshot["assets"].get("USDC", 0)
        
        # Should be at least the credited amounts
        assert total_usdc >= 1000.0 + 5000.0 + 500.0, (
            f"Total USDC {total_usdc} should include all engine credits"
        )

    def test_concurrent_operations_thread_safe(self, multi_engine_setup):
        """Concurrent vault operations should be thread-safe."""
        import threading
        import time
        
        vaults = multi_engine_setup
        errors = []
        
        def hammer_vault(vault, iterations):
            try:
                for _ in range(iterations):
                    vault.credit("USDC", 1.0)
                    vault.debit("USDC", 0.5)
            except Exception as e:
                errors.append(str(e))
        
        threads = [
            threading.Thread(target=hammer_vault, args=(vaults["arb"], 50)),
            threading.Thread(target=hammer_vault, args=(vaults["funding"], 50)),
            threading.Thread(target=hammer_vault, args=(vaults["scalp"], 50)),
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"Thread safety errors: {errors}"


class TestVaultPersistence:
    """Test vault state persistence across restarts."""

    def test_vault_survives_restart(self, temp_db):
        """Vault state should persist after registry reset."""
        from src.shared.state.vault_manager import VaultRegistry, get_vault_registry
        
        # Create and modify vault
        registry = get_vault_registry()
        vault = registry.get_vault("persistence_test")
        vault.credit("USDC", 1234.56)
        
        # Simulate restart by resetting singleton
        VaultRegistry._instance = None
        
        # Get fresh registry
        new_registry = get_vault_registry()
        new_vault = new_registry.get_vault("persistence_test")
        
        # Should have persisted balance
        assert new_vault.usdc_balance >= 1234.56, (
            f"Balance should persist: got {new_vault.usdc_balance}"
        )
