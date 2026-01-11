"""
Unit Tests: RebalanceSensor
===========================
Tests the Opportunity-Liquidity Matrix decision logic.

Test Cases:
1. test_high_yield_triggers_bridge - APY > 15%, Phantom low → BRIDGE
2. test_low_yield_stays_idle - APY < 5% → IDLE
3. test_sufficient_phantom_stays_idle - Phantom >= required → IDLE
4. test_cooldown_prevents_bridge - Bridge within 5 min → COOLDOWN
5. test_insufficient_cex_stays_idle - CEX < deficit → IDLE

V200: Initial test suite
"""

import os
import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ═══════════════════════════════════════════════════════════════════════════════
# TEST FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def mock_env():
    """Mock environment variables for all tests."""
    with patch.dict(os.environ, {
        'MIN_BRIDGE_AMOUNT_USD': '5.00',
        'CEX_DUST_FLOOR_USD': '1.00',
    }):
        yield


@pytest.fixture
def reset_singletons():
    """Reset singleton instances between tests."""
    from src.signals.rebalance_sensor import reset_rebalance_sensor
    
    reset_rebalance_sensor()
    yield
    reset_rebalance_sensor()


@pytest.fixture
def sample_opportunity():
    """Create a sample high-yield funding opportunity."""
    from src.signals.rebalance_signal import FundingOpportunitySignal
    
    return FundingOpportunitySignal(
        market="SOL-PERP",
        funding_rate_8h=0.02,  # 0.02% per 8h = ~21.9% APY
        expected_yield_usd=2.50,
        required_capital=100.0,
        time_to_funding_sec=3600,
        direction="SHORT_PERP",
    )


@pytest.fixture
def low_yield_opportunity():
    """Create a low-yield funding opportunity."""
    from src.signals.rebalance_signal import FundingOpportunitySignal
    
    return FundingOpportunitySignal(
        market="SOL-PERP",
        funding_rate_8h=0.001,  # 0.001% per 8h = ~1.1% APY
        expected_yield_usd=0.25,
        required_capital=100.0,
        time_to_funding_sec=3600,
        direction="SHORT_PERP",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 1: HIGH YIELD TRIGGERS BRIDGE
# ═══════════════════════════════════════════════════════════════════════════════

class TestHighYieldTriggersBridge:
    """APY > 15%, Phantom balance low → Should trigger BRIDGE."""
    
    @pytest.mark.asyncio
    async def test_high_yield_insufficient_phantom_triggers_bridge(
        self, mock_env, reset_singletons, sample_opportunity
    ):
        """High yield with low Phantom balance should trigger bridge."""
        from src.signals.rebalance_sensor import RebalanceSensor
        from src.signals.rebalance_signal import RebalanceDecision
        
        sensor = RebalanceSensor()
        
        # Mock callbacks: Phantom has $10, CEX has $200
        sensor.set_balance_callbacks(
            phantom_fn=AsyncMock(return_value=10.0),
            cex_fn=AsyncMock(return_value=200.0),
        )
        sensor.set_bridge_callback(AsyncMock(return_value=MagicMock(withdrawal_id="test_tx")))
        
        evaluation = await sensor.evaluate_opportunity(sample_opportunity)
        
        assert evaluation.decision == RebalanceDecision.BRIDGE
        assert evaluation.bridge_triggered is True
        assert evaluation.bridge_amount > 0
        assert "HIGH YIELD" in evaluation.reason or "Yield" in evaluation.reason
    
    @pytest.mark.asyncio
    async def test_bridge_amount_equals_deficit(
        self, mock_env, reset_singletons, sample_opportunity
    ):
        """Bridge amount should equal the deficit (required - phantom)."""
        from src.signals.rebalance_sensor import RebalanceSensor
        
        sensor = RebalanceSensor()
        
        # Phantom: $25, Required: $100 → Deficit: $75
        sensor.set_balance_callbacks(
            phantom_fn=AsyncMock(return_value=25.0),
            cex_fn=AsyncMock(return_value=200.0),
        )
        sensor.set_bridge_callback(AsyncMock())
        
        evaluation = await sensor.evaluate_opportunity(sample_opportunity)
        
        expected_deficit = 100.0 - 25.0  # $75
        assert evaluation.deficit == expected_deficit
        assert evaluation.bridge_amount == expected_deficit


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 2: LOW YIELD STAYS IDLE
# ═══════════════════════════════════════════════════════════════════════════════

class TestLowYieldStaysIdle:
    """APY < 5% → Should stay IDLE."""
    
    @pytest.mark.asyncio
    async def test_low_yield_stays_idle(
        self, mock_env, reset_singletons, low_yield_opportunity
    ):
        """Low yield opportunity should not trigger bridge."""
        from src.signals.rebalance_sensor import RebalanceSensor
        from src.signals.rebalance_signal import RebalanceDecision
        
        sensor = RebalanceSensor()
        
        sensor.set_balance_callbacks(
            phantom_fn=AsyncMock(return_value=10.0),
            cex_fn=AsyncMock(return_value=200.0),
        )
        
        evaluation = await sensor.evaluate_opportunity(low_yield_opportunity)
        
        assert evaluation.decision == RebalanceDecision.IDLE
        assert evaluation.bridge_triggered is False
        assert "below minimum" in evaluation.reason.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 3: SUFFICIENT PHANTOM STAYS IDLE
# ═══════════════════════════════════════════════════════════════════════════════

class TestSufficientPhantomStaysIdle:
    """Phantom balance >= required → Should stay IDLE."""
    
    @pytest.mark.asyncio
    async def test_sufficient_phantom_stays_idle(
        self, mock_env, reset_singletons, sample_opportunity
    ):
        """When Phantom has enough, no bridge needed."""
        from src.signals.rebalance_sensor import RebalanceSensor
        from src.signals.rebalance_signal import RebalanceDecision
        
        sensor = RebalanceSensor()
        
        # Phantom has $150, required is $100
        sensor.set_balance_callbacks(
            phantom_fn=AsyncMock(return_value=150.0),
            cex_fn=AsyncMock(return_value=200.0),
        )
        
        evaluation = await sensor.evaluate_opportunity(sample_opportunity)
        
        assert evaluation.decision == RebalanceDecision.IDLE
        assert evaluation.bridge_triggered is False
        assert "sufficient" in evaluation.reason.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 4: COOLDOWN PREVENTS BRIDGE
# ═══════════════════════════════════════════════════════════════════════════════

class TestCooldownPreventsBridge:
    """Recent bridge within 5 min → Should return COOLDOWN."""
    
    @pytest.mark.asyncio
    async def test_cooldown_prevents_immediate_second_bridge(
        self, mock_env, reset_singletons, sample_opportunity
    ):
        """Cannot bridge twice within cooldown period."""
        from src.signals.rebalance_sensor import RebalanceSensor
        from src.signals.rebalance_signal import RebalanceDecision
        
        sensor = RebalanceSensor()
        
        sensor.set_balance_callbacks(
            phantom_fn=AsyncMock(return_value=10.0),
            cex_fn=AsyncMock(return_value=200.0),
        )
        sensor.set_bridge_callback(AsyncMock())
        
        # First evaluation should trigger bridge
        eval1 = await sensor.evaluate_opportunity(sample_opportunity)
        assert eval1.decision == RebalanceDecision.BRIDGE
        
        # Second evaluation should hit cooldown
        eval2 = await sensor.evaluate_opportunity(sample_opportunity)
        assert eval2.decision == RebalanceDecision.COOLDOWN
        assert "cooldown" in eval2.reason.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 5: INSUFFICIENT CEX STAYS IDLE
# ═══════════════════════════════════════════════════════════════════════════════

class TestInsufficientCexStaysIdle:
    """CEX balance < deficit → Should stay IDLE."""
    
    @pytest.mark.asyncio
    async def test_insufficient_cex_stays_idle(
        self, mock_env, reset_singletons, sample_opportunity
    ):
        """When CEX can't cover deficit, stay idle."""
        from src.signals.rebalance_sensor import RebalanceSensor
        from src.signals.rebalance_signal import RebalanceDecision
        
        sensor = RebalanceSensor()
        
        # CEX only has $3, which after $1 dust floor = $2 available
        # Required: $100, Phantom: $10, Deficit: $90
        # $2 available < $5 minimum bridge
        sensor.set_balance_callbacks(
            phantom_fn=AsyncMock(return_value=10.0),
            cex_fn=AsyncMock(return_value=3.0),
        )
        
        evaluation = await sensor.evaluate_opportunity(sample_opportunity)
        
        assert evaluation.decision == RebalanceDecision.IDLE
        assert evaluation.bridge_triggered is False
        assert "cex" in evaluation.reason.lower() or "insufficient" in evaluation.reason.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 6: SIGNAL DATACLASS HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

class TestSignalDataclasses:
    """Test signal dataclass helper methods."""
    
    def test_funding_opportunity_annualized_apy(self, sample_opportunity):
        """Test APY calculation: 0.02% per 8h = ~21.9% APY."""
        # 0.02 * 3 (periods/day) * 365 = 21.9
        expected_apy = 0.02 * 3 * 365
        assert abs(sample_opportunity.annualized_apy - expected_apy) < 0.01
    
    def test_funding_opportunity_is_high_yield(self, sample_opportunity, low_yield_opportunity):
        """Test high yield detection (>15% APY)."""
        assert sample_opportunity.is_high_yield is True
        assert low_yield_opportunity.is_high_yield is False
    
    def test_bridge_trigger_to_dict(self):
        """Test BridgeTriggerSignal serialization."""
        from src.signals.rebalance_signal import BridgeTriggerSignal
        
        trigger = BridgeTriggerSignal(
            amount=50.0,
            reason="funding_opportunity",
            withdrawal_id="test_123",
        )
        
        data = trigger.to_dict()
        assert data["amount"] == 50.0
        assert data["reason"] == "funding_opportunity"
        assert data["withdrawal_id"] == "test_123"


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 7: STATS AND STATUS
# ═══════════════════════════════════════════════════════════════════════════════

class TestStatsAndStatus:
    """Test sensor statistics and status reporting."""
    
    @pytest.mark.asyncio
    async def test_stats_increment_on_evaluation(
        self, mock_env, reset_singletons, sample_opportunity
    ):
        """Stats should increment on each evaluation."""
        from src.signals.rebalance_sensor import RebalanceSensor
        
        sensor = RebalanceSensor()
        
        sensor.set_balance_callbacks(
            phantom_fn=AsyncMock(return_value=10.0),
            cex_fn=AsyncMock(return_value=200.0),
        )
        sensor.set_bridge_callback(AsyncMock())
        
        assert sensor.get_stats()["total_evaluations"] == 0
        
        await sensor.evaluate_opportunity(sample_opportunity)
        
        stats = sensor.get_stats()
        assert stats["total_evaluations"] == 1
        assert stats["total_bridges_triggered"] == 1
    
    @pytest.mark.asyncio
    async def test_status_shows_cooldown(
        self, mock_env, reset_singletons, sample_opportunity
    ):
        """Status should indicate cooldown state."""
        from src.signals.rebalance_sensor import RebalanceSensor
        
        sensor = RebalanceSensor()
        
        sensor.set_balance_callbacks(
            phantom_fn=AsyncMock(return_value=10.0),
            cex_fn=AsyncMock(return_value=200.0),
        )
        sensor.set_bridge_callback(AsyncMock())
        
        await sensor.evaluate_opportunity(sample_opportunity)
        
        status = sensor.get_status()
        assert status["in_cooldown"] is True
        assert status["last_bridge_ago_sec"] is not None
