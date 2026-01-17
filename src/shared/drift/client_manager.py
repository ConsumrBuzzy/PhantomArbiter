"""
Drift Client Manager Singleton
==============================

Singleton pattern for managing a single DriftClient instance across the entire application.
Eliminates HTTP 429 rate limiting by sharing one connection and subscription.

Features:
- Singleton pattern with thread-safe access
- Reference counting for proper cleanup
- Lazy initialization on first use
- Automatic retry logic with exponential backoff
- Cached market data access

Usage:
    # Get shared client
    client = await DriftClientManager.get_client("mainnet")
    
    # Use client for market data
    funding_rate = await DriftClientManager.get_funding_rate("SOL-PERP")
    
    # Release when done
    await DriftClientManager.release_client()
"""

import asyncio
import os
import time
from typing import Optional, Dict, Any, List
import base58

from solders.keypair import Keypair
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed

from src.shared.system.logging import Logger
from src.shared.drift.cache_manager import CacheManager


class DriftClientManager:
    """
    Singleton manager for DriftClient instances.
    
    Ensures only one DriftClient exists per network to prevent rate limiting.
    Provides cached access to market data with automatic retry logic.
    """
    
    _instance: Optional['DriftClientManager'] = None
    _lock = asyncio.Lock()
    
    def __init__(self):
        """Private constructor - use get_client() instead."""
        self._drift_client: Optional[Any] = None
        self._rpc_client: Optional[AsyncClient] = None
        self._wallet: Optional[Any] = None
        self._network: str = "mainnet"
        self._ref_count: int = 0
        self._cache = CacheManager()
        self._initialized: bool = False
    
    @classmethod
    async def get_client(cls, network: str = "mainnet") -> Optional[Any]:
        """
        Get shared DriftClient instance.
        
        Implements lazy initialization and reference counting.
        
        Args:
            network: "mainnet" or "devnet"
        
        Returns:
            DriftClient instance or None if initialization fails
        """
        async with cls._lock:
            # Create singleton instance if needed
            if cls._instance is None:
                cls._instance = cls()
            
            instance = cls._instance
            instance._network = network
            
            # Initialize client if needed
            if not instance._initialized:
                success = await instance._initialize_client()
                if not success:
                    Logger.error("[DriftManager] Failed to initialize client")
                    return None
                instance._initialized = True
            
            # Increment reference count
            instance._ref_count += 1
            Logger.debug(f"[DriftManager] Client acquired, ref_count: {instance._ref_count}")
            
            return instance._drift_client
    
    @classmethod
    async def release_client(cls) -> None:
        """
        Release DriftClient reference.
        
        Decrements reference count and cleans up when count reaches 0.
        """
        async with cls._lock:
            if cls._instance is None:
                return
            
            instance = cls._instance
            instance._ref_count = max(0, instance._ref_count - 1)
            Logger.debug(f"[DriftManager] Client released, ref_count: {instance._ref_count}")
            
            # Cleanup when no more references
            if instance._ref_count == 0:
                await instance._cleanup_client()
                instance._initialized = False
                Logger.info("[DriftManager] Client cleaned up (ref_count = 0)")
    
    @classmethod
    async def get_funding_rate(cls, market: str) -> Optional[Dict[str, Any]]:
        """
        Get funding rate for a market with caching.
        
        Args:
            market: Market symbol (e.g., "SOL-PERP")
        
        Returns:
            Funding rate data or None if unavailable
        """
        if cls._instance is None or not cls._instance._initialized:
            Logger.debug(f"[DriftManager] Client not initialized for funding rate: {market}")
            return None
        
        instance = cls._instance
        cache_key = f"funding:{market}"
        
        # Check cache first
        cached = await instance._cache.get(cache_key)
        if cached is not None:
            return cached
        
        # Fetch from DriftClient
        try:
            # Map market symbols to indices
            MARKET_INDICES = {
                "SOL-PERP": 0, "BTC-PERP": 1, "ETH-PERP": 2,
                "APT-PERP": 3, "1MBONK-PERP": 4, "POL-PERP": 5,
                "ARB-PERP": 6, "DOGE-PERP": 7, "BNB-PERP": 8,
            }
            
            market_index = MARKET_INDICES.get(market)
            if market_index is None:
                return None
            
            if not instance._is_market_subscribed(market_index):
                Logger.debug(f"[DriftManager] Market {market} not subscribed")
                return None
            
            # Get perp market account
            perp_market = instance._drift_client.get_perp_market_account(market_index)
            if not perp_market:
                return None
            
            # Extract funding rate
            funding_rate_hourly = float(perp_market.amm.last_funding_rate) / 1e9
            rate_8h = funding_rate_hourly * 8 * 100  # Convert to percentage
            rate_annual = funding_rate_hourly * 24 * 365 * 100
            
            # Get mark price
            mark_price = float(perp_market.amm.historical_oracle_data.last_oracle_price) / 1e6
            
            result = {
                "rate_8h": rate_8h,
                "rate_annual": rate_annual,
                "is_positive": funding_rate_hourly > 0,
                "mark_price": mark_price
            }
            
            # Cache for 30 seconds
            await instance._cache.set(cache_key, result, ttl=30)
            
            return result
            
        except Exception as e:
            Logger.error(f"[DriftManager] Failed to fetch funding rate for {market}: {e}")
            return None
    
    @classmethod
    async def get_all_perp_markets(cls) -> List[Dict[str, Any]]:
        """
        Get all perpetual markets with caching.
        
        Returns:
            List of market data dictionaries
        """
        if cls._instance is None or not cls._instance._initialized:
            Logger.debug("[DriftManager] Client not initialized for perp markets")
            return []
        
        instance = cls._instance
        cache_key = "markets:all_perp"
        
        # Check cache first
        cached = await instance._cache.get(cache_key)
        if cached is not None:
            return cached
        
        # Fetch from DriftClient
        try:
            markets = []
            
            # Market name mapping
            MARKET_NAMES = {
                0: "SOL-PERP", 1: "BTC-PERP", 2: "ETH-PERP",
                3: "APT-PERP", 4: "1MBONK-PERP", 5: "POL-PERP",
                6: "ARB-PERP", 7: "DOGE-PERP", 8: "BNB-PERP",
            }
            
            # Fetch markets 0-8 (most common)
            for market_index in range(9):
                try:
                    if not instance._is_market_subscribed(market_index):
                        continue
                    
                    perp_market = instance._drift_client.get_perp_market_account(market_index)
                    if not perp_market:
                        continue
                    
                    # Extract market data
                    funding_rate_hourly = float(perp_market.amm.last_funding_rate) / 1e9
                    oracle_price = float(perp_market.amm.historical_oracle_data.last_oracle_price) / 1e6
                    
                    # Get open interest
                    base_asset_amount_long = float(perp_market.amm.base_asset_amount_long) / 1e9
                    base_asset_amount_short = abs(float(perp_market.amm.base_asset_amount_short) / 1e9)
                    open_interest = base_asset_amount_long + base_asset_amount_short
                    
                    markets.append({
                        "marketIndex": market_index,
                        "symbol": MARKET_NAMES.get(market_index, f"MARKET-{market_index}"),
                        "markPrice": oracle_price,
                        "oraclePrice": oracle_price,
                        "fundingRate": funding_rate_hourly,
                        "openInterest": open_interest,
                        "volume24h": 0.0,  # Not available on-chain
                        "baseAssetAmountLong": base_asset_amount_long,
                        "baseAssetAmountShort": base_asset_amount_short,
                    })
                    
                except Exception as e:
                    Logger.debug(f"[DriftManager] Market {market_index} error: {e}")
                    continue
            
            # Cache for 60 seconds
            await instance._cache.set(cache_key, markets, ttl=60)
            
            Logger.debug(f"[DriftManager] Fetched {len(markets)} perp markets")
            return markets
            
        except Exception as e:
            Logger.error(f"[DriftManager] Failed to fetch perp markets: {e}")
            return []
    
    @classmethod
    async def is_initialized(cls) -> bool:
        """Check if DriftClient is initialized."""
        return (cls._instance is not None and 
                cls._instance._initialized and 
                cls._instance._drift_client is not None)
    
    @classmethod
    async def force_reconnect(cls) -> bool:
        """
        Force reconnection to Drift Protocol.
        
        Returns:
            True if reconnection successful, False otherwise
        """
        async with cls._lock:
            if cls._instance is None:
                return False
            
            instance = cls._instance
            
            Logger.info("[DriftManager] Force reconnecting...")
            
            # Cleanup current connection
            await instance._cleanup_client()
            instance._initialized = False
            
            # Wait before reconnecting
            await asyncio.sleep(5)
            
            # Reinitialize
            success = await instance._initialize_client()
            if success:
                instance._initialized = True
                Logger.success("[DriftManager] ✅ Force reconnection successful")
            else:
                Logger.error("[DriftManager] ❌ Force reconnection failed")
            
            return success
    
    async def _initialize_client(self) -> bool:
        """
        Initialize DriftClient with retry logic.
        
        Returns:
            True if successful, False otherwise
        """
        max_retries = 3
        backoff = 1.0
        
        for attempt in range(1, max_retries + 1):
            try:
                Logger.info(f"[DriftManager] Initializing client (attempt {attempt}/{max_retries})...")
                
                # Get RPC URL
                if self._network == "mainnet":
                    rpc_url = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
                else:
                    rpc_url = "https://api.devnet.solana.com"
                
                # Create RPC client
                self._rpc_client = AsyncClient(rpc_url, commitment=Confirmed)
                
                # Get wallet keypair
                private_key = os.getenv("SOLANA_PRIVATE_KEY") or os.getenv("PHANTOM_PRIVATE_KEY")
                if not private_key:
                    Logger.error("[DriftManager] No private key found in environment")
                    return False
                
                secret_bytes = base58.b58decode(private_key)
                keypair = Keypair.from_bytes(secret_bytes)
                
                # Initialize DriftClient
                from driftpy.drift_client import DriftClient
                from driftpy.wallet import Wallet
                
                wallet_obj = Wallet(keypair)
                self._drift_client = DriftClient(
                    self._rpc_client,
                    wallet_obj,
                    env="mainnet" if self._network == "mainnet" else "devnet"
                )
                
                # Subscribe to program accounts
                await self._drift_client.subscribe()
                
                Logger.success(f"[DriftManager] ✅ Client initialized successfully")
                return True
                
            except Exception as e:
                Logger.warning(f"[DriftManager] Initialization attempt {attempt} failed: {e}")
                
                if attempt < max_retries:
                    Logger.info(f"[DriftManager] Retrying in {backoff:.1f}s...")
                    await asyncio.sleep(backoff)
                    backoff *= 2
                else:
                    Logger.error(f"[DriftManager] ❌ Initialization failed after {max_retries} attempts")
                    return False
        
        return False
    
    async def _cleanup_client(self) -> None:
        """Cleanup DriftClient and connections."""
        try:
            if self._drift_client:
                await self._drift_client.unsubscribe()
                self._drift_client = None
            
            if self._rpc_client:
                await self._rpc_client.close()
                self._rpc_client = None
            
            # Clear cache
            await self._cache.clear()
            
            Logger.debug("[DriftManager] Client cleanup completed")
            
        except Exception as e:
            Logger.warning(f"[DriftManager] Cleanup error: {e}")
    
    def _is_market_subscribed(self, market_index: int) -> bool:
        """
        Check if market is subscribed to prevent KeyError.
        
        Args:
            market_index: Market index to check
        
        Returns:
            True if subscribed, False otherwise
        """
        try:
            if not self._drift_client:
                return False
            
            # Try to access the market account
            perp_market = self._drift_client.get_perp_market_account(market_index)
            return perp_market is not None
            
        except (KeyError, AttributeError, IndexError):
            return False
        except Exception as e:
            Logger.debug(f"[DriftManager] Market subscription check failed for {market_index}: {e}")
            return False