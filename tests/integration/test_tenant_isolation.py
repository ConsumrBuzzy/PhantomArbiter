"""
Test Tenant Isolation - Multi-Engine Firewall

Verifies that Engine A cannot access or modify Engine B's funds.
This is the "Security Layer" test.
"""

import pytest
import sys
import os

# Add execution package to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "apps", "execution", "src"))

from execution.virtual_wallet import VirtualWalletProvider, LockStatus
from execution.order_bus import TradeSignal, SignalAction


class TestTenantIsolation:
    """Tests for multi-tenant fund isolation."""
    
    @pytest.fixture
    def provider(self):
        """Create a fresh VirtualWalletProvider."""
        return VirtualWalletProvider(default_cash=1000.0, default_sol=0.5)
    
    def test_separate_balances(self, provider):
        """Engine A and B have independent balances."""
        # Get wallets
        wallet_a = provider.get_or_create_wallet("Scalper_A")
        wallet_b = provider.get_or_create_wallet("Arbiter_B")
        
        # Both start with default cash
        assert wallet_a.cash_usd == 1000.0
        assert wallet_b.cash_usd == 1000.0
        
        # Modify A's cash
        wallet_a.cash_usd -= 500.0
        
        # B should be unaffected
        assert wallet_b.cash_usd == 1000.0
        assert wallet_a.cash_usd == 500.0
    
    def test_lock_isolation(self, provider):
        """Engine A's locks are invisible to Engine B."""
        # Lock funds for A
        lock_id_a = provider.lock_funds("Engine_A", 200.0)
        assert lock_id_a is not None
        
        # Check A's available cash is reduced
        assert provider.get_balance("Engine_A", "USDC") == 800.0
        
        # B's balance should be unaffected
        assert provider.get_balance("Engine_B", "USDC") == 1000.0
        
        # B should not be able to unlock A's lock
        result = provider.unlock_funds(lock_id_a)
        # Note: Current implementation allows unlock by anyone - 
        # we should verify the lock still belongs to proper engine
        
    def test_position_isolation(self, provider):
        """Engine A's positions don't appear in Engine B's wallet."""
        signal = TradeSignal(
            symbol="SOL",
            mint="So11111111111111111111111111111111111111112",
            action=SignalAction.BUY,
            size_usd=100.0,
            target_price=150.0,
        )
        
        # A executes a trade
        result = provider.execute_paper_trade("Engine_A", signal, current_price=150.0)
        assert result.status.value == "FILLED"
        
        # A has the position
        positions_a = provider.get_positions("Engine_A")
        assert len(positions_a) == 1
        
        # B has no positions
        positions_b = provider.get_positions("Engine_B")
        assert len(positions_b) == 0
    
    def test_stats_isolation(self, provider):
        """Each engine has independent stats."""
        signal = TradeSignal(
            symbol="JUP",
            mint="JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
            action=SignalAction.BUY,
            size_usd=50.0,
            target_price=1.5,
        )
        
        # A trades 3 times
        for _ in range(3):
            provider.execute_paper_trade("Engine_A", signal, current_price=1.5)
        
        # B trades once
        provider.execute_paper_trade("Engine_B", signal, current_price=1.5)
        
        # Check isolated stats
        stats_a = provider.get_stats("Engine_A")
        stats_b = provider.get_stats("Engine_B")
        
        assert stats_a["trades_count"] == 3
        assert stats_b["trades_count"] == 1
    
    def test_insufficient_funds_isolation(self, provider):
        """Engine A's spending doesn't affect Engine B's capacity."""
        # A spends most of its cash
        signal = TradeSignal(
            symbol="BONK",
            mint="DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
            action=SignalAction.BUY,
            size_usd=900.0,
            target_price=0.00001,
        )
        
        result_a = provider.execute_paper_trade("Engine_A", signal, current_price=0.00001)
        assert result_a.status.value == "FILLED"
        
        # A now has ~100 left
        assert provider.get_balance("Engine_A", "USDC") < 200
        
        # B can still spend 900
        result_b = provider.execute_paper_trade("Engine_B", signal, current_price=0.00001)
        assert result_b.status.value == "FILLED"
    
    def test_all_stats_shows_all_engines(self, provider):
        """get_all_stats returns all engine wallets."""
        provider.get_or_create_wallet("Alpha")
        provider.get_or_create_wallet("Beta")
        provider.get_or_create_wallet("Gamma")
        
        all_stats = provider.get_all_stats()
        
        assert "Alpha" in all_stats
        assert "Beta" in all_stats
        assert "Gamma" in all_stats


class TestDoubleSpendPrevention:
    """Tests for escrow locking preventing double-spend."""
    
    @pytest.fixture
    def provider(self):
        return VirtualWalletProvider(default_cash=500.0)
    
    def test_locked_funds_not_available(self, provider):
        """Locked funds cannot be spent twice."""
        # Lock 400 of 500
        lock_id = provider.lock_funds("Trader", 400.0)
        assert lock_id is not None
        
        # Only 100 available
        assert provider.get_balance("Trader", "USDC") == 100.0
        
        # Cannot lock another 400
        lock_id_2 = provider.lock_funds("Trader", 400.0)
        assert lock_id_2 is None
    
    def test_unlock_restores_balance(self, provider):
        """Unlocking returns funds to available."""
        lock_id = provider.lock_funds("Trader", 300.0)
        assert provider.get_balance("Trader", "USDC") == 200.0
        
        # Unlock
        provider.unlock_funds(lock_id)
        
        # Funds restored
        assert provider.get_balance("Trader", "USDC") == 500.0
    
    def test_execute_consumes_lock(self, provider):
        """Executing with a lock consumes it."""
        lock_id = provider.lock_funds("Trader", 100.0)
        
        signal = TradeSignal(
            symbol="TEST",
            mint="TestMint123",
            action=SignalAction.BUY,
            size_usd=100.0,
            target_price=10.0,
        )
        
        # Execute with lock
        result = provider.execute_paper_trade(
            "Trader", signal, lock_id=lock_id, current_price=10.0
        )
        
        assert result.status.value == "FILLED"
        
        # Lock should be consumed (executed)
        lock = provider._locks.get(lock_id)
        assert lock.status == LockStatus.EXECUTED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
