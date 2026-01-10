"""
Scavenger Fragments
===================
Phase 17: Modular Industrialization

UI components for the "Scavenger" Intelligence layer.
- ScavengerFragment: Shows Hot Pools (Failure Recoils)
- FlowFragment: Shows Institutional Inflows (BridgePod)
"""

from typing import Any
from rich.panel import Panel
from rich.table import Table, box
from rich.console import RenderableType

from src.legacy.arbiter.ui.fragments.base import BaseFragment


class ScavengerFragment(BaseFragment):
    """
    Displays 'Hot Pools' experiencing failure spikes.
    Typically placed in the 'left' or 'shadow' slot.
    """

    def __init__(self):
        super().__init__("scavenger", priority=8)

    def render(self, state: Any) -> RenderableType:
        # Extract data from state
        pod_stats = getattr(state, "pod_stats", {})
        hot_pools = []

        # Look for harvester stats
        for pod_id, stats in pod_stats.items():
            if "harvester" in pod_id.lower() or "failure" in pod_id.lower():
                hot_pools = stats.get("hot_pools", [])

        table = Table(box=box.SIMPLE, expand=True)
        table.add_column("Pool", style="yellow")
        table.add_column("Fails (30s)", justify="center")
        table.add_column("Status", justify="right")

        if not hot_pools:
            table.add_row("[dim]Stable[/dim]", "0", "[green]NOMINAL[/green]")
        else:
            for item in hot_pools[:5]:
                pool = item.get("pool", "unknown")[:8] + "..."
                fails = str(item.get("failures", 0))
                recoil = (
                    "[bold green]RECOIL[/bold green]"
                    if item.get("recoil")
                    else "🔥 HOT"
                )
                table.add_row(pool, fails, recoil)

        return Panel(
            table,
            title="[bold yellow]🦂 Scavenger (Hot Pools)[/bold yellow]",
            border_style="yellow",
        )


class FlowFragment(BaseFragment):
    """
    Displays Institutional Inflows detected by BridgePod.
    Typically placed in the 'right' or 'stats' slot.
    """

    def __init__(self):
        super().__init__("flow", priority=8)

    def render(self, state: Any) -> RenderableType:
        pod_stats = getattr(state, "pod_stats", {})
        bridge_stats = {}

        # Look for sniffer/bridge stats
        for pod_id, stats in pod_stats.items():
            if "sniffer" in pod_id.lower() or "bridge" in pod_id.lower():
                bridge_stats = stats
                break

        table = Table(box=box.SIMPLE, expand=True)
        table.add_column("Period", style="cyan")
        table.add_column("Inflow (USD)", justify="right")
        table.add_column("Whales", justify="center")

        if not bridge_stats:
            table.add_row("1h", "$0", "0")
        else:
            inflow = bridge_stats.get("inflow_1h_usd", 0)
            whales = str(bridge_stats.get("whale_count", 0))
            table.add_row("1h Total", f"[green]${inflow:,.0f}[/green]", whales)

        return Panel(
            table,
            title="[bold cyan]🌉 Institutional Flow[/bold cyan]",
            border_style="cyan",
        )
