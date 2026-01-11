"""
Unit Tests: Bridge Manager Safety Gates
=======================================
Tests the 4 critical safety gates for the CEX-DEX Liquidity Bridge.

Test Cases:
1. test_network_guard_enforcement - Rejects non-Solana networks
2. test_address_whitelist_mismatch - Blocks unverified addresses
3. test_insufficient_liquidity_gate - Handles low balance gracefully
4. test_successful_solana_bridge - Full success path

V200: Initial test suite
"""

import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from dataclasses import dataclass


# ═══════════════════════════════════════════════════════════════════════════════
# TEST FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def mock_env():
    """Mock environment variables for all tests."""
    with patch.dict(os.environ, {
        'COINBASE_API_KEY_NAME': 'organizations/test-org/apiKeys/test-key',
        'COINBASE_API_PRIVATE_KEY': '-----BEGIN EC PRIVATE KEY-----\ntest_key_data\n-----END EC PRIVATE KEY-----',
        'PHANTOM_SOLANA_ADDRESS': 'PhantomTestAddress123456789',
        'MIN_BRIDGE_AMOUNT_USD': '5.00',
        'CEX_DUST_FLOOR_USD': '1.00',
    }):
        yield


@pytest.fixture
def reset_singletons():
    """Reset singleton instances between tests."""
    from src.drivers.coinbase_driver import reset_coinbase_driver
    from src.drivers.bridge_manager import reset_bridge_manager
    
    reset_coinbase_driver()
    reset_bridge_manager()
    yield
    reset_coinbase_driver()
    reset_bridge_manager()


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 1: NETWORK GUARD ENFORCEMENT
# ═══════════════════════════════════════════════════════════════════════════════

class TestNetworkGuardEnforcement:
    """
    Network Guard: Request withdrawal without network='solana' must FAIL.
    
    This is the most critical safety gate - prevents expensive ERC20 fees.
    """
    
    @pytest.mark.asyncio
    async def test_rejects_erc20_network(self, mock_env, reset_singletons):
        """Withdrawal with network='erc20' should HARD FAIL."""
        from src.drivers.coinbase_driver import (
            CoinbaseExchangeDriver,
            WithdrawalResult,
        )
        
        driver = CoinbaseExchangeDriver()
        
        # Mock the balance check to bypass other gates
        with patch.object(driver, 'get_withdrawable_usdc', new_callable=AsyncMock) as mock_balance:
            mock_balance.return_value = 100.0  # Plenty of balance
            
            # Attempt withdrawal with ERC20 network
            response = await driver.bridge_to_phantom(
                amount=50.0,
                network='erc20'  # WRONG NETWORK
            )
            
            assert response.success is False
            assert response.result == WithdrawalResult.NETWORK_GUARD_FAILED
            assert 'solana' in response.message.lower()
    
    @pytest.mark.asyncio
    async def test_rejects_ethereum_network(self, mock_env, reset_singletons):
        """Withdrawal with network='ethereum' should HARD FAIL."""
        from src.drivers.coinbase_driver import (
            CoinbaseExchangeDriver,
            WithdrawalResult,
        )
        
        driver = CoinbaseExchangeDriver()
        
        with patch.object(driver, 'get_withdrawable_usdc', new_callable=AsyncMock) as mock_balance:
            mock_balance.return_value = 100.0
            
            response = await driver.bridge_to_phantom(
                amount=50.0,
                network='ethereum'
            )
            
            assert response.success is False
            assert response.result == WithdrawalResult.NETWORK_GUARD_FAILED
    
    @pytest.mark.asyncio
    async def test_rejects_empty_network(self, mock_env, reset_singletons):
        """Withdrawal with empty network should HARD FAIL."""
        from src.drivers.coinbase_driver import (
            CoinbaseExchangeDriver,
            WithdrawalResult,
        )
        
        driver = CoinbaseExchangeDriver()
        
        with patch.object(driver, 'get_withdrawable_usdc', new_callable=AsyncMock) as mock_balance:
            mock_balance.return_value = 100.0
            
            response = await driver.bridge_to_phantom(
                amount=50.0,
                network=''  # Empty network
            )
            
            assert response.success is False
            assert response.result == WithdrawalResult.NETWORK_GUARD_FAILED
    
    def test_validate_network_internal(self, mock_env, reset_singletons):
        """Internal network validation raises ValueError for non-Solana."""
        from src.drivers.coinbase_driver import CoinbaseExchangeDriver
        
        driver = CoinbaseExchangeDriver()
        
        # Valid network
        assert driver._validate_network('solana') is True
        assert driver._validate_network('SOLANA') is True
        assert driver._validate_network('Solana') is True
        
        # Invalid networks should raise
        with pytest.raises(ValueError, match="NETWORK GUARD FAILED"):
            driver._validate_network('erc20')
        
        with pytest.raises(ValueError, match="NETWORK GUARD FAILED"):
            driver._validate_network('ethereum')
        
        with pytest.raises(ValueError, match="NETWORK GUARD FAILED"):
            driver._validate_network('')


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 2: ADDRESS WHITELIST MISMATCH
# ═══════════════════════════════════════════════════════════════════════════════

class TestAddressWhitelistMismatch:
    """
    Address Whitelist: Attempt withdrawal to non-whitelisted address must FAIL.
    
    Prevents accidental or malicious withdrawals to wrong addresses.
    """
    
    @pytest.mark.asyncio
    async def test_rejects_non_whitelisted_address(self, mock_env, reset_singletons):
        """Withdrawal to non-whitelisted address should be blocked."""
        from src.drivers.coinbase_driver import (
            CoinbaseExchangeDriver,
            WithdrawalResult,
        )
        
        driver = CoinbaseExchangeDriver()
        
        with patch.object(driver, 'get_withdrawable_usdc', new_callable=AsyncMock) as mock_balance:
            mock_balance.return_value = 100.0
            
            response = await driver.bridge_to_phantom(
                amount=50.0,
                phantom_address='AttackerAddress123456789',  # NOT whitelisted
            )
            
            assert response.success is False
            assert response.result == WithdrawalResult.ADDRESS_NOT_WHITELISTED
            assert 'security' in response.message.lower() or 'whitelist' in response.message.lower()
    
    @pytest.mark.asyncio
    async def test_uses_whitelisted_address_when_not_provided(self, mock_env, reset_singletons):
        """When no address provided, use whitelisted address from .env."""
        from src.drivers.coinbase_driver import CoinbaseExchangeDriver
        
        driver = CoinbaseExchangeDriver()
        
        # The driver should use PHANTOM_SOLANA_ADDRESS from env
        assert driver._phantom_address == 'PhantomTestAddress123456789'
        
        # Validation should pass for whitelisted address
        assert driver._validate_address('PhantomTestAddress123456789') is True
    
    @pytest.mark.asyncio
    async def test_rejects_partial_address_match(self, mock_env, reset_singletons):
        """Address must match exactly, not partially."""
        from src.drivers.coinbase_driver import CoinbaseExchangeDriver
        
        driver = CoinbaseExchangeDriver()
        
        # Partial match should fail
        assert driver._validate_address('PhantomTestAddress') is False
        assert driver._validate_address('PhantomTestAddress123456789_extra') is False


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 3: INSUFFICIENT LIQUIDITY GATE
# ═══════════════════════════════════════════════════════════════════════════════

class TestInsufficientLiquidityGate:
    """
    Insufficient Liquidity: Balance below MIN_BRIDGE should result in IDLE state.
    
    Tests:
    - Balance $4.00, MIN_BRIDGE $5.00 → Should not bridge
    - Balance $6.00, amount $5.00, dust floor $1.00 → Should fail
    """
    
    @pytest.mark.asyncio
    async def test_sensor_detects_insufficient_balance(self, mock_env, reset_singletons):
        """LiquiditySensor should detect insufficient balance."""
        from src.drivers.coinbase_driver import CoinbaseExchangeDriver
        from src.drivers.bridge_manager import LiquiditySensor, LiquiditySnapshot
        
        driver = CoinbaseExchangeDriver()
        sensor = LiquiditySensor(coinbase_driver=driver)
        
        # Simulate $4.00 balance (below $5.00 minimum)
        snapshot = LiquiditySnapshot(cex_usdc=4.00, dex_usdc=0.0)
        
        decision = sensor.evaluate(snapshot)
        
        assert decision.should_bridge is False
        assert 'insufficient' in decision.reason.lower()
    
    @pytest.mark.asyncio
    async def test_manager_stays_idle_on_low_balance(self, mock_env, reset_singletons):
        """BridgeManager should stay IDLE when balance is too low."""
        from src.drivers.coinbase_driver import CoinbaseExchangeDriver
        from src.drivers.bridge_manager import BridgeManager, BridgeState
        
        driver = CoinbaseExchangeDriver()
        
        # Mock low balance
        with patch.object(driver, 'get_withdrawable_usdc', new_callable=AsyncMock) as mock_balance:
            mock_balance.return_value = 4.00  # Below $5.00 minimum
            
            manager = BridgeManager(coinbase_driver=driver)
            result = await manager.check_and_bridge()
            
            assert result is None  # No bridge executed
            assert manager.state == BridgeState.IDLE
    
    @pytest.mark.asyncio
    async def test_rejects_when_dust_floor_violated(self, mock_env, reset_singletons):
        """Withdrawal that would violate dust floor should fail."""
        from src.drivers.coinbase_driver import (
            CoinbaseExchangeDriver,
            WithdrawalResult,
        )
        
        driver = CoinbaseExchangeDriver()
        
        # Mock balance at $6.00
        with patch.object(driver, 'get_withdrawable_usdc', new_callable=AsyncMock) as mock_balance:
            mock_balance.return_value = 6.00
            
            # Try to withdraw $5.50, would leave only $0.50 (below $1.00 dust floor)
            response = await driver.bridge_to_phantom(amount=5.50)
            
            assert response.success is False
            assert response.result == WithdrawalResult.BELOW_DUST_FLOOR
            assert 'dust' in response.message.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 4: SUCCESSFUL SOLANA BRIDGE
# ═══════════════════════════════════════════════════════════════════════════════

class TestSuccessfulSolanaBridge:
    """
    Successful Bridge: Correct address + Correct network + Correct balance.
    
    Should return TXID and update state.
    """
    
    @pytest.mark.asyncio
    async def test_successful_bridge_execution(self, mock_env, reset_singletons):
        """Full success path with mocked CCXT."""
        from src.drivers.coinbase_driver import (
            CoinbaseExchangeDriver,
            WithdrawalResult,
        )
        
        driver = CoinbaseExchangeDriver()
        
        # Mock successful withdrawal
        mock_exchange = AsyncMock()
        mock_exchange.withdraw = AsyncMock(return_value={
            'id': 'withdrawal_12345',
            'status': 'pending',
        })
        mock_exchange.fetch_balance = AsyncMock(return_value={
            'USDC': {'free': 100.0, 'used': 0.0, 'total': 100.0}
        })
        
        with patch.object(driver, '_ensure_exchange', new_callable=AsyncMock) as mock_ensure:
            mock_ensure.return_value = mock_exchange
            
            # Also mock balance check
            with patch.object(driver, 'get_withdrawable_usdc', new_callable=AsyncMock) as mock_balance:
                mock_balance.return_value = 100.0
                
                response = await driver.bridge_to_phantom(
                    amount=25.0,
                    network='solana',
                )
                
                assert response.success is True
                assert response.result == WithdrawalResult.SUCCESS
                assert response.withdrawal_id == 'withdrawal_12345'
                assert response.amount == 25.0
                assert response.network == 'solana'
    
    @pytest.mark.asyncio
    async def test_bridge_manager_success_flow(self, mock_env, reset_singletons):
        """BridgeManager completes full bridge cycle."""
        from src.drivers.coinbase_driver import CoinbaseExchangeDriver
        from src.drivers.bridge_manager import BridgeManager, BridgeState
        
        driver = CoinbaseExchangeDriver()
        
        # Mock high CEX balance, low DEX balance
        with patch.object(driver, 'get_withdrawable_usdc', new_callable=AsyncMock) as mock_balance:
            mock_balance.return_value = 100.0
            
            # Mock successful withdrawal
            mock_response = MagicMock()
            mock_response.success = True
            mock_response.amount = 50.0
            mock_response.withdrawal_id = 'tx_abc123'
            
            with patch.object(driver, 'bridge_to_phantom', new_callable=AsyncMock) as mock_bridge:
                mock_bridge.return_value = mock_response
                
                manager = BridgeManager(coinbase_driver=driver)
                result = await manager.check_and_bridge()
                
                assert result is not None
                assert result.success is True
                assert manager.state == BridgeState.CONFIRMING
                assert manager._bridge_count == 1


# ═══════════════════════════════════════════════════════════════════════════════
# ADDITIONAL EDGE CASE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Additional edge case tests."""
    
    @pytest.mark.asyncio
    async def test_not_configured_returns_error(self, reset_singletons):
        """Driver without credentials should return NOT_CONFIGURED."""
        # Clear env vars
        with patch.dict(os.environ, {}, clear=True):
            from src.drivers.coinbase_driver import (
                CoinbaseExchangeDriver,
                WithdrawalResult,
                reset_coinbase_driver,
            )
            
            reset_coinbase_driver()
            driver = CoinbaseExchangeDriver()
            
            response = await driver.bridge_to_phantom(amount=50.0)
            
            assert response.success is False
            assert response.result == WithdrawalResult.NOT_CONFIGURED
    
    @pytest.mark.asyncio
    async def test_amount_below_minimum(self, mock_env, reset_singletons):
        """Amount below MIN_BRIDGE_AMOUNT_USD should fail."""
        from src.drivers.coinbase_driver import (
            CoinbaseExchangeDriver,
            WithdrawalResult,
        )
        
        driver = CoinbaseExchangeDriver()
        
        with patch.object(driver, 'get_withdrawable_usdc', new_callable=AsyncMock) as mock_balance:
            mock_balance.return_value = 100.0
            
            response = await driver.bridge_to_phantom(amount=2.00)  # Below $5.00 min
            
            assert response.success is False
            assert response.result == WithdrawalResult.AMOUNT_TOO_SMALL
