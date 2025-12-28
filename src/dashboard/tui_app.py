from textual.app import App, ComposeResult
from textual.containers import Container, Grid
from textual.widgets import Header, Footer, Log
from textual.binding import Binding

# Modular Widgets
from src.dashboard.widgets.stats import StatsPanel
from src.dashboard.widgets.wallet import WalletWidget
from src.dashboard.widgets.inventory import InventoryWidget
from src.dashboard.widgets.opportunity import ArbWidget
from src.dashboard.widgets.scalper import ScalpWidget
from src.shared.state.app_state import state

class PhantomDashboard(App):
    CSS = """
    Screen {
        background: $surface;
    }
    
    #main_grid {
        layout: grid;
        grid-size: 3 3;
        grid-rows: 10% 55% 35%;
        grid-columns: 1fr 1fr 1fr;
        height: 100%;
        width: 100%;
        grid-gutter: 1; /* Add spacing */
    }
    
    /* Panels */
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
    
    #stats_panel { row-span: 1; column-span: 1; background: $boost; border: solid green; }
    #wallet_panel { row-span: 1; column-span: 2; background: $surface; }
    
    #dual_wallet_container { 
        border: solid cyan; 
        height: 100%; 
        width: 100%; 
    }

    /* Row 2: Arb (Left), Scalp (Mid), Inventory (Right) */
    #arb_panel { row-span: 1; column-span: 1; background: $surface; border: solid blue; }
    #scalp_panel { row-span: 1; column-span: 1; background: $surface; border: solid yellow; }
    #inventory_panel { row-span: 1; column-span: 1; background: $surface; border: solid magenta; }
    
    /* Row 3: Logs */
    #log_panel { row-span: 1; column-span: 3; background: $surface; border: solid white; }
    
    /* Global Styles */
    .wallet_header { color: cyan; text-style: bold; text-align: center; width: 100%; }
    .wallet_total { color: green; text-style: bold; text-align: center; width: 100%; }
    .wallet_grid_inner { layout: grid; grid-size: 2 2; grid-gutter: 1; padding: 0 1; }
    
    .stat_value { text-align: center; color: $text-muted; }
    .green { color: green; }
    .red { color: red; }
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("c", "clear_logs", "Clear Logs"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        
        with Container(id="main_grid"):
            # Row 1: Dashboard Core
            yield StatsPanel(id="stats_panel")
            yield WalletWidget(id="wallet_panel")
            
            # Row 2: The Three Pillars (Arb, Scalp, Inventory)
            yield Container(ArbWidget(), id="arb_panel")
            yield Container(ScalpWidget(), id="scalp_panel")
            yield Container(InventoryWidget(id="inventory_table"), id="inventory_panel")
            
            # Row 3: System Logs
            yield Log(id="log_panel")
        
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Phantom Arbiter [Dashboard 2.1]"
        self.sub_title = "Supervisor Kernel: ONLINE"
        
        state.log("🚀 Phantom Cockpit: Interface Mounted")
        state.log("📡 Mode: " + ("LIVE" if state.mode == "LIVE" else "PAPER"))
        
        self.set_interval(0.5, self.update_ui)
        
    def update_ui(self) -> None:
        # 1. Update Core Stats
        try:
            self.query_one(StatsPanel).update_stats()
        except: pass
        
        # 2. Update Wallets
        try:
            self.query_one(WalletWidget).update_wallets()
        except: pass
        
        # 3. Update Columns (Three Pillars)
        try:
            self.query_one(ArbWidget).update_opps()
        except: pass
        
        try:
            self.query_one(ScalpWidget).update_scalps()
        except: pass
        
        try:
            self.query_one(InventoryWidget).update_inventory()
        except: pass
        
        # 4. Update Logs
        try:
            log_widget = self.query_one(Log)
            current_len = len(state.logs)
            last_len = getattr(self, "_last_log_len", 0)
            
            if current_len > last_len:
                all_logs = list(state.logs)
                new_items = all_logs[last_len:]
                for item in new_items:
                    log_widget.write_line(item)
                self._last_log_len = current_len
        except: pass

    def action_clear_logs(self) -> None:
        self.query_one(Log).clear()
        self._last_log_len = 0

if __name__ == "__main__":
    app = PhantomDashboard()
    app.run()
