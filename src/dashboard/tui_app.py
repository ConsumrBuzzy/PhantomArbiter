from textual.app import App, ComposeResult
from textual.containers import Container, Grid
from textual.widgets import Header, Footer, Log
from textual.binding import Binding

# Modular Widgets
from src.dashboard.widgets.stats import StatsPanel
from src.dashboard.widgets.wallet import WalletWidget
from src.dashboard.widgets.inventory import InventoryWidget
from src.dashboard.widgets.opportunity import OpportunityWidget
from src.shared.state.app_state import state

class PhantomDashboard(App):
    CSS = """
    Screen {
        background: $surface;
    }
    
    #main_grid {
        layout: grid;
        grid-size: 3 3;
        grid-rows: 8% 62% 30%;
        grid-columns: 1fr 1fr 1fr;
        height: 100%;
        width: 100%;
    }
    
    /* Global Styles */
    .panel_header {
        text-align: center;
        text-style: bold;
        background: $primary;
        color: white;
        padding: 0 1;
        width: 100%;
    }
    
    Static, DataTable, Log, Container {
        height: 100%;
        width: 100%;
    }
    
    /* Stats Panel */
    #stats_panel {
        row-span: 1;
        column-span: 1;
        background: $boost;
        border: solid green;
    }
    .stat_row { margin-left: 1; }
    .status_ok { color: green; text-style: bold; }
    .status_error { color: red; text-style: bold; }
    
    /* Wallet Panel */
    #wallet_panel {
        row-span: 1;
        column-span: 2;
        background: $surface;
        border: solid cyan;
    }
    .horizontal_layout { layout: horizontal; }
    .wallet_header { color: cyan; text-style: bold; padding-left: 1; }
    .wallet_total { color: green; text-style: bold; text-align: center; width: 100%; padding-bottom: 1; }
    .wallet_grid_inner { layout: grid; grid-size: 3 1; grid-gutter: 1; }
    
    /* Opportunity Panel */
    #opp_container {
        row-span: 1;
        column-span: 2;
        background: $surface;
        border: solid blue;
    }
    
    /* Inventory Panel */
    #inventory_container {
        row-span: 1;
        column-span: 1;
        background: $surface;
        border: solid magenta;
    }
    
    /* Log Panel */
    #log_panel {
        row-span: 1;
        column-span: 3;
        background: $surface;
        border: solid yellow;
    }
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("c", "clear_logs", "Clear Logs"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        
        with Container(id="main_grid"):
            # Row 1: Core Stats (Left) + Wallet (Right, spans 2)
            yield StatsPanel(id="stats_panel")
            yield WalletWidget(id="wallet_panel")
            
            # Row 2: Opportunities (Left, spans 2) + Inventory (Right)
            yield Container(OpportunityWidget(), id="opp_container")
            yield Container(InventoryWidget(id="inventory_table"), id="inventory_container")
            
            # Row 3: Log Panel (Full Width)
            yield Log(id="log_panel")
        
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Phantom Arbiter [Dashboard 2.0]"
        self.sub_title = "Cycle: --μs | State: OPERATIONAL"
        
        # Log Startup
        state.log("🚀 Phantom Cockpit: Interface Mounted")
        state.log("📡 Mode: " + ("LIVE" if state.mode == "LIVE" else "PAPER"))
        
        self.set_interval(0.5, self.update_ui)
        
    def update_ui(self) -> None:
        try:
            # 1. Update Core Stats
            self.query_one(StatsPanel).update_stats()
            
            # 2. Update Wallets
            self.query_one(WalletWidget).update_wallets()
            
            # 3. Update Inventory
            self.query_one(InventoryWidget).update_inventory()
            
            # 4. Update Opportunities
            self.query_one(OpportunityWidget).update_opps()

            # 5. Update Logs
            log_widget = self.query_one(Log)
            current_len = len(state.logs)
            last_len = getattr(self, "_last_log_len", 0)
            
            if current_len > last_len:
                all_logs = list(state.logs)
                new_items = all_logs[last_len:]
                for item in new_items:
                    log_widget.write_line(item)
                self._last_log_len = current_len
        except Exception as e:
            # Prevent silent crash of the UI loop
            pass

    def action_clear_logs(self) -> None:
        self.query_one(Log).clear()
        self._last_log_len = 0

if __name__ == "__main__":
    app = PhantomDashboard()
    app.run()
