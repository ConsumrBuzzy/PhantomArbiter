"""
V1.0: Arbitrage Orchestrator
============================
Main coordinator that runs the arbitrage loop.
"""

import asyncio
import time
from typing import Optional, List, Dict
from dataclasses import dataclass

from config.settings import Settings
from src.system.logging import Logger
from src.arbitrage.monitoring.live_dashboard import LiveDashboard, SpreadInfo


@dataclass
class ArbitrageConfig:
    """Configuration for the orchestrator."""
    mode: str = "FUNDING"          # SPATIAL | TRIANGULAR | FUNDING | ALL
    budget: float = 500.0
    tick_interval: float = 2.0     # Seconds between scans
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
        
        # Initialize components (lazy loaded)
        self._feeds = []
        self._spread_detector = None
        self._strategies = {}
        
        # State
        self.running = False
        self.last_tick = 0.0
        
    def _init_feeds(self):
        """Initialize price feeds for all supported DEXs."""
        from src.arbitrage.feeds.jupiter_feed import JupiterFeed
        from src.arbitrage.feeds.raydium_feed import RaydiumFeed
        from src.arbitrage.feeds.orca_feed import OrcaFeed
        
        self._feeds = [
            JupiterFeed(),
            RaydiumFeed(),
            OrcaFeed(use_on_chain=False),  # Use DexScreener for speed
        ]
        
        Logger.info(f"📡 Initialized {len(self._feeds)} price feeds: Jupiter, Raydium, Orca")
        
    def _init_spread_detector(self):
        """Initialize spread detector with feeds."""
        from src.arbitrage.core.spread_detector import SpreadDetector
        
        self._spread_detector = SpreadDetector(feeds=self._feeds)
        Logger.info("🔍 Spread detector ready")
        
    def _get_monitored_pairs(self) -> List[tuple]:
        """Get pairs to monitor based on settings."""
        # Default pairs
        USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        SOL = "So11111111111111111111111111111111111111112"
        BONK = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
        WIF = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
        
        return [
            ("SOL/USDC", SOL, USDC),
            ("BONK/USDC", BONK, USDC),
            ("WIF/USDC", WIF, USDC),
        ]
    
    async def _fetch_funding_rates(self) -> Dict[str, float]:
        """Fetch funding rates from Drift (mock if not connected)."""
        try:
            from src.arbitrage.feeds.drift_funding import MockDriftFundingFeed
            feed = MockDriftFundingFeed()  # Use mock for now
            
            rates = {}
            for market in ["SOL-PERP", "BTC-PERP", "ETH-PERP"]:
                info = await feed.get_funding_rate(market)
                if info:
                    rates[market] = info.rate_8h
            return rates
        except Exception as e:
            Logger.debug(f"Funding rate fetch error: {e}")
            return {}
    
    async def _tick(self):
        """Single tick of the arbitrage loop."""
        pairs = self._get_monitored_pairs()
        
        # 1. Scan for spread opportunities
        opportunities = self._spread_detector.scan_all_pairs(pairs)
        
        # 2. Convert to dashboard format
        spread_infos = []
        for opp in opportunities:
            # Build price dict for all DEXs
            prices = {}
            for feed in self._feeds:
                spot = feed.get_spot_price(opp.base_mint, opp.quote_mint)
                if spot:
                    prices[feed.get_name().title()] = spot.price
                    
            spread_infos.append(SpreadInfo(
                pair=opp.pair,
                prices=prices,
                best_buy=opp.buy_dex,
                best_sell=opp.sell_dex,
                spread_pct=opp.spread_pct,
                estimated_profit_usd=opp.net_profit_usd,
                status=opp.status
            ))
        
        # 3. Update dashboard with spreads
        self.dashboard.update_spreads(spread_infos)
        
        # 4. Fetch and update funding rates (for FUNDING mode)
        if self.config.mode in ['FUNDING', 'ALL']:
            funding_rates = await self._fetch_funding_rates()
            self.dashboard.update_funding_rates(funding_rates)
        
        # 5. TODO: Execute profitable opportunities
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
        mode="SPATIAL",
        budget=500.0,
        tick_interval=3.0,
        enable_execution=False
    )
    
    orchestrator = ArbitrageOrchestrator(config)
    await orchestrator.run(duration=60)  # Run for 60 seconds


if __name__ == "__main__":
    asyncio.run(main())
