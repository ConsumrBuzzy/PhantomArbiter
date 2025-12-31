"""
V9.1 Relative Strength Analysis Module
=======================================
Comparative analysis for portfolio optimization:
1. Peer-to-Peer: Rank held coins against each other
2. Benchmark: Compare against SOL (market proxy)
"""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from src.core.shared_cache import SharedPriceCache
from src.shared.system.logging import Logger


@dataclass
class RSRanking:
    """Relative Strength ranking for a single asset."""

    symbol: str
    price: float
    rs_vs_benchmark: float  # RS ratio vs SOL (>100 = outperforming)
    rs_momentum: float  # Change in RS over lookback period
    win_rate: float  # Strategy win rate for this asset
    pnl_usd: float  # Realized PnL
    rank: int = 0  # Final rank (1 = strongest)

    @property
    def is_leader(self) -> bool:
        """Is this asset outperforming the benchmark?"""
        return self.rs_vs_benchmark > 100

    @property
    def momentum_direction(self) -> str:
        """Direction of RS momentum."""
        if self.rs_momentum > 2:
            return "🟢 Rising"
        elif self.rs_momentum < -2:
            return "🔴 Falling"
        return "⚪ Flat"


class RelativeStrengthAnalyzer:
    """
    V9.1: Comparative Relative Strength Analysis.

    Ranks assets by:
    1. RS vs Benchmark (SOL) - Market outperformance
    2. RS Momentum - Direction of relative performance
    3. Win Rate - Strategy fit

    Uses these rankings to inform:
    - Position sizing (larger positions in leaders)
    - Exit decisions (sell laggards first)
    - Strategy validation (all falling = pause trading)
    """

    # SOL mint for benchmark comparison
    SOL_MINT = "So11111111111111111111111111111111111111112"
    SOL_SYMBOL = "SOL"

    def __init__(self):
        self.last_rs_values: Dict[str, float] = {}  # For momentum calculation
        self.rs_history: Dict[str, List[float]] = {}  # Rolling RS values
        self.consecutive_falling: Dict[str, int] = {}  # Falling streak counter

    def get_current_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Get current prices from cache."""
        prices = {}
        for symbol in symbols:
            price, _ = SharedPriceCache.get_price(symbol, max_age=120)
            if price and price > 0:
                prices[symbol] = price
        return prices

    def get_sol_price(self) -> float:
        """Get SOL price for benchmark comparison."""
        # Try multiple methods
        price, _ = SharedPriceCache.get_price("SOL", max_age=120)
        if price and price > 0:
            return price

        # Fallback: fetch from Jupiter
        try:
            from src.core.data import batch_fetch_jupiter_prices

            prices = batch_fetch_jupiter_prices([self.SOL_MINT])
            if prices and self.SOL_MINT in prices:
                return prices[self.SOL_MINT]
        except Exception:
            pass

        return 0

    def calculate_rs_ratio(
        self,
        asset_price: float,
        benchmark_price: float,
        asset_price_24h: float = 0,
        benchmark_price_24h: float = 0,
    ) -> float:
        """
        Calculate Relative Strength ratio based on 24h performance.

        Formula: ((Asset Return) - (Benchmark Return)) + 100

        Alternative (when no historical): Normalized price ratio scaled to 100

        Interpretation:
        - > 100: Asset outperforming benchmark
        - = 100: Parity
        - < 100: Asset underperforming
        """
        # If we have 24h prices, use percentage change comparison
        if asset_price_24h > 0 and benchmark_price_24h > 0:
            asset_return = ((asset_price - asset_price_24h) / asset_price_24h) * 100
            benchmark_return = (
                (benchmark_price - benchmark_price_24h) / benchmark_price_24h
            ) * 100
            # RS = 100 + (asset_return - benchmark_return)
            return 100 + (asset_return - benchmark_return)

        # Fallback: Use market cap proxy (assume similar market cap = 100)
        # This is less accurate but gives relative ranking
        if benchmark_price <= 0:
            return 100.0

        # Simple ratio normalized: log scale helps with different price magnitudes
        import math

        ratio = asset_price / benchmark_price
        # Normalize to ~100: use log scale to compress large differences
        if ratio > 0:
            normalized = 100 + (math.log10(ratio * 1000) * 20)  # Scale factor
            return max(50, min(150, normalized))  # Clamp to reasonable range
        return 100.0

    def calculate_rs_momentum(self, symbol: str, current_rs: float) -> float:
        """
        Calculate RS momentum (change over time).

        Returns percentage change in RS ratio.
        """
        previous_rs = self.last_rs_values.get(symbol, current_rs)

        if previous_rs <= 0:
            return 0.0

        momentum = ((current_rs - previous_rs) / previous_rs) * 100

        # Update history
        self.last_rs_values[symbol] = current_rs

        if symbol not in self.rs_history:
            self.rs_history[symbol] = []
        self.rs_history[symbol].append(current_rs)

        # Keep last 10 values
        if len(self.rs_history[symbol]) > 10:
            self.rs_history[symbol] = self.rs_history[symbol][-10:]

        # Track consecutive falling
        if momentum < -1:  # Falling
            self.consecutive_falling[symbol] = (
                self.consecutive_falling.get(symbol, 0) + 1
            )
        else:
            self.consecutive_falling[symbol] = 0

        return momentum

    def get_win_rates(self, symbols: List[str]) -> Dict[str, float]:
        """Get win rates from database or cache."""
        win_rates = {}
        try:
            # V11.3: Use db_manager instead of legacy database.py
            from src.shared.system.db_manager import db_manager

            # db_manager.get_win_rate() returns overall win rate (float 0.0-1.0)
            # For per-symbol, we'd need a different query. For now, use overall.
            overall_rate = (
                db_manager.get_win_rate(limit=20) * 100
            )  # Convert to percentage
            for symbol in symbols:
                win_rates[symbol] = overall_rate
        except Exception:
            # Fallback: all neutral
            for symbol in symbols:
                win_rates[symbol] = 50.0
        return win_rates

    def analyze_portfolio(self, held_symbols: List[str]) -> List[RSRanking]:
        """
        Analyze entire portfolio and return ranked list.

        Args:
            held_symbols: List of symbols currently held

        Returns:
            List of RSRanking objects, sorted by rank (1 = best)
        """
        if not held_symbols:
            return []

        # Get benchmark price
        sol_price = self.get_sol_price()

        # Get current prices
        prices = self.get_current_prices(held_symbols)

        # Get win rates
        win_rates = self.get_win_rates(held_symbols)

        # Build rankings
        rankings = []

        for symbol in held_symbols:
            price = prices.get(symbol, 0)
            if price <= 0:
                continue

            # Calculate RS vs benchmark
            rs_ratio = self.calculate_rs_ratio(price, sol_price)

            # Calculate momentum
            momentum = self.calculate_rs_momentum(symbol, rs_ratio)

            ranking = RSRanking(
                symbol=symbol,
                price=price,
                rs_vs_benchmark=rs_ratio,
                rs_momentum=momentum,
                win_rate=win_rates.get(symbol, 50.0),
                pnl_usd=0,  # TODO: Get from database
            )
            rankings.append(ranking)

        # Sort by composite score (RS ratio + momentum + win rate)
        def composite_score(r: RSRanking) -> float:
            # Weighted score: RS ratio (40%) + momentum (30%) + win rate (30%)
            return (
                (r.rs_vs_benchmark * 0.4)
                + (r.rs_momentum * 0.3 * 10)
                + (r.win_rate * 0.3)
            )

        rankings.sort(key=composite_score, reverse=True)

        # Assign ranks
        for i, r in enumerate(rankings):
            r.rank = i + 1

        return rankings

    def get_leaders(self, rankings: List[RSRanking]) -> List[RSRanking]:
        """Get assets that are outperforming the benchmark."""
        return [r for r in rankings if r.is_leader]

    def get_laggards(self, rankings: List[RSRanking]) -> List[RSRanking]:
        """Get assets that are underperforming the benchmark."""
        return [r for r in rankings if not r.is_leader]

    def get_exit_candidates(self, rankings: List[RSRanking]) -> List[RSRanking]:
        """
        Get assets that should be considered for exit.

        Criteria:
        - RS falling for 3+ consecutive periods, OR
        - Win rate < 35%, OR
        - Bottom 25% of rankings
        """
        candidates = []
        for r in rankings:
            falling_streak = self.consecutive_falling.get(r.symbol, 0)

            if falling_streak >= 3:
                candidates.append(r)
            elif r.win_rate < 35:
                candidates.append(r)
            elif r.rank > len(rankings) * 0.75:  # Bottom 25%
                candidates.append(r)

        return candidates

    def should_pause_trading(self, rankings: List[RSRanking]) -> Tuple[bool, str]:
        """
        Check if overall strategy should pause.

        Pause if:
        - All assets falling vs benchmark
        - Average RS < 90 (10% below market)
        """
        if not rankings:
            return False, "No positions"

        all_falling = all(r.rs_vs_benchmark < 100 for r in rankings)
        avg_rs = sum(r.rs_vs_benchmark for r in rankings) / len(rankings)

        if all_falling and avg_rs < 90:
            return True, f"All assets underperforming market (avg RS: {avg_rs:.1f})"

        return False, "OK"

    def should_early_exit(
        self, symbol: str, held_symbols: List[str]
    ) -> Tuple[bool, str]:
        """
        V9.1: Check if asset should exit early based on RS momentum.

        Triggers early exit if:
        - RS falling for 3+ consecutive periods
        - RS ratio < 90 (10% below market)

        This is called from the watcher/TSL logic to catch momentum
        reversals before the price TSL is hit.

        Returns: (should_exit: bool, reason: str)
        """
        rankings = self.analyze_portfolio(held_symbols)

        for r in rankings:
            if r.symbol == symbol:
                falling_streak = self.consecutive_falling.get(symbol, 0)

                # Exit if RS falling for 3+ periods
                if falling_streak >= 3:
                    return True, f"RS Momentum Exit (falling {falling_streak} periods)"

                # Exit if significantly underperforming market
                if r.rs_vs_benchmark < 85:
                    return True, f"RS Weakness Exit (RS {r.rs_vs_benchmark:.1f} < 85)"

        return False, "OK"

    def get_ranking_for_symbol(
        self, symbol: str, held_symbols: List[str]
    ) -> Optional[RSRanking]:
        """Get RS ranking for a specific symbol."""
        rankings = self.analyze_portfolio(held_symbols)
        for r in rankings:
            if r.symbol == symbol:
                return r
        return None

    def display_analysis(self, rankings: List[RSRanking]):
        """Display portfolio analysis to console."""
        if not rankings:
            Logger.info("   No holdings to analyze")
            return

        Logger.section("📊 RELATIVE STRENGTH ANALYSIS")

        sol_price = self.get_sol_price()
        Logger.info(f"   Benchmark: SOL @ ${sol_price:.2f}")

        # Display rankings
        Logger.info(
            f"   {'Rank':<5} {'Symbol':<10} {'Price':<12} {'RS Ratio':<10} {'Momentum':<12} {'WR':<8}"
        )
        Logger.info("   " + "-" * 60)

        for r in rankings:
            momentum_str = r.momentum_direction
            leader_str = "⭐" if r.is_leader else "  "
            Logger.info(
                f"   {r.rank:<5} {r.symbol:<10} ${r.price:<11.4f} {r.rs_vs_benchmark:<10.1f} {momentum_str:<12} {r.win_rate:.1f}%{leader_str}"
            )

        # Summary
        leaders = self.get_leaders(rankings)
        laggards = self.get_laggards(rankings)

        Logger.info("")
        Logger.info(
            f"   Leaders (>100 RS): {len(leaders)} | Laggards (<100 RS): {len(laggards)}"
        )

        # Exit candidates
        exit_candidates = self.get_exit_candidates(rankings)
        if exit_candidates:
            Logger.warning(
                f"   ⚠️ Exit Candidates: {[r.symbol for r in exit_candidates]}"
            )

        # Pause check
        should_pause, reason = self.should_pause_trading(rankings)
        if should_pause:
            Logger.warning(f"   ⛔ PAUSE RECOMMENDED: {reason}")


# === Quick Test ===
if __name__ == "__main__":
    analyzer = RelativeStrengthAnalyzer()

    print("\n📊 Relative Strength Analyzer Test")
    print("=" * 50)

    # Test with sample held assets
    test_symbols = ["WIF", "POPCAT", "JUP"]

    rankings = analyzer.analyze_portfolio(test_symbols)
    analyzer.display_analysis(rankings)
