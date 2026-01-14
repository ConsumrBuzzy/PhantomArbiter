"""
Near-Miss Analyzer
==================
Stateless logic engine for analyzing opportunities that are "close" to profitability.

For a $30 budget, many blue-chip spreads fall short by $0.02-$0.10.
This module categorizes opportunities by their proximity to break-even,
allowing the trader to see what's "almost viable" rather than just binary pass/fail.

Uses Python 3.12+ structural pattern matching for clean status categorization.
"""

from __future__ import annotations

from typing import NamedTuple, Literal, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# TYPE DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

NearMissStatus = Literal["VIABLE", "NEAR_MISS", "WARM", "FAR"]


class OpportunityLike(Protocol):
    """Protocol for opportunity objects that can be analyzed."""

    @property
    def net_profit_usd(self) -> float: ...

    @property
    def spread_pct(self) -> float: ...

    @property
    def max_size_usd(self) -> float: ...


class NearMissMetrics(NamedTuple):
    """Computed metrics for near-miss analysis.

    Attributes:
        status: Categorical status (VIABLE, NEAR_MISS, WARM, FAR)
        status_icon: Unicode icon for dashboard display
        gap_to_profit_usd: USD amount needed to reach break-even
        required_spread_pct: Spread % that would make this profitable
        gap_display: Human-readable gap string for UI
    """

    status: NearMissStatus
    status_icon: str
    gap_to_profit_usd: float
    required_spread_pct: float
    gap_display: str


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYZER
# ═══════════════════════════════════════════════════════════════════════════════


class NearMissAnalyzer:
    """
    Stateless logic engine for near-miss opportunity analysis.

    Thresholds (optimized for $30 budget):
        - VIABLE: net_profit > 0
        - NEAR_MISS: -$0.05 <= net_profit <= 0 (within 5 cents)
        - WARM: -$0.10 <= net_profit < -$0.05 (within 10 cents)
        - FAR: net_profit < -$0.10

    Example:
        >>> analyzer = NearMissAnalyzer()
        >>> metrics = analyzer.calculate_metrics(opportunity)
        >>> print(f"{metrics.status_icon} Gap: {metrics.gap_display}")
        ⚡ NEAR Gap: +$0.032
    """

    # Configurable thresholds (in USD)
    NEAR_THRESHOLD: float = 0.05
    WARM_THRESHOLD: float = 0.10

    # Status icon mapping
    STATUS_ICONS: dict[NearMissStatus, str] = {
        "VIABLE": "✅ READY",
        "NEAR_MISS": "⚡ NEAR",
        "WARM": "🔸 WARM",
        "FAR": "❌",
    }

    @classmethod
    def classify_status(cls, net_profit_usd: float) -> NearMissStatus:
        """
        Classify opportunity status using structural pattern matching.

        Args:
            net_profit_usd: Net profit after all fees

        Returns:
            NearMissStatus literal
        """
        match net_profit_usd:
            case n if n > 0:
                return "VIABLE"
            case n if n >= -cls.NEAR_THRESHOLD:
                return "NEAR_MISS"
            case n if n >= -cls.WARM_THRESHOLD:
                return "WARM"
            case _:
                return "FAR"

    @classmethod
    def calculate_metrics(
        cls, opp: OpportunityLike, trade_size_usd: float | None = None
    ) -> NearMissMetrics:
        """
        Calculate complete near-miss metrics for an opportunity.

        Args:
            opp: Opportunity object with net_profit_usd, spread_pct, max_size_usd
            trade_size_usd: Override trade size (defaults to opp.max_size_usd)

        Returns:
            NearMissMetrics with status, icon, gap, required spread
        """
        trade_size = trade_size_usd or opp.max_size_usd

        # 1. Classify status
        status = cls.classify_status(opp.net_profit_usd)
        icon = cls.STATUS_ICONS[status]

        # 2. Calculate gap to profitability
        gap_to_profit = max(0.0, -opp.net_profit_usd)

        # 3. Back-calculate required spread
        # Formula: (TradeSize * Spread%) - Fees = NetProfit
        # Therefore: Fees = (TradeSize * Spread%) - NetProfit
        # Required gross = Fees + $0.01 (minimum target profit)
        # Required spread = (Required gross / TradeSize) * 100

        current_gross = trade_size * (opp.spread_pct / 100)
        estimated_fees = current_gross - opp.net_profit_usd

        # Target: net $0.01 profit
        target_gross = estimated_fees + 0.01
        required_spread = (target_gross / trade_size) * 100 if trade_size > 0 else 0.0

        # 4. Format gap display
        if gap_to_profit > 0:
            gap_display = f"+${gap_to_profit:.3f}"
        else:
            gap_display = "READY"

        return NearMissMetrics(
            status=status,
            status_icon=icon,
            gap_to_profit_usd=gap_to_profit,
            required_spread_pct=required_spread,
            gap_display=gap_display,
        )

    @classmethod
    def is_actionable(cls, opp: OpportunityLike) -> bool:
        """
        Check if opportunity is worth watching (VIABLE or NEAR_MISS).

        Use this to filter opportunities for priority monitoring.
        """
        status = cls.classify_status(opp.net_profit_usd)
        return status in ("VIABLE", "NEAR_MISS")


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE-LEVEL CONVENIENCE
# ═══════════════════════════════════════════════════════════════════════════════


def analyze_near_miss(
    opp: OpportunityLike, trade_size_usd: float | None = None
) -> NearMissMetrics:
    """Convenience function for one-off analysis."""
    return NearMissAnalyzer.calculate_metrics(opp, trade_size_usd)
