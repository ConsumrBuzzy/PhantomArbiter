"""
Narrow Path Fragments
=====================
Phase 17: Modular Industrialization

UI components for the "Narrow Path" Multi-Hop strategies.
- HopStatsFragment: Cycle metrics (nodes, edges, profit)
- ShadowFragment: Shadow/Live PnL comparison
"""

from typing import Any
from rich.panel import Panel
from rich.table import Table, box
from rich.console import RenderableType

from src.arbiter.ui.fragments.base import BaseFragment

class HopStatsFragment(BaseFragment):
    """
    Displays main cycle stats (Nodes/Edges/Volume).
    Replaces the generic 'stats' panel.
    """
    def __init__(self):
        super().__init__("hop_stats", priority=9)

    def render(self, state: Any) -> RenderableType:
        # Extract stats from state
        trades = state.stats.get('total_trades', 0)
        volume = state.stats.get('volume', 0)
        
        table = Table(box=box.SIMPLE, expand=True)
        table.add_column("Metric", style="dim")
        table.add_column("Value", justify="right", style="bold")
        
        table.add_row("Active Trades", str(trades))
        table.add_row("24h Volume", f"${volume:,.0f}")
        
        # If we had node/edge counts in state, we'd show them here
        # For now, placeholder
        return Panel(table, title="[bold blue]🌌 Multiverse Stats[/bold blue]", border_style="blue")


class ShadowFragment(BaseFragment):
    """
    Legacy Shadow Panel (for non-Scavenger modes).
    """
    def __init__(self):
        super().__init__("shadow", priority=5)

    def render(self, state: Any) -> RenderableType:
        shadow_stats = getattr(state, 'shadow_stats', {})
        
        table = Table(box=box.SIMPLE, expand=True)
        table.add_column("Strategy", style="dim")
        table.add_column("PnL", justify="right")
        
        # Placeholder rendering
        table.add_row("Live", "$0.00")
        table.add_row("Paper", "$0.00")
        
        return Panel(table, title="[bold white]👻 Shadow Mode[/bold white]", border_style="white")
