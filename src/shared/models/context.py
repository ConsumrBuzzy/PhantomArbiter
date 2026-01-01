"""
Market Context - Global Intelligence Data Model
================================================
V140: Narrow Path Infrastructure (Phase 3.5)

The MarketContext is the "single source of truth" for global market
conditions. It is updated by the CyclePod and consumed by:
- DecisionEngine (adjusts risk parameters)
- HopPods (adjusts minimum profit thresholds)
- TacticalStrategy (decides whether to execute)

This enables the "Wise Pod" pattern where specialized pods can focus
on their niche while a global context prevents loss-making trades.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional
import time


class CongestionLevel(Enum):
    """Network congestion classification."""

    LOW = "low"  # Normal trading conditions
    MODERATE = "moderate"  # Elevated but manageable
    HIGH = "high"  # Significant congestion, raise thresholds
    EXTREME = "extreme"  # Network stress, pause non-critical pods


class MarketSector(Enum):
    """Dominant market sector classification."""

    STABLE = "stable"  # USDC/USDT dominant flow
    BRIDGE = "bridge"  # SOL bridge activity (normal arb)
    MEME = "meme"  # Meme coin speculation
    DEFI = "defi"  # LRT/LST activity
    NFT = "nft"  # NFT mint congestion
    UNKNOWN = "unknown"


@dataclass
class JitoMetrics:
    """Jito tip monitoring data."""

    current_tip_lamports: int = 10_000
    p5_tip_lamports: int = 5_000  # 5th percentile (floor)
    p50_tip_lamports: int = 15_000  # Median
    p95_tip_lamports: int = 100_000  # 95th percentile (ceiling)
    tip_velocity: float = 0.0  # Rate of change (+ = rising)
    sample_count: int = 0
    last_update: float = field(default_factory=time.time)

    def get_heat_level(self) -> str:
        """Get congestion heat indicator for dashboard."""
        if self.current_tip_lamports > self.p95_tip_lamports:
            return "🔴"  # Extreme
        elif self.current_tip_lamports > self.p50_tip_lamports * 2:
            return "🟠"  # High
        elif self.current_tip_lamports > self.p50_tip_lamports:
            return "🟡"  # Moderate
        return "🟢"  # Low


@dataclass
class VolumeMetrics:
    """DEX volume and flow data."""

    raydium_volume_1h: float = 0.0
    orca_volume_1h: float = 0.0
    meteora_volume_1h: float = 0.0
    total_volume_1h: float = 0.0

    # Sector flows
    stable_flow_pct: float = 0.0  # % of volume in stables
    meme_flow_pct: float = 0.0  # % of volume in meme coins
    bridge_flow_pct: float = 0.0  # % of volume in SOL bridges

    dominant_dex: str = "UNKNOWN"
    last_update: float = field(default_factory=time.time)


@dataclass
class VolatilityMetrics:
    """Price volatility tracking (Solana VIX equivalent)."""

    sol_volatility_1h: float = 0.0  # SOL price std dev
    update_frequency_hz: float = 0.0  # Price updates per second
    price_change_velocity: float = 0.0  # Avg % change per minute

    # Derived index (0-100 scale)
    volatility_index: float = 25.0  # "Fear/Greed" proxy

    def get_vix_label(self) -> str:
        """Human-readable VIX classification."""
        if self.volatility_index > 75:
            return "EXTREME"
        elif self.volatility_index > 50:
            return "HIGH"
        elif self.volatility_index > 25:
            return "MODERATE"
        return "LOW"


@dataclass
class MarketContext:
    """
    Global market intelligence consumed by all pods and engines.

    This is the "Governor of Wisdom" - a single object that tells the
    entire system whether conditions are favorable for trading.
    """

    # Core metrics
    jito: JitoMetrics = field(default_factory=JitoMetrics)
    volume: VolumeMetrics = field(default_factory=VolumeMetrics)
    volatility: VolatilityMetrics = field(default_factory=VolatilityMetrics)

    # Derived state
    congestion_level: CongestionLevel = CongestionLevel.LOW
    active_sector: MarketSector = MarketSector.BRIDGE

    # Adjustments for HopPods
    global_min_profit_adj: float = 0.0  # Added to all thresholds
    hop_cooldown_multiplier: float = 1.0  # Slow scans during congestion

    # Control flags
    trading_enabled: bool = True
    reason: str = ""

    # Timestamps
    last_update: float = field(default_factory=time.time)
    update_count: int = 0

    def get_adjusted_threshold(self, base_threshold: float) -> float:
        """
        Get profit threshold adjusted for current market conditions.

        Args:
            base_threshold: The pod's base profit threshold (e.g., 0.10%)

        Returns:
            Adjusted threshold accounting for congestion and fees
        """
        # Base adjustment from congestion
        congestion_adj = {
            CongestionLevel.LOW: 0.0,
            CongestionLevel.MODERATE: 0.05,
            CongestionLevel.HIGH: 0.15,
            CongestionLevel.EXTREME: 0.30,
        }.get(self.congestion_level, 0.0)

        return base_threshold + congestion_adj + self.global_min_profit_adj

    def should_pause_trading(self) -> bool:
        """Check if conditions are too extreme for trading."""
        if not self.trading_enabled:
            return True
        if self.congestion_level == CongestionLevel.EXTREME:
            return True
        if self.volatility.volatility_index > 90:
            return True
        return False

    def get_dashboard_summary(self) -> Dict[str, str]:
        """Get summary data for dashboard display."""
        return {
            "jito_heat": self.jito.get_heat_level(),
            "jito_tip": f"{self.jito.current_tip_lamports:,} lamports",
            "congestion": self.congestion_level.value.upper(),
            "sector": self.active_sector.value.upper(),
            "vix": f"{self.volatility.volatility_index:.0f} ({self.volatility.get_vix_label()})",
            "profit_adj": f"+{self.global_min_profit_adj:.2f}%",
            "trading": "✅ ENABLED" if self.trading_enabled else "⛔ PAUSED",
        }


# ═══════════════════════════════════════════════════════════════════════════
# SINGLETON INSTANCE
# ═══════════════════════════════════════════════════════════════════════════

_market_context: Optional[MarketContext] = None


def get_market_context() -> MarketContext:
    """Get or create the singleton MarketContext."""
    global _market_context
    if _market_context is None:
        _market_context = MarketContext()
    return _market_context


def reset_market_context() -> None:
    """Reset context (for testing)."""
    global _market_context
    _market_context = None
