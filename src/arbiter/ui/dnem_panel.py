from datetime import datetime
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

RESERVED_SOL = 0.02

class DNEMDashboard:
    def __init__(self):
        self.layout = Layout()
        self.layout.split(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="logs", size=8) # Dedicated Log Panel
        )
        self.layout["main"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=1)
        )
        self.layout["left"].split_column(
            Layout(name="positions", ratio=1),
            Layout(name="pnl", ratio=1)
        )
        self.layout["right"].split_column(
            Layout(name="risk", ratio=1),
            Layout(name="sim", ratio=1)
        )

    def update(self, data: dict):
        """Update all panels with new data."""
        self.layout["header"].update(self._header(data))
        self.layout["positions"].update(self._positions_panel(data))
        self.layout["pnl"].update(self._pnl_panel(data))
        self.layout["risk"].update(self._risk_panel(data))
        self.layout["sim"].update(self._sim_panel(data))
        self.layout["logs"].update(self._log_panel(data))

    def _header(self, data: dict):
        now = datetime.now().strftime("%H:%M:%S")
        
        # Engine Heartbeat
        mode = data.get("mode", "UNKNOWN")
        state = data.get("state", "STARTING")
        
        status_color = "green" if state == "ACTIVE" else "yellow"
        if state == "UNWIND": status_color = "red"
        
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="right", ratio=1)
        
        grid.add_row(
            f"🏛️  PHANTOM ARBITER",
            f"[{status_color} bold reverse] {state} [/] | {mode}",
            f"CLOCK: {now} UTC"
        )
        
        return Panel(grid, style="white on blue")

    def _positions_panel(self, data: dict):
        table = Table(box=box.SIMPLE)
        table.add_column("Asset", style="cyan")
        table.add_column("Amount", justify="right")
        table.add_column("Value (USD)", justify="right")
        
        spot_sol = data.get("spot_sol", 0)
        perp_sol = data.get("perp_sol", 0)
        price = data.get("sol_price", 0)
        
        table.add_row("Spot SOL", f"{spot_sol:.4f}", f"${spot_sol * price:.2f}")
        table.add_row("Perp SOL", f"{perp_sol:.4f}", f"${perp_sol * price:.2f}")
        
        net_delta = spot_sol + perp_sol
        hedgeable = max(0, spot_sol - RESERVED_SOL)
        drift = (net_delta / hedgeable * 100) if hedgeable > 0 else 0
        
        color = "green" if abs(drift) < 2.0 else "red"
        table.add_row("Net Delta", f"[{color}]{net_delta:+.4f}[/]", f"Drift: [{color}]{drift:+.2f}%[/]")
        
        return Panel(table, title="📊 Positions & Delta", border_style="cyan")

    def _pnl_panel(self, data: dict):
        table = Table(box=box.SIMPLE)
        table.add_column("Metric")
        table.add_column("Value", justify="right", style="green")
        
        u_pnl = data.get("unrealized_pnl", 0)
        s_pnl = data.get("settled_pnl", 0)
        
        # Estimate Funding
        perp_sol = data.get("perp_sol", 0)
        price = data.get("sol_price", 0)
        rate_hr = data.get("funding_rate_hr", 0)
        hr_yield = abs(perp_sol) * price * rate_hr
        
        table.add_row("Unrealized PnL", f"${u_pnl:+.4f}")
        table.add_row("Settled PnL", f"${s_pnl:+.4f}")
        table.add_section()
        
        rate_color = "green" if rate_hr > 0 else "red"
        table.add_row("Funding Rate", f"[{rate_color}]{rate_hr:.6f}/hr[/]")
        table.add_row("Est. Yield/Hr", f"${hr_yield:.4f}")
        
        return Panel(table, title="💰 PnL & Yield", border_style="green")

    def _risk_panel(self, data: dict):
        health = data.get("health_score", 100)
        
        # Determine Status
        status = "SECURE"
        color = "green"
        if health < 50: 
            status = "DANGER"
            color = "red"
        elif health < 80:
            status = "WARNING"
            color = "yellow"
            
        funding = data.get("funding_rate_hr", 0)
        unwind = "NO"
        if funding < -0.0005:
            unwind = "WATCHDOG ACTIVE"
            color = "yellow"
        
        grid = Table.grid(expand=True)
        grid.add_column()
        grid.add_column(justify="right")
        
        prog = int(health / 10)
        bar = "█" * prog + "░" * (10 - prog)
        
        grid.add_row("Health Score", f"[{color}]{health:.1f}% {bar}[/]")
        grid.add_row("Watchdog", f"[{color}]{unwind}[/]")
        
        return Panel(grid, title=f"🛡️ Risk: [{color}]{status}[/]", border_style="red")

    def _sim_panel(self, data: dict):
        table = Table(box=box.SIMPLE, show_header=True)
        table.add_column("Lev", width=4)
        table.add_column("Size")
        table.add_column("Health")
        
        base_amt = abs(data.get("perp_sol", 0)) or 0.1
        
        for lev in [1.0, 2.0, 3.0]:
            size = base_amt * lev
            table.add_row(f"{lev}x", f"{size:.1f} S", f"[green]OK[/]")
            
        return Panel(table, title="🎢 Leverage Sim", border_style="magenta")

    def _log_panel(self, data: dict):
        logs = data.get("recent_logs", [])
        text = Text()
        for log in logs:
            text.append(log + "\n")
        return Panel(text, title="📜 Live Logs", border_style="white", style="dim")
