"""
V67.0: Drift & Latency Monitor Dashboard
========================================
Phase 5B: Real-time observability for Institutional Realism metrics.

Run: python scripts/monitor_drift.py

Panels:
- RPC Race Stats (who's winning the latency race)
- Execution Drift (Paper vs Live delta)
- Whale-Pulse Activity (boosted signals)
- System Health (memory, FFI latency)
"""

import sys
import time
import psutil
from typing import Dict, List
from collections import deque
from datetime import datetime

try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.progress_bar import ProgressBar
except ImportError:
    print("❌ Rich not installed. Run: pip install rich")
    sys.exit(1)

sys.path.insert(0, ".")


# =============================================================================
# DATA SOURCES (Mock or Real)
# =============================================================================


class DriftMonitor:
    """Aggregates metrics from ShadowManager and other sources."""

    def __init__(self):
        self.shadow_audits: deque = deque(maxlen=20)
        self.rpc_stats: Dict[str, Dict] = {
            "Helius": {"wins": 0, "avg_latency_ms": 0, "calls": 0},
            "Alchemy": {"wins": 0, "avg_latency_ms": 0, "calls": 0},
            "Triton": {"wins": 0, "avg_latency_ms": 0, "calls": 0},
        }
        self.whale_alerts: deque = deque(maxlen=10)
        self.start_time = time.time()

        # Try to connect to real ShadowManager
        self._shadow_manager = None
        try:
            from src.engine.shadow_manager import ShadowManager

            self._shadow_manager = ShadowManager()
        except Exception:
            pass

    def get_shadow_audits(self) -> List:
        """Get recent shadow audits."""
        if self._shadow_manager:
            return self._shadow_manager.get_recent_audits(10)
        return list(self.shadow_audits)

    def get_shadow_stats(self) -> Dict:
        """Get aggregate shadow stats."""
        if self._shadow_manager:
            return self._shadow_manager.get_stats()
        return {
            "total_audits": len(self.shadow_audits),
            "significant_deltas": 0,
            "avg_delta_pct": 0.0,
        }

    def get_rpc_stats(self) -> Dict:
        """Get RPC race statistics."""
        # TODO: Connect to real Race-to-First aggregator
        return self.rpc_stats

    def get_system_health(self) -> Dict:
        """Get system health metrics."""
        process = psutil.Process()
        return {
            "memory_mb": process.memory_info().rss / 1024 / 1024,
            "cpu_pct": process.cpu_percent(interval=0.1),
            "uptime_min": (time.time() - self.start_time) / 60,
        }


# =============================================================================
# DASHBOARD PANELS
# =============================================================================


def create_rpc_panel(monitor: DriftMonitor) -> Panel:
    """Create RPC Race-to-First panel."""
    table = Table(title="🏎️ RPC Race Stats", expand=True)
    table.add_column("Provider", style="cyan")
    table.add_column("Wins", justify="right")
    table.add_column("Win %", justify="right")
    table.add_column("Avg Latency", justify="right")

    stats = monitor.get_rpc_stats()
    total_wins = sum(s["wins"] for s in stats.values())

    for name, data in stats.items():
        win_pct = (data["wins"] / total_wins * 100) if total_wins > 0 else 0
        latency = (
            f"{data['avg_latency_ms']:.0f}ms" if data["avg_latency_ms"] > 0 else "-"
        )

        # Color based on win percentage
        if win_pct > 50:
            style = "bold green"
        elif win_pct > 20:
            style = "yellow"
        else:
            style = "dim"

        table.add_row(name, str(data["wins"]), f"{win_pct:.1f}%", latency, style=style)

    return Panel(table, title="[bold blue]Race-to-First", border_style="blue")


def create_drift_panel(monitor: DriftMonitor) -> Panel:
    """Create Shadow Audit drift panel."""
    table = Table(title="📊 Execution Drift (Paper vs Live)", expand=True)
    table.add_column("Token", style="cyan", max_width=10)
    table.add_column("Delta", justify="right")
    table.add_column("Lag", justify="right")
    table.add_column("Status", justify="center")

    audits = monitor.get_shadow_audits()

    if not audits:
        table.add_row("No audits yet", "-", "-", "⏳", style="dim")
    else:
        for audit in audits[-10:]:
            token = getattr(audit, "mint", "UNKNOWN")[:8]
            delta = getattr(audit, "delta_pct", 0)
            lag = getattr(audit, "execution_lag_ms", 0)

            # Status based on delta
            if abs(delta) < 0.5:
                status = "✅"
                style = "green"
            elif abs(delta) < 1.5:
                status = "⚠️"
                style = "yellow"
            else:
                status = "🔴"
                style = "red"

            table.add_row(token, f"{delta:+.2f}%", f"{lag:.0f}ms", status, style=style)

    # Stats row
    stats = monitor.get_shadow_stats()
    avg_drift = stats.get("avg_delta_pct", 0)

    return Panel(
        table,
        title=f"[bold yellow]Shadow Audit | Avg Drift: {avg_drift:+.2f}%",
        border_style="yellow",
    )


def create_whale_panel(monitor: DriftMonitor) -> Panel:
    """Create Whale-Pulse activity panel."""
    content = []

    # Try to get real whale alerts from signal bus
    alerts = list(monitor.whale_alerts)

    if not alerts:
        content.append("[dim]No whale activity detected[/dim]")
        content.append("")
        content.append("[bold]Bonus Tiers:[/bold]")
        content.append("  $1k-5k:    +5% confidence")
        content.append("  $5k-25k:   +15% confidence")
        content.append("  $25k-100k: +25% confidence")
        content.append("  $100k+:    +35% confidence")
    else:
        for alert in alerts[-5:]:
            mint = alert.get("mint", "???")[:8]
            usd = alert.get("usd_value", 0)
            bonus = alert.get("bonus", 0)
            content.append(f"🐋 {mint} | ${usd:,.0f} | +{bonus:.0%}")

    return Panel(
        "\n".join(content),
        title="[bold magenta]🐋 Whale-Pulse Activity",
        border_style="magenta",
    )


def create_health_panel(monitor: DriftMonitor) -> Panel:
    """Create system health panel."""
    health = monitor.get_system_health()

    lines = [
        f"💾 Memory: {health['memory_mb']:.1f} MB",
        f"🔥 CPU:    {health['cpu_pct']:.1f}%",
        f"⏱️  Uptime: {health['uptime_min']:.1f} min",
        "",
        "[bold]Phase 4+5 Status:[/bold]",
        "  ✅ SignalScorer (Rust)",
        "  ✅ ShadowManager",
        "  ✅ Whale-Pulse",
    ]

    return Panel(
        "\n".join(lines), title="[bold green]System Health", border_style="green"
    )


def create_layout(monitor: DriftMonitor) -> Layout:
    """Create the dashboard layout."""
    layout = Layout()

    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1),
        Layout(name="footer", size=5),
    )

    layout["header"].update(
        Panel(
            "[bold cyan]🏛️ PHANTOMARBITER DRIFT MONITOR[/bold cyan] | Phase 5B: Institutional Realism",
            style="on dark_blue",
        )
    )

    layout["main"].split_row(Layout(name="left"), Layout(name="right"))

    layout["left"].split_column(
        Layout(create_rpc_panel(monitor), name="rpc"),
        Layout(create_whale_panel(monitor), name="whale"),
    )

    layout["right"].split_column(
        Layout(create_drift_panel(monitor), name="drift"),
        Layout(create_health_panel(monitor), name="health"),
    )

    timestamp = datetime.now().strftime("%H:%M:%S")
    layout["footer"].update(
        Panel(
            f"[dim]Last updated: {timestamp} | Press Ctrl+C to exit[/dim]", style="dim"
        )
    )

    return layout


# =============================================================================
# MAIN
# =============================================================================


def main():
    console = Console()
    monitor = DriftMonitor()

    console.print("[bold green]🚀 Starting Drift Monitor Dashboard...[/bold green]")
    console.print("[dim]Press Ctrl+C to exit[/dim]\n")

    try:
        with Live(
            create_layout(monitor), console=console, refresh_per_second=1
        ) as live:
            while True:
                live.update(create_layout(monitor))
                time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard stopped.[/yellow]")


if __name__ == "__main__":
    main()
