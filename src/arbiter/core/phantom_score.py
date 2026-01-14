"""
Phantom Arbiter - Phantom Score (Sentiment Proxy)
==================================================
Since we don't have a sentiment API, use Volume + Price velocity.

Formula:
========
    S = (V_change × 0.7) + (P_change × 0.3)

Where:
    - V_change: Percentage change in trading volume (last hour)
    - P_change: Price velocity (how fast price is moving)

Interpretation:
===============
    S > 50:  HIGH sentiment - crowd is active, funding likely stable
    S > 20:  MEDIUM sentiment - normal activity
    S < 20:  LOW sentiment - crowd losing interest, funding may drop
    S < 0:   DANGER - volume dropping, funding flip likely

Use Case:
=========
Before entering a position, check the Phantom Score:
- If S > 30: Safe to enter, funding likely to stay high
- If S < 10: Wait - sentiment cooling, funding may collapse
"""

import time
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from collections import deque

from src.shared.system.logging import Logger


@dataclass
class PhantomScore:
    """Sentiment score for a coin."""

    coin: str
    score: float  # The combined S value
    volume_change: float  # V_change component
    price_velocity: float  # P_change component
    confidence: str  # "HIGH", "MEDIUM", "LOW"
    recommendation: str  # "ENTER", "HOLD", "WAIT", "EXIT"
    timestamp: float = field(default_factory=time.time)

    def __str__(self) -> str:
        emoji = "🟢" if self.score > 50 else "🟡" if self.score > 20 else "🔴"
        return (
            f"{emoji} {self.coin} Phantom Score: {self.score:.1f}\n"
            f"   Volume Change: {self.volume_change:+.1f}%\n"
            f"   Price Velocity: {self.price_velocity:+.1f}%\n"
            f"   Confidence: {self.confidence}\n"
            f"   Recommendation: {self.recommendation}"
        )


class PhantomScoreCalculator:
    """
    Calculates the Phantom Score for coins.

    Uses volume and price data to estimate sentiment without
    needing a separate sentiment API.
    """

    # Weights for the formula
    VOLUME_WEIGHT = 0.7
    PRICE_WEIGHT = 0.3

    # Thresholds
    HIGH_SENTIMENT = 50
    MEDIUM_SENTIMENT = 20
    LOW_SENTIMENT = 10
    DANGER_SENTIMENT = 0

    def __init__(self):
        # Price/volume history (last 24 hours, hourly samples)
        self.price_history: Dict[str, deque] = {}
        self.volume_history: Dict[str, deque] = {}

        # Max history to keep (24 hourly samples)
        self.max_history = 24

    def record_data_point(self, coin: str, price: float, volume_24h: float):
        """Record a price/volume data point for a coin."""
        if coin not in self.price_history:
            self.price_history[coin] = deque(maxlen=self.max_history)
            self.volume_history[coin] = deque(maxlen=self.max_history)

        self.price_history[coin].append({"price": price, "timestamp": time.time()})

        self.volume_history[coin].append(
            {"volume": volume_24h, "timestamp": time.time()}
        )

    def calculate_volume_change(self, coin: str) -> Optional[float]:
        """Calculate % change in volume over last hour."""
        history = self.volume_history.get(coin)
        if not history or len(history) < 2:
            return None

        current = history[-1]["volume"]
        previous = history[-2]["volume"]

        if previous == 0:
            return 0

        return ((current - previous) / previous) * 100

    def calculate_price_velocity(self, coin: str) -> Optional[float]:
        """Calculate price velocity (% change per hour)."""
        history = self.price_history.get(coin)
        if not history or len(history) < 2:
            return None

        current = history[-1]["price"]
        previous = history[-2]["price"]
        current_time = history[-1]["timestamp"]
        previous_time = history[-2]["timestamp"]

        if previous == 0 or current_time == previous_time:
            return 0

        # Price change %
        price_change = ((current - previous) / previous) * 100

        # Normalize to hourly rate
        hours = (current_time - previous_time) / 3600
        if hours > 0:
            velocity = price_change / hours
        else:
            velocity = price_change

        return velocity

    def calculate_score(self, coin: str) -> Optional[PhantomScore]:
        """
        Calculate the Phantom Score for a coin.

        S = (V_change × 0.7) + (P_change × 0.3)
        """
        v_change = self.calculate_volume_change(coin)
        p_change = self.calculate_price_velocity(coin)

        if v_change is None or p_change is None:
            return None

        # Apply formula
        score = (v_change * self.VOLUME_WEIGHT) + (p_change * self.PRICE_WEIGHT)

        # Determine confidence based on data quality
        history_len = len(self.price_history.get(coin, []))
        if history_len >= 12:
            confidence = "HIGH"
        elif history_len >= 6:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        # Generate recommendation
        if score > self.HIGH_SENTIMENT:
            recommendation = "ENTER"  # High activity, safe to enter
        elif score > self.MEDIUM_SENTIMENT:
            recommendation = "HOLD"  # Moderate activity, hold position
        elif score > self.LOW_SENTIMENT:
            recommendation = "WAIT"  # Low activity, wait for better moment
        else:
            recommendation = "EXIT"  # Danger, sentiment collapsing

        return PhantomScore(
            coin=coin,
            score=score,
            volume_change=v_change,
            price_velocity=p_change,
            confidence=confidence,
            recommendation=recommendation,
        )

    async def calculate_live_score(self, coin: str) -> Optional[PhantomScore]:
        """
        Calculate score using live data from feeds.

        This fetches current data and records it before calculating.
        """
        try:
            from src.shared.feeds.jupiter_feed import JupiterFeed

            USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            MINTS = {
                "SOL": "So11111111111111111111111111111111111111112",
                "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
                "JUP": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
            }

            feed = JupiterFeed()
            mint = MINTS.get(coin)
            if not mint:
                return None

            spot = feed.get_spot_price(mint, USDC)
            if not spot:
                return None

            # For volume, we'd need to fetch from a volume API
            # For now, simulate with price-based proxy
            simulated_volume = spot.price * 1000000  # Rough volume estimate

            # Record data point
            self.record_data_point(coin, spot.price, simulated_volume)

            return self.calculate_score(coin)

        except Exception as e:
            Logger.debug(f"Live score error: {e}")
            return None

    def get_entry_recommendation(self, score: PhantomScore) -> Dict[str, Any]:
        """
        Get detailed entry recommendation based on score.

        Returns:
            Dict with should_enter, confidence, and reasoning
        """
        if score.score > self.HIGH_SENTIMENT:
            return {
                "should_enter": True,
                "confidence": "HIGH",
                "reasoning": (
                    f"Strong sentiment ({score.score:.0f}). "
                    f"Volume up {score.volume_change:+.1f}%, price moving {score.price_velocity:+.1f}%/h. "
                    "Crowd is active - funding likely to stay high."
                ),
            }
        elif score.score > self.MEDIUM_SENTIMENT:
            return {
                "should_enter": True,
                "confidence": "MEDIUM",
                "reasoning": (
                    f"Moderate sentiment ({score.score:.0f}). "
                    "Activity is stable but not exceptional. "
                    "Consider smaller position size."
                ),
            }
        elif score.score > self.LOW_SENTIMENT:
            return {
                "should_enter": False,
                "confidence": "LOW",
                "reasoning": (
                    f"Weak sentiment ({score.score:.0f}). "
                    f"Volume change {score.volume_change:+.1f}% suggests cooling interest. "
                    "Wait for better conditions."
                ),
            }
        else:
            return {
                "should_enter": False,
                "confidence": "HIGH",
                "reasoning": (
                    f"DANGER: Sentiment collapsing ({score.score:.0f}). "
                    f"Volume dropping, price velocity negative. "
                    "Do NOT enter - funding flip likely!"
                ),
            }


# ═══════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import asyncio

    async def test():
        print("=" * 60)
        print("Phantom Score Calculator Test")
        print("=" * 60)

        calc = PhantomScoreCalculator()

        # Simulate hourly data points for SOL
        print("\n--- Simulating SOL with RISING sentiment ---")

        # Hour 1: Low activity
        calc.record_data_point("SOL", 100.0, 1000000)
        time.sleep(0.01)  # Small delay to separate timestamps

        # Hour 2: Volume picking up
        calc.record_data_point("SOL", 101.0, 1200000)  # +20% volume, +1% price

        score = calc.calculate_score("SOL")
        if score:
            print(score)
            rec = calc.get_entry_recommendation(score)
            print("\nEntry Recommendation:")
            print(f"   Should Enter: {rec['should_enter']}")
            print(f"   Confidence: {rec['confidence']}")
            print(f"   Reasoning: {rec['reasoning']}")

        # Simulate FALLING sentiment
        print("\n--- Simulating WIF with FALLING sentiment ---")

        calc.record_data_point("WIF", 2.00, 500000)
        time.sleep(0.01)
        calc.record_data_point("WIF", 1.95, 400000)  # -20% volume, -2.5% price

        score = calc.calculate_score("WIF")
        if score:
            print(score)
            rec = calc.get_entry_recommendation(score)
            print("\nEntry Recommendation:")
            print(f"   Should Enter: {rec['should_enter']}")
            print(f"   Confidence: {rec['confidence']}")
            print(f"   Reasoning: {rec['reasoning']}")

    asyncio.run(test())
