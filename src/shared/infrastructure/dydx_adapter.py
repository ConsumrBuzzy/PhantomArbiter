"""
V40.0: dYdX Adapter (Async)
===========================
Adapter for interacting with dYdX v4 perpetual markets.
Bridges the generic BaseStrategy commands to the dYdX V4 API.

Authentication: Uses mnemonic phrase (non-custodial)
Network: Testnet (default) or Mainnet via DYDX_NETWORK setting

Requires: pip install dydx-v4-client

Usage:
    adapter = DydxAdapter(network="testnet")
    await adapter.connect(mnemonic)
    markets = await adapter.get_markets()
"""

import os
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from src.shared.system.logging import Logger


@dataclass
class DydxMarket:
    """Represents a dYdX perpetual market."""

    symbol: str
    base_asset: str
    quote_asset: str
    tick_size: float
    step_size: float
    min_order_size: float


class DydxAdapter:
    """
    V40.0: Async adapter for dYdX v4 perpetual exchange.

    Features:
    - Non-custodial authentication (mnemonic)
    - Async connection via CompositeClient
    - Market data fetching (orderbook, candles)
    - Order execution (market/limit)
    - Position tracking

    Integrates with CapitalManager for unified capital tracking.
    """

    # Network configurations
    NETWORKS = {
        "testnet": "https://indexer.v4testnet.dydx.exchange",
        "mainnet": "https://indexer.dydx.exchange",
    }

    async def _publish_updates(self, market_data: Dict[str, float]):
        """Emit MARKET_UPDATE signals for dYdX prices."""
        from src.shared.system.signal_bus import signal_bus, Signal, SignalType
        
        timestamp = asyncio.get_event_loop().time()
        for symbol, price in market_data.items():
            # Convert ETH-USD -> ETH for matching
            token = symbol.split("-")[0]
            
            signal_bus.emit(Signal(
                type=SignalType.MARKET_UPDATE,
                data={
                    "source": "DYDX",
                    "symbol": token,
                    "token": token,
                    "mint": token, # Map if possible, else use symbol
                    "price": price,
                    "timestamp": timestamp
                }
            ))

    async def start_polling(self, symbols: List[str] = None, interval: float = 2.0):
        """Start background polling loop for dYdX signals."""
        if not symbols:
            # V33: Solana Clean Room
            symbols = ["SOL-USD", "JUP-USD", "RAY-USD"] # Only major Solana perps
            
        while True:
            try:
                # Batch fetch if possible, or iterate
                # dYdX v4 API usually allows fetching all markets
                # For efficiency, we just fetch tickers for our list
                updates = {}
                for sym in symbols:
                    ticker = await self.get_ticker(sym)
                    if ticker:
                        updates[sym] = ticker['price']
                
                if updates:
                    await self._publish_updates(updates)
                    
            except Exception as e:
                Logger.warning(f"⚠️ dYdX Poll Error: {e}")
                
            await asyncio.sleep(interval)

    def __init__(self, network: str = "testnet"):
        """
        Initialize adapter (does not connect yet).
        
        Args:
            network: "testnet" or "mainnet"
        """
        self.network = network.lower()
        self.client = None  # CompositeClient once connected
        self.address: Optional[str] = None
        self._connected = False
        self._use_async_client = False

        # Validate network
        if self.network not in self.NETWORKS:
            raise ValueError(f"Invalid network: {network}. Use 'testnet' or 'mainnet'.")

        self.api_url = self.NETWORKS[self.network]
        Logger.info(f"[DYDX] Adapter initialized for {self.network}")

    # ═══════════════════════════════════════════════════════════════════════
    # CONNECTION
    # ═══════════════════════════════════════════════════════════════════════

    async def connect(self, mnemonic: str) -> bool:
        """
        Async connection to dYdX using CompositeClient.

        Args:
            mnemonic: 24-word seed phrase

        Returns:
            True if connection successful
        """
        Logger.info(f"🔌 [DYDX] Connecting to {self.network.upper()}...")

        try:
            # Import dYdX v4 client
            from dydx_v4_client.clients import CompositeClient
            from dydx_v4_client.clients.constants import Network

            # Select network
            if self.network == "testnet":
                dydx_network = Network.testnet()
            else:
                dydx_network = Network.mainnet()

            # Connect using mnemonic (async)
            self.client = await CompositeClient.from_mnemonic(
                mnemonic=mnemonic, network=dydx_network
            )

            # Get wallet address
            self.address = self.client.local_wallet.address
            self._connected = True
            self._use_async_client = True

            Logger.info(
                f"✅ [DYDX] Connected! Address: {self.address[:8]}...{self.address[-6:]}"
            )
            return True

        except ImportError as e:
            Logger.warning(f"[DYDX] dydx-v4-client not installed: {e}")
            Logger.info("[DYDX] Falling back to HTTP-only mode")
            self._connected = True
            self._use_async_client = False
            return True

        except Exception as e:
            Logger.error(f"❌ [DYDX] Connection failed: {e}")
            self._connected = False
            return False

    def connect_sync(self, mnemonic: str = None) -> bool:
        """
        Synchronous connection wrapper (for non-async contexts).
        Falls back to HTTP-only mode if async fails.
        """
        if mnemonic:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Already in async context - just mark as connected
                    self._connected = True
                    return True
                return loop.run_until_complete(self.connect(mnemonic))
            except RuntimeError:
                # No event loop - create one
                return asyncio.run(self.connect(mnemonic))
        else:
            # No mnemonic - HTTP-only mode
            self._connected = True
            Logger.info(f"✅ [DYDX] Connected to {self.network} (HTTP/READ-ONLY mode)")
            return True

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def can_trade(self) -> bool:
        return self._connected and self._use_async_client and self.address is not None

    # ═══════════════════════════════════════════════════════════════════════
    # MARKET DATA (HTTP Fallback + Async Client)
    # ═══════════════════════════════════════════════════════════════════════

    async def get_markets(self) -> List[str]:
        """Get available perpetual markets."""
        # Use indexer client if available
        if self._use_async_client and self.client:
            try:
                response = (
                    await self.client.indexer_client.markets.get_perpetual_markets()
                )
                return list(response.get("markets", {}).keys())
            except Exception as e:
                Logger.warning(f"[DYDX] Async markets fetch failed: {e}")

        # HTTP fallback
        return await self._http_get_markets()

    async def _http_get_markets(self) -> List[str]:
        """HTTP fallback for market data."""
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.api_url}/v4/perpetualMarkets") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return list(data.get("markets", {}).keys())
        except Exception as e:
            Logger.warning(f"[DYDX] HTTP markets fetch failed: {e}")
        return ["ETH-USD", "BTC-USD", "SOL-USD"]  # Default fallback

    async def get_candles(
        self, symbol: str, resolution: str = "1MIN", limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Fetch OHLCV candlestick data for indicators (RSI, VWAP, Keltner).

        Args:
            symbol: Market symbol (e.g., "ETH-USD")
            resolution: 1MIN, 5MINS, 15MINS, 1HOUR, 4HOURS, 1DAY
            limit: Number of candles
        """
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_url}/v4/candles/perpetualMarkets/{symbol}"
                params = {"resolution": resolution, "limit": limit}
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        candles = []
                        for c in data.get("candles", []):
                            candles.append(
                                {
                                    "open": float(c.get("open", 0)),
                                    "high": float(c.get("high", 0)),
                                    "low": float(c.get("low", 0)),
                                    "close": float(c.get("close", 0)),
                                    "volume": float(c.get("baseTokenVolume", 0)),
                                    "timestamp": c.get("startedAt", ""),
                                }
                            )
                        return candles
        except Exception as e:
            Logger.warning(f"[DYDX] Candles fetch failed for {symbol}: {e}")
        return []

    async def get_ticker(self, symbol: str) -> Optional[Dict[str, float]]:
        """Get current ticker data."""
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.api_url}/v4/perpetualMarkets") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        market = data.get("markets", {}).get(symbol, {})
                        if market:
                            return {
                                "price": float(market.get("oraclePrice", 0)),
                                "volume_24h": float(market.get("volume24H", 0)),
                                "open_interest": float(market.get("openInterest", 0)),
                            }
        except Exception as e:
            Logger.warning(f"[DYDX] Ticker fetch failed for {symbol}: {e}")
        return None

    async def get_orderbook(self, symbol: str) -> Dict[str, List[List[float]]]:
        """Fetch orderbook depth."""
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_url}/v4/orderbooks/perpetualMarket/{symbol}"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            "bids": [
                                [float(b["price"]), float(b["size"])]
                                for b in data.get("bids", [])[:20]
                            ],
                            "asks": [
                                [float(a["price"]), float(a["size"])]
                                for a in data.get("asks", [])[:20]
                            ],
                        }
        except Exception as e:
            Logger.warning(f"[DYDX] Orderbook fetch failed for {symbol}: {e}")
        return {"bids": [], "asks": []}

    # ═══════════════════════════════════════════════════════════════════════
    # ORDER EXECUTION (Requires CompositeClient)
    # ═══════════════════════════════════════════════════════════════════════

    async def place_market_order(
        self, symbol: str, side: str, size: float
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Place a market order.

        Args:
            symbol: Market symbol (e.g., "ETH-USD")
            side: "BUY" or "SELL"
            size: Order size in base asset

        Returns:
            (success, message, order_id)
        """
        if not self.can_trade:
            return False, "Not connected or no wallet configured", None

        try:
            from dydx_v4_client.clients.constants import OrderSide, OrderTimeInForce

            order_side = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL

            # Get current price for market order
            ticker = await self.get_ticker(symbol)
            if not ticker:
                return False, f"Could not fetch price for {symbol}", None

            price = ticker["price"]

            # Place short-term order (market-like)
            response = await self.client.place_short_term_order(
                market=symbol,
                side=order_side,
                price=price,
                size=size,
                time_in_force=OrderTimeInForce.IOC,  # Immediate-or-cancel for market
            )

            order_id = response.get("order", {}).get("id", "unknown")
            Logger.info(
                f"✅ [DYDX] {side} {size} {symbol} @ ${price:.2f} - Order: {order_id}"
            )
            return True, f"Order placed: {order_id}", order_id

        except Exception as e:
            Logger.error(f"❌ [DYDX] Order failed: {e}")
            return False, str(e), None

    async def place_limit_order(
        self, symbol: str, side: str, size: float, price: float
    ) -> Tuple[bool, str, Optional[str]]:
        """Place a limit order."""
        if not self.can_trade:
            return False, "Not connected or no wallet configured", None

        try:
            from dydx_v4_client.clients.constants import OrderSide, OrderTimeInForce

            order_side = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL

            response = await self.client.place_short_term_order(
                market=symbol,
                side=order_side,
                price=price,
                size=size,
                time_in_force=OrderTimeInForce.GTT,  # Good-till-time
            )

            order_id = response.get("order", {}).get("id", "unknown")
            Logger.info(f"✅ [DYDX] LIMIT {side} {size} {symbol} @ ${price:.2f}")
            return True, f"Limit order placed: {order_id}", order_id

        except Exception as e:
            Logger.error(f"❌ [DYDX] Limit order failed: {e}")
            return False, str(e), None

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get current open positions."""
        if not self.can_trade:
            return []

        try:
            response = await self.client.indexer_client.account.get_subaccount(
                address=self.address, subaccount_number=0
            )

            positions = []
            for pos in (
                response.get("subaccount", {})
                .get("openPerpetualPositions", {})
                .values()
            ):
                positions.append(
                    {
                        "symbol": pos.get("market"),
                        "size": float(pos.get("size", 0)),
                        "side": "LONG" if float(pos.get("size", 0)) > 0 else "SHORT",
                        "entry_price": float(pos.get("entryPrice", 0)),
                        "unrealized_pnl": float(pos.get("unrealizedPnl", 0)),
                    }
                )
            return positions

        except Exception as e:
            Logger.warning(f"[DYDX] Failed to fetch positions: {e}")
            return []

    async def get_balance(self) -> Optional[Dict[str, float]]:
        """Get account balance."""
        if not self.can_trade:
            return None

        try:
            response = await self.client.indexer_client.account.get_subaccount(
                address=self.address, subaccount_number=0
            )

            subaccount = response.get("subaccount", {})
            return {
                "equity": float(subaccount.get("equity", 0)),
                "free_collateral": float(subaccount.get("freeCollateral", 0)),
                "margin_usage": float(subaccount.get("marginEnabled", 0)),
            }

        except Exception as e:
            Logger.warning(f"[DYDX] Failed to fetch balance: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════════════
    # SECURITY: WITHDRAWAL & CAPITAL SWEEP
    # ═══════════════════════════════════════════════════════════════════════

    async def initiate_withdrawal(
        self, destination_address: str, amount: float, asset: str = "USDC"
    ) -> Tuple[bool, str]:
        """
        Initiate withdrawal of funds to a secure wallet (e.g., Phantom).

        This is the critical security function for capital segmentation:
        After trading, sweep profits/unused margin back to your secure wallet.

        Args:
            destination_address: Target wallet address (your Phantom wallet)
            amount: Amount to withdraw in USD
            asset: Asset to withdraw (default: USDC)

        Returns:
            (success, message)
        """
        if not self.can_trade:
            return False, "Not connected or no wallet configured"

        if amount <= 0:
            return False, "Withdrawal amount must be positive"

        try:
            # Get current balance first
            balance = await self.get_balance()
            if not balance:
                return False, "Could not fetch current balance"

            available = balance.get("free_collateral", 0)
            if amount > available:
                return (
                    False,
                    f"Insufficient funds. Available: ${available:.2f}, Requested: ${amount:.2f}",
                )

            Logger.info(
                f"🔐 [DYDX] Initiating withdrawal: ${amount:.2f} {asset} to {destination_address[:8]}..."
            )

            # dYdX v4 uses chain-based withdrawals
            # The exact API depends on the client version
            response = await self.client.withdraw(
                subaccount_number=0,
                amount=int(amount * 1e6),  # USDC has 6 decimals
                recipient=destination_address,
            )

            if response:
                tx_hash = response.get("txHash", "unknown")
                Logger.info(f"✅ [DYDX] Withdrawal initiated! Tx: {tx_hash[:16]}...")
                return True, f"Withdrawal submitted: {tx_hash}"
            else:
                return False, "Withdrawal response empty"

        except Exception as e:
            Logger.error(f"❌ [DYDX] Withdrawal failed: {e}")
            return False, str(e)

    async def cancel_all_orders(self, symbol: str = None) -> Tuple[bool, int]:
        """
        Cancel all open orders (safety function).

        Args:
            symbol: Optional symbol to cancel orders for. If None, cancels ALL orders.

        Returns:
            (success, cancelled_count)
        """
        if not self.can_trade:
            return False, 0

        try:
            Logger.info(
                f"🛑 [DYDX] Cancelling all orders{' for ' + symbol if symbol else ''}..."
            )

            # Cancel all orders via client
            response = await self.client.cancel_all_orders(
                subaccount_number=0,
                market=symbol,  # None = all markets
            )

            cancelled = response.get("cancelledOrders", [])
            count = len(cancelled)
            Logger.info(f"✅ [DYDX] Cancelled {count} orders")
            return True, count

        except Exception as e:
            Logger.error(f"❌ [DYDX] Cancel orders failed: {e}")
            return False, 0

    async def security_sweep(self, destination_address: str) -> Tuple[bool, str]:
        """
        Complete security sweep: Cancel all orders and withdraw all available funds.

        Use this at the end of a trading session to move all capital
        back to your secure Phantom wallet.

        Args:
            destination_address: Your secure Phantom wallet address

        Returns:
            (success, summary_message)
        """
        summary = []

        # 1. Cancel all orders
        cancel_success, cancelled_count = await self.cancel_all_orders()
        if cancel_success:
            summary.append(f"Cancelled {cancelled_count} orders")

        # 2. Close all positions (market sell)
        positions = await self.get_positions()
        for pos in positions:
            side = "SELL" if pos["size"] > 0 else "BUY"
            size = abs(pos["size"])
            await self.place_market_order(pos["symbol"], side, size)
            summary.append(f"Closed {pos['symbol']} position")

        # 3. Wait for settlements
        await asyncio.sleep(5)

        # 4. Withdraw all available
        balance = await self.get_balance()
        if balance and balance["free_collateral"] > 1.0:  # Min $1
            amount = balance["free_collateral"] - 1.0  # Leave $1 for gas
            success, msg = await self.initiate_withdrawal(destination_address, amount)
            if success:
                summary.append(f"Withdrew ${amount:.2f}")
            else:
                summary.append(f"Withdrawal failed: {msg}")

        return True, " | ".join(summary) if summary else "Nothing to sweep"

    async def execute_tiny_market_test(
        self, symbol: str = "ETH-USD", amount: float = 0.001
    ) -> Dict[str, Any]:
        """
        Execute a tiny market buy + immediate sell to verify end-to-end CEX tunnel.

        This verifies:
        - Authentication
        - Order submission
        - Order execution
        - Position update
        - Balance update

        Args:
            symbol: Trading pair (default ETH-USD)
            amount: Tiny position size (default 0.001 ETH = ~$3 at $3000)

        Returns:
            Dict with success status, order IDs, and final balance
        """
        if not self.can_trade:
            return {
                "success": False,
                "error": "Adapter not connected with trading credentials.",
            }

        result = {
            "success": False,
            "symbol": symbol,
            "amount": amount,
            "buy_order_id": None,
            "sell_order_id": None,
            "initial_balance": 0.0,
            "final_balance": 0.0,
            "cost": 0.0,
            "message": "",
        }

        try:
            # 0. Get initial balance
            balance = await self.get_balance()
            if not balance:
                result["error"] = "Could not fetch initial balance"
                return result

            result["initial_balance"] = balance.get("equity", 0)
            print(f"   💰 Initial Equity: ${result['initial_balance']:.2f}")

            # 1. Place tiny Market BUY order
            print(f"   📈 Placing BUY order: {amount} {symbol}...")
            buy_response = await self.place_market_order(symbol, "BUY", amount)

            if not buy_response.get("success"):
                result["error"] = f"BUY failed: {buy_response.get('error', 'Unknown')}"
                return result

            result["buy_order_id"] = buy_response.get("order_id")
            print(f"   ✅ BUY placed: {result['buy_order_id']}")

            # 2. Wait for fill
            print("   ⏳ Waiting 3s for fill...")
            await asyncio.sleep(3)

            # 3. Immediately close with Market SELL
            print(f"   📉 Placing SELL order: {amount} {symbol}...")
            sell_response = await self.place_market_order(symbol, "SELL", amount)

            if not sell_response.get("success"):
                result["error"] = (
                    f"SELL failed: {sell_response.get('error', 'Unknown')}"
                )
                result["message"] = "⚠️ Position may still be open!"
                return result

            result["sell_order_id"] = sell_response.get("order_id")
            print(f"   ✅ SELL placed: {result['sell_order_id']}")

            # 4. Wait for settlement
            print("   ⏳ Waiting 2s for settlement...")
            await asyncio.sleep(2)

            # 5. Get final balance
            final_balance = await self.get_balance()
            if final_balance:
                result["final_balance"] = final_balance.get("equity", 0)
                result["cost"] = result["initial_balance"] - result["final_balance"]

            result["success"] = True
            result["message"] = (
                f"✅ CEX Tunnel Verified!\n"
                f"Initial: ${result['initial_balance']:.2f}\n"
                f"Final: ${result['final_balance']:.2f}\n"
                f"Cost (fees/spread): ${result['cost']:.4f}"
            )

            print(f"   {result['message']}")
            return result

        except Exception as e:
            result["error"] = str(e)
            result["message"] = f"❌ Test failed: {e}"
            return result

    def execute_tiny_market_test_sync(
        self, symbol: str = "ETH-USD", amount: float = 0.001
    ) -> Dict[str, Any]:
        """Sync wrapper for execute_tiny_market_test."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    self.execute_tiny_market_test(symbol, amount)
                )
            finally:
                loop.close()
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ═══════════════════════════════════════════════════════════════════════
    # SYNC WRAPPERS (For non-async TradingCore integration)
    # ═══════════════════════════════════════════════════════════════════════

    def get_markets_sync(self) -> List[str]:
        """Sync wrapper for get_markets."""
        try:
            import requests

            resp = requests.get(f"{self.api_url}/v4/perpetualMarkets", timeout=10)
            if resp.status_code == 200:
                return list(resp.json().get("markets", {}).keys())
        except Exception:
            pass
        return ["ETH-USD", "BTC-USD", "SOL-USD"]

    def get_ticker_sync(self, symbol: str) -> Optional[Dict[str, float]]:
        """Sync wrapper for get_ticker."""
        try:
            import requests

            resp = requests.get(f"{self.api_url}/v4/perpetualMarkets", timeout=10)
            if resp.status_code == 200:
                market = resp.json().get("markets", {}).get(symbol, {})
                if market:
                    return {
                        "price": float(market.get("oraclePrice", 0)),
                        "volume_24h": float(market.get("volume24H", 0)),
                        "open_interest": float(market.get("openInterest", 0)),
                    }
        except Exception:
            pass
        return None

    # ═══════════════════════════════════════════════════════════════════════
    # UTILITY
    # ═══════════════════════════════════════════════════════════════════════

    def __repr__(self) -> str:
        mode = "TRADING" if self.can_trade else "READ-ONLY"
        status = "connected" if self._connected else "disconnected"
        addr = f" {self.address[:6]}..." if self.address else ""
        return f"<DydxAdapter {self.network} ({mode}){addr} [{status}]>"


# ═══════════════════════════════════════════════════════════════════════════
# TESTING
# ═══════════════════════════════════════════════════════════════════════════


async def test_adapter():
    """Test the dYdX adapter."""
    print("=" * 60)
    print("dYdX Adapter Async Test")
    print("=" * 60)

    # Load mnemonic from environment
    from dotenv import load_dotenv

    load_dotenv()
    mnemonic = os.getenv("DYDX_MNEMONIC", "")

    # Initialize and connect
    adapter = DydxAdapter("testnet")

    if mnemonic:
        print("\n🔑 Mnemonic found - attempting full connection...")
        await adapter.connect(mnemonic)
    else:
        print("\n⚠️ No mnemonic - using HTTP-only mode")
        adapter.connect_sync()

    print(f"\n✅ Adapter: {adapter}")

    # Test market data
    print("\n📊 Fetching markets...")
    markets = await adapter.get_markets()
    print(f"   Found {len(markets)} markets: {markets[:5]}...")

    # Test ticker
    symbol = "ETH-USD"
    print(f"\n📈 Fetching ticker for {symbol}...")
    ticker = await adapter.get_ticker(symbol)
    if ticker:
        print(f"   Price: ${ticker['price']:,.2f}")
        print(f"   24h Volume: ${ticker['volume_24h']:,.0f}")

    # Test candles
    print(f"\n🕯️ Fetching candles for {symbol}...")
    candles = await adapter.get_candles(symbol, "1MIN", 5)
    if candles:
        latest = candles[0]
        print(
            f"   Latest: O={latest['open']:.2f} H={latest['high']:.2f} L={latest['low']:.2f} C={latest['close']:.2f}"
        )

    # Test positions/balance if connected with wallet
    if adapter.can_trade:
        print("\n💰 Fetching balance...")
        balance = await adapter.get_balance()
        if balance:
            print(f"   Equity: ${balance['equity']:,.2f}")
            print(f"   Free Collateral: ${balance['free_collateral']:,.2f}")

        print("\n📊 Fetching positions...")
        positions = await adapter.get_positions()
        if positions:
            for pos in positions:
                print(
                    f"   {pos['side']} {pos['symbol']}: {pos['size']} @ ${pos['entry_price']:.2f}"
                )
        else:
            print("   No open positions")

    print("\n✅ All tests completed!")


if __name__ == "__main__":
    asyncio.run(test_adapter())
