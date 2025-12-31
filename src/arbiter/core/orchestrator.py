"""
V1.0: Arbitrage Orchestrator
============================
Main coordinator that runs the arbitrage loop.
"""

import asyncio
import time
from typing import List
from dataclasses import dataclass

from src.shared.system.logging import Logger
from src.arbiter.monitoring.live_dashboard import LiveDashboard, SpreadInfo
from src.arbiter.core.stuck_token_guard import StuckTokenGuard


@dataclass
class ArbitrageConfig:
    """Configuration for the orchestrator."""

    mode: str = "FUNDING"  # SPATIAL | TRIANGULAR | FUNDING | ALL
    budget: float = 500.0
    tick_interval: float = 2.0  # Seconds between scans
    enable_execution: bool = False  # Paper mode by default
    telegram_enabled: bool = True


class ArbitrageOrchestrator:
    """
    Main orchestrator for the arbitrage engine.

    Coordinates:
    - Price feeds
    - Spread detection
    - Strategy execution
    - Dashboard updates
    - Telegram notifications
    """

    def __init__(self, config: ArbitrageConfig = None):
        self.config = config or ArbitrageConfig()

        # Initialize dashboard
        self.dashboard = LiveDashboard(budget=self.config.budget)
        self.dashboard.mode = self.config.mode

        # Initialize Telegram alerts (if enabled)
        self._telegram = None
        if self.config.telegram_enabled:
            self._init_telegram()

        # Initialize components (lazy loaded)
        self._feeds = []
        self._spread_detector = None
        self._strategies = {}

        # State
        self.running = False
        self.last_tick = 0.0
        self.last_telegram_status = 0.0
        self.telegram_status_interval = 300.0  # 5 minutes

        # V120: Stuck token guard
        self._stuck_token_guard = StuckTokenGuard()
        self._last_stuck_check = 0.0
        self._stuck_check_interval = 60.0  # Check every 60 seconds

    def _init_telegram(self):
        """Initialize Telegram alerts."""
        try:
            from src.shared.notification.telegram_manager import TelegramManager

            self._telegram = TelegramManager()
            self._telegram.start()
        except Exception as e:
            Logger.debug(f"Telegram init error: {e}")

    def _init_feeds(self):
        """Initialize price feeds for all supported DEXs."""
        from src.shared.feeds.jupiter_feed import JupiterFeed
        from src.shared.feeds.raydium_feed import RaydiumFeed
        from src.shared.feeds.orca_feed import OrcaFeed

        self._feeds = [
            JupiterFeed(),
            RaydiumFeed(),
            OrcaFeed(use_on_chain=False),  # Use DexScreener for speed
        ]

        Logger.info(
            f"📡 Initialized {len(self._feeds)} price feeds: Jupiter, Raydium, Orca"
        )

    def _init_spread_detector(self):
        """Initialize spread detector with feeds."""
        from src.arbiter.core.spread_detector import SpreadDetector
        from src.arbiter.core.triangular_scanner import TriangularScanner

        self._spread_detector = SpreadDetector(feeds=self._feeds)
        self._triangular_scanner = TriangularScanner(feeds=self._feeds)
        Logger.info("🔍 Spread detector & Triangular scanner ready")

    def _get_monitored_pairs(self) -> List[tuple]:
        """
        Get pairs to monitor, including Bridge pairs for Triangular Arb.
        Returns: List of (pair_name, base_mint, quote_mint)
        """
        from src.shared.system.db_manager import DBManager

        # Standard Mints
        USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        SOL = "So11111111111111111111111111111111111111112"

        db = DBManager()
        active_tokens = db.get_active_tokens()

        pairs = []

        # 1. Add SOL/USDC (The King Pair)
        pairs.append(("SOL/USDC", SOL, USDC))

        # 2. Add pairings for all watchlist tokens
        for token in active_tokens:
            symbol = token["symbol"]
            mint = token["mint"]

            if mint in [USDC, SOL]:
                continue

            # PRIMARY: Token/USDC
            pairs.append((f"{symbol}/USDC", mint, USDC))

            # BRIDGE: Token/SOL (Critical for Triangular Arb)
            # This creates the "Triangle" edges: USDC -> SOL -> Token -> USDC
            # BRIDGE: Token/SOL (Critical for Triangular Arb)
            # This creates the "Triangle" edges: USDC -> SOL -> Token -> USDC
            pairs.append((f"{symbol}/SOL", mint, SOL))

        Logger.info(f"📊 Monitored Pairs: {len(pairs)} (Includes Bridges)")
        return pairs

    async def _tick(self):
        """Single tick of the arbitrage loop."""
        pairs = self._get_monitored_pairs()

        # 1. Scan for spread opportunities (Spatial)
        opportunities = self._spread_detector.scan_all_pairs(pairs)

        # 2. Update Triangular Graph & Scan for Cycles
        # This uses the price cache populated by scan_all_pairs
        try:
            self._triangular_scanner.update_graph(self._spread_detector)
            cycles = self._triangular_scanner.find_cycles()
            if cycles:
                for cyc in cycles:
                    Logger.info(
                        f"📐 [V115] TRIANGULAR ARB: {' -> '.join(cyc.route_tokens)} | Net: ${cyc.net_profit_usd:.2f}"
                    )
                    # Execution Logic (Live):
                    # await self._executor.execute_triangular_arb(cyc)
                    pass  # Watch mode only
        except Exception as e:
            # Don't let new scanner crash the main loop
            Logger.debug(f"Triangular scan error: {e}")

        # 3. Convert to dashboard format
        spread_infos = []
        for opp in opportunities:
            # Build price dict for all DEXs
            prices = {}
            for feed in self._feeds:
                spot = feed.get_spot_price(opp.base_mint, opp.quote_mint)
                if spot:
                    prices[feed.get_name().title()] = spot.price

            spread_infos.append(
                SpreadInfo(
                    pair=opp.pair,
                    prices=prices,
                    best_buy=opp.buy_dex,
                    best_sell=opp.sell_dex,
                    spread_pct=opp.spread_pct,
                    estimated_profit_usd=opp.net_profit_usd,
                    status=opp.status,
                )
            )

        # 3. Update dashboard with spreads
        self.dashboard.update_spreads(spread_infos)

        # 4. Fetch and update funding rates (for FUNDING mode)
        if self.config.mode in ["FUNDING", "ALL"]:
            funding_rates = await self._fetch_funding_rates()
            self.dashboard.update_funding_rates(funding_rates)

        # 5. Send Telegram status update (every 5 minutes)
        if self._telegram and self.config.telegram_enabled:
            now = time.time()
            if now - self.last_telegram_status >= self.telegram_status_interval:
                self._telegram.send_status_update(self.dashboard)
                self.last_telegram_status = now
                Logger.debug("📱 Sent Telegram status update")

        # 6. TODO: Execute profitable opportunities
        # for opp in opportunities:
        #     if opp.is_profitable and self.config.enable_execution:
        #         await self._execute(opp)

        self.last_tick = time.time()

    async def run(self, duration: float = None):
        """
        Run the arbitrage loop.

        Args:
            duration: Optional duration in seconds (None = run forever)
        """
        Logger.info("🚀 Starting Arbitrage Engine...")

        # Initialize components
        self._init_feeds()
        self._init_spread_detector()

        self.running = True
        start_time = time.time()

        try:
            while self.running:
                # Check duration limit
                if duration and (time.time() - start_time) >= duration:
                    Logger.info(f"⏱️ Duration limit reached ({duration}s)")
                    break

                # Run tick
                try:
                    await self._tick()
                except Exception as e:
                    Logger.error(f"Tick error: {e}")

                # Render dashboard
                self.dashboard.render(clear=True)

                # V120: Periodic stuck token check
                if time.time() - self._last_stuck_check >= self._stuck_check_interval:
                    try:
                        stuck_count = self._stuck_token_guard.run_check()
                        if stuck_count > 0:
                            Logger.warning(
                                f"[ORCH] 🚨 {stuck_count} stuck token(s) detected!"
                            )
                    except Exception as e:
                        Logger.debug(f"[ORCH] Stuck token check error: {e}")
                    self._last_stuck_check = time.time()

                # Wait for next tick
                await asyncio.sleep(self.config.tick_interval)

        except KeyboardInterrupt:
            Logger.info("🛑 Stopped by user")
        finally:
            self.running = False

    def stop(self):
        """Stop the orchestrator."""
        self.running = False


# ═══════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════


async def main():
    """Main entry point for testing."""
    config = ArbitrageConfig(
        mode="SPATIAL", budget=500.0, tick_interval=3.0, enable_execution=False
    )

    orchestrator = ArbitrageOrchestrator(config)
    await orchestrator.run(duration=60)  # Run for 60 seconds


if __name__ == "__main__":
    asyncio.run(main())
