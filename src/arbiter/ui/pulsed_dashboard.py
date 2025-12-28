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
from typing import List, Dict

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
        self.layout["main"].split_row(
            Layout(name="left", ratio=2), # Opportunities
            Layout(name="right", ratio=1) # Ops/Logs
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
        
        # limit to top 15 to fit screen
        for opp in spreads[:15]:
            status = verified_map.get(opp.pair, "🔍")
            status_color = "white"
            
            if "LIVE" in str(status) or "READY" in str(status): 
                status_color = "green"
            elif "LIQ" in str(status):
                status_color = "red"
                
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
        
    def generate_stats_panel(self, trades: int, volume: float, turnover: float):
        lines = [
            f"[bold]Session Stats[/bold]",
            f"Trades:   {trades}",
            f"Volume:   ${volume:,.2f}",
            f"Turnover: {turnover:.1f}x",
            "",
            "[dim]Waiting for next cycle...[/dim]"
        ]
        return Panel("\n".join(lines), title="Strategy Engine", border_style="yellow")

class RichPulseReporter(ArbiterReporter):
    """Overrides default Reporter to render to Rich Layout."""
    
    def __init__(self, telegram=None):
        super().__init__(telegram)
        self.dashboard = PulsedDashboard()
        self.live = Live(self.dashboard.layout, refresh_per_second=4, screen=True)
        self.live.start() # Keep it running
        
    def print_dashboard(self, spreads, balance, gas, daily_profit, total_trades, volume, turnover, verified_opps=None, pod_names=None):
        # Update layout components (non-blocking)
        
        # 1. Header
        self.dashboard.layout["header"].update(
            self.dashboard.generate_header(balance, gas, daily_profit, pod_names)
        )
        
        # 2. Left: Opportunities
        self.dashboard.layout["left"].update(
            self.dashboard.generate_opp_table(spreads, verified_opps)
        )
        
        # 3. Right: Stats
        self.dashboard.layout["right"].update(
            self.dashboard.generate_stats_panel(total_trades, volume, turnover)
        )
        
        # 4. Footer (Log placeholder)
        now = datetime.now().strftime("%H:%M:%S")
        self.dashboard.layout["footer"].update(
            Panel(f"[{now}] System Active | Scanning...", style="dim")
        )
        
    def stop(self):
        self.live.stop()
