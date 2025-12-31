"""
Race Speedometer: Visualizing the "Fast-Path"
=============================================
Tracks and displays "Race-to-First" stats from the Rust Aggregator.
"""

from rich.table import Table
from rich.panel import Panel
from rich.console import Group
from collections import defaultdict
import time


class RaceSpeedometer:
    def __init__(self):
        # Stats: {Provider: Wins}
        self.stats = defaultdict(int)
        self.total_deduped = 0
        self.total_events = 0
        self.start_time = time.time()

        # Latency tracking (Provider -> List of latencies? No, fast aggregated stats)
        # For now simpler is better.

    def update(self, provider_name: str, latency_ms: float = 0.0):
        """Register a win for a provider."""
        self.stats[provider_name] += 1
        self.total_events += 1
        # self.latencies.append(latency_ms) # If we want to track latency

    def update_dedup(self, count=1):
        """Register deduped (dropped) messages."""
        self.total_deduped += count

    def generate_view(self) -> Panel:
        """Render the speedometer panel."""
        table = Table(title="🏎️  RPC Race Statistics", expand=True, border_style="cyan")
        table.add_column("Provider", style="cyan", no_wrap=True)
        table.add_column("Wins 🥇", justify="right", style="green")
        table.add_column("Win %", justify="right", style="magenta")
        table.add_column("Speed (est)", justify="right", style="yellow")

        total_wins = sum(self.stats.values()) or 1

        # Sort by wins desc
        sorted_stats = sorted(self.stats.items(), key=lambda x: x[1], reverse=True)

        for provider, wins in sorted_stats:
            percentage = (wins / total_wins) * 100
            table.add_row(
                provider,
                f"{wins:,}",
                f"{percentage:.1f}%",
                "⚡ FAST" if percentage > 30 else "🐢",
            )

        # Footer metrics
        duration = time.time() - self.start_time
        mps = self.total_events / duration if duration > 0 else 0

        footer = f"Generated: {self.total_events} | Deduped: {self.total_deduped} | Rate: {mps:.1f} msg/s"

        return Panel(
            Group(table, f"[dim]{footer}[/dim]"),
            title="[bold green]Network Fast-Path[/bold green]",
            border_style="green",
        )
