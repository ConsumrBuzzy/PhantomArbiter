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
        self.sub_title = "Cycle: --μs | State: CONNECTING"
        
        # Start Polling
        self.set_interval(0.1, self.update_ui)
        
    def update_ui(self) -> None:
        from src.shared.state.app_state import state
        
        # 1. Update Stats
        core_status = "ONLINE" if state.stats["rust_core_active"] else "OFFLINE"
        self.query_one("#status_core", Static).update(f"Rust Core: {core_status}")
        self.query_one("#stat_cycles", Static).update(f"Pathfinder: {state.stats['cycles_per_sec']} cycles/sec")
        self.query_one("#stat_latency", Static).update(f"WSS Latency: {state.stats['wss_latency_ms']}ms")
        self.query_one("#stat_pnl", Static).update(f"Total PnL: {state.stats['total_pnl_sol']:.4f} SOL")
        
        # 2. Update Logs
        # We check if there are new logs. 
        # For efficiency, we might just write the last one if it's new, 
        # but let's just drain the deque for now or keep a pointer.
        # Simplest Strategy for TUI: Clear and re-populate is too slow.
        # Append-only strategy:
        # We need a cursor.
        log_widget = self.query_one(Log)
        # Hack: Just write everything that isn't written? 
        # Textual Log doesn't expose its content easily for diffing.
        # Let's just write the last 10 lines from state? No, that duplicates.
        
        # Better: AppState has a `get_new_logs(cursor)` or we just push continuously.
        # But we are polling.
        # Let's clear and write the last 50 lines? No, flicker.
        
        # Let's try to just write the *latest* log if it changed.
        if state.logs:
            last_log = state.logs[-1]
            # We assume if we haven't seen it, write it.
            # Ideally we use a message bus, but for polling:
            if not hasattr(self, "_last_log_seen"):
                self._last_log_seen = ""
                
            if last_log != self._last_log_seen:
                # Potential issue: multiple logs in 100ms.
                # Only writes the very last one. Misses intermediates.
                # FIX: Check length.
                current_len = len(state.logs)
                last_len = getattr(self, "_last_log_len", 0)
                
                if current_len > last_len:
                    # Write all new items
                    # logs is a deque. list(state.logs) gives all.
                    all_logs = list(state.logs)
                    new_items = all_logs[last_len:]
                    for item in new_items:
                        log_widget.write_line(item)
                    
                    self._last_log_len = current_len
                    self._last_log_seen = last_log

    def action_clear_logs(self) -> None:
        self.query_one(Log).clear()
        # Also reset state tracking
        self._last_log_len = 0

if __name__ == "__main__":
    app = PhantomDashboard()
    app.run()
