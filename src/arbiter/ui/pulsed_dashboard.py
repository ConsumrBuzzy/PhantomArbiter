"""
Rich Pulse Dashboard
====================
A lightweight "Headless TUI" using Rich.live.
Provides Panels and layout without the full application lifecycle of Textual.
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
from src.arbiter.core.spread_detector import SpreadOpportunity

class PulsedDashboard:
    """Layout manager for the Pulse View."""
    
    def __init__(self):
        self.layout = Layout()
        self.layout.split(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3)
        )
        # Main area: Split Left (Arbiter) and Right (Scalper/Inventory/Stats)
        self.layout["main"].split_row(
            Layout(name="left", ratio=3), 
            Layout(name="right", ratio=2)
        )
        
        # Right Column: Split Top (Scalper), Middle (Inventory), Bottom (Stats)
        self.layout["right"].split_column(
            Layout(name="scalper", ratio=1),
            Layout(name="inventory", ratio=1),
            Layout(name="stats", size=6)
        )
        
    def generate_header(self, balance: float, gas: float, daily_profit: float, pod_names: List[str]):
        pod_str = f" | 🔭 {','.join(pod_names)}" if pod_names else ""
        text = f"[bold cyan]PHANTOM PULSE[/bold cyan] | 💰 Bal: [green]${balance:.2f}[/green] | ⛽ Gas: [yellow]${gas:.2f}[/yellow] | 📈 P/L: [green]${daily_profit:+.2f}[/green]{pod_str}"
        return Panel(text, style="white on blue", box=box.HEAVY_HEAD)
        
    def generate_opp_table(self, spreads: List[SpreadOpportunity], verified_opps: List[SpreadOpportunity] = None):
        table = Table(box=box.SIMPLE_HEAD, expand=True)
        table.add_column("Pair", style="cyan")
        table.add_column("Spread", justify="right")
        table.add_column("Net Profit", justify="right")
        table.add_column("Route", style="dim")
        table.add_column("Status", justify="center")
        
        verified_map = {op.pair: getattr(op, 'verification_status', None) for op in (verified_opps or [])}
        
        # limit to top 20 to fit screen vertical
        for opp in spreads[:20]:
            status = verified_map.get(opp.pair, "🔍")
            status_color = "white"
            if "LIVE" in str(status) or "READY" in str(status): status_color = "green"
            elif "LIQ" in str(status): status_color = "red"
                
            spread_color = "green" if opp.spread_pct > 0.5 else "yellow"
            if opp.spread_pct < 0: spread_color = "red"
            
            table.add_row(
                opp.pair,
                f"[{spread_color}]{opp.spread_pct:.2f}%[/{spread_color}]",
                f"[bold {spread_color}]${opp.net_profit_usd:+.3f}[/bold {spread_color}]",
                f"{opp.buy_dex}->{opp.sell_dex}",
                f"[{status_color}]{status}[/{status_color}]"
            )
        return Panel(table, title="[bold]Live Market Observer[/bold]", border_style="blue")
        
    def generate_scalper_panel(self, signals: List[Any]):
        """Show active scalp signals/trades."""
        table = Table(box=box.SIMPLE, expand=True)
        table.add_column("Token", style="magenta")
        table.add_column("Type")
        table.add_column("Confidence")
        
        if not signals:
            table.add_row("-", "Scanning...", "-")
        else:
            for s in signals[:5]: # Top 5
                conf_color = "green" if s.confidence > 0.8 else "yellow"
                table.add_row(s.token, s.signal_type, f"[{conf_color}]{s.confidence:.0%}[/{conf_color}]")
                
        return Panel(table, title="Scalper Signals (Trend)", border_style="magenta")

    def generate_inventory_panel(self, inventory: List[Any]):
        """Show held bags."""
        table = Table(box=box.SIMPLE, expand=True)
        table.add_column("Token")
        table.add_column("Value", justify="right")
        table.add_column("PnL", justify="right")
        
        if not inventory:
            table.add_row("No positions", "-", "-")
        else:
            for item in inventory[:5]:
                pnl_color = "green" if item.pnl > 0 else "red"
                table.add_row(item.symbol, f"${item.value_usd:.2f}", f"[{pnl_color}]${item.pnl:.2f}[/{pnl_color}]")
                
        return Panel(table, title="Inventory (Held Bags)", border_style="yellow")

    def generate_stats_panel(self, trades: int, volume: float, turnover: float):
        lines = [
            f"[bold]Session Stats[/bold]",
            f"Trades:   {trades}",
            f"Volume:   ${volume:,.2f}",
            f"Turnover: {turnover:.1f}x",
            "",
            "[dim]Waiting for next cycle...[/dim]"
        ]
        return Panel("\n".join(lines), title="Strategy Engine", border_style="white")

class RichPulseReporter(ArbiterReporter):
    """Overrides default Reporter to render to Rich Layout."""
    
    def __init__(self, telegram=None):
        super().__init__(telegram)
        self.dashboard = PulsedDashboard()
        self.live = Live(self.dashboard.layout, refresh_per_second=4, screen=True)
        self.live.start()
        
    def update_from_state(self, app_state):
        """Pull ALL data from AppState (The Global Truth)."""
        # 1. Header
        # Use mocked balance or real from state if available
        # Ideally Director updates stats['balance']
        balance = app_state.stats.get('balance', 0.0)
        gas = 0.0 # TODO: Expose in state
        daily_profit = app_state.stats.get('daily_profit', 0.0)
        pod_status = app_state.stats.get('pod_status', "")
        
        self.dashboard.layout["header"].update(
            self.dashboard.generate_header(balance, gas, daily_profit, [pod_status] if pod_status else [])
        )
        
        # 2. Arbiter (Left)
        # Convert AppState dicts back to objects or use raw?
        # AppState.opportunities is list of ArbOpportunity objects (simplified)
        # We need to adapt them for generate_opp_table
        # Or just rewrite generate_opp_table to accept ArbOpportunity
        self.dashboard.layout["left"].update(
            self._render_arb_table(app_state.opportunities)
        )
        
        # 3. Scalper (Right Top)
        self.dashboard.layout["scalper"].update(
            self.dashboard.generate_scalper_panel(app_state.scalp_signals)
        )
        
        # 4. Inventory (Right Mid)
        self.dashboard.layout["inventory"].update(
            self.dashboard.generate_inventory_panel(app_state.inventory)
        )
        
        # 5. Stats
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

    def _render_arb_table(self, opportunities):
        """Adapter for AppState ArbOpportunity -> Rich Table."""
        table = Table(box=box.SIMPLE_HEAD, expand=True)
        table.add_column("Pair", style="cyan")
        table.add_column("Spread", justify="right")
        table.add_column("Est Profit", justify="right")
        table.add_column("Route", style="dim")
        
        for opp in opportunities[:20]:
            spread_color = "green" if opp.profit_pct > 0.5 else "yellow"
            table.add_row(
                opp.token,
                f"[{spread_color}]{opp.profit_pct:.2f}%[/{spread_color}]",
                f"[bold {spread_color}]${opp.est_profit_sol:.3f}[/bold {spread_color}]", # Using field name from AppState
                opp.route
            )
        return Panel(table, title="[bold]Live Market Observer[/bold]", border_style="blue")

    def print_dashboard(self, *args, **kwargs):
        # Legacy hook - ignore, we use update_from_state now
        pass
        
    def stop(self):
        self.live.stop()
