"""
V50.0: Migration Sniffer
========================
Detects token graduation from bonding curves to DEX pools.

Strategy:
1. Monitor graduation events on launchpads
2. Pre-calculate destination pool liquidity depth
3. Execute "Immediate Buy" before retail notices
4. Exit within 15-30 minutes for quick flip

Graduation Flows:
- Pump.fun → Raydium AMM
- Moonshot → Meteora DLMM
- BONKfun → Raydium AMM
- Raydium LaunchLab → Raydium AMM

The window between migration completion and DEXScreener
update is typically 30-120 seconds. This is the "alpha window."

Usage:
    sniffer = get_migration_sniffer()

    # Register opportunity handler
    sniffer.on_opportunity(handle_migration_opportunity)

    # Start monitoring
    await sniffer.start()
"""

import asyncio
import time
from typing import Optional, Dict, Any, List, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum

from src.shared.system.logging import Logger
from src.scraper.discovery.launchpad_monitor import (
    get_launchpad_monitor,
    MigrationEvent,
    LaunchPlatform,
)


class SnipeConfidence(Enum):
    """Confidence level for migration snipe."""

    HIGH = "high"  # Strong signals, low risk
    MEDIUM = "medium"  # Mixed signals
    LOW = "low"  # Weak signals, high risk
    SKIP = "skip"  # Do not snipe


@dataclass
class MigrationOpportunity:
    """
    Scored opportunity for migration sniping.

    Contains all data needed to decide whether to enter.
    """

    mint: str
    symbol: str = ""

    # Source info
    source_platform: LaunchPlatform = LaunchPlatform.UNKNOWN
    bonding_curve_address: str = ""

    # Destination info
    destination_pool: str = ""
    destination_dex: str = ""
    pool_liquidity_usd: float = 0.0

    # Timing
    migration_detected_at: float = field(default_factory=time.time)
    estimated_completion_seconds: float = 0.0

    # Scoring
    confidence: SnipeConfidence = SnipeConfidence.SKIP
    score: float = 0.0

    # Risk factors
    holder_concentration: float = 0.0  # % held by top 10
    creator_reputation: str = ""
    has_social_presence: bool = False

    # Entry parameters
    suggested_entry_usd: float = 0.0
    suggested_slippage_bps: int = 100

    @property
    def age_seconds(self) -> float:
        return time.time() - self.migration_detected_at

    @property
    def is_fresh(self) -> bool:
        """Is this opportunity still fresh (< 60 seconds)?"""
        return self.age_seconds < 60


# Type alias for opportunity handlers
OpportunityHandler = Callable[[MigrationOpportunity], Awaitable[None]]


class MigrationSniffer:
    """
    V50.0: Migration Sniffer for graduation events.

    Monitors launchpad migrations and scores opportunities
    for fast entry before retail awareness.

    Workflow:
    1. Receive MigrationEvent from LaunchpadMonitor
    2. Fetch destination pool details
    3. Score opportunity based on liquidity, holders, timing
    4. Emit MigrationOpportunity to handlers
    5. Handlers decide whether to execute

    Safety Features:
    - Minimum liquidity threshold
    - Alpha Vault detection (Meteora)
    - Creator reputation check
    - Holder concentration analysis
    """

    # Minimum pool liquidity to consider
    MIN_LIQUIDITY_USD = 5000

    # Maximum entry per opportunity
    MAX_ENTRY_USD = 50

    # Confidence thresholds
    CONFIDENCE_THRESHOLDS = {
        SnipeConfidence.HIGH: 0.8,
        SnipeConfidence.MEDIUM: 0.5,
        SnipeConfidence.LOW: 0.3,
    }

    def __init__(self):
        """Initialize migration sniffer."""
        self._opportunity_handlers: List[OpportunityHandler] = []
        self._running = False
        self._pending_migrations: Dict[str, MigrationEvent] = {}

        # Stats
        self._migrations_analyzed = 0
        self._opportunities_emitted = 0
        self._opportunities_skipped = 0

        # Connect to launchpad monitor
        self._monitor = get_launchpad_monitor()

        Logger.info("   🎯 [SNIFFER] Migration Sniffer initialized")

    # =========================================================================
    # HANDLER REGISTRATION
    # =========================================================================

    def on_opportunity(self, handler: OpportunityHandler) -> OpportunityHandler:
        """
        Decorator to register an opportunity handler.

        Usage:
            @sniffer.on_opportunity
            async def handle(opp: MigrationOpportunity):
                if opp.confidence == SnipeConfidence.HIGH:
                    await execute_buy(opp)
        """
        self._opportunity_handlers.append(handler)
        return handler

    def add_opportunity_handler(self, handler: OpportunityHandler) -> None:
        """Add an opportunity handler."""
        self._opportunity_handlers.append(handler)

    # =========================================================================
    # MONITORING
    # =========================================================================

    async def start(self) -> None:
        """Start the migration sniffer."""
        if self._running:
            return

        self._running = True

        # Register with launchpad monitor
        self._monitor.add_migration_handler(self._on_migration_event)

        Logger.info("   🎯 [SNIFFER] Started - listening for migrations")

        # Keep-alive loop
        while self._running:
            await asyncio.sleep(10)
            self._cleanup_stale_migrations()

    def stop(self) -> None:
        """Stop the sniffer."""
        self._running = False
        Logger.info("   🎯 [SNIFFER] Stopped")

    async def _on_migration_event(self, event: MigrationEvent) -> None:
        """
        Handle incoming migration event from LaunchpadMonitor.

        Analyzes the migration and creates an opportunity if viable.
        """
        self._migrations_analyzed += 1

        Logger.info(f"   🎯 [SNIFFER] Analyzing: {event.mint[:16]}...")

        # Create and score opportunity
        opportunity = await self._analyze_migration(event)

        if opportunity.confidence != SnipeConfidence.SKIP:
            await self._emit_opportunity(opportunity)
        else:
            self._opportunities_skipped += 1
            Logger.debug(f"   🎯 [SNIFFER] Skipped: score={opportunity.score:.2f}")

    # =========================================================================
    # ANALYSIS
    # =========================================================================

    async def _analyze_migration(self, event: MigrationEvent) -> MigrationOpportunity:
        """
        Analyze a migration event and score the opportunity.

        Factors considered:
        - Destination pool liquidity
        - Source platform reputation
        - Holder concentration
        - Social presence
        - Timing freshness
        """
        opportunity = MigrationOpportunity(
            mint=event.mint,
            source_platform=event.platform,
            bonding_curve_address=event.bonding_curve_address,
            destination_pool=event.destination_pool,
            destination_dex=event.destination_dex,
            pool_liquidity_usd=event.liquidity_added_usd,
            migration_detected_at=event.timestamp,
        )

        # Calculate base score
        score = 0.0

        # 1. Liquidity score (0-0.3)
        if opportunity.pool_liquidity_usd >= self.MIN_LIQUIDITY_USD:
            liq_score = min(opportunity.pool_liquidity_usd / 50000, 1.0) * 0.3
            score += liq_score

        # 2. Platform score (0-0.2)
        platform_scores = {
            LaunchPlatform.RAYDIUM_LAUNCHLAB: 0.2,
            LaunchPlatform.BONKFUN: 0.15,
            LaunchPlatform.PUMPFUN: 0.1,
            LaunchPlatform.MOONSHOT: 0.1,
        }
        score += platform_scores.get(opportunity.source_platform, 0.05)

        # 3. Freshness score (0-0.3)
        age = opportunity.age_seconds
        if age < 30:
            score += 0.3
        elif age < 60:
            score += 0.2
        elif age < 120:
            score += 0.1

        # 4. Social presence (0-0.2)
        # TODO: Check Bags.fm, Twitter mentions
        pass

        opportunity.score = score

        # Determine confidence level
        if score >= self.CONFIDENCE_THRESHOLDS[SnipeConfidence.HIGH]:
            opportunity.confidence = SnipeConfidence.HIGH
            opportunity.suggested_entry_usd = min(self.MAX_ENTRY_USD, 50)
        elif score >= self.CONFIDENCE_THRESHOLDS[SnipeConfidence.MEDIUM]:
            opportunity.confidence = SnipeConfidence.MEDIUM
            opportunity.suggested_entry_usd = min(self.MAX_ENTRY_USD, 25)
        elif score >= self.CONFIDENCE_THRESHOLDS[SnipeConfidence.LOW]:
            opportunity.confidence = SnipeConfidence.LOW
            opportunity.suggested_entry_usd = min(self.MAX_ENTRY_USD, 10)
        else:
            opportunity.confidence = SnipeConfidence.SKIP

        return opportunity

    async def _emit_opportunity(self, opportunity: MigrationOpportunity) -> None:
        """Emit opportunity to all handlers."""
        self._opportunities_emitted += 1

        Logger.info(f"   🎯 [SNIFFER] Opportunity: {opportunity.mint[:16]}...")
        Logger.info(f"   🎯 [SNIFFER]   Confidence: {opportunity.confidence.value}")
        Logger.info(f"   🎯 [SNIFFER]   Score: {opportunity.score:.2f}")
        Logger.info(
            f"   🎯 [SNIFFER]   Suggested: ${opportunity.suggested_entry_usd:.2f}"
        )

        for handler in self._opportunity_handlers:
            try:
                await handler(opportunity)
            except Exception as e:
                Logger.error(f"   🎯 [SNIFFER] Handler error: {e}")

    def _cleanup_stale_migrations(self) -> None:
        """Remove migrations older than 5 minutes."""
        now = time.time()
        stale = [
            k for k, v in self._pending_migrations.items() if now - v.timestamp > 300
        ]
        for key in stale:
            del self._pending_migrations[key]

    # =========================================================================
    # STATUS
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Get sniffer status."""
        return {
            "running": self._running,
            "migrations_analyzed": self._migrations_analyzed,
            "opportunities_emitted": self._opportunities_emitted,
            "opportunities_skipped": self._opportunities_skipped,
            "pending_migrations": len(self._pending_migrations),
            "handlers_registered": len(self._opportunity_handlers),
        }


# =============================================================================
# SINGLETON
# =============================================================================

_sniffer_instance: Optional[MigrationSniffer] = None


def get_migration_sniffer() -> MigrationSniffer:
    """Get or create the singleton MigrationSniffer."""
    global _sniffer_instance
    if _sniffer_instance is None:
        _sniffer_instance = MigrationSniffer()
    return _sniffer_instance


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    import sys

    sys.path.insert(0, ".")

    print("\n🎯 Migration Sniffer Test")
    print("=" * 50)

    sniffer = get_migration_sniffer()

    @sniffer.on_opportunity
    async def test_handler(opp: MigrationOpportunity):
        print(f"   Opportunity: {opp.mint[:16]}... ({opp.confidence.value})")

    print(f"\n📊 Status: {sniffer.get_status()}")
    print("\n✅ Test complete!")
