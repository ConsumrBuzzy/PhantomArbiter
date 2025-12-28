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

class WalletWidget(Static):
    """Displays Wallet Balance and Gas."""
    def compose(self) -> ComposeResult:
        yield Static("💼 WALLET", classes="panel_title")
        yield Static("Total Value: $0.00", id="wallet_total", classes="big_stat")
        
        yield Grid(
            Static("USDC: $0.00", id="wallet_usdc"),
            Static("SOL: 0.000", id="wallet_sol"),
            Static("Gas: 0.000 SOL", id="wallet_gas"),
            id="wallet_grid"
        )

class InventoryWidget(DataTable):
    """Displays Held Bags (Inventory)."""
    pass

class PhantomDashboard(App):
    CSS = """
    Screen {
        layout: grid;
        grid-size: 3 3;
        grid-rows: 1fr 4fr 2fr;
        grid-columns: 1fr 1fr 1fr;
    }
    
    #stats_panel {
        row-span: 1;
        column-span: 1;
        background: $boost;
        border: solid green;
        padding: 1;
    }
    
    #wallet_panel {
        row-span: 1;
        column-span: 2;
        background: $surface;
        border: solid cyan;
        padding: 1;
    }
    
    .panel_title {
        text-style: bold;
        color: cyan;
    }
    
    .big_stat {
        text-style: bold;
        color: green;
        text-align: center;
        width: 100%; 
        padding-bottom: 1;
    }
    
    #wallet_grid {
        layout: grid;
        grid-size: 3 1;
        grid-gutter: 1;
    }

    #inventory_container {
        row-span: 1;
        column-span: 3;
        background: $surface;
        border: solid magenta;
        height: 100%;
        min-height: 10;
    }
    
    #log_panel {
        row-span: 1;
        column-span: 3;
        background: $surface;
        border: solid yellow;
        height: 100%;
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
        
        # Row 1: Core Stats (Left) + Wallet (Right)
        yield StatsPanel(id="stats_panel")
        yield WalletWidget(id="wallet_panel")
        
        # Row 2: Inventory (Full Width)
        # Note: We wrap DataTable in a Container for styling/sizing
        inv = InventoryWidget(id="inventory_table")
        inv.add_columns("Token", "Amount", "Value (USD)")
        yield Container(inv, id="inventory_container")
        
        # Row 3: Log Panel (Full Width)
        yield Log(id="log_panel")
        
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Phantom Arbiter [Dashboard 2.0]"
        self.sub_title = "Cycle: --μs | State: CONNECTING"
        
        # Start Polling
        self.set_interval(0.25, self.update_ui)
        
    def update_ui(self) -> None:
        from src.shared.state.app_state import state
        
        # 1. Update Core Stats
        core_status = "ONLINE" if state.stats["rust_core_active"] else "OFFLINE"
        self.query_one("#status_core", Static).update(f"Rust Core: {core_status}")
        self.query_one("#stat_cycles", Static).update(f"Pathfinder: {state.stats['cycles_per_sec']} cycles/sec")
        self.query_one("#stat_latency", Static).update(f"WSS Latency: {state.stats['wss_latency_ms']}ms")
        self.query_one("#stat_pnl", Static).update(f"Total PnL: {state.stats['total_pnl_sol']:.4f} SOL")
        
        # 2. Update Wallet Stats
        # Use valid wallet based on mode (default to PAPER for visual if not set)
        w_data = state.wallet_live if state.mode == "LIVE" else state.wallet_paper
        mode_label = "[LIVE]" if state.mode == "LIVE" else "[PAPER]"
        
        # Update Title to reflect mode
        self.query_one("#wallet_panel Static.panel_title").update(f"💼 WALLET {mode_label}")
        
        self.query_one("#wallet_total", Static).update(f"${w_data.total_value_usd:,.2f}")
        self.query_one("#wallet_usdc", Static).update(f"USDC: ${w_data.balance_usdc:,.2f}")
        self.query_one("#wallet_sol", Static).update(f"SOL: {w_data.balance_sol:.4f}")
        self.query_one("#wallet_gas", Static).update(f"Gas: {w_data.gas_sol:.4f} SOL")
        
        # 3. Update Inventory Table
        table = self.query_one(InventoryWidget)
        
        # Simple diffing logic: if item count differs, rebuild
        # Real logic should update individual cells, but this is fine for dashboard
        current_rows = table.row_count
        target_rows = len(w_data.inventory)
        
        # For simplicity, clear and redraw if counts differ OR periodically force refresh?
        # Let's just redraw if not empty to ensure values update.
        # Ideally we track a hash of inventory to see if it changed.
        
        # HACK: Clear and redraw every N cycles involves flickering.
        # Better: Iterate keys.
        if target_rows != current_rows:
            table.clear()
            for symbol, amt in w_data.inventory.items():
                # Mock value calculation if not in wallet data yet
                val = 0.0 # Placeholder
                table.add_row(symbol, f"{amt:.4f}", f"${val:.2f}")
        
        # 4. Update Logs (Append only)
        log_widget = self.query_one(Log)
        current_len = len(state.logs)
        last_len = getattr(self, "_last_log_len", 0)
        
        if current_len > last_len:
            all_logs = list(state.logs)
            new_items = all_logs[last_len:]
            for item in new_items:
                log_widget.write_line(item)
            self._last_log_len = current_len

    def action_clear_logs(self) -> None:
        self.query_one(Log).clear()
        self._last_log_len = 0

if __name__ == "__main__":
    app = PhantomDashboard()
    app.run()
