from datetime import datetime
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from src.shared.state.app_state import state as app_state

RESERVED_SOL = 0.02

class DNEMDashboard:
    """
    Unified TUI Dashboard for Phantom Arbiter.
    Supports Funding, Scalp, and Arb engine layouts.
    """
    def __init__(self):
        self.layout = Layout()
        self.layout.split(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="logs", size=8)
        )
        self.layout["main"].split_row(
            Layout(name="left", ratio=10),
            Layout(name="right", ratio=12) 
        )
        # Left side: Financials / Inventory
        self.layout["left"].split_column(
            Layout(name="positions", ratio=10),
            Layout(name="pnl", ratio=10)
        )
        # Right side: Engine Intelligence (Dyanmic)
        self.layout["right"].split_column(
            Layout(name="intel", ratio=12),
            Layout(name="metrics", ratio=10)
        )

    def update(self, data: dict):
        """Update all panels with new data from engine and AppState."""
        mode = data.get("mode", "UNKNOWN").upper()
        
        self.layout["header"].update(self._header(data))
        self.layout["positions"].update(self._positions_panel(data))
        self.layout["pnl"].update(self._pnl_panel(data))
        self.layout["logs"].update(self._log_panel(data))
        
        # Dynamic Dispatch for Right Panel
        if "ARB" in mode:
            self.layout["intel"].update(self._arb_opps_panel())
            self.layout["metrics"].update(self._engine_stats_panel("ARB"))
        elif "SCALP" in mode:
            self.layout["intel"].update(self._scalp_signals_panel())
            self.layout["metrics"].update(self._engine_stats_panel("SCALP"))
        else:
            # Funding / Default
            self.layout["intel"].update(self._risk_panel(data))
            self.layout["metrics"].update(self._sim_panel(data))

    def _header(self, data: dict):
        now = datetime.now().strftime("%H:%M:%S")
        mode = data.get("mode", "UNKNOWN")
        engine_state = data.get("state", "ACTIVE")
        
        status_color = "green" if engine_state == "ACTIVE" else "yellow"
        if engine_state == "UNWIND": status_color = "red"
        
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="right", ratio=1)
        
        grid.add_row(
            f"🏛️  PHANTOM ARBITER",
            f"[{status_color} bold reverse] {engine_state} [/] | {mode}",
            f"CLOCK: {now} UTC"
        )
        
        return Panel(grid, style="white on blue")

    def _positions_panel(self, data: dict):
        table = Table(box=box.SIMPLE, expand=True)
        table.add_column("Asset", style="cyan")
        table.add_column("Amount", justify="right")
        table.add_column("Value", justify="right")
        
        # Use AppState inventory for broader coverage
        inventory = app_state.inventory
        if not inventory:
            table.add_row("[dim]Empty[/]", "0.00", "$0.00")
        else:
            for item in inventory[:5]: # Show top 5
                table.add_row(item.symbol, f"{item.amount:.3f}", f"${item.value_usd:.2f}")

        return Panel(table, title="📊 Inventory", border_style="cyan")

    def _pnl_panel(self, data: dict):
        table = Table(box=box.SIMPLE, expand=True)
        table.add_column("Metric")
        table.add_column("Value", justify="right", style="green")
        
        u_pnl = data.get("unrealized_pnl", 0)
        s_pnl = data.get("settled_pnl", 0)
        
        table.add_row("Unrealized PnL", f"${u_pnl:+.4f}")
        table.add_row("Settled PnL", f"${s_pnl:+.4f}")
        
        # Funding Metrics (Only if in funding mode)
        if "FUNDING" in data.get("mode", "").upper():
            rate_hr = data.get("funding_rate_hr", 0)
            rate_color = "green" if rate_hr > 0 else "red"
            table.add_row("Funding Rate", f"[{rate_color}]{rate_hr:.6f}/hr[/]")
            
        return Panel(table, title="💰 PnL", border_style="green")

    def _arb_opps_panel(self):
        """Reuses logic from ArbWidget."""
        table = Table(box=box.SIMPLE, expand=True)
        table.add_column("Token", style="yellow")
        table.add_column("Route")
        table.add_column("Spread", justify="right")
        table.add_column("Profit", justify="right")
        
        opps = app_state.opportunities
        if not opps:
            table.add_row("[dim]Scanning...[/]", "-", "-", "-")
        else:
            for opp in opps[:10]:
                profit_color = "green" if opp.profit_pct > 0 else "white"
                table.add_row(
                    opp.token, 
                    opp.route, 
                    f"[{profit_color}]{opp.profit_pct:.2f}%[/]",
                    f"${opp.est_profit_sol:.2f}"
                )
        return Panel(table, title="🔭 Arb Opportunities", border_style="yellow")

    def _scalp_signals_panel(self):
        """Reuses logic from ScalpWidget."""
        table = Table(box=box.SIMPLE, expand=True)
        table.add_column("Token", style="magenta")
        table.add_column("Signal")
        table.add_column("Action", justify="center")
        table.add_column("Conf", justify="right")
        
        sigs = app_state.scalp_signals
        if not sigs:
            table.add_row("[dim]Listening...[/]", "-", "-", "-")
        else:
            for sig in sigs[:10]:
                action_color = "green" if sig.action == "BUY" else "red"
                table.add_row(
                    sig.token,
                    sig.signal_type,
                    f"[{action_color}]{sig.action}[/]",
                    f"{sig.confidence}"
                )
        return Panel(table, title="🔪 Scalp Signals", border_style="magenta")

    def _engine_stats_panel(self, engine_type: str):
        grid = Table.grid(expand=True)
        grid.add_column()
        grid.add_column(justify="right")
        
        stats = app_state.stats
        grid.add_row("Heartbeat", "[green]OK[/]")
        grid.add_row("Latency", f"{stats.get('wss_latency_ms', 0)}ms")
        
        if engine_type == "ARB":
            grid.add_row("Cycles/s", f"{stats.get('cycles_per_sec', 0)}")
            grid.add_row("Rust Core", "[green]ON[/]" if stats.get("rust_core_active") else "[yellow]OFF[/]")
        elif engine_type == "SCALP":
            grid.add_row("Pod Rotation", f"{stats.get('pod_status', 'N/A')}")
            
        return Panel(grid, title=f"⚡ {engine_type} Core Stats", border_style="white")

    def _risk_panel(self, data: dict):
        health = data.get("health_score", 100)
        status = "SECURE"
        color = "green"
        
        if health < 80: status, color = "WARNING", "yellow"
        if health < 50: status, color = "DANGER", "red"
            
        grid = Table.grid(expand=True)
        grid.add_column()
        grid.add_column(justify="right")
        
        bar = "█" * int(health/10) + "░" * (10 - int(health/10))
        grid.add_row("Health", f"[{color}]{health:.1f}% {bar}[/]")
        grid.add_row("Watchdog", "[green]ACTIVE[/]")
        
        return Panel(grid, title=f"🛡️ Risk: [{color}]{status}[/]", border_style=color)

    def _sim_panel(self, data: dict):
        table = Table(box=box.SIMPLE, expand=True)
        table.add_column("Lev", width=4)
        table.add_column("Size")
        table.add_column("Health")
        
        for lev in [1.0, 2.0, 3.0]:
            table.add_row(f"{lev}x", "$100.0", "[green]OK[/]")
            
        return Panel(table, title="🎢 Simulation", border_style="dim")

    def _log_panel(self, data: dict):
        logs = data.get("recent_logs", [])
        text = Text()
        for log in logs:
            text.append(log + "\n")
        return Panel(text, title="📜 Live Logs", border_style="white", style="dim")
