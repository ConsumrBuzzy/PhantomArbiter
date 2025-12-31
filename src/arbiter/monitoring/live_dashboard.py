"""
V1.0: Live Arbitrage Dashboard
==============================
Real-time console output showing market spreads and opportunities.

This is the PRIMARY INTERFACE for the arbitrage engine.
Updates every second with colorful, easy-to-read output.
"""

import os
import time
from dataclasses import dataclass, field
from typing import List, Dict
from datetime import datetime

from config.settings import Settings


@dataclass
class PriceUpdate:
    """Price data from a single DEX."""

    dex: str
    pair: str
    price: float
    timestamp: float = field(default_factory=time.time)

    @property
    def age_ms(self) -> int:
        return int((time.time() - self.timestamp) * 1000)


@dataclass
class SpreadInfo:
    """Calculated spread between DEXs for a pair."""

    pair: str
    prices: Dict[str, float]  # {dex_name: price}
    best_buy: str  # DEX with lowest price
    best_sell: str  # DEX with highest price
    spread_pct: float  # Percentage spread
    estimated_profit_usd: float  # At current trade size
    status: str  # "READY", "MONITOR", "LOW"


@dataclass
class TodayStats:
    """Running stats for today's performance."""

    trades: int = 0
    volume_usd: float = 0.0
    profit_usd: float = 0.0
    budget: float = 500.0
    start_time: float = field(default_factory=time.time)

    @property
    def turnover_ratio(self) -> float:
        return self.volume_usd / self.budget if self.budget > 0 else 0

    @property
    def profit_pct(self) -> float:
        return (self.profit_usd / self.budget) * 100 if self.budget > 0 else 0


class LiveDashboard:
    """
    Real-time arbitrage monitoring dashboard.

    Features:
    - Live spread matrix across DEXs
    - Funding rate display (Drift)
    - Today's P&L and turnover
    - Color-coded opportunity alerts
    """

    # ANSI Colors
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Foreground colors
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"

    # Status colors
    STATUS_COLORS = {
        "READY": "\033[92m",  # Green
        "MONITOR": "\033[94m",  # Blue
        "LOW": "\033[90m",  # Gray
        "EXECUTING": "\033[93m",  # Yellow
        "PROFIT": "\033[92m",  # Green
        "LOSS": "\033[91m",  # Red
    }

    # Box drawing characters
    BOX = {
        "tl": "╔",
        "tr": "╗",
        "bl": "╚",
        "br": "╝",
        "h": "═",
        "v": "║",
        "lm": "╠",
        "rm": "╣",
        "tm": "╦",
        "bm": "╩",
        "x": "╬",
        "hl": "─",
        "vl": "│",
    }

    def __init__(self, budget: float = 500.0):
        self.stats = TodayStats(budget=budget)
        self.spreads: List[SpreadInfo] = []
        self.funding_rates: Dict[str, float] = {}
        self.last_update = time.time()
        self.mode = getattr(Settings, "ARBITRAGE_MODE", "FUNDING")

        # Pair configuration (will be populated from settings)
        self.monitored_pairs = ["SOL/USDC", "BONK/SOL", "WIF/USDC"]
        self.dex_names = ["Jupiter", "Raydium", "Orca"]

    def _clear_screen(self):
        """Clear terminal screen."""
        os.system("cls" if os.name == "nt" else "clear")

    def _center(self, text: str, width: int) -> str:
        """Center text within width."""
        text_len = len(
            text.replace("\033[0m", "")
            .replace("\033[1m", "")
            .replace("\033[2m", "")
            .replace("\033[91m", "")
            .replace("\033[92m", "")
            .replace("\033[93m", "")
            .replace("\033[94m", "")
            .replace("\033[95m", "")
            .replace("\033[96m", "")
            .replace("\033[97m", "")
            .replace("\033[90m", "")
        )
        padding = (width - text_len) // 2
        return " " * padding + text

    def _make_box_line(self, left: str, fill: str, right: str, width: int) -> str:
        """Create a box line."""
        return left + fill * (width - 2) + right

    def _pad_cell(self, text: str, width: int) -> str:
        """Pad text to width, accounting for ANSI codes."""
        # Strip ANSI for length calculation
        visible_len = len(text)
        for code in [
            "\033[0m",
            "\033[1m",
            "\033[2m",
            "\033[91m",
            "\033[92m",
            "\033[93m",
            "\033[94m",
            "\033[95m",
            "\033[96m",
            "\033[97m",
            "\033[90m",
        ]:
            visible_len -= text.count(code) * len(code)

        padding = width - visible_len
        if padding > 0:
            return text + " " * padding
        return text[:width]

    def _format_spread_indicator(self, spread_pct: float) -> str:
        """Format spread with color and arrows."""
        if spread_pct >= 0.5:
            return f"{self.GREEN}+{spread_pct:.2f}% ▲▲{self.RESET}"
        elif spread_pct >= 0.3:
            return f"{self.YELLOW}+{spread_pct:.2f}% ▲{self.RESET}"
        elif spread_pct >= 0.1:
            return f"{self.BLUE}+{spread_pct:.2f}%{self.RESET}"
        else:
            return f"{self.DIM}+{spread_pct:.2f}%{self.RESET}"

    def _format_status(self, status: str) -> str:
        """Format status with emoji and color."""
        color = self.STATUS_COLORS.get(status, self.WHITE)
        icons = {
            "READY": "🟢",
            "MONITOR": "🔵",
            "LOW": "⚪",
            "EXECUTING": "🟡",
        }
        icon = icons.get(status, "⚪")
        return f"{icon} {color}{status}{self.RESET}"

    def _format_price(self, price: float) -> str:
        """Format price with appropriate precision."""
        if price >= 1.0:
            return f"${price:.2f}"
        elif price >= 0.001:
            return f"${price:.4f}"
        elif price >= 0.000001:
            return f"${price:.6f}"
        else:
            return f"${price:.8f}"

    def _format_funding_rate(self, rate: float) -> str:
        """Format funding rate with color."""
        if rate > 0:
            return f"{self.GREEN}+{rate:.4f}%{self.RESET}"
        elif rate < 0:
            return f"{self.RED}{rate:.4f}%{self.RESET}"
        else:
            return f"{rate:.4f}%"

    def update_spreads(self, spreads: List[SpreadInfo]):
        """Update spread data."""
        self.spreads = spreads
        self.last_update = time.time()

    def update_funding_rates(self, rates: Dict[str, float]):
        """Update funding rate data from Drift."""
        self.funding_rates = rates

    def record_trade(self, volume_usd: float, profit_usd: float):
        """Record a completed trade."""
        self.stats.trades += 1
        self.stats.volume_usd += volume_usd
        self.stats.profit_usd += profit_usd

    def generate_dashboard(self) -> str:
        """Generate the full dashboard string."""
        WIDTH = 72
        lines = []

        # Header
        lines.append(
            f"{self.CYAN}{self._make_box_line(self.BOX['tl'], self.BOX['h'], self.BOX['tr'], WIDTH)}{self.RESET}"
        )
        lines.append(
            f"{self.CYAN}{self.BOX['v']}{self.RESET}{self._center(f'{self.BOLD}ARBITRAGE ENGINE v1.0{self.RESET}', WIDTH - 2)}{self.CYAN}{self.BOX['v']}{self.RESET}"
        )
        lines.append(
            f"{self.CYAN}{self.BOX['v']}{self.RESET}{self._center(f'Mode: {self.YELLOW}{self.mode}{self.RESET} | Budget: {self.GREEN}${self.stats.budget:.0f}{self.RESET}', WIDTH - 2)}{self.CYAN}{self.BOX['v']}{self.RESET}"
        )
        lines.append(
            f"{self.CYAN}{self._make_box_line(self.BOX['lm'], self.BOX['h'], self.BOX['rm'], WIDTH)}{self.RESET}"
        )

        # Live Spreads Section
        now = datetime.now().strftime("%H:%M:%S")
        lines.append(
            f"{self.CYAN}{self.BOX['v']}{self.RESET} {self.BOLD}LIVE SPREADS{self.RESET}                                      Updated: {self.DIM}{now}{self.RESET} {self.CYAN}{self.BOX['v']}{self.RESET}"
        )
        lines.append(
            f"{self.CYAN}{self._make_box_line(self.BOX['lm'], self.BOX['h'], self.BOX['rm'], WIDTH)}{self.RESET}"
        )

        # Column headers
        header = f"{self.CYAN}{self.BOX['v']}{self.RESET} {'Pair':<10} │ {'Jupiter':>9} │ {'Raydium':>9} │ {'Orca':>8} │ {'Spread':^12} │ {'Action':^10} {self.CYAN}{self.BOX['v']}{self.RESET}"
        lines.append(header)
        lines.append(
            f"{self.CYAN}{self.BOX['v']}{self.RESET}{'─' * 11}┼{'─' * 11}┼{'─' * 11}┼{'─' * 10}┼{'─' * 14}┼{'─' * 12}{self.CYAN}{self.BOX['v']}{self.RESET}"
        )

        # Spread rows
        if self.spreads:
            for spread in self.spreads[:5]:  # Max 5 pairs
                jup_price = spread.prices.get("Jupiter", 0)
                ray_price = spread.prices.get("Raydium", 0)
                orca_price = spread.prices.get("Orca", 0)

                jup_str = self._format_price(jup_price) if jup_price > 0 else "--"
                ray_str = self._format_price(ray_price) if ray_price > 0 else "--"
                orca_str = self._format_price(orca_price) if orca_price > 0 else "--"

                spread_str = self._format_spread_indicator(spread.spread_pct)
                status_str = self._format_status(spread.status)

                row = f"{self.CYAN}{self.BOX['v']}{self.RESET} {spread.pair:<10} │ {jup_str:>9} │ {ray_str:>9} │ {orca_str:>8} │ {spread_str:^12} │ {status_str:^10} {self.CYAN}{self.BOX['v']}{self.RESET}"
                lines.append(row)
        else:
            lines.append(
                f"{self.CYAN}{self.BOX['v']}{self.RESET} {self.DIM}Waiting for price data...{self.RESET}{' ' * 43}{self.CYAN}{self.BOX['v']}{self.RESET}"
            )

        # Funding Rates Section (if enabled)
        if self.mode in ["FUNDING", "ALL"]:
            lines.append(
                f"{self.CYAN}{self._make_box_line(self.BOX['lm'], self.BOX['h'], self.BOX['rm'], WIDTH)}{self.RESET}"
            )
            lines.append(
                f"{self.CYAN}{self.BOX['v']}{self.RESET} {self.BOLD}FUNDING RATES (Drift){self.RESET}{' ' * 48}{self.CYAN}{self.BOX['v']}{self.RESET}"
            )
            lines.append(
                f"{self.CYAN}{self._make_box_line(self.BOX['lm'], self.BOX['h'], self.BOX['rm'], WIDTH)}{self.RESET}"
            )

            if self.funding_rates:
                for market, rate in list(self.funding_rates.items())[:3]:
                    rate_str = self._format_funding_rate(rate)
                    min_rate = getattr(Settings, "FUNDING_MIN_RATE_PCT", 0.01)
                    status = (
                        f"{self.GREEN}PROFITABLE{self.RESET}"
                        if abs(rate) >= min_rate
                        else f"{self.DIM}BELOW MIN{self.RESET}"
                    )
                    lines.append(
                        f"{self.CYAN}{self.BOX['v']}{self.RESET} {market:<10} │ {rate_str}/8h │ Next: 2h 15m │ {status}{' ' * 16}{self.CYAN}{self.BOX['v']}{self.RESET}"
                    )
            else:
                lines.append(
                    f"{self.CYAN}{self.BOX['v']}{self.RESET} {self.DIM}Connecting to Drift...{self.RESET}{' ' * 47}{self.CYAN}{self.BOX['v']}{self.RESET}"
                )

        # Today's Performance
        lines.append(
            f"{self.CYAN}{self._make_box_line(self.BOX['lm'], self.BOX['h'], self.BOX['rm'], WIDTH)}{self.RESET}"
        )
        lines.append(
            f"{self.CYAN}{self.BOX['v']}{self.RESET} {self.BOLD}TODAY'S PERFORMANCE{self.RESET}{' ' * 50}{self.CYAN}{self.BOX['v']}{self.RESET}"
        )
        lines.append(
            f"{self.CYAN}{self._make_box_line(self.BOX['lm'], self.BOX['h'], self.BOX['rm'], WIDTH)}{self.RESET}"
        )

        turnover = self.stats.turnover_ratio
        trades = self.stats.trades
        volume = self.stats.volume_usd
        profit = self.stats.profit_usd
        profit_pct = self.stats.profit_pct

        # Color profit
        if profit >= 0:
            profit_str = f"{self.GREEN}+${profit:.2f} (+{profit_pct:.2f}%){self.RESET}"
        else:
            profit_str = (
                f"{self.RED}-${abs(profit):.2f} ({profit_pct:.2f}%){self.RESET}"
            )

        perf_line = f" Turnover: {self.YELLOW}{turnover:.1f}x{self.RESET} │ Trades: {trades} │ Volume: ${volume:,.2f} │ Profit: {profit_str}"
        lines.append(
            f"{self.CYAN}{self.BOX['v']}{self.RESET}{perf_line}{' ' * (WIDTH - len(perf_line.replace(self.RESET, '').replace(self.GREEN, '').replace(self.YELLOW, '').replace(self.RED, '')) - 3)}{self.CYAN}{self.BOX['v']}{self.RESET}"
        )

        # Footer
        lines.append(
            f"{self.CYAN}{self._make_box_line(self.BOX['bl'], self.BOX['h'], self.BOX['br'], WIDTH)}{self.RESET}"
        )

        return "\n".join(lines)

    def render(self, clear: bool = True):
        """Render the dashboard to console."""
        if clear:
            self._clear_screen()
        print(self.generate_dashboard())

    def get_telegram_summary(self) -> str:
        """Get a compact summary for Telegram."""
        lines = [
            "📊 *ARBITRAGE ENGINE*",
            f"Mode: `{self.mode}` | Budget: `${self.stats.budget:.0f}`",
            "",
            "*Top Spreads:*",
        ]

        for spread in self.spreads[:3]:
            emoji = (
                "🟢"
                if spread.status == "READY"
                else "🔵"
                if spread.status == "MONITOR"
                else "⚪"
            )
            lines.append(f"{emoji} {spread.pair}: +{spread.spread_pct:.2f}%")

        lines.extend(
            [
                "",
                "*Today:*",
                f"• Turnover: {self.stats.turnover_ratio:.1f}x",
                f"• Trades: {self.stats.trades}",
                f"• Profit: ${self.stats.profit_usd:+.2f} ({self.stats.profit_pct:+.2f}%)",
            ]
        )

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# DEMO / TEST
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Demo with fake data
    dashboard = LiveDashboard(budget=500.0)

    # Add sample spread data
    sample_spreads = [
        SpreadInfo(
            pair="SOL/USDC",
            prices={"Jupiter": 95.42, "Raydium": 95.51, "Orca": 95.48},
            best_buy="Jupiter",
            best_sell="Raydium",
            spread_pct=0.09,
            estimated_profit_usd=0.09,
            status="MONITOR",
        ),
        SpreadInfo(
            pair="BONK/SOL",
            prices={"Jupiter": 0.0000234, "Raydium": 0.0000235, "Orca": 0.0},
            best_buy="Jupiter",
            best_sell="Raydium",
            spread_pct=0.03,
            estimated_profit_usd=0.03,
            status="LOW",
        ),
        SpreadInfo(
            pair="WIF/USDC",
            prices={"Jupiter": 2.34, "Raydium": 2.35, "Orca": 2.34},
            best_buy="Jupiter",
            best_sell="Raydium",
            spread_pct=0.42,
            estimated_profit_usd=0.84,
            status="READY",
        ),
    ]

    dashboard.update_spreads(sample_spreads)
    dashboard.update_funding_rates({"SOL-PERP": 0.0125, "BTC-PERP": 0.0089})

    # Simulate some trades
    dashboard.record_trade(200.0, 0.84)
    dashboard.record_trade(150.0, 0.45)
    dashboard.record_trade(100.0, -0.12)

    # Render
    dashboard.render()

    print("\n" + "=" * 72)
    print("Telegram Summary:")
    print("=" * 72)
    print(dashboard.get_telegram_summary())
