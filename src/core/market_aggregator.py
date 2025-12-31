"""
V40.0 Phase 3: Market Aggregator
================================
Unified market status and telemetry across DEX (Solana) and dYdX (Perpetuals).

Provides:
- DEX Advanced Telemetry (ATR, ADX, Bollinger Bands)
- dYdX Health Status (margin, equity, liquidation)
- Unified /status command output for Telegram

Usage:
    aggregator = MarketAggregator(dex_adapter, dydx_adapter)
    status = await aggregator.get_unified_status()
"""

import asyncio
from dataclasses import dataclass
from typing import Optional, Dict, Any
from src.shared.system.logging import Logger
from src.analysis.regime_detector import RegimeDetector


@dataclass
class MarketTelemetry:
    """Telemetry data for a single market."""

    symbol: str
    price: float
    atr_pct: float  # ATR as percentage of price
    adx: float  # Average Directional Index (Trend Strength)
    rsi: float  # Relative Strength
    bb_width: float  # Bollinger Band Width
    trend: str  # TrendRegime
    volatility: str  # VolatilityRegime
    quality: int  # Tradeability Score (0-100)


class MarketAggregator:
    """
    V40.0: Unified market aggregator for DEX and dYdX telemetry.
    V60.0: Upgraded with RegimeDetector (Pandas/Vectorized).
    """

    def __init__(self, dex_adapter=None, dydx_adapter=None):
        """
        Initialize with adapters.
        """
        self.dex_adapter = dex_adapter
        self.dydx_adapter = dydx_adapter
        Logger.info("[AGGREGATOR] MarketAggregator initialized (with RegimeDetector)")

    # ═══════════════════════════════════════════════════════════════════════
    # TELEMETRY GENERATION
    # ═══════════════════════════════════════════════════════════════════════

    async def get_dex_telemetry(self, symbol: str = "SOL") -> Optional[MarketTelemetry]:
        """
        Get advanced telemetry using the V60.0 RegimeDetector.
        """
        try:
            # Try to get candles from DEX adapter or fallback
            if self.dex_adapter and hasattr(self.dex_adapter, "get_candles"):
                candles = await self.dex_adapter.get_candles(symbol, limit=80)
            else:
                # Fallback: Use dYdX SOL-USD as proxy
                if self.dydx_adapter:
                    candles = await self.dydx_adapter.get_candles("SOL-USD", "1MIN", 80)
                else:
                    return None

            if not candles or len(candles) < 30:
                return None

            # Use Regime Detector
            regime = RegimeDetector.detect(candles, symbol=symbol)
            price = candles[-1]["close"]

            return MarketTelemetry(
                symbol=symbol,
                price=price,
                atr_pct=regime.atr_pct,
                adx=regime.adx,
                rsi=regime.rsi,
                bb_width=regime.bb_width,
                trend=regime.trend,
                volatility=regime.volatility,
                quality=regime.quality_score,
            )

        except Exception as e:
            Logger.warning(f"[AGGREGATOR] DEX telemetry failed: {e}")
            import traceback

            traceback.print_exc()
            return None

    async def get_dydx_health(self) -> Optional[Dict[str, Any]]:
        """Get dYdX account health metrics."""
        if not self.dydx_adapter:
            return None

        try:
            balance = await self.dydx_adapter.get_balance()
            positions = await self.dydx_adapter.get_positions()
            ticker = await self.dydx_adapter.get_ticker("ETH-USD")

            if not balance:
                return None

            # Calculate margin ratio
            equity = balance.get("equity", 0)
            free_collateral = balance.get("free_collateral", 0)
            margin_ratio = free_collateral / equity if equity > 0 else 1.0

            return {
                "equity": equity,
                "free_collateral": free_collateral,
                "margin_ratio": margin_ratio,
                "positions_count": len(positions),
                "positions": positions,
                "eth_price": ticker.get("price", 0) if ticker else 0,
                "volume_24h": ticker.get("volume_24h", 0) if ticker else 0,
            }

        except Exception as e:
            Logger.warning(f"[AGGREGATOR] dYdX health check failed: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════════════
    # UNIFIED STATUS OUTPUT
    # ═══════════════════════════════════════════════════════════════════════

    async def get_unified_status(self) -> str:
        """
        Generate unified status report for Telegram /status command.

        Combines:
        - DEX Advanced Telemetry (volatility, trend)
        - dYdX Health Status (margin, positions)

        Returns:
            Formatted status string for Telegram
        """
        sections = []

        # Header
        sections.append("📊 **MARKET STATUS REPORT**")
        sections.append("═" * 30)

        # DEX Telemetry
        dex = await self.get_dex_telemetry("SOL")
        if dex:
            vol_emoji = (
                "🔴"
                if dex.volatility == "HIGH"
                else "🟡"
                if dex.volatility == "MEDIUM"
                else "🟢"
            )
            trend_emoji = (
                "📈" if "TREND" in dex.trend else "↔️" if dex.trend == "RANGING" else "⏸️"
            )

            sections.append("")
            sections.append("🔗 **DEX Market (Solana)**")
            sections.append(f"Price: ${dex.price:,.4f}")
            sections.append(
                f"{vol_emoji} Volatility: **{dex.volatility}** (ATR: {dex.atr_pct * 100:.2f}%)"
            )
            sections.append(
                f"{trend_emoji} Trend: **{dex.trend}** (ADX: {dex.adx:.1f})"
            )
            sections.append(f"BB Width: {dex.bb_width * 100:.1f}%")
        else:
            sections.append("")
            sections.append("🔗 **DEX Market**: ⚠️ Unavailable")

        # dYdX Health
        dydx = await self.get_dydx_health()
        if dydx:
            health_emoji = (
                "🟢"
                if dydx["margin_ratio"] > 0.5
                else "🟡"
                if dydx["margin_ratio"] > 0.2
                else "🔴"
            )

            sections.append("")
            sections.append("📈 **dYdX Perpetuals**")
            sections.append(f"ETH-USD: ${dydx['eth_price']:,.2f}")
            sections.append(f"{health_emoji} Equity: **${dydx['equity']:,.2f}**")
            sections.append(f"Margin Available: {dydx['margin_ratio'] * 100:.1f}%")
            sections.append(f"Open Positions: {dydx['positions_count']}")
            if dydx["volume_24h"] > 0:
                sections.append(f"24h Volume: ${dydx['volume_24h'] / 1e6:.1f}M")
        elif self.dydx_adapter:
            sections.append("")
            sections.append("📈 **dYdX**: 📡 Read-Only Mode")

        # Footer
        sections.append("")
        sections.append("═" * 30)

        return "\n".join(sections)

    async def get_raw_metrics(self) -> Dict[str, Any]:
        """
        Get raw metrics for alert policy evaluation.

        Returns dict with keys:
        - atr_pct: ATR as percentage (for volatility alerts)
        - adx: ADX value (for trend alerts)
        - dydx_margin_ratio: Margin available (for CEX risk alerts)
        - dydx_equity: Account equity
        """
        metrics = {
            "atr_pct": 0.0,
            "adx": 0.0,
            "bb_width": 0.0,
            "dydx_margin_ratio": 1.0,
            "dydx_equity": 0.0,
            "dex_price": 0.0,
            "eth_price": 0.0,
        }

        # Get DEX telemetry
        dex = await self.get_dex_telemetry("SOL")
        if dex:
            metrics["atr_pct"] = dex.atr_pct
            metrics["adx"] = dex.adx
            metrics["bb_width"] = dex.bb_width
            metrics["dex_price"] = dex.price

        # Get dYdX health
        dydx = await self.get_dydx_health()
        if dydx:
            metrics["dydx_margin_ratio"] = dydx.get("margin_ratio", 1.0)
            metrics["dydx_equity"] = dydx.get("equity", 0.0)
            metrics["eth_price"] = dydx.get("eth_price", 0.0)

        return metrics

    # ═══════════════════════════════════════════════════════════════════════
    # JLP STATUS (V45.0 Lazy Landlord)
    # ═══════════════════════════════════════════════════════════════════════

    async def get_jlp_status(self, jlp_state: dict) -> dict:
        """
        Fetch JLP price and calculate current profit/loss.

        Args:
            jlp_state: Dict with entry_price, quantity, initial_value_usd

        Returns:
            Dict with current JLP status and P/L
        """
        import aiohttp

        result = {
            "ready": False,
            "jlp_price": 0.0,
            "current_value": 0.0,
            "profit": 0.0,
            "profit_pct": 0.0,
            "status": "",
            "message": "",
        }

        # Check if JLP state is initialized
        if not jlp_state or jlp_state.get("quantity", 0) == 0:
            result["message"] = (
                "JLP monitoring inactive. Buy JLP and run /set_jlp [price] [quantity]"
            )
            return result

        entry_price = jlp_state.get("entry_price", 0)
        quantity = jlp_state.get("quantity", 0)
        initial_value = jlp_state.get("initial_value_usd", entry_price * quantity)

        # Jupiter JLP Token Address (Pool Token)
        JLP_TOKEN_ADDRESS = "27G8MtK7VtTcCHkpASjSDdkWWYfoqT6ggEuKidVJidD4"

        try:
            async with aiohttp.ClientSession() as session:
                # Use Jupiter Price API
                url = f"https://api.jup.ag/price/v2?ids={JLP_TOKEN_ADDRESS}"

                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        token_data = data.get("data", {}).get(JLP_TOKEN_ADDRESS, {})
                        jlp_price = float(token_data.get("price", 0))
                    else:
                        # Fallback: Try alternate endpoint
                        Logger.warning(f"[JLP] Jupiter API returned {response.status}")
                        jlp_price = 0.0
        except Exception as e:
            Logger.warning(f"[JLP] API error: {e}")
            jlp_price = 0.0

        if jlp_price <= 0:
            result["message"] = "Failed to fetch JLP price from Jupiter API"
            return result

        # Calculate metrics
        result["jlp_price"] = jlp_price
        result["current_value"] = jlp_price * quantity
        result["profit"] = result["current_value"] - initial_value
        result["profit_pct"] = (
            (result["profit"] / initial_value * 100) if initial_value > 0 else 0
        )
        result["ready"] = True

        # Status message
        if result["profit"] >= 0:
            result["status"] = "🏠 Collecting Rent"
        else:
            result["status"] = "📉 Temporary IL/Market Down"

        result["message"] = (
            f"🏠 JLP Status\n"
            f"Price: ${jlp_price:.4f}\n"
            f"Holdings: {quantity:.4f} JLP\n"
            f"Value: ${result['current_value']:.2f}\n"
            f"P/L: ${result['profit']:.2f} ({result['profit_pct']:.2f}%)\n"
            f"{result['status']}"
        )

        return result

    def __repr__(self) -> str:
        dex = "DEX" if self.dex_adapter else "NO-DEX"
        dydx = "dYdX" if self.dydx_adapter else "NO-dYdX"
        return f"<MarketAggregator [{dex}] [{dydx}]>"


# ═══════════════════════════════════════════════════════════════════════════
# TESTING
# ═══════════════════════════════════════════════════════════════════════════


async def test_aggregator():
    """Test the MarketAggregator."""
    print("=" * 60)
    print("MarketAggregator Test")
    print("=" * 60)

    # Test with dYdX adapter only
    from src.infrastructure.dydx_adapter import DydxAdapter

    dydx = DydxAdapter("testnet")
    dydx.connect_sync()

    aggregator = MarketAggregator(dydx_adapter=dydx)
    print(f"\n✅ Aggregator: {aggregator}")

    # Get unified status
    print("\n📊 Fetching unified status...")
    status = await aggregator.get_unified_status()
    print(status)

    print("\n✅ Test complete!")


if __name__ == "__main__":
    asyncio.run(test_aggregator())
