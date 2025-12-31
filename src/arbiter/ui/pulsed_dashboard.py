"""
Rich Pulse Dashboard
====================
A lightweight "Headless TUI" using Rich.live.
Provides Panels and layout without the full application lifecycle of Textual.

V140: Updated to use Modular Fragment Architecture.
"""

from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.console import Console
from rich import box
from datetime import datetime
from typing import List, Dict, Any

from src.arbiter.core.reporter import ArbiterReporter
from src.arbiter.ui.fragments.registry import registry
from src.arbiter.ui.fragments.scavenger import ScavengerFragment, FlowFragment
from config.settings import Settings

class PulsedDashboard:
    """Layout manager for the Pulse View."""
    
    def __init__(self):
        self.layout = Layout()
        self.layout.split(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3)
        )
        # Main area: Split Left (Arbiter + Signals) and Right (Scalper/Inventory/Stats)
        self.layout["main"].split_row(
            Layout(name="left_container", ratio=3), 
            Layout(name="right", ratio=2)
        )
        
        self.layout["left_container"].split_column(
            Layout(name="left", ratio=2), # Arb Table
            Layout(name="signals", ratio=1), # Signal Audit
            Layout(name="shadow", ratio=1) # Shadow/Drift Pane
        )
        
        # Right Column: Split Top (Scalper), Middle (Inventory), Bottom (Stats)
        self.layout["right"].split_column(
            Layout(name="scalper", ratio=1),
            Layout(name="inventory", ratio=1),
            Layout(name="stats", size=6)
        )
        
        self._init_fragments()

    def _init_fragments(self):
        """Register fragments based on active mode."""
        if getattr(Settings, 'HOP_ENGINE_ENABLED', False):
            # Phase 17: Narrow Path / Hop Mode
            from src.arbiter.ui.fragments.narrow_path import (
                MultiverseFragment, 
                GraphStatsFragment, 
                JitoBundleFragment
            )
            from src.arbiter.ui.fragments.scavenger import ScavengerFragment
            
            # Left Bottom
            registry.register("shadow", ScavengerFragment())
            
            # Right Column (The "Pair Hop" Control Center)
            registry.register("scalper", MultiverseFragment())
            registry.register("inventory", GraphStatsFragment())
            registry.register("stats", JitoBundleFragment())
        else:
            # Legacy Mode / Scalper Mode
            registry.register("shadow", ShadowFragment())
            # registry.register("stats", StandardStatsFragment())

    def generate_header(self, state: Any):
        """Render header with Real/Paper split."""
        # Real Wallet
        real_usdc = state.wallet_live.balance_usdc
        real_sol = state.wallet_live.balance_sol
        
        # Paper Wallet
        paper_usdc = state.wallet_paper.balance_usdc
        paper_sol = state.wallet_paper.balance_sol
        
        pod_status = state.stats.get('pod_status', "")
        pod_str = f" | 🔭 {pod_status}" if pod_status else ""
        
        # Layout: REAL [USDC | SOL]  ||  PAPER [USDC | SOL]
        text = (
            f"[bold cyan]PHANTOM PULSE[/bold cyan]{pod_str}   "
            f"🔴 [bold]REAL:[/bold] [green]${real_usdc:,.2f}[/green] / [yellow]{real_sol:.3f} SOL[/yellow]   "
            f"⚪ [dim]PAPER:[/dim] [green]${paper_usdc:,.2f}[/green] / [yellow]{paper_sol:.3f} SOL[/yellow]"
        )
        return Panel(text, style="white on blue", box=box.HEAVY_HEAD)
        
    def generate_opp_table(self, spreads: Any, verified_opps: Any = None):
        """Legacy helper - TODO: Migrate to Fragment."""
        # Implementation kept for continuity until full migration
        table = Table(box=box.SIMPLE_HEAD, expand=True)
        table.add_column("Pair", style="cyan")
        table.add_column("Spread", justify="right")
        table.add_column("Net Profit", justify="right")
        table.add_column("Route", style="dim")
        table.add_column("Status", justify="center")
        
        # Minimal placeholder if passed complex objects
        return Panel(table, title="[bold]Live Market Observer[/bold]", border_style="blue")
        
    def generate_scalper_panel(self, signals: List[Any], market_pulse: Dict[str, Any] = None):
        """Legacy helper - TODO: Migrate to Fragment."""
        if getattr(Settings, 'HOP_ENGINE_ENABLED', False):
             return self.generate_multiverse_panel(signals)
             
        table = Table(box=box.SIMPLE, expand=True)
        table.add_column("Token", style="magenta")
        table.add_column("Status", style="cyan")
        return Panel(table, title="[magenta]Scalper & Price Watch[/magenta]", border_style="magenta")

    def generate_multiverse_panel(self, hop_data: Any = None):
         """Legacy helper - TODO: Migrate to Fragment."""
         table = Table(box=box.SIMPLE, expand=True)
         table.add_column("Hops", style="cyan", width=4)
         return Panel(table, title="[cyan]🌌 Multiverse Hop Scanner[/cyan]", border_style="cyan")

    def generate_signal_panel(self, signals: List[Any]):
        """Legacy helper - TODO: Migrate to Fragment."""
        table = Table(box=box.SIMPLE, expand=True)
        table.add_column("Time", style="dim")
        table.add_column("Type")
        table.add_column("Source", style="cyan")
        table.add_column("Summary", ratio=1)
        
        for sig in list(signals)[:10]:
            ts = datetime.fromtimestamp(sig.timestamp).strftime("%H:%M:%S")
            s_type = sig.type.value
            color = "white"
            if s_type == "WHALE": color = "bold blue"
            elif s_type == "SCOUT": color = "bold green"
            elif s_type == "ARB_OPP": color = "cyan"
            
            summary = str(sig.data.get("symbol", sig.data.get("message", "Data...")))
            table.add_row(ts, f"[{color}]{s_type}[/{color}]", sig.source, summary)
            
        return Panel(table, title="Signal Intelligence (Global Feed)", border_style="magenta")
        
    def generate_inventory_panel(self, inventory: Any):
         """Legacy helper - TODO: Migrate"""
         # V140: In Narrow Path mode, shows Graph Stats instead.
         if getattr(Settings, 'HOP_ENGINE_ENABLED', False):
            return self.generate_graph_stats_panel(inventory)
         return Panel("Inventory", title="Inventory", border_style="yellow")

    def generate_graph_stats_panel(self, stats_data: Any = None):
        """Legacy helper - TODO: Migrate"""
        from rich.table import Table as RichTable
        grid = RichTable.grid(expand=True)
        grid.add_column(ratio=1)
        grid.add_row("Nodes:", "0")
        return Panel(grid, title="[yellow]📊 Graph Engine Stats[/yellow]", border_style="yellow")

    def generate_stats_panel(self, trades: int, volume: float, turnover: float):
        """Legacy helper - TODO: Migrate"""
        return Panel("Session Stats", title="Strategy Engine", border_style="white")


class RichPulseReporter(ArbiterReporter):
    """Overrides default Reporter to render to Rich Layout."""
    
    def __init__(self, telegram=None):
        super().__init__(telegram)
        from src.shared.system.logging import Logger
        Logger.set_silent(True) # V135: Silence console logs to prevent TUI artifacts
        self.dashboard = PulsedDashboard()
        self.live = Live(self.dashboard.layout, refresh_per_second=2, screen=True) 
        self.live.start()
        
    def update_from_state(self, app_state):
        """Pull ALL data from AppState (The Global Truth)."""
        # 1. Header
        self.dashboard.layout["header"].update(
            self.dashboard.generate_header(app_state)
        )
        
        # 2. Arbiter (Left) - Legacy
        self.dashboard.layout["left"].update(
            self.dashboard.generate_opp_table(app_state.opportunities)
        )
        
        # 3. Scalper (Right Top)
        scalper_panel = registry.render_slot("scalper", app_state)
        if scalper_panel:
            self.dashboard.layout["scalper"].update(scalper_panel)
        else:
            self.dashboard.layout["scalper"].update(
                self.dashboard.generate_scalper_panel(app_state.scalp_signals, app_state.market_pulse)
            )
        
        # 3b. Signals (Left Bottom) - Legacy
        # Currently no fragment for signals, sticking to legacy
        self.dashboard.layout["signals"].update(
             self.dashboard.generate_signal_panel(app_state.system_signals)
        )

        # 3c. Inventory (Right Mid)
        inventory_panel = registry.render_slot("inventory", app_state)
        if inventory_panel:
            self.dashboard.layout["inventory"].update(inventory_panel)
        else:
            self.dashboard.layout["inventory"].update(
                 self.dashboard.generate_inventory_panel(app_state.inventory)
            )
        
        # 4. Modular Slots (Shadow & Stats)
        shadow_panel = registry.render_slot("shadow", app_state)
        if shadow_panel:
            self.dashboard.layout["shadow"].update(shadow_panel)
            
        stats_panel = registry.render_slot("stats", app_state)
        if stats_panel:
            self.dashboard.layout["stats"].update(stats_panel)
        else:
             # Fallback to legacy
             self.dashboard.layout["stats"].update(
                self.dashboard.generate_stats_panel(
                    trades=app_state.stats.get('total_trades', 0),
                    volume=app_state.stats.get('volume', 0),
                    turnover=0
                )
            )
        
        # 6. Footer
        now = datetime.now().strftime("%H:%M:%S")
        log_msg = app_state.logs[-1] if app_state.logs else "System Active"
        self.dashboard.layout["footer"].update(
            Panel(f"[{now}] {log_msg}", style="dim")
        )

    def print_dashboard(self, *args, **kwargs):
        pass
        
    def stop(self):
        self.live.stop()
        from src.shared.system.logging import Logger
        Logger.set_silent(False) 
