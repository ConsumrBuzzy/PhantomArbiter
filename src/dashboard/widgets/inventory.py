from textual.widgets import DataTable
from src.shared.state.app_state import state


class InventoryWidget(DataTable):
    """Displays Held Bags (Institutional Inventory)."""

    def on_mount(self):
        # Rich Columns (Institutional)
        self.add_columns(
            "Token",
            "Amount",
            "Entry ($)",
            "Mark ($)",
            "Value ($)",
            "Unrealized PnL",
            "Status",
        )
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.show_header = True

    def update_inventory(self):
        w_data = state.wallet_live if state.mode == "LIVE" else state.wallet_paper
        current_holdings = w_data.inventory

        self.clear()

        for symbol, amt in current_holdings.items():
            if amt <= 0.0001:
                continue  # Dust filter

            # Real-time Price
            price = state.market_pulse.get(symbol, 0.0)
            if price == 0.0:
                price = 0.0

            val = amt * price

            # Entry Price Logic (Mock for now, will pull from trade history later)
            # Default to 5% profit scenario for demo visualization
            entry_price = price * 0.95

            pnl_usd = val - (amt * entry_price)
            pnl_pct = 5.0

            status = "HOLD"
            if pnl_pct > 10:
                status = "🚀 MOON"
            elif pnl_pct < -5:
                status = "⚠️ RISK"

            pnl_str = f"${pnl_usd:+.2f} ({pnl_pct:+.1f}%)"

            self.add_row(
                symbol,
                f"{amt:.4f}",
                f"${entry_price:.4f}",  # Entry column
                f"${price:.4f}",  # Mark column
                f"${val:,.2f}",
                pnl_str,
                status,
            )
