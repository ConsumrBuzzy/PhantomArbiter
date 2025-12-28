from textual.app import ComposeResult
from textual.widgets import DataTable
from src.shared.state.app_state import state

class InventoryWidget(DataTable):
    """Displays Held Bags (Inventory)."""
    
    def on_mount(self):
        self.add_columns("Token", "Amount", "Value ($)")
        self.cursor_type = "row"
        self.zebra_stripes = True

    def update_inventory(self):
        w_data = state.wallet_live if state.mode == "LIVE" else state.wallet_paper
        
        # Simple diff: check row count
        if len(w_data.inventory) != self.row_count:
            self.clear()
            for symbol, amt in w_data.inventory.items():
                price = state.market_pulse.get(symbol, 0.0)
                val = amt * price
                self.add_row(symbol, f"{amt:.4f}", f"${val:.2f}")
