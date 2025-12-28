from textual.app import App, ComposeResult
from textual.containers import Container, Grid
from textual.widgets import Header, Footer, Log, Static, DataTable
from textual.binding import Binding

class StatsPanel(Static):
    """Displays real-time stats."""
    
    def compose(self) -> ComposeResult:
        yield Static("⚡ Phantom Arbiter Core V2.0", id="stats_title")
        yield Static("Rust Core: ONLINE", id="status_core", classes="status_ok")
        yield Static("Pathfinder: 1450 cycles/sec", id="stat_cycles")
        yield Static("WSS Latency: 4ms", id="stat_latency")
        yield Static("Total PnL: 0.00 SOL", id="stat_pnl")

class ArbTable(DataTable):
    """Table for active opportunities."""
    pass

class PhantomDashboard(App):
    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 3;
        grid-rows: 1fr 3fr 2fr;
        grid-columns: 1fr 2fr;
    }
    
    #stats_panel {
        row-span: 1;
        column-span: 1;
        background: $boost;
        border: solid green;
        padding: 1;
    }
    
    #arb_table_container {
        row-span: 3;
        column-span: 1;
        background: $surface;
        border: solid blue;
    }

    #log_panel {
        row-span: 2;
        column-span: 1;
        background: $surface;
        border: solid yellow;
    }
    
    .status_ok {
        color: green;
        text-style: bold;
    }
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("c", "clear_logs", "Clear Logs"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        
        # Grid items
        yield StatsPanel(id="stats_panel")
        
        # Arb Table (Right Side)
        table = ArbTable(id="arb_table")
        table.add_columns("Token", "Route", "Profit %", "Est. SOL")
        yield Container(table, id="arb_table_container")
        
        # Log Panel
        yield Log(id="log_panel")
        
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Phantom Arbiter [Rust Edition]"
        self.sub_title = "Cycle: 45μs | State: HUNTING"
        
        # Test Data
        table = self.query_one(ArbTable)
        table.add_row("USDC", "Ray -> Orca", "+0.45%", "0.012")
        table.add_row("BONK", "Meteora -> Ray", "+1.20%", "0.050")
        
        log = self.query_one(Log)
        log.write_line("[bold green]System Initialized.[/]")
        log.write_line("Loaded Rust Core: phantom_core v0.1.0")
        log.write_line("Connecting to Helios WSS...")
        log.write_line("⚡ FLASH SWAP Detected: 50 SOL -> 4800 USDC")

    def action_clear_logs(self) -> None:
        self.query_one(Log).clear()

if __name__ == "__main__":
    app = PhantomDashboard()
    app.run()
