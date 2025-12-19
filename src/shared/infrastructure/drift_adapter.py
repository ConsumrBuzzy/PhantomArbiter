"""
Drift Protocol Adapter (Solana Derivatives)
============================================
On-chain perpetuals trading via Drift Protocol on Solana.

Features:
- Uses existing Phantom wallet keypair for signing
- Perpetual futures (LONG/SHORT)
- Delta-neutral strategy support (Landlord)
- Same adapter pattern as dYdX for easy swap

Dependencies:
    pip install driftpy anchorpy

Environment:
    PHANTOM_PRIVATE_KEY or derivation from existing wallet config

Usage:
    adapter = DriftAdapter("mainnet")
    await adapter.connect(keypair)
    result = await adapter.execute_tunnel_test()
"""

import os
import asyncio
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

# Solana imports (already in project)
try:
    from solders.keypair import Keypair
    from solders.pubkey import Pubkey
    from solana.rpc.async_api import AsyncClient
    SOLANA_AVAILABLE = True
except ImportError:
    SOLANA_AVAILABLE = False

# Drift Protocol imports
try:
    from driftpy.drift_client import DriftClient
    from driftpy.accounts import get_perp_market_account, get_user_account
    from driftpy.types import PositionDirection, OrderType, MarketType
    from driftpy.constants.numeric_constants import BASE_PRECISION, QUOTE_PRECISION
    DRIFTPY_AVAILABLE = True
except ImportError:
    DRIFTPY_AVAILABLE = False

from src.system.logging import Logger


@dataclass
class DriftPosition:
    """Represents a position on Drift."""
    market_index: int
    symbol: str
    size: float  # Positive = Long, Negative = Short
    entry_price: float
    unrealized_pnl: float
    leverage: float


class DriftAdapter:
    """
    Solana-native derivatives adapter using Drift Protocol.
    
    Replaces dYdX for on-chain perpetual trading with your Phantom wallet.
    """
    
    # Drift Markets (Common perpetual markets)
    MARKETS = {
        "SOL-PERP": 0,
        "BTC-PERP": 1,
        "ETH-PERP": 2,
        "APT-PERP": 3,
        "ARB-PERP": 4,
    }
    
    # RPC Endpoints
    RPC_ENDPOINTS = {
        "mainnet": "https://api.mainnet-beta.solana.com",
        "devnet": "https://api.devnet.solana.com",
    }
    
    def __init__(self, network: str = "mainnet"):
        """
        Initialize Drift adapter.
        
        Args:
            network: "mainnet" or "devnet"
        """
        self.network = network
        
        # V45.0: RPC Segregation
        # Allow override from env for dedicated Landlord RPC
        env_rpc = os.getenv("DRIFT_RPC_URL")
        if env_rpc:
            self.rpc_url = env_rpc
            if self.network == "mainnet":
                 Logger.info(f"[DRIFT] Using Configured RPC: {self.rpc_url[:15]}...")
        else:
            self.rpc_url = self.RPC_ENDPOINTS.get(network, self.RPC_ENDPOINTS["mainnet"])
        
        self.client: Optional[DriftClient] = None
        self.keypair: Optional[Keypair] = None
        self.connection: Optional[AsyncClient] = None
        
        self._connected = False
        self.can_trade = False
        self.address = None
        
        if not SOLANA_AVAILABLE:
            Logger.warning("[DRIFT] solana/solders not installed")
        if not DRIFTPY_AVAILABLE:
            Logger.warning("[DRIFT] driftpy not installed. Run: pip install driftpy")
    
    async def connect(self, keypair: Keypair = None, private_key_bytes: bytes = None):
        """
        Connect to Drift Protocol with wallet credentials.
        
        Args:
            keypair: Solders Keypair object
            private_key_bytes: Raw 64-byte private key (alternative to keypair)
        """
        if not DRIFTPY_AVAILABLE:
            raise ImportError("driftpy not installed. Run: pip install driftpy anchorpy")
        
        # Get keypair
        if keypair:
            self.keypair = keypair
        elif private_key_bytes:
            self.keypair = Keypair.from_bytes(private_key_bytes)
        else:
            # Try to load from environment
            pk_str = os.getenv("PHANTOM_PRIVATE_KEY", "")
            if pk_str:
                import base58
                self.keypair = Keypair.from_bytes(base58.b58decode(pk_str))
            else:
                raise ValueError("No keypair provided. Set PHANTOM_PRIVATE_KEY or pass keypair.")
        
        self.address = str(self.keypair.pubkey())
        Logger.info(f"[DRIFT] Connecting with wallet: {self.address[:8]}...")
        
        # Create Solana connection
        self.connection = AsyncClient(self.rpc_url)
        
        # Initialize Drift client
        self.client = DriftClient(
            self.connection,
            self.keypair,
            env=self.network
        )
        
        # Subscribe to account updates
        await self.client.subscribe()
        
        self._connected = True
        self.can_trade = True
        
        Logger.info(f"[DRIFT] ✅ Connected to Drift ({self.network}). Address: {self.address[:12]}...")
        print(f"   🌐 Drift Protocol: {self.network} | {self.address[:12]}...")
    
    def connect_sync(self, keypair: Keypair = None):
        """Sync wrapper for connect."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.connect(keypair))
            finally:
                loop.close()
        except Exception as e:
            Logger.warning(f"[DRIFT] Connect failed: {e}")
            self._connected = False
    
    @property
    def is_connected(self) -> bool:
        return self._connected and self.client is not None
    
    # ═══════════════════════════════════════════════════════════════════════
    # MARKET DATA (Read-only, no auth needed)
    # ═══════════════════════════════════════════════════════════════════════
    
    async def get_perp_markets(self) -> List[str]:
        """Get list of available perpetual markets."""
        return list(self.MARKETS.keys())
    
    async def get_mark_price(self, symbol: str) -> Optional[float]:
        """Get current mark price for a perpetual market."""
        if not self.client:
            return None
        
        market_index = self.MARKETS.get(symbol, 0)
        try:
            market = await get_perp_market_account(
                self.client.program, market_index
            )
            # Price is in QUOTE_PRECISION
            return market.amm.last_mark_price_twap / QUOTE_PRECISION
        except Exception as e:
            Logger.warning(f"[DRIFT] Get price error: {e}")
            return None
    
    async def get_funding_rate(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get current funding rate for a perpetual market.
        
        Funding is paid every hour on Drift.
        
        Returns:
            Dict with funding rate info:
            - rate_hourly: Hourly funding rate as percentage
            - rate_8h: 8-hour funding rate (for comparison with CEX)
            - rate_annual: Annualized rate
            - next_payment_ts: Unix timestamp of next funding
            - is_positive: True = longs pay shorts
        """
        if not self.client:
            return None
        
        market_index = self.MARKETS.get(symbol, 0)
        try:
            market = await get_perp_market_account(
                self.client.program, market_index
            )
            
            # Drift stores funding as cumulative, we estimate hourly rate
            # last_funding_rate is in QUOTE_PRECISION (1e6)
            # It's hourly rate × 24 for daily, scaled by 1e6
            last_funding = market.amm.last_funding_rate / 1e9  # Scale down
            
            # Convert to percentage
            rate_hourly = last_funding * 100
            rate_8h = rate_hourly * 8
            rate_annual = rate_hourly * 24 * 365
            
            return {
                "market": symbol,
                "rate_hourly": rate_hourly,
                "rate_8h": rate_8h,  # Comparable to CEX 8h funding
                "rate_annual": rate_annual,
                "is_positive": rate_hourly > 0,  # Positive = longs pay shorts
                "mark_price": market.amm.last_mark_price_twap / QUOTE_PRECISION,
            }
        except Exception as e:
            Logger.warning(f"[DRIFT] Get funding rate error: {e}")
            return None
    
    async def get_time_to_funding(self) -> int:
        """
        Get seconds until next funding payment.
        
        Drift pays funding every hour, on the hour.
        """
        import time
        now = int(time.time())
        next_hour = (now // 3600 + 1) * 3600
        return next_hour - now
    
    # ═══════════════════════════════════════════════════════════════════════
    # ACCOUNT DATA
    # ═══════════════════════════════════════════════════════════════════════

    
    async def get_account_info(self) -> Optional[Dict[str, Any]]:
        """Get user account information (collateral, margin, etc.)."""
        if not self.client or not self.can_trade:
            return None
        
        try:
            user = await self.client.get_user()
            
            return {
                "collateral": user.get_total_collateral() / QUOTE_PRECISION,
                "free_collateral": user.get_free_collateral() / QUOTE_PRECISION,
                "margin_ratio": user.get_margin_ratio() if hasattr(user, 'get_margin_ratio') else 0,
                "leverage": user.get_leverage() / 10000 if hasattr(user, 'get_leverage') else 0,
                "unrealized_pnl": user.get_unrealized_pnl() / QUOTE_PRECISION if hasattr(user, 'get_unrealized_pnl') else 0,
            }
        except Exception as e:
            Logger.warning(f"[DRIFT] Account info error: {e}")
            return None
    
    async def get_positions(self) -> List[DriftPosition]:
        """Get all open perpetual positions."""
        if not self.client or not self.can_trade:
            return []
        
        try:
            user = await self.client.get_user()
            positions = []
            
            for pos in user.get_perp_positions():
                if pos.base_asset_amount != 0:
                    # Find symbol from market index
                    symbol = next(
                        (s for s, idx in self.MARKETS.items() if idx == pos.market_index),
                        f"MARKET-{pos.market_index}"
                    )
                    
                    positions.append(DriftPosition(
                        market_index=pos.market_index,
                        symbol=symbol,
                        size=pos.base_asset_amount / BASE_PRECISION,
                        entry_price=pos.quote_entry_amount / (abs(pos.base_asset_amount) + 1e-10) * BASE_PRECISION / QUOTE_PRECISION,
                        unrealized_pnl=0,  # Would need mark price calc
                        leverage=0
                    ))
            
            return positions
        except Exception as e:
            Logger.warning(f"[DRIFT] Get positions error: {e}")
            return []
    
    # ═══════════════════════════════════════════════════════════════════════
    # ACCOUNT VERIFICATION (Non-destructive health check)
    # ═══════════════════════════════════════════════════════════════════════
    
    async def verify_drift_account(self) -> Dict[str, Any]:
        """
        Non-destructive check for Landlord strategy prerequisites.
        
        Verifies:
        - Drift user account exists
        - Collateral is deposited
        - Account health metrics
        
        Returns:
            Dict with ready status and account details
        """
        if not self.client:
            return {
                "ready": False,
                "message": "❌ Adapter not connected.",
                "collateral": 0,
                "positions": 0
            }
        
        result = {
            "ready": False,
            "message": "",
            "collateral": 0.0,
            "free_collateral": 0.0,
            "margin_ratio": 0.0,
            "positions": 0,
            "address": self.address
        }
        
        try:
            # 1. Check if user account exists
            user = await self.client.get_user()
            if not user:
                result["message"] = "❌ Drift Account NOT FOUND. Initialize account first."
                return result
            
            # 2. Get collateral info
            result["collateral"] = user.get_total_collateral() / QUOTE_PRECISION
            result["free_collateral"] = user.get_free_collateral() / QUOTE_PRECISION
            
            # 3. Get margin ratio if available
            if hasattr(user, 'get_margin_ratio'):
                result["margin_ratio"] = user.get_margin_ratio()
            
            # 4. Count open positions
            positions = user.get_perp_positions()
            result["positions"] = sum(1 for p in positions if p.base_asset_amount != 0)
            
            # 5. Determine readiness
            if result["collateral"] < 1.0:
                result["message"] = f"⚠️ Low collateral: ${result['collateral']:.2f}. Deposit USDC to Drift."
                result["ready"] = False
            else:
                result["ready"] = True
                result["message"] = (
                    f"✅ Drift Account Ready!\n"
                    f"Collateral: ${result['collateral']:.2f}\n"
                    f"Free: ${result['free_collateral']:.2f}\n"
                    f"Positions: {result['positions']}"
                )
            
            return result
            
        except Exception as e:
            result["message"] = f"❌ Verification failed: {e}"
            return result
    
    def verify_drift_account_sync(self) -> Dict[str, Any]:
        """Sync wrapper for verify_drift_account."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.verify_drift_account())
            finally:
                loop.close()
        except Exception as e:
            return {"ready": False, "message": f"Error: {e}"}
    
    # ═══════════════════════════════════════════════════════════════════════
    # TRADING
    # ═══════════════════════════════════════════════════════════════════════
    
    async def place_perp_order(
        self,
        symbol: str,
        direction: str,  # "LONG" or "SHORT"
        size: float,
        order_type: str = "MARKET"
    ) -> Dict[str, Any]:
        """
        Place a perpetual order.
        
        Args:
            symbol: Market symbol (e.g., "SOL-PERP")
            direction: "LONG" or "SHORT"
            size: Position size in base asset
            order_type: "MARKET" or "LIMIT"
        
        Returns:
            Dict with success status and transaction signature
        """
        if not self.client or not self.can_trade:
            return {"success": False, "error": "Not connected"}
        
        market_index = self.MARKETS.get(symbol)
        if market_index is None:
            return {"success": False, "error": f"Unknown market: {symbol}"}
        
        try:
            pos_direction = PositionDirection.Long() if direction.upper() == "LONG" else PositionDirection.Short()
            
            # Convert size to base precision
            base_amount = int(size * BASE_PRECISION)
            
            sig = await self.client.open_position(
                pos_direction,
                base_amount,
                market_index
            )
            
            return {
                "success": True,
                "signature": str(sig),
                "symbol": symbol,
                "direction": direction,
                "size": size
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def close_position(self, symbol: str) -> Dict[str, Any]:
        """Close an entire position for a market."""
        if not self.client or not self.can_trade:
            return {"success": False, "error": "Not connected"}
        
        market_index = self.MARKETS.get(symbol)
        if market_index is None:
            return {"success": False, "error": f"Unknown market: {symbol}"}
        
        try:
            sig = await self.client.close_position(market_index)
            return {"success": True, "signature": str(sig)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ═══════════════════════════════════════════════════════════════════════
    # TUNNEL TEST
    # ═══════════════════════════════════════════════════════════════════════
    
    async def execute_tunnel_test(
        self, 
        symbol: str = "SOL-PERP", 
        size: float = 0.001
    ) -> Dict[str, Any]:
        """
        Execute tiny LONG + immediate SHORT to verify tunnel.
        
        This verifies:
        - Wallet signing works
        - Drift account is initialized
        - Orders execute properly
        - Balance updates correctly
        
        Args:
            symbol: Market to test (default SOL-PERP)
            size: Tiny position size (default 0.001 SOL ~$0.20)
        
        Returns:
            Dict with test results
        """
        if not self.can_trade:
            return {
                "success": False,
                "error": "Adapter not connected with trading credentials."
            }
        
        result = {
            "success": False,
            "symbol": symbol,
            "size": size,
            "open_sig": None,
            "close_sig": None,
            "initial_collateral": 0.0,
            "final_collateral": 0.0,
            "cost": 0.0,
            "message": ""
        }
        
        try:
            # 0. Get initial account state
            account = await self.get_account_info()
            if account:
                result["initial_collateral"] = account.get("collateral", 0)
            print(f"   💰 Initial Collateral: ${result['initial_collateral']:.4f}")
            
            # 1. Open tiny LONG
            print(f"   📈 Opening LONG: {size} {symbol}...")
            open_result = await self.place_perp_order(symbol, "LONG", size)
            
            if not open_result.get("success"):
                result["error"] = f"LONG failed: {open_result.get('error')}"
                return result
            
            result["open_sig"] = open_result.get("signature")
            print(f"   ✅ LONG opened: {result['open_sig'][:16]}...")
            
            # 2. Wait for confirmation
            print("   ⏳ Waiting 3s for confirmation...")
            await asyncio.sleep(3)
            
            # 3. Close position (SHORT to flatten)
            print(f"   📉 Closing position...")
            close_result = await self.close_position(symbol)
            
            if not close_result.get("success"):
                result["error"] = f"CLOSE failed: {close_result.get('error')}"
                result["message"] = "⚠️ Position may still be open!"
                return result
            
            result["close_sig"] = close_result.get("signature")
            print(f"   ✅ Position closed: {result['close_sig'][:16]}...")
            
            # 4. Get final state
            await asyncio.sleep(2)
            final_account = await self.get_account_info()
            if final_account:
                result["final_collateral"] = final_account.get("collateral", 0)
                result["cost"] = result["initial_collateral"] - result["final_collateral"]
            
            result["success"] = True
            result["message"] = (
                f"✅ Drift Tunnel Verified!\n"
                f"Initial: ${result['initial_collateral']:.4f}\n"
                f"Final: ${result['final_collateral']:.4f}\n"
                f"Cost (fees/spread): ${result['cost']:.4f}"
            )
            
            print(f"   {result['message']}")
            return result
            
        except Exception as e:
            result["error"] = str(e)
            result["message"] = f"❌ Test failed: {e}"
            return result
    
    def execute_tunnel_test_sync(self, symbol: str = "SOL-PERP", size: float = 0.001) -> Dict[str, Any]:
        """Sync wrapper for execute_tunnel_test."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.execute_tunnel_test(symbol, size))
            finally:
                loop.close()
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ═══════════════════════════════════════════════════════════════════════
    # SYNC WRAPPERS
    # ═══════════════════════════════════════════════════════════════════════
    
    def get_mark_price_sync(self, symbol: str) -> Optional[float]:
        """Sync wrapper for get_mark_price."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.get_mark_price(symbol))
            finally:
                loop.close()
        except:
            return None
    
    def __repr__(self) -> str:
        mode = "TRADING" if self.can_trade else "READ-ONLY"
        status = "connected" if self._connected else "disconnected"
        addr = f" {self.address[:8]}..." if self.address else ""
        return f"<DriftAdapter {self.network} ({mode}){addr} [{status}]>"


# ═══════════════════════════════════════════════════════════════════════════
# TESTING
# ═══════════════════════════════════════════════════════════════════════════

async def test_drift_adapter():
    """Test the Drift adapter."""
    print("=" * 60)
    print("Drift Protocol Adapter Test")
    print("=" * 60)
    
    adapter = DriftAdapter("devnet")  # Use devnet for testing
    print(f"\n✅ Adapter: {adapter}")
    
    # List markets
    markets = await adapter.get_perp_markets()
    print(f"\n📊 Available Markets: {markets}")
    
    print("\n✅ Basic test complete!")
    print("\n⚠️ To test trading, set PHANTOM_PRIVATE_KEY and call:")
    print("   await adapter.connect()")
    print("   result = await adapter.execute_tunnel_test()")


if __name__ == "__main__":
    asyncio.run(test_drift_adapter())
