"""
Phantom Arbiter - Scalp Engine Sentiment
======================================
The "missing piece" that tells the bot whether funding will stay high.

Free Data Sources:
==================
1. LunarCrush API (Free Tier) - Social Score, Galaxy Score
2. Fear & Greed Index - Market-wide 0-100 score
3. Volume Change - Trading activity as sentiment proxy
4. Price Momentum - Crowd excitement indicator

Sentiment Score Formula:
========================
    S = (LunarCrush × 0.35) + (FearGreed × 0.25) + (VolChange × 0.25) + (Momentum × 0.15)

Interpretation:
===============
    S > 70:  STRONG BUY signal - crowd excited, funding will stay high
    S > 50:  ENTER - sentiment supports the trade
    S > 30:  HOLD - sentiment neutral, monitor closely
    S < 30:  EXIT - sentiment dropping, funding flip likely

Usage:
======
    engine = SentimentEngine()
    score = await engine.get_sentiment_score("SOL")
    if score.should_enter:
        execute_arb("SOL", 50)
"""

import asyncio
import time
import requests
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from config.settings import Settings
from src.shared.system.logging import Logger


@dataclass
class SentimentScore:
    """Combined sentiment score from multiple sources."""

    coin: str

    # Overall score (0-100)
    score: float

    # Component scores (0-100 each)
    lunarcrush_score: Optional[float] = None
    fear_greed_score: Optional[float] = None
    volume_score: Optional[float] = None
    momentum_score: Optional[float] = None

    # Recommendations
    signal: str = "NEUTRAL"  # "STRONG_BUY", "ENTER", "HOLD", "EXIT", "DANGER"
    should_enter: bool = False
    confidence: str = "LOW"  # "HIGH", "MEDIUM", "LOW"

    # Metadata
    sources_used: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def __str__(self) -> str:
        emoji = {
            "STRONG_BUY": "🟢🟢",
            "ENTER": "🟢",
            "HOLD": "🟡",
            "EXIT": "🟠",
            "DANGER": "🔴",
        }.get(self.signal, "⚪")

        lines = [
            f"\n{'=' * 50}",
            f"  {emoji} {self.coin} SENTIMENT: {self.score:.0f}/100 - {self.signal}",
            f"{'=' * 50}",
        ]

        if self.lunarcrush_score is not None:
            lines.append(f"  LunarCrush:   {self.lunarcrush_score:.0f}/100")
        if self.fear_greed_score is not None:
            lines.append(f"  Fear & Greed: {self.fear_greed_score:.0f}/100")
        if self.volume_score is not None:
            lines.append(f"  Volume:       {self.volume_score:.0f}/100")
        if self.momentum_score is not None:
            lines.append(f"  Momentum:     {self.momentum_score:.0f}/100")

        lines.extend(
            [
                "",
                f"  Should Enter: {'✅ YES' if self.should_enter else '❌ NO'}",
                f"  Confidence:   {self.confidence}",
                f"  Sources:      {', '.join(self.sources_used) or 'None'}",
            ]
        )

        return "\n".join(lines)


class SentimentEngine:
    """
    Combines multiple sentiment sources into a single score.

    The sentiment acts as a MULTIPLIER for funding arbitrage:
    - High sentiment = Longs are excited, funding stays high
    - Low sentiment = Longs exiting, funding will flip
    """

    # Component weights (must sum to 1.0)
    WEIGHT_LUNARCRUSH = 0.35
    WEIGHT_FEAR_GREED = 0.25
    WEIGHT_VOLUME = 0.25
    WEIGHT_MOMENTUM = 0.15

    # Thresholds
    STRONG_BUY_THRESHOLD = 70
    ENTER_THRESHOLD = 50
    HOLD_THRESHOLD = 30

    def __init__(self):
        # API endpoints
        self.fear_greed_url = "https://api.alternative.me/fng/"
        self.lunarcrush_url = "https://lunarcrush.com/api3/coins"  # Free tier

        # Cache
        self._cache: Dict[str, Any] = {}
        self._cache_ttl = 300  # 5 minute cache

    async def get_sentiment_score(self, coin: str) -> SentimentScore:
        """
        Get combined sentiment score for a coin.

        Fetches from all available sources and combines.
        """
        sources_used = []

        # 1. Fear & Greed (market-wide)
        fear_greed = await self._get_fear_greed()
        if fear_greed is not None:
            sources_used.append("Fear&Greed")

        # 2. LunarCrush (coin-specific)
        lunarcrush = await self._get_lunarcrush_score(coin)
        if lunarcrush is not None:
            sources_used.append("LunarCrush")

        # 3. Volume change (from our feeds)
        volume_score = await self._get_volume_score(coin)
        if volume_score is not None:
            sources_used.append("Volume")

        # 4. Price momentum (from our feeds)
        momentum = await self._get_momentum_score(coin)
        if momentum is not None:
            sources_used.append("Momentum")

        # Calculate weighted average
        total_weight = 0
        weighted_sum = 0

        if lunarcrush is not None:
            weighted_sum += lunarcrush * self.WEIGHT_LUNARCRUSH
            total_weight += self.WEIGHT_LUNARCRUSH

        if fear_greed is not None:
            weighted_sum += fear_greed * self.WEIGHT_FEAR_GREED
            total_weight += self.WEIGHT_FEAR_GREED

        if volume_score is not None:
            weighted_sum += volume_score * self.WEIGHT_VOLUME
            total_weight += self.WEIGHT_VOLUME

        if momentum is not None:
            weighted_sum += momentum * self.WEIGHT_MOMENTUM
            total_weight += self.WEIGHT_MOMENTUM

        # Final score
        if total_weight > 0:
            final_score = weighted_sum / total_weight
        else:
            final_score = 50  # Default neutral

        # Determine signal
        if final_score >= self.STRONG_BUY_THRESHOLD:
            signal = "STRONG_BUY"
            should_enter = True
        elif final_score >= self.ENTER_THRESHOLD:
            signal = "ENTER"
            should_enter = True
        elif final_score >= self.HOLD_THRESHOLD:
            signal = "HOLD"
            should_enter = False
        elif final_score >= 20:
            signal = "EXIT"
            should_enter = False
        else:
            signal = "DANGER"
            should_enter = False

        # Confidence based on sources
        if len(sources_used) >= 3:
            confidence = "HIGH"
        elif len(sources_used) >= 2:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        return SentimentScore(
            coin=coin,
            score=final_score,
            lunarcrush_score=lunarcrush,
            fear_greed_score=fear_greed,
            volume_score=volume_score,
            momentum_score=momentum,
            signal=signal,
            should_enter=should_enter,
            confidence=confidence,
            sources_used=sources_used,
        )

    async def _get_fear_greed(self) -> Optional[float]:
        """
        Fetch Fear & Greed Index (0-100).

        This is market-wide, not coin-specific.
        0 = Extreme Fear, 100 = Extreme Greed
        """
        cache_key = "fear_greed"

        # Check cache
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if time.time() - cached["timestamp"] < self._cache_ttl:
                return cached["value"]

        try:
            response = requests.get(self.fear_greed_url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                value = int(data["data"][0]["value"])

                # Cache it
                self._cache[cache_key] = {"value": value, "timestamp": time.time()}

                Logger.debug(f"[SENTIMENT] Fear & Greed: {value}")
                return float(value)

        except Exception as e:
            Logger.debug(f"[SENTIMENT] Fear & Greed fetch error: {e}")

        return None

    async def _get_lunarcrush_score(self, coin: str) -> Optional[float]:
        """
        Fetch LunarCrush social score (0-100 normalized).

        Uses Galaxy Score (1-100) which combines:
        - Social mentions velocity
        - Market cap
        - Trading volume
        - Social engagement

        API Docs: https://lunarcrush.com/developers/api/overview
        """
        api_key = getattr(Settings, "LUNARCRUSH_API_KEY", None)
        if not api_key:
            Logger.debug("[SENTIMENT] LUNARCRUSH_API_KEY not set")
            return None

        cache_key = f"lunarcrush_{coin}"

        # Check cache
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if time.time() - cached["timestamp"] < self._cache_ttl:
                return cached["value"]

        # Map coin symbols to LunarCrush format
        coin_map = {
            "SOL": "solana",
            "WIF": "dogwifhat",
            "JUP": "jupiter",
            "BTC": "bitcoin",
            "ETH": "ethereum",
        }

        lc_coin = coin_map.get(coin, coin.lower())

        try:
            # LunarCrush v2 API endpoint
            url = f"https://lunarcrush.com/api4/public/coins/{lc_coin}/v1"
            headers = {"Authorization": f"Bearer {api_key}"}

            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()

                # Try to get Galaxy Score (overall social metric)
                # Galaxy Score is 1-100
                if "data" in data:
                    galaxy_score = data["data"].get("galaxy_score", None)
                    alt_rank = data["data"].get("alt_rank", None)
                    social_volume = data["data"].get("social_volume", 0)

                    if galaxy_score:
                        score = float(galaxy_score)
                        Logger.info(
                            f"[SENTIMENT] LunarCrush {coin}: Galaxy={score:.0f}, AltRank={alt_rank}"
                        )

                        # Cache it
                        self._cache[cache_key] = {
                            "value": score,
                            "timestamp": time.time(),
                        }
                        return score

                # Fallback: try social_volume as proxy
                Logger.debug(f"[SENTIMENT] LunarCrush response: {data}")

            elif response.status_code == 401:
                Logger.warning("[SENTIMENT] LunarCrush API key invalid or expired")
            elif response.status_code == 429:
                Logger.warning("[SENTIMENT] LunarCrush rate limit hit")
            else:
                Logger.debug(f"[SENTIMENT] LunarCrush status {response.status_code}")

        except Exception as e:
            Logger.debug(f"[SENTIMENT] LunarCrush error: {e}")

        return None

    async def _get_volume_score(self, coin: str) -> Optional[float]:
        """
        Calculate volume-based sentiment score.

        High volume = High interest = Score closer to 100
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
            spot = feed.get_spot_price(MINTS.get(coin, ""), USDC)

            if spot:
                # Use price as proxy for volume activity
                # Higher price = more market cap = more activity
                # This is a simplification - real implementation would use DEX volume

                # Normalize SOL ~$100 = 50 score
                if coin == "SOL":
                    score = min(100, (spot.price / 200) * 100)
                else:
                    score = 50  # Default for other coins

                return score

        except Exception as e:
            Logger.debug(f"[SENTIMENT] Volume score error: {e}")

        return None

    async def _get_momentum_score(self, coin: str) -> Optional[float]:
        """
        Calculate price momentum score.

        Rising prices = Bullish sentiment = Score closer to 100
        """
        # For now, return neutral
        # In production, track price over last hour and calculate momentum
        return 50.0

    def get_entry_filter(
        self, sentiment: SentimentScore, funding_apr: float
    ) -> Dict[str, Any]:
        """
        Combine sentiment with funding rate for final entry decision.

        The "Multiplier" logic:
        - High funding + High sentiment = EXECUTE
        - High funding + Low sentiment = WAIT
        - Low funding + Any sentiment = SKIP
        """
        MIN_APR = 10.0  # Minimum 10% APR to consider

        if funding_apr < MIN_APR:
            return {
                "should_enter": False,
                "reason": f"Funding APR {funding_apr:.1f}% below minimum {MIN_APR}%",
                "action": "SKIP",
            }

        if sentiment.should_enter:
            if sentiment.signal == "STRONG_BUY":
                return {
                    "should_enter": True,
                    "reason": f"High APR ({funding_apr:.1f}%) + Strong sentiment ({sentiment.score:.0f})",
                    "action": "EXECUTE",
                }
            else:
                return {
                    "should_enter": True,
                    "reason": f"Good APR ({funding_apr:.1f}%) + Okay sentiment ({sentiment.score:.0f})",
                    "action": "EXECUTE_CAUTIOUS",
                }
        else:
            if sentiment.signal == "DANGER":
                return {
                    "should_enter": False,
                    "reason": f"Sentiment collapsing ({sentiment.score:.0f}) - funding flip likely",
                    "action": "ABORT",
                }
            else:
                return {
                    "should_enter": False,
                    "reason": f"Good APR but sentiment weak ({sentiment.score:.0f}) - wait",
                    "action": "WAIT",
                }


# ═══════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    async def test():
        print("=" * 60)
        print("Sentiment Engine Test")
        print("=" * 60)

        engine = SentimentEngine()

        for coin in ["SOL", "WIF", "JUP"]:
            score = await engine.get_sentiment_score(coin)
            print(score)

            # Test entry filter
            filter_result = engine.get_entry_filter(score, funding_apr=25.0)
            print("\n  Entry Filter (at 25% APR):")
            print(f"    Action: {filter_result['action']}")
            print(f"    Reason: {filter_result['reason']}")

    asyncio.run(test())
