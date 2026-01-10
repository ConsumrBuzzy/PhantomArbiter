"""
V89.2: Unified Market Snapshot Utility
Central logic for "Green/Red" market summaries used by Console Dashboard and Telegram.
"""

from typing import Dict
from src.core.shared_cache import SharedPriceCache


class MarketSnapshot:
    """Generates consistent market snapshots."""

    @staticmethod
    def get_snapshot() -> Dict[str, str]:
        """
        Get market snapshot data.
        Returns dict with:
            - top_gainers: formatted string
            - top_losers: formatted string
            - summary_line: combined string
            - mover_count: int
        """
        try:
            from src.shared.infrastructure.token_registry import get_registry

            raw = SharedPriceCache._read_raw()
            # V89.8: Read from market_data (where DexScreener writes price_change_1h)
            market_data = raw.get("market_data", {})

            # V89.10: Use TokenRegistry for symbol resolution
            registry = get_registry()

            # V89.12: Also read prices from cache
            prices_cache = raw.get("prices", {})

            movers = []
            for mint, data in market_data.items():
                if isinstance(data, dict):
                    change = data.get("price_change_1h") or 0
                    # V89.11: Use centralized registry with confidence tracking
                    symbol, confidence, source = registry.get_symbol_with_confidence(
                        mint
                    )
                    # V89.12: Get price (from prices cache or market_data)
                    price = (
                        prices_cache.get(symbol, {}).get("price", 0)
                        if isinstance(prices_cache.get(symbol), dict)
                        else 0
                    )
                    if change != 0:
                        movers.append((symbol, change, confidence, price))

            # Sort by change
            movers.sort(key=lambda x: x[1], reverse=True)

            if not movers:
                return {
                    "top_gainers": "—",
                    "top_losers": "—",
                    "summary_line": "—",
                    "mover_count": 0,
                }

            # Filter Groups
            gainers = [(s, c, conf, p) for s, c, conf, p in movers if c >= 0.5]
            losers = [(s, c, conf, p) for s, c, conf, p in movers if c <= -0.5]
            greys = [(s, c, conf, p) for s, c, conf, p in movers if -0.5 < c < 0.5]

            # Sort
            gainers.sort(key=lambda x: x[1], reverse=True)
            losers.sort(key=lambda x: x[1])
            # Sort greys by absolute change (most active first)
            greys.sort(key=lambda x: abs(x[1]), reverse=True)

            # Format Top 5 of each - with confidence icons AND prices
            top_g = gainers[:5]
            top_l = losers[:5]
            top_grey = greys[:8]

            # V89.11: Confidence icons
            def conf_icon(confidence):
                if confidence >= 0.9:
                    return "✅"
                if confidence >= 0.5:
                    return "⚠️"
                return "❌"

            # V89.12: Format with price
            def fmt_price(price):
                if price >= 1:
                    return f"${price:.2f}"
                if price >= 0.01:
                    return f"${price:.4f}"
                return f"${price:.6f}"

            g_fmt = (
                "\n".join(
                    [
                        f"{conf_icon(conf)} {s:<6} {fmt_price(p):<10} +{c:>5.1f}%"
                        for s, c, conf, p in top_g
                    ]
                )
                if top_g
                else "_No Gainers_"
            )
            l_fmt = (
                "\n".join(
                    [
                        f"{conf_icon(conf)} {s:<6} {fmt_price(p):<10} {c:>6.1f}%"
                        for s, c, conf, p in top_l
                    ]
                )
                if top_l
                else "_No Losers_"
            )
            grey_fmt = (
                " ".join([f"{s}({c:+.1f}%)" for s, c, conf, p in top_grey])
                if top_grey
                else "_None_"
            )

            # Dashboard One-Liners (Compact for table - no icons for space)
            g_line = (
                " ".join([f"{s}+{c:.0f}%" for s, c, conf, p in top_g[:3]])
                if top_g
                else "—"
            )
            l_line = (
                " ".join([f"{s}{c:.0f}%" for s, c, conf, p in top_l[:3]])
                if top_l
                else "—"
            )

            # Telegram Block (Detailed)
            summary = (
                f"**🚀 TOP GAINERS:**\\n{g_fmt}\\n\\n"
                f"**🩸 TOP LOSERS:**\\n{l_fmt}\\n\\n"
                f"**☁️ WATCHLIST (Quiet):**\\n{grey_fmt}"
            )

            # V89.13: List format for Console Dashboard
            def fmt_list_line(symbol, price, change, conf):
                icon = conf_icon(conf)
                price_str = fmt_price(price)
                return f"{icon} {symbol:<6} {price_str:<10} {change:+5.1f}%"

            gainer_list = [fmt_list_line(s, p, c, conf) for s, c, conf, p in top_g]
            loser_list = [fmt_list_line(s, p, c, conf) for s, c, conf, p in top_l]

            return {
                "top_gainers": g_line,  # Compact for old format
                "top_losers": l_line,
                "summary_line": summary,
                "mover_count": len(movers),
                # V89.13: List format for console
                "snapshot_gainers": gainer_list,
                "snapshot_losers": loser_list,
            }

        except Exception as e:
            Logger.error(f"⚠️ MarketSnapshot error: {e}")
            return {
                "top_gainers": "—",
                "top_losers": "—",
                "summary_line": "Error loading snapshot",
                "mover_count": 0,
                "snapshot_gainers": [],
                "snapshot_losers": [],
            }
