"""
Coinbase Exchange Driver (CDP/JWT Authentication)
==================================================
CCXT-based driver for Coinbase Advanced Trade integration.

Uses the modern Coinbase Cloud (CDP) API with JWT authentication,
which is significantly more secure than legacy key+secret.

Implements the CEX side of the Liquidity Bridge:
- Fetch withdrawable USDC balance
- Execute Solana-network withdrawals to Phantom

Safety Gates:
1. Network Guard: Only Solana network allowed (no ERC20)
2. Dust Floor: Keep $1.00 in CEX for API polling
3. Minimum Bridge: Configurable minimum withdrawal amount
4. Address Whitelist: Only configured Phantom address

V200: Initial implementation with CDP/JWT auth
"""

import os
import time
import asyncio
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from enum import Enum

import ccxt.async_support as ccxt

from src.shared.system.logging import Logger


# ═══════════════════════════════════════════════════════════════════════════════
# RESULT TYPES
# ═══════════════════════════════════════════════════════════════════════════════

class WithdrawalResult(Enum):
    """Withdrawal operation result codes."""
    SUCCESS = "SUCCESS"
    AMOUNT_TOO_SMALL = "AMOUNT_TOO_SMALL"
    BELOW_DUST_FLOOR = "BELOW_DUST_FLOOR"
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    NETWORK_GUARD_FAILED = "NETWORK_GUARD_FAILED"
    ADDRESS_NOT_WHITELISTED = "ADDRESS_NOT_WHITELISTED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    EXCHANGE_ERROR = "EXCHANGE_ERROR"


@dataclass
class BridgeResponse:
    """Result of a bridge operation."""
    success: bool
    result: WithdrawalResult
    message: str
    withdrawal_id: Optional[str] = None
    amount: float = 0.0
    network: str = ""
    timestamp: float = 0.0
    
    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "result": self.result.value,
            "message": self.message,
            "withdrawal_id": self.withdrawal_id,
            "amount": self.amount,
            "network": self.network,
            "timestamp": self.timestamp,
        }


@dataclass
class CEXBalance:
    """CEX balance snapshot."""
    free: float = 0.0      # Available to withdraw
    used: float = 0.0      # In orders / pending
    total: float = 0.0     # free + used
    timestamp: float = 0.0
    
    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


# ═══════════════════════════════════════════════════════════════════════════════
# COINBASE DRIVER
# ═══════════════════════════════════════════════════════════════════════════════

class CoinbaseExchangeDriver:
    """
    CCXT-based driver for Coinbase Advanced Trade with CDP/JWT auth.
    
    Provides:
    - Balance checking (withdrawable USDC)
    - Solana-network withdrawals to Phantom
    
    Usage:
        driver = CoinbaseExchangeDriver()
        usdc = await driver.get_withdrawable_usdc()
        result = await driver.bridge_to_phantom(amount=50.0)
    """
    
    # ─────────────────────────────────────────────────────────────────────────
    # SAFETY CONSTANTS (loaded from env)
    # ─────────────────────────────────────────────────────────────────────────
    ALLOWED_NETWORK = "solana"
    
    def __init__(
        self,
        api_key_name: Optional[str] = None,
        api_private_key: Optional[str] = None,
    ):
        """
        Initialize the Coinbase driver with CDP/JWT credentials.
        
        Args:
            api_key_name: CDP API key name (format: "organizations/.../apiKeys/...")
            api_private_key: EC private key PEM string
        """
        # CDP Credentials (using existing env var names)
        self._api_key_name = api_key_name or os.getenv("COINBASE_CLIENT_API_KEY", "")
        self._api_private_key = api_private_key or os.getenv("COINBASE_API_PRIVATE_KEY", "")
        
        # Handle escaped newlines in private key from .env
        if self._api_private_key:
            self._api_private_key = self._api_private_key.replace("\\n", "\n")
        
        # Bridge Configuration
        self._phantom_address = os.getenv("PHANTOM_SOLANA_ADDRESS", "")
        self._min_bridge_amount = float(os.getenv("MIN_BRIDGE_AMOUNT_USD", "5.0"))
        self._dust_floor = float(os.getenv("CEX_DUST_FLOOR_USD", "1.0"))
        
        # State
        self._exchange: Optional[ccxt.coinbase] = None
        self._last_balance: CEXBalance = CEXBalance()
        self._initialized = False
        self._connection_status = "disconnected"
        
    async def _ensure_exchange(self) -> ccxt.coinbase:
        """
        Lazy-initialize the CCXT exchange instance with CDP/JWT auth.
        
        CCXT handles JWT token generation internally when provided with
        the CDP key name and private key.
        """
        if self._exchange is None:
            if not self._api_key_name or not self._api_private_key:
                raise ValueError(
                    "Coinbase CDP credentials not configured. "
                    "Set COINBASE_CLIENT_API_KEY and COINBASE_API_PRIVATE_KEY in .env"
                )
            
            self._exchange = ccxt.coinbase({
                'apiKey': self._api_key_name,
                'secret': self._api_private_key,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'spot',
                    # CDP auth mode
                    'brokerId': 'CCXT',
                }
            })
            self._initialized = True
            self._connection_status = "connected"
            Logger.info("📡 CoinbaseExchangeDriver initialized (CDP/JWT)")
            
        return self._exchange
    
    # ─────────────────────────────────────────────────────────────────────────
    # BALANCE METHODS
    # ─────────────────────────────────────────────────────────────────────────
    
    async def get_withdrawable_usdc(self) -> float:
        """
        Get USDC available for withdrawal.
        
        Returns:
            float: USDC balance available to withdraw (free balance)
        """
        try:
            exchange = await self._ensure_exchange()
            balance = await exchange.fetch_balance()
            
            usdc_balance = balance.get('USDC', {})
            free_balance = float(usdc_balance.get('free', 0.0))
            
            self._last_balance = CEXBalance(
                free=free_balance,
                used=float(usdc_balance.get('used', 0.0)),
                total=float(usdc_balance.get('total', 0.0)),
            )
            
            Logger.debug(f"💰 Coinbase USDC (free): ${free_balance:.2f}")
            return free_balance
            
        except ccxt.AuthenticationError as e:
            Logger.error(f"❌ Coinbase auth failed: {e}")
            self._connection_status = "auth_error"
            return 0.0
        except ccxt.NetworkError as e:
            Logger.error(f"❌ Coinbase network error: {e}")
            self._connection_status = "network_error"
            return 0.0
        except Exception as e:
            Logger.error(f"❌ Coinbase balance fetch error: {e}")
            self._connection_status = "error"
            return 0.0
    
    async def get_full_balance(self) -> Dict[str, CEXBalance]:
        """
        Get complete balance breakdown for all assets.
        
        Returns:
            Dict mapping asset symbols to CEXBalance objects
        """
        try:
            exchange = await self._ensure_exchange()
            balance = await exchange.fetch_balance()
            
            result = {}
            for symbol in ['USDC', 'USD', 'SOL', 'BTC', 'ETH']:
                asset = balance.get(symbol, {})
                if float(asset.get('total', 0)) > 0:
                    result[symbol] = CEXBalance(
                        free=float(asset.get('free', 0.0)),
                        used=float(asset.get('used', 0.0)),
                        total=float(asset.get('total', 0.0)),
                    )
            
            # Update USDC cache
            if 'USDC' in result:
                self._last_balance = result['USDC']
            
            return result
            
        except Exception as e:
            Logger.error(f"❌ Coinbase full balance error: {e}")
            return {'USDC': CEXBalance()}
    
    async def check_api_connectivity(self) -> Dict[str, Any]:
        """
        Verify API connectivity by fetching balance.
        
        Returns:
            Dict with connection status and balance info
        """
        try:
            balance = await self.get_withdrawable_usdc()
            return {
                "status": "connected",
                "auth_method": "CDP/JWT",
                "usdc_balance": balance,
                "timestamp": time.time(),
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "timestamp": time.time(),
            }
    
    # ─────────────────────────────────────────────────────────────────────────
    # MARKET DATA METHODS (Live Production)
    # ─────────────────────────────────────────────────────────────────────────
    
    async def fetch_ticker(self, symbol: str = "SOL/USDC") -> Dict[str, Any]:
        """
        Fetch current ticker data for a trading pair.
        
        Used by SolTape and engines for real-time price discovery.
        
        Args:
            symbol: Trading pair (default: "SOL/USDC")
            
        Returns:
            Dict with 'last', 'bid', 'ask', 'volume', etc.
        """
        try:
            exchange = await self._ensure_exchange()
            ticker = await exchange.fetch_ticker(symbol)
            
            Logger.debug(
                f"📈 {symbol}: ${ticker['last']:.4f} "
                f"(bid: ${ticker['bid']:.4f}, ask: ${ticker['ask']:.4f})"
            )
            
            return {
                "symbol": symbol,
                "last": ticker.get("last", 0.0),
                "bid": ticker.get("bid", 0.0),
                "ask": ticker.get("ask", 0.0),
                "high": ticker.get("high", 0.0),
                "low": ticker.get("low", 0.0),
                "volume": ticker.get("baseVolume", 0.0),
                "timestamp": ticker.get("timestamp", time.time() * 1000),
                "source": "coinbase",
            }
            
        except ccxt.BadSymbol as e:
            Logger.debug(f"Symbol {symbol} not found on Coinbase: {e}")
            return {"symbol": symbol, "last": 0.0, "error": "symbol_not_found"}
        except Exception as e:
            Logger.error(f"❌ Ticker fetch error: {e}")
            return {"symbol": symbol, "last": 0.0, "error": str(e)}
    
    async def fetch_ohlcv(
        self,
        symbol: str = "SOL/USDC",
        timeframe: str = "1h",
        limit: int = 24,
    ) -> List[List]:
        """
        Fetch OHLCV (candlestick) data for charting.
        
        Used by dashboard for historical price visualization.
        
        Args:
            symbol: Trading pair
            timeframe: Candle interval ("1m", "5m", "15m", "1h", "1d")
            limit: Number of candles to fetch
            
        Returns:
            List of [timestamp, open, high, low, close, volume]
        """
        try:
            exchange = await self._ensure_exchange()
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            
            Logger.debug(f"📊 Fetched {len(ohlcv)} {timeframe} candles for {symbol}")
            return ohlcv
            
        except Exception as e:
            Logger.error(f"❌ OHLCV fetch error: {e}")
            return []
    
    async def get_sol_price(self) -> float:
        """
        Get current SOL price in USD.
        
        Convenience method for engines.
        
        Returns:
            Current SOL/USDC price
        """
        ticker = await self.fetch_ticker("SOL/USDC")
        return ticker.get("last", 0.0)
    
    async def sync_real_balances(self) -> Dict[str, Any]:
        """
        Sync and return all real balances from Coinbase.
        
        Used for "Reality Check" - populates CEXWalletSnapshot
        with actual production data.
        
        Returns:
            Dict with 'usdc', 'usd', 'sol', 'total_usd' and account details
        """
        try:
            exchange = await self._ensure_exchange()
            balance = await exchange.fetch_balance()
            
            # Extract key balances
            usdc = float(balance.get('USDC', {}).get('free', 0.0))
            usd = float(balance.get('USD', {}).get('free', 0.0))
            sol = float(balance.get('SOL', {}).get('free', 0.0))
            
            # Calculate total in USD
            sol_price = await self.get_sol_price()
            sol_value = sol * sol_price if sol_price > 0 else 0.0
            total_usd = usdc + usd + sol_value
            
            result = {
                "usdc": usdc,
                "usd": usd,
                "sol": sol,
                "sol_price": sol_price,
                "sol_value_usd": sol_value,
                "total_usd": total_usd,
                "timestamp": time.time(),
                "source": "coinbase_production",
            }
            
            Logger.info(
                f"💰 Real Balances: USDC=${usdc:.2f} | USD=${usd:.2f} | "
                f"SOL={sol:.4f} (${sol_value:.2f}) | Total=${total_usd:.2f}"
            )
            
            return result
            
        except Exception as e:
            Logger.error(f"❌ Sync real balances error: {e}")
            return {
                "usdc": 0.0,
                "usd": 0.0,
                "sol": 0.0,
                "total_usd": 0.0,
                "error": str(e),
            }
    
    # ─────────────────────────────────────────────────────────────────────────
    # SAFETY GATE VALIDATORS
    # ─────────────────────────────────────────────────────────────────────────
    
    def _validate_network(self, network: str) -> bool:
        """
        Network Guard: Only allow Solana network.
        
        This is a HARD GATE to prevent expensive ERC20 withdrawals.
        Raises ValueError if network is not 'solana'.
        """
        if network.lower() != self.ALLOWED_NETWORK:
            raise ValueError(
                f"NETWORK GUARD FAILED: Network must be '{self.ALLOWED_NETWORK}', "
                f"got '{network}'. ERC20 withdrawals are BLOCKED."
            )
        return True
    
    def _validate_address(self, address: str) -> bool:
        """
        Whitelist Guard: Only allow pre-configured Phantom address.
        
        Address must match PHANTOM_SOLANA_ADDRESS from .env exactly.
        """
        if not self._phantom_address:
            Logger.error("❌ PHANTOM_SOLANA_ADDRESS not configured in .env")
            return False
        if address != self._phantom_address:
            Logger.error(
                f"🚨 Security Alert: Address mismatch! "
                f"Expected: {self._phantom_address[:8]}..., Got: {address[:8]}..."
            )
            return False
        return True
    
    def _validate_amount(self, amount: float) -> bool:
        """
        Minimum Amount Guard: Enforce minimum bridge threshold.
        """
        return amount >= self._min_bridge_amount
    
    async def _validate_dust_floor(self, amount: float) -> bool:
        """
        Dust Floor Guard: Never leave CEX below dust floor.
        """
        current_balance = await self.get_withdrawable_usdc()
        remaining = current_balance - amount
        return remaining >= self._dust_floor
    
    # ─────────────────────────────────────────────────────────────────────────
    # BRIDGE EXECUTION
    # ─────────────────────────────────────────────────────────────────────────
    
    async def bridge_to_phantom(
        self,
        amount: float,
        phantom_address: Optional[str] = None,
        network: str = "solana",
    ) -> BridgeResponse:
        """
        Withdraw USDC from Coinbase to Phantom via Solana network.
        
        Safety Gates Applied (in order):
        1. Configuration Check: API credentials present
        2. Network Guard: Only 'solana' allowed (HARD FAIL on ERC20)
        3. Address Whitelist: Only configured Phantom address
        4. Minimum Amount: Must exceed MIN_BRIDGE_AMOUNT_USD
        5. Dust Floor: Keep CEX_DUST_FLOOR_USD in CEX
        
        Args:
            amount: USDC amount to bridge
            phantom_address: Target address (must match whitelist, or uses env)
            network: Must be 'solana' (enforced, not optional)
            
        Returns:
            BridgeResponse with success status and details
        """
        # Use whitelisted address if not provided
        target_address = phantom_address or self._phantom_address
        
        # ─────────────────────────────────────────────────────────────────
        # SAFETY GATE 0: Configuration Check
        # ─────────────────────────────────────────────────────────────────
        if not self.is_configured:
            return BridgeResponse(
                success=False,
                result=WithdrawalResult.NOT_CONFIGURED,
                message="Coinbase CDP credentials not configured in .env",
            )
        
        # ─────────────────────────────────────────────────────────────────
        # SAFETY GATE 1: Network Guard (HARD FAIL)
        # ─────────────────────────────────────────────────────────────────
        try:
            self._validate_network(network)
        except ValueError as e:
            Logger.error(f"🚨 {e}")
            return BridgeResponse(
                success=False,
                result=WithdrawalResult.NETWORK_GUARD_FAILED,
                message=str(e),
                network=network,
            )
        
        # ─────────────────────────────────────────────────────────────────
        # SAFETY GATE 2: Address Whitelist
        # ─────────────────────────────────────────────────────────────────
        if not self._validate_address(target_address):
            return BridgeResponse(
                success=False,
                result=WithdrawalResult.ADDRESS_NOT_WHITELISTED,
                message="Security Alert: Address not in whitelist. Withdrawal blocked.",
            )
        
        # ─────────────────────────────────────────────────────────────────
        # SAFETY GATE 3: Minimum Amount
        # ─────────────────────────────────────────────────────────────────
        if not self._validate_amount(amount):
            return BridgeResponse(
                success=False,
                result=WithdrawalResult.AMOUNT_TOO_SMALL,
                message=f"Amount ${amount:.2f} below minimum ${self._min_bridge_amount:.2f}",
                amount=amount,
            )
        
        # ─────────────────────────────────────────────────────────────────
        # SAFETY GATE 4: Check Balance
        # ─────────────────────────────────────────────────────────────────
        current_balance = await self.get_withdrawable_usdc()
        if amount > current_balance:
            return BridgeResponse(
                success=False,
                result=WithdrawalResult.INSUFFICIENT_BALANCE,
                message=f"Insufficient balance: ${current_balance:.2f} < ${amount:.2f}",
                amount=amount,
            )
        
        # ─────────────────────────────────────────────────────────────────
        # SAFETY GATE 5: Dust Floor
        # ─────────────────────────────────────────────────────────────────
        if not await self._validate_dust_floor(amount):
            max_withdraw = max(0, current_balance - self._dust_floor)
            return BridgeResponse(
                success=False,
                result=WithdrawalResult.BELOW_DUST_FLOOR,
                message=f"Would leave < ${self._dust_floor:.2f} dust. Max withdrawal: ${max_withdraw:.2f}",
                amount=amount,
            )
        
        # ─────────────────────────────────────────────────────────────────
        # EXECUTE WITHDRAWAL
        # ─────────────────────────────────────────────────────────────────
        try:
            exchange = await self._ensure_exchange()
            
            # CRITICAL: Network parameter forces Solana
            params = {'network': self.ALLOWED_NETWORK}
            
            Logger.info(
                f"🌉 Bridging ${amount:.2f} USDC to Phantom via Solana..."
            )
            
            withdrawal = await exchange.withdraw(
                code='USDC',
                amount=amount,
                address=target_address,
                params=params,
            )
            
            withdrawal_id = withdrawal.get('id', 'unknown')
            Logger.info(f"✅ Bridge initiated: {withdrawal_id}")
            
            return BridgeResponse(
                success=True,
                result=WithdrawalResult.SUCCESS,
                message="Withdrawal initiated successfully",
                withdrawal_id=withdrawal_id,
                amount=amount,
                network=self.ALLOWED_NETWORK,
            )
            
        except ccxt.InsufficientFunds as e:
            return BridgeResponse(
                success=False,
                result=WithdrawalResult.INSUFFICIENT_BALANCE,
                message=f"Insufficient funds: {e}",
                amount=amount,
            )
        except ccxt.InvalidAddress as e:
            return BridgeResponse(
                success=False,
                result=WithdrawalResult.EXCHANGE_ERROR,
                message=f"Invalid address: {e}",
                amount=amount,
            )
        except Exception as e:
            Logger.error(f"❌ Bridge failed: {e}")
            return BridgeResponse(
                success=False,
                result=WithdrawalResult.EXCHANGE_ERROR,
                message=str(e),
                amount=amount,
            )
    
    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────
    
    async def close(self):
        """Close the exchange connection."""
        if self._exchange:
            await self._exchange.close()
            self._exchange = None
            self._initialized = False
            self._connection_status = "disconnected"
    
    @property
    def is_configured(self) -> bool:
        """Check if CDP API credentials are configured."""
        return bool(self._api_key_name and self._api_private_key)
    
    @property
    def last_balance(self) -> CEXBalance:
        """Get last fetched balance (for caching)."""
        return self._last_balance
    
    @property
    def connection_status(self) -> str:
        """Get current connection status."""
        return self._connection_status
    
    @property
    def phantom_address(self) -> str:
        """Get configured Phantom address (first/last 4 chars for privacy)."""
        if self._phantom_address and len(self._phantom_address) > 8:
            return f"{self._phantom_address[:4]}...{self._phantom_address[-4:]}"
        return "not_configured"


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON ACCESS
# ═══════════════════════════════════════════════════════════════════════════════

_driver_instance: Optional[CoinbaseExchangeDriver] = None


def get_coinbase_driver() -> CoinbaseExchangeDriver:
    """Get or create the global CoinbaseExchangeDriver instance."""
    global _driver_instance
    
    if _driver_instance is None:
        _driver_instance = CoinbaseExchangeDriver()
    
    return _driver_instance


def reset_coinbase_driver():
    """Reset the global driver (for testing)."""
    global _driver_instance
    _driver_instance = None
