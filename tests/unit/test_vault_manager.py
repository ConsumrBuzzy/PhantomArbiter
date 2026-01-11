"""
Vault Manager Unit Tests
========================
Tests for Multi-Vault Architecture isolation guarantees.

Run with: python -m pytest tests/unit/test_vault_manager.py -v
"""

import pytest
import os
import tempfile
from pathlib import Path


class TestVaultRegistry:
    """Test VaultRegistry isolation and operations."""

    @pytest.fixture(autouse=True)
    def use_global_fixture(self, temp_db):
        """Enable temp_db autouse for this class."""
        pass

    def test_vault_isolation_between_engines(self):
        """Two engines with same asset should have independent balances."""
        from src.shared.state.vault_manager import get_vault_registry
        
        registry = get_vault_registry()
        
        # Get vaults for two different engines
        arb_vault = registry.get_vault("arb")
        scalp_vault = registry.get_vault("scalp")
        
        # Credit different amounts to same asset
        arb_vault.credit("USDC", 100.0)
        scalp_vault.credit("USDC", 500.0)
        
        # Verify isolation
        assert arb_vault.balances.get("USDC", 0) != scalp_vault.balances.get("USDC", 0)
        assert arb_vault.usdc_balance > 0
        assert scalp_vault.usdc_balance > arb_vault.usdc_balance

    def test_vault_reset_only_affects_target_engine(self):
        """Resetting one vault should not affect others."""
        from src.shared.state.vault_manager import get_vault_registry
        
        registry = get_vault_registry()
        
        arb_vault = registry.get_vault("arb")
        funding_vault = registry.get_vault("funding")
        
        # Modify both vaults
        arb_vault.credit("SOL", 10.0)
        funding_vault.credit("SOL", 20.0)
        
        initial_funding_sol = funding_vault.sol_balance
        
        # Reset only arb
        registry.reset_vault("arb")
        
        # Funding should be unchanged
        assert funding_vault.sol_balance == initial_funding_sol
        
        # Arb should be back to initial
        arb_vault_fresh = registry.get_vault("arb")
        assert arb_vault_fresh.sol_balance == 0.25  # Default initial

    def test_sync_from_live_copies_balances(self):
        """sync_from_live should mirror live wallet balances into vault."""
        from src.shared.state.vault_manager import get_vault_registry
        
        registry = get_vault_registry()
        vault = registry.get_vault("test_engine")
        
        live_balances = {
            "SOL": 5.5,
            "USDC": 1000.0,
            "JTO": 50.0
        }
        
        vault.sync_from_live(live_balances)
        
        assert vault.sol_balance == 5.5
        assert vault.usdc_balance == 1000.0
        assert vault.balances.get("JTO") == 50.0

    def test_global_snapshot_aggregation(self):
        """get_global_snapshot should correctly aggregate across vaults."""
        from src.shared.state.vault_manager import get_vault_registry
        
        registry = get_vault_registry()
        
        # Create multiple vaults with different balances
        v1 = registry.get_vault("engine_a")
        v2 = registry.get_vault("engine_b")
        
        v1.credit("USDC", 100.0)
        v2.credit("USDC", 200.0)
        v1.credit("SOL", 1.0)
        v2.credit("SOL", 2.0)
        
        snapshot = registry.get_global_snapshot(sol_price=150.0)
        
        # Aggregated USDC should include both + defaults
        assert snapshot["assets"]["USDC"] > 0
        assert snapshot["assets"]["SOL"] > 0
        assert snapshot["total_equity"] > 0

    def test_lazy_instantiation_no_db_bloat(self):
        """Vaults should only be created when accessed."""
        from src.shared.state.vault_manager import get_vault_registry
        
        registry = get_vault_registry()
        
        # Registry starts empty
        assert len(registry._vaults) == 0
        
        # Access one vault
        registry.get_vault("single_engine")
        
        # Only one vault created
        assert len(registry._vaults) == 1

    def test_debit_fails_on_insufficient_balance(self):
        """Debit should return False when balance is insufficient."""
        from src.shared.state.vault_manager import get_vault_registry
        
        registry = get_vault_registry()
        vault = registry.get_vault("broke_engine")
        
        # Try to debit more than available
        initial_usdc = vault.usdc_balance
        result = vault.debit("USDC", initial_usdc + 1000.0)
        
        assert result is False
        assert vault.usdc_balance == initial_usdc  # No change


class TestEngineVault:
    """Test individual EngineVault operations."""

    @pytest.fixture(autouse=True)
    def use_global_fixture(self, temp_db):
        """Enable temp_db autouse for this class."""
        pass

    def test_credit_adds_to_balance(self):
        """Credit should increase balance."""
        from src.shared.state.vault_manager import get_engine_vault
        
        vault = get_engine_vault("test_credit")
        initial = vault.usdc_balance
        
        vault.credit("USDC", 50.0)
        
        assert vault.usdc_balance == initial + 50.0

    def test_debit_subtracts_from_balance(self):
        """Debit should decrease balance when sufficient."""
        from src.shared.state.vault_manager import get_engine_vault
        
        vault = get_engine_vault("test_debit")
        vault.credit("USDC", 100.0)
        before = vault.usdc_balance
        
        result = vault.debit("USDC", 30.0)
        
        assert result is True
        assert vault.usdc_balance == before - 30.0

    def test_get_balances_includes_equity(self):
        """get_balances should calculate equity with SOL price."""
        from src.shared.state.vault_manager import get_engine_vault
        
        vault = get_engine_vault("test_equity")
        vault.credit("USDC", 100.0)
        vault.credit("SOL", 1.0)
        
        balances = vault.get_balances(sol_price=150.0)
        
        # Equity should include USDC + SOL value
        assert balances["equity"] > 100.0
        assert balances["sol_balance"] > 0
        assert "assets" in balances
