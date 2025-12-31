"""
Narrow Path Fragments
=====================
Phase 17: Modular Industrialization

UI components for the "Narrow Path" Multi-Hop strategies.
- MultiverseFragment: Cycle metrics and finding status
- GraphStatsFragment: Graph topology (Nodes/Edges)
- JitoBundleFragment: Execution preview
"""

from typing import Any
from rich.panel import Panel
from rich.table import Table, box
from rich.console import RenderableType

from src.arbiter.ui.fragments.base import BaseFragment


class MultiverseFragment(BaseFragment):
    """
    Top Right: Multiverse Cycle View.
    Displays the state of the CyclePod (Scanned paths, best opportunity).
    """

    def __init__(self):
        super().__init__("multiverse", priority=10)

    def render(self, state: Any) -> RenderableType:
        # AppState logic should provide these
        best_cycle = getattr(state, "hop_cycles", {}).get("best", {})
        cycles_by_hops = getattr(state, "hop_cycles", {}).get("cycles_by_hops", {})

        table = Table(box=box.SIMPLE, expand=True)
        table.add_column("Hops", style="cyan")
        table.add_column("Paths", justify="right")
        table.add_column("Best ROI", justify="right", style="bold green")

        # 3-hop
        c3 = cycles_by_hops.get(3, 0)
        table.add_row("3-Hop", str(c3), "--")

        # 4-hop
        c4 = cycles_by_hops.get(4, 0)
        table.add_row("4-Hop", str(c4), "--")

        # Best Opp
        best_profit = best_cycle.get("profit_pct", 0.0)
        best_path = best_cycle.get("path_display", "Scanning...")

        summary = f"\n[bold gold1]Best Opportunity:[/bold gold1]\n{best_path}\nROI: [green]+{best_profit:.3f}%[/green]"

        from rich.layout import Layout

        layout = Layout()
        layout.split_column(
            Layout(table), Layout(Panel(summary, box=box.SIMPLE, style="dim"))
        )

        return Panel(
            layout,
            title="[bold cyan]🌌 Multiverse Scanner[/bold cyan]",
            border_style="cyan",
        )


class GraphStatsFragment(BaseFragment):
    """
    Mid Right: Graph Stats.
    Displays Token counts, Pairs, and Liquidity depth.
    """

    def __init__(self):
        super().__init__("graph_stats", priority=10)

    def render(self, state: Any) -> RenderableType:
        # Placeholder stats until Graph is fully connected to State
        # In a real impl, we'd pull from state.graph_stats
        nodes = getattr(state, "graph_stats", {}).get("nodes", 1240)
        edges = getattr(state, "graph_stats", {}).get("edges", 3105)
        updated = getattr(state, "graph_stats", {}).get("last_update", "Now")

        grid = Table.grid(expand=True)
        grid.add_column()
        grid.add_column(justify="right")

        grid.add_row("Active Nodes:", f"[bold white]{nodes}[/bold white]")
        grid.add_row("Directed Edges:", f"[bold white]{edges}[/bold white]")
        grid.add_row("Deep Liquidity:", "[green]42 pools[/green]")
        grid.add_row("Sparse Pools:", "[yellow]15 pools[/yellow]")
        grid.add_row("Last Update:", f"[dim]{updated}[/dim]")

        return Panel(
            grid,
            title="[bold yellow]📊 Graph Topology[/bold yellow]",
            border_style="yellow",
        )


class JitoBundleFragment(BaseFragment):
    """
    Bottom Right: Jito Bundle Preview.
    Shows the last executed or planned bundle structure.
    """

    def __init__(self):
        super().__init__("jito_bundle", priority=10)

    def render(self, state: Any) -> RenderableType:
        # Pull from ExecutionPod stats if available
        pod_stats = getattr(state, "pod_stats", {})
        pods = pod_stats.get("pods", [])
        exec_pod = next((p for p in pods if p["pod_type"] == "execution"), None)

        if not exec_pod:
            return Panel(
                "Waiting for ExecutionPod...",
                title="[bold red]⚔️ Jito Allocator[/bold red]",
                border_style="red",
            )

        history = exec_pod.get("recent_history", [])
        last_trade = history[-1] if history else None

        if last_trade:
            # Format trade
            profit = last_trade.get("expected_profit_pct", 0)
            tip = last_trade.get("tip_lamports", 0)
            mode = last_trade.get("mode", "GHOST")
            sig = last_trade.get("signature", "N/A")

            content = (
                f"[bold]Mode:[/bold] {mode.upper()}\n"
                f"[bold]Profit:[/bold] [green]+{profit:.3f}%[/green]\n"
                f"[bold]Jito Tip:[/bold] {tip} lamports\n"
                f"[dim]Sig: {sig[:8]}...[/dim]"
            )
        else:
            content = "[dim]No bundles executed yet.[/dim]"

        return Panel(
            content,
            title="[bold red]⚔️ Jito Bundle Preview[/bold red]",
            border_style="red",
        )


class ShadowFragment(BaseFragment):
    """
    Legacy Shadow Panel (for non-Scavenger modes).
    """

    def __init__(self):
        super().__init__("shadow", priority=5)

    def render(self, state: Any) -> RenderableType:
        # Use state correctly
        table = Table(box=box.SIMPLE, expand=True)
        table.add_column("Strategy", style="dim")
        table.add_column("PnL", justify="right")
        table.add_row("Live", "$0.00")
        table.add_row("Paper", "$0.00")
        return Panel(
            table, title="[bold white]👻 Shadow Mode[/bold white]", border_style="white"
        )
