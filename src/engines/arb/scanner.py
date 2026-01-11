"""
V2.0: Arb Engine Scanner
=======================
Monitors price differences across DEXs to detect arbitrage opportunities.
Migrated to Modular Factory Architecture.
"""

import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

from config.settings import Settings


@dataclass
class SpreadOpportunity:
    """
    Represents an arbitrage opportunity between two DEXs.

    A "spread" is the price difference between the best place to buy
    and the best place to sell the same asset.
    """

    pair: str  # e.g., "SOL/USDC"
    base_mint: str  # Token being traded
    quote_mint: str  # Quote currency (usually USDC)

    buy_dex: str  # DEX with lowest price (buy here)
    sell_dex: str  # DEX with highest price (sell here)
    buy_price: float  # Price on buy DEX
    sell_price: float  # Price on sell DEX

    spread_pct: float  # (sell - buy) / buy * 100
    gross_profit_usd: float  # Profit before fees
    estimated_fees_usd: float  # Trading + gas fees
    net_profit_usd: float  # Profit after all costs
    net_profit_pct: float  # ROI percentage

    max_size_usd: float  # Limited by liquidity depth
    confidence: float  # 0-1, based on price freshness

    timestamp: float = field(default_factory=time.time)

    # Dashboard/Verification fields (added for compatibility)
    verification_status: Optional[str] = None
    trigger_wallet: Optional[str] = None

    # V128.7: Standardized Quote Storage (Prevents AttributeError)
    buy_quote: Optional[Dict] = None
    sell_quote: Optional[Dict] = None

    def calculate_optimal_size(
        self, impact_factor: float, min_size: float = 10.0, max_size: float = 1000.0
    ) -> float:
        """
        Calculate optimal trade size using calculus.
        Maximize P(x) = (Spread * x) - (Impact * x^2) - Fees
        Derivative P'(x) = Spread - 2 * Impact * x = 0
        x_opt = Spread / (2 * Impact)

        Args:
            impact_factor: Price impact coefficient (quadratic cost)
            min_size: Minimum trade size in USD
            max_size: Maximum trade size in USD

        Returns:
            Optimal trade size in USD (clamped)
        """
        if impact_factor <= 0:
            return max_size

        # Spread as partial (e.g., 1% = 0.01)
        s = self.spread_pct / 100

        # x_opt = S / 2I
        optimal_size = s / (2 * impact_factor)

        # Clamp between min and max
        return max(min_size, min(optimal_size, max_size))

    @property
    def is_profitable(self) -> bool:
        """Is this opportunity profitable after fees?"""
        # For simulation: trigger on any net gain > 0
        # For live: use MIN_PROFIT_AFTER_FEES threshold
        return self.net_profit_usd > 0

    @property
    def status(self) -> str:
        """Status indicator for dashboard."""
        if self.is_profitable:
            if self.spread_pct >= 0.5:
                return "🔥 HOT"
            elif self.spread_pct >= 0.3:
                return "READY"
            else:
                return "THIN"
        return "❌"


class SpreadDetector:
    """
    Detects price spreads across multiple DEXs.

    This is the core of spatial arbitrage - finding where
    to buy low and sell high across different venues.
    """

    def __init__(self, feeds: List = None):
        """Initialize with list of price feeds."""
        self.feeds = {f.get_name(): f for f in feeds} if feeds else {}
        self.default_trade_size = 100.0  # USD

        # Configuration
        self.min_spread_pct = getattr(Settings, "MIN_SPREAD_PCT", 0.1)
        self.default_trade_size = getattr(Settings, "DEFAULT_TRADE_SIZE_USD", 100.0)

        # SOL price cache for gas calculation
        self._sol_price_cache = 95.0  # Default fallback
        self._sol_price_ts = 0.0

        # Cache
        self._price_cache: Dict[str, Dict[str, float]] = {}
        self._last_scan = 0.0

    async def shutdown(self):
        """Cleanup async resources."""
        for feed in self.feeds.values():
            if hasattr(feed, "close"):
                await feed.close()

    def add_feed(self, feed) -> None:
        """Add a price feed source."""
        self.feeds[feed.get_name()] = feed

    async def _get_sol_price(self) -> float:
        """Get live SOL/USD price for gas cost estimation (async)."""
        import asyncio

        # Cache for 30 seconds to avoid excessive API calls
        if time.time() - self._sol_price_ts < 30:
            return self._sol_price_cache

        SOL_MINT = "So11111111111111111111111111111111111111112"
        USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

        for feed in self.feeds.values():
            try:
                # V131: Properly handle async feeds
                if asyncio.iscoroutinefunction(feed.get_spot_price):
                    spot = await feed.get_spot_price(SOL_MINT, USDC_MINT)
                else:
                    spot = feed.get_spot_price(SOL_MINT, USDC_MINT)

                if spot and spot.price > 0:
                    self._sol_price_cache = spot.price
                    self._sol_price_ts = time.time()
                    return spot.price
            except:
                pass

        return self._sol_price_cache  # Return cached/default

    async def scan_pair(
        self,
        base_mint: str,
        quote_mint: str,
        pair_name: str = None,
        trade_size: float = None,
    ) -> Optional[SpreadOpportunity]:
        """
        Scan all DEXs for spread opportunity on a single pair.
        V131: Made async to properly await price feeds.

        Args:
            base_mint: Token to trade
            quote_mint: Quote currency
            pair_name: Optional human-readable name (e.g., "SOL/USDC")
            trade_size: USD value to test (affects slippage)

        Returns:
            SpreadOpportunity if a spread exists, else None
        """
        if not self.feeds:
            return None

        trade_size = trade_size or self.default_trade_size
        pair_name = pair_name or f"{base_mint[:8]}/{quote_mint[:8]}"

        # Fetch prices from all feeds
        prices: Dict[str, "SpotPrice"] = {}

        for name, feed in self.feeds.items():
            try:
                # V131: Await the async price fetch
                spot = await feed.get_spot_price(base_mint, quote_mint)
                if spot and spot.price > 0:
                    prices[name] = spot
            except Exception:
                pass  # Skip failed feeds

        if len(prices) < 2:
            return None  # Need at least 2 DEXs to compare

        # Find best buy and sell
        sorted_prices = sorted(prices.items(), key=lambda x: x[1].price)
        buy_dex, buy_spot = sorted_prices[0]  # Lowest price
        sell_dex, sell_spot = sorted_prices[-1]  # Highest price

        buy_price = buy_spot.price
        sell_price = sell_spot.price

        # Calculate spread
        spread_pct = ((sell_price - buy_price) / buy_price) * 100

        if spread_pct < 0.01:  # Negligible spread
            return None

        # ═══ V83.0: CALCULUS-BASED OPTIMAL SIZING ═══
        # Estimate Impact Factor (I) from liquidity
        # Model: Impact = (Trade Size / Available Liquidity)^2
        # Approx: I = 1 / (Liquidity * k) where k is pool constant

        pool_liquidity = min(
            buy_spot.liquidity_usd or 100000, sell_spot.liquidity_usd or 100000
        )

        # Heuristic: 1% impact at 1% of pool liquidity
        # I = 0.01 / (0.01 * Liquidity) -> Impact Coeff
        # Let's use a simpler linear approximation for the derivative:
        # Impact Coeff 'I' for quadratic cost model: Cost = I * x^2
        # If we expect 1% slip at $1k trade on $100k pool:
        # 10 = I * 1000^2  => I = 10 / 1,000,000 = 1e-5

        # Dynamic Impact Factor derived from Pool Depth
        # Default to "decent" liquidity ($100k) if unknown
        impact_factor = 1e-5 * (100000 / max(pool_liquidity, 10000))

        # Create temp opportunity to calculate size
        temp_opp = SpreadOpportunity(
            pair=pair_name,
            base_mint=base_mint,
            quote_mint=quote_mint,
            buy_dex=buy_dex,
            sell_dex=sell_dex,
            buy_price=buy_price,
            sell_price=sell_price,
            spread_pct=spread_pct,
            gross_profit_usd=0,
            estimated_fees_usd=0,
            net_profit_usd=0,
            net_profit_pct=0.0,
            max_size_usd=0,
            confidence=0,
        )

        # Calculate Optimal Size (Max Profit)
        optimal_size = temp_opp.calculate_optimal_size(
            impact_factor=impact_factor,
            min_size=10.0,
            max_size=getattr(Settings, "MAX_TRADE_SIZE_USD", 1000.0),
        )

        # Use optimal size for final calculation
        trade_size = optimal_size

        # Estimate profitability with ADAPTIVE fees
        gross_profit = trade_size * (spread_pct / 100)

        # Use centralized FeeEstimator for adaptive fees
        from src.shared.pricing.fee_estimator import get_fee_estimator

        fee_est = get_fee_estimator()

        # V131: Use cached SOL price (async _get_sol_price not available in sync context)
        fee_est._sol_price_cache = self._sol_price_cache
        fee_est._sol_price_ts = time.time()

        fees = fee_est.estimate(
            trade_size_usd=trade_size,
            buy_dex=buy_dex,
            sell_dex=sell_dex,
            sol_price=fee_est._sol_price_cache,
        )

        # ML Slippage Prediction: adjust for expected slippage based on historical data
        expected_slippage_pct = 0.0
        try:
            from src.shared.system.db_manager import db_manager

            # Get token symbol from pair name (e.g., "SOL/USDC" -> "SOL")
            token = pair_name.split("/")[0] if "/" in pair_name else pair_name
            expected_slippage_pct = db_manager.get_expected_slippage(token, trade_size)
        except Exception:
            pass  # No data = assume no extra slippage

        slippage_cost = trade_size * (expected_slippage_pct / 100)

        # V115: Raydium Impact Penalty
        # Raydium CLMM/Standard often quotes worse than unit-price scan suggests.
        # Add a fixed 0.2% 'Ghost Penalty' if Raydium is involved.
        ghost_penalty = 0.0
        if buy_dex == "RAYDIUM" or sell_dex == "RAYDIUM":
            ghost_penalty = trade_size * 0.002  # 0.2%

        # ML Decay Prediction: adjust for expected spread decay during execution
        # Uses learned cycle time (or default 3s) as execution window
        decay_cost = 0.0
        try:
            from src.shared.system.db_manager import db_manager

            decay_velocity = db_manager.get_decay_velocity(pair_name)  # %/sec
            if decay_velocity > 0:
                # V111: Route-specific latency fingerprint
                route_lat = db_manager.get_route_latency(buy_dex, sell_dex)

                # Use learned route latency if available, fallback to pod cycle time
                if route_lat > 0:
                    exec_window = route_lat / 1000
                else:
                    exec_window = (
                        db_manager.get_avg_cycle_time() / 1000
                        if db_manager.get_avg_cycle_time() > 0
                        else 3.0
                    )

                exec_window = min(exec_window, 10.0)  # Cap at 10s

                # Dampen penalty for established tokens (trust them more)
                token_base = pair_name.split("/")[0] if "/" in pair_name else pair_name
                ESTABLISHED = {
                    "SOL",
                    "USDC",
                    "USDT",
                    "BONK",
                    "RAY",
                    "JUP",
                    "ORCA",
                    "WIF",
                    "JTO",
                    "PYTH",
                }
                decay_multiplier = 0.3 if token_base in ESTABLISHED else 1.0

                expected_decay = decay_velocity * exec_window * decay_multiplier
                decay_cost = trade_size * (expected_decay / 100)
        except Exception:
            pass

        net_profit = (
            gross_profit - fees.total_usd - slippage_cost - decay_cost - ghost_penalty
        )

        return SpreadOpportunity(
            pair=pair_name,
            base_mint=base_mint,
            quote_mint=quote_mint,
            buy_dex=buy_dex,
            sell_dex=sell_dex,
            buy_price=buy_price,
            sell_price=sell_price,
            spread_pct=spread_pct,
            gross_profit_usd=gross_profit,
            estimated_fees_usd=fees.total_usd,
            net_profit_usd=net_profit,
            net_profit_pct=(net_profit / trade_size * 100) if trade_size > 0 else 0.0,
            max_size_usd=trade_size,
            confidence=0.9,
            timestamp=time.time(),
        )

    async def scan_all_pairs(
        self, pairs: List[Tuple[str, str, str]], trade_size: float = None
    ) -> List[SpreadOpportunity]:
        """
        Scan multiple pairs for opportunities using ASYNC batch fetching.
        """
        import asyncio

        trade_size = trade_size or self.default_trade_size
        opportunities = []

        # Collect unique mints
        all_mints = list(set(base_mint for pair_name, base_mint, quote_mint in pairs))

        if not all_mints or not self.feeds:
            return []

        # Parallel fetch from ALL feeds
        feed_prices: Dict[str, Dict[str, float]] = {}

        async def fetch_from_feed(feed_item):
            feed_name, feed = feed_item
            start_time = time.time()  # V131: Feed latency tracking
            try:
                if hasattr(feed, "get_multiple_prices"):
                    # Check if method is async
                    if asyncio.iscoroutinefunction(feed.get_multiple_prices):
                        res = await feed.get_multiple_prices(all_mints)
                    else:
                        res = feed.get_multiple_prices(all_mints)

                    # V131: Log feed latency for learning
                    latency_ms = (time.time() - start_time) * 1000
                    if not hasattr(self, "_feed_latencies"):
                        self._feed_latencies = {}
                    self._feed_latencies[feed_name] = latency_ms

                    return feed_name, res, latency_ms
                else:
                    # Fallback: parallel individual fetches
                    prices = {}
                    for mint in all_mints:
                        spot = await feed.get_spot_price(
                            mint, "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
                        )
                        if spot and spot.price > 0:
                            prices[mint] = spot.price
                    latency_ms = (time.time() - start_time) * 1000
                    return feed_name, prices, latency_ms
            except Exception:
                latency_ms = (time.time() - start_time) * 1000
                return feed_name, {}, latency_ms

        # V127: AsyncIO Parallel Fetch (True Parallelism)
        # Fetch from all feeds via asyncio.gather on the event loop
        tasks = [fetch_from_feed(item) for item in self.feeds.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                continue
            if not result:
                continue

            # V131: Unpack 3-tuple (feed_name, prices, latency_ms)
            if len(result) == 3:
                feed_name, prices, latency_ms = result
            else:
                feed_name, prices = result
                latency_ms = 0

            if prices:
                feed_prices[feed_name] = prices

        if len(feed_prices) < 2:
            # Need at least 2 feeds for spread comparison
            # Fall back to sequential scan
            # DEBUG: Why sequential?
            print(
                f"DEBUG: Falling back to sequential (Feeds: {len(feed_prices)} - {list(feed_prices.keys())})"
            )

            opps_seq = []
            for pair_name, base_mint, quote_mint in pairs:
                opp = await self.scan_pair(
                    base_mint, quote_mint, pair_name, trade_size=trade_size
                )
                if opp:
                    opps_seq.append(opp)
            return sorted(opps_seq, key=lambda x: x.spread_pct, reverse=True)

        # Calculate spreads for each pair
        # print(f"DEBUG: Parallel Scan: {len(pairs)} pairs | Feeds: {list(feed_prices.keys())}") # CONFIRM FEEDS

        from src.shared.pricing.fee_estimator import get_fee_estimator

        fee_est = get_fee_estimator()
        fee_est._sol_price_cache = await self._get_sol_price()
        fee_est._sol_price_ts = time.time()

        for pair_name, base_mint, quote_mint in pairs:
            # Gather prices from all feeds for this token
            prices: Dict[str, float] = {}
            for feed_name, feed_data in feed_prices.items():
                if base_mint in feed_data:
                    prices[feed_name] = feed_data[base_mint]

            # Update PoolRegistry (Smart Pool Tracking)
            try:
                from src.shared.execution.pool_registry import get_pool_registry

                registry = get_pool_registry()
                registry.update_coverage(
                    symbol=pair_name.split("/")[0],
                    mint=base_mint,
                    has_raydium=("RAYDIUM" in prices),
                    has_orca=("ORCA" in prices),
                    has_meteora=("METEORA" in prices),
                )
            except ImportError:
                pass

            if len(prices) < 2:
                continue

            # Find best buy and sell
            sorted_prices = sorted(prices.items(), key=lambda x: x[1])
            buy_dex, buy_price = sorted_prices[0]
            sell_dex, sell_price = sorted_prices[-1]

            spread_pct = ((sell_price - buy_price) / buy_price) * 100

            # Allow ALL spreads (even negative) to show up in dashboard (proof of life)
            # if spread_pct < -2.0:
            #     continue

            # Show even tiny spreads so dashboard isn't blank
            # if spread_pct < 0.01:
            #     continue

            gross_profit = trade_size * (spread_pct / 100)
            fees = fee_est.estimate(
                trade_size_usd=trade_size,
                buy_dex=buy_dex,
                sell_dex=sell_dex,
                sol_price=fee_est._sol_price_cache,
            )

            # ML Slippage Prediction
            slippage_cost = 0.0
            try:
                from src.shared.system.db_manager import db_manager

                token = pair_name.split("/")[0] if "/" in pair_name else pair_name
                expected_slippage_pct = db_manager.get_expected_slippage(
                    token, trade_size
                )
                slippage_cost = trade_size * (expected_slippage_pct / 100)
            except:
                pass

            # ML Decay Prediction
            decay_cost = 0.0
            try:
                decay_velocity = db_manager.get_decay_velocity(pair_name)
                if decay_velocity > 0:
                    exec_window = (
                        db_manager.get_avg_cycle_time() / 1000
                        if db_manager.get_avg_cycle_time() > 0
                        else 3.0
                    )
                    exec_window = min(exec_window, 10.0)

                    # Dampen penalty for established tokens (trust them more)
                    token_base = (
                        pair_name.split("/")[0] if "/" in pair_name else pair_name
                    )
                    ESTABLISHED = {
                        "SOL",
                        "USDC",
                        "USDT",
                        "BONK",
                        "RAY",
                        "JUP",
                        "ORCA",
                        "WIF",
                        "JTO",
                        "PYTH",
                    }
                    decay_multiplier = 0.3 if token_base in ESTABLISHED else 1.0

                    decay_cost = (
                        trade_size
                        * (decay_velocity * exec_window / 100)
                        * decay_multiplier
                    )
            except:
                pass

            net_profit = gross_profit - fees.total_usd - slippage_cost - decay_cost

            opportunities.append(
                SpreadOpportunity(
                    pair=pair_name,
                    base_mint=base_mint,
                    quote_mint=quote_mint,
                    buy_dex=buy_dex,
                    sell_dex=sell_dex,
                    buy_price=buy_price,
                    sell_price=sell_price,
                    spread_pct=spread_pct,
                    gross_profit_usd=gross_profit,
                    estimated_fees_usd=fees.total_usd,
                    net_profit_usd=net_profit,
                    net_profit_pct=(net_profit / trade_size * 100) if trade_size > 0 else 0.0,
                    max_size_usd=trade_size,
                    confidence=0.9,
                    timestamp=time.time(),
                )
            )
            
            # V40: Emit ARB_OPP signal for dashboard visualization (hop lines)
            try:
                from src.shared.system.signal_bus import signal_bus, Signal, SignalType
                signal_bus.emit(Signal(
                    type=SignalType.ARB_OPP,
                    source="SPREAD_DETECTOR",
                    data={
                        "pair": pair_name,
                        "path": [base_mint, quote_mint],  # Simplified 2-hop path
                        "buy_dex": buy_dex,
                        "sell_dex": sell_dex,
                        "spread_pct": spread_pct,
                        "profit": net_profit / trade_size if trade_size > 0 else 0,  # As decimal
                        "status": "PROFITABLE" if net_profit > 0 else "UNPROFITABLE"
                    }
                ))
            except Exception:
                pass  # Don't crash spread detection

        # ═══ V131: Liquidity Blocklist Filter ═══
        # Filter out pairs with >80% LIQ failure rate (temporary block)
        try:
            from src.shared.system.db_manager import db_manager

            liq_rates = db_manager.get_liq_failure_rate(hours=2)
            if liq_rates:
                blocked = [pair for pair, rate in liq_rates.items() if rate > 0.8]
                if blocked:
                    original_count = len(opportunities)
                    opportunities = [o for o in opportunities if o.pair not in blocked]
                    filtered = original_count - len(opportunities)
                    if filtered > 0:
                        from src.shared.system.logging import Logger

                        Logger.debug(
                            f"[ML] Filtered {filtered} pairs with high LIQ failure"
                        )
        except Exception:
            pass  # Silent fail for ML filtering

        return sorted(opportunities, key=lambda x: x.spread_pct, reverse=True)

    def get_price_matrix(self) -> Dict[str, Dict[str, float]]:
        """
        Get the current price cache as a matrix.

        Returns:
            {pair: {dex: price, ...}, ...}
        """
        return self._price_cache.copy()
