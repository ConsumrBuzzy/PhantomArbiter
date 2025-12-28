from textual.app import ComposeResult
from textual.widgets import Static
from src.shared.state.app_state import state

class StatsPanel(Static):
    """Displays real-time system stats."""
    
    def compose(self) -> ComposeResult:
        # Title
        yield Static("⚡ Phantom Arbiter Core V2.0", id="stats_title", classes="panel_header")
        
        # Grid of Stats
        yield Static("Rust Core: --", id="status_core", classes="stat_row")
        yield Static("Pathfinder: 0 cps", id="stat_cycles", classes="stat_row")
        yield Static("WSS Latency: 0ms", id="stat_latency", classes="stat_row")
        yield Static("Global PnL: 0.00 SOL", id="stat_pnl", classes="stat_row")

    def update_stats(self):
        """Called by parent to refresh data."""
        core_status = "ONLINE" if state.stats["rust_core_active"] else "OFFLINE"
        core_class = "status_ok" if state.stats["rust_core_active"] else "status_error"
        
        self.query_one("#status_core").update(f"Rust Core: {core_status}")
        self.query_one("#status_core").set_classes(f"stat_row {core_class}")
        
        self.query_one("#stat_cycles").update(f"Pathfinder: {state.stats['cycles_per_sec']} cps")
        self.query_one("#stat_latency").update(f"WSS Latency: {state.stats['wss_latency_ms']}ms")
        self.query_one("#stat_pnl").update(f"Global PnL: {state.stats['total_pnl_sol']:.4f} SOL")
