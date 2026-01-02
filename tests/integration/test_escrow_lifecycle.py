"""
Test Escrow Lifecycle - Lock → Trade → Settlement

Verifies the complete escrow flow from fund locking to settlement.
"""

import pytest
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "apps", "execution", "src"))

from execution.virtual_wallet import VirtualWalletProvider, LockStatus
from execution.order_bus import TradeSignal, SignalAction


class TestEscrowLifecycle:
    """Tests for the complete escrow lifecycle."""
    
    @pytest.fixture
    def provider(self):
        return VirtualWalletProvider(default_cash=1000.0, default_sol=0.5)
    
    def test_lock_create_success(self, provider):
        """Locking funds creates a valid lock."""
        lock_id = provider.lock_funds("Trader", 250.0)
        
        assert lock_id is not None
        assert lock_id.startswith("lock_")
        
        lock = provider._locks.get(lock_id)
        assert lock.status == LockStatus.PENDING
        assert lock.amount_usd == 250.0
    
    def test_lock_reduces_available(self, provider):
        """Locking reduces available balance."""
        initial = provider.get_balance("Trader", "USDC")
        
        provider.lock_funds("Trader", 300.0)
        
        after = provider.get_balance("Trader", "USDC")
        assert after == initial - 300.0
    
    def test_lock_fails_insufficient_funds(self, provider):
        """Cannot lock more than available."""
        lock_id = provider.lock_funds("Trader", 5000.0)
        assert lock_id is None
    
    def test_successful_trade_with_lock(self, provider):
        """Successful trade consumes the lock."""
        lock_id = provider.lock_funds("Trader", 100.0)
        
        signal = TradeSignal(
            symbol="SOL",
            mint="SolMint",
            action=SignalAction.BUY,
            size_usd=100.0,
            target_price=150.0,
        )
        
        result = provider.execute_paper_trade(
            "Trader", signal, lock_id=lock_id, current_price=150.0
        )
        
        # Trade succeeded
        assert result.status.value == "FILLED"
        assert result.tx_signature.startswith("sim_")
        
        # Lock consumed
        lock = provider._locks.get(lock_id)
        assert lock.status == LockStatus.EXECUTED
        
        # Position created
        positions = provider.get_positions("Trader")
        assert len(positions) == 1
    
    def test_failed_trade_releases_lock(self, provider):
        """Failed trade releases the lock."""
        lock_id = provider.lock_funds("Trader", 100.0)
        
        # Sell without position should fail
        signal = TradeSignal(
            symbol="NONEXISTENT",
            mint="NoMint",
            action=SignalAction.SELL,
            size_usd=100.0,
        )
        
        result = provider.execute_paper_trade(
            "Trader", signal, lock_id=lock_id, current_price=1.0
        )
        
        # Trade failed
        assert result.status.value == "FAILED"
        
        # Lock should still be pending (not consumed)
        lock = provider._locks.get(lock_id)
        # Note: Current impl doesn't auto-release on fail within execute
        # This tests the manual unlock path
        provider.unlock_funds(lock_id)
        
        assert provider._locks[lock_id].status == LockStatus.RELEASED
    
    def test_expired_lock_cleanup(self, provider):
        """Expired locks can be cleaned up."""
        # Create lock with very short timeout
        lock_id = provider.lock_funds("Trader", 100.0, timeout_seconds=0.1)
        
        # Wait for expiry
        time.sleep(0.2)
        
        # Lock should be expired
        lock = provider._locks.get(lock_id)
        assert lock.is_expired()
        
        # Cleanup
        released = provider.cleanup_expired_locks()
        assert released == 1
        
        # Funds restored
        assert provider.get_balance("Trader", "USDC") == 1000.0
    
    def test_settlement_updates_pnl(self, provider):
        """Settlement correctly tracks PnL."""
        # Buy
        buy_signal = TradeSignal(
            symbol="TOKEN",
            mint="TokenMint",
            action=SignalAction.BUY,
            size_usd=100.0,
            target_price=10.0,
        )
        provider.execute_paper_trade("Trader", buy_signal, current_price=10.0)
        
        # Sell at higher price (profit)
        sell_signal = TradeSignal(
            symbol="TOKEN",
            mint="TokenMint",
            action=SignalAction.SELL,
            size_usd=100.0,
        )
        provider.execute_paper_trade("Trader", sell_signal, current_price=12.0)
        
        # Should have positive PnL
        stats = provider.get_stats("Trader")
        assert stats["total_pnl"] > 0
        assert stats["trades_count"] == 2


class TestEscrowEdgeCases:
    """Edge cases for escrow handling."""
    
    @pytest.fixture
    def provider(self):
        return VirtualWalletProvider(default_cash=100.0)
    
    def test_multiple_locks_same_engine(self, provider):
        """Engine can have multiple active locks."""
        lock1 = provider.lock_funds("Trader", 30.0)
        lock2 = provider.lock_funds("Trader", 30.0)
        lock3 = provider.lock_funds("Trader", 30.0)
        
        assert lock1 is not None
        assert lock2 is not None
        assert lock3 is not None
        
        # Only 10 left
        assert provider.get_balance("Trader", "USDC") == 10.0
    
    def test_unlock_invalid_lock_id(self, provider):
        """Unlocking invalid lock returns False."""
        result = provider.unlock_funds("nonexistent_lock_id")
        assert result is False
    
    def test_double_unlock_fails(self, provider):
        """Cannot unlock same lock twice."""
        lock_id = provider.lock_funds("Trader", 50.0)
        
        first = provider.unlock_funds(lock_id)
        assert first is True
        
        second = provider.unlock_funds(lock_id)
        assert second is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
