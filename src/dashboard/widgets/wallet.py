from textual.app import ComposeResult
from textual.widgets import Static, Label
from textual.containers import Container, Grid
from src.shared.state.app_state import state, WalletData


class WalletDisplay(Static):
    """Single wallet display component (Institutional Style)."""

    def __init__(self, title: str, id_prefix: str):
        super().__init__()
        self.title = title
        self.prefix = id_prefix
        # Session tracking
        self.start_balance = 0.0
        self.first_update = True

    def compose(self) -> ComposeResult:
        yield Label(self.title, classes="wallet_header")
        yield Label("$0.00", id=f"{self.prefix}_total", classes="wallet_total")

        # Grid: Equity | PnL | Cash | Gas
        yield Grid(
            Label("PnL: $0.00 (0.0%)", id=f"{self.prefix}_pnl", classes="stat_value"),
            Label("Cash: $0.00", id=f"{self.prefix}_usdc", classes="stat_value"),
            Label("SOL: 0.000", id=f"{self.prefix}_sol", classes="stat_value"),
            Label("Gas: 0.000", id=f"{self.prefix}_gas", classes="stat_value"),
            id=f"{self.prefix}_grid",
            classes="wallet_grid_inner",
        )

    def update_data(self, data: WalletData):
        # 1. Capture Session Start
        if self.first_update and data.total_value_usd > 0:
            self.start_balance = data.total_value_usd
            self.first_update = False

        # 2. Calculate PnL
        pnl_usd = 0.0
        pnl_pct = 0.0
        if self.start_balance > 0:
            pnl_usd = data.total_value_usd - self.start_balance
            pnl_pct = (pnl_usd / self.start_balance) * 100

        # 3. Format & Update
        self.query_one(f"#{self.prefix}_total", Label).update(
            f"${data.total_value_usd:,.2f}"
        )

        # PnL Color
        pnl_lbl = self.query_one(f"#{self.prefix}_pnl", Label)
        pnl_lbl.update(f"PnL: ${pnl_usd:+.2f} ({pnl_pct:+.2f}%)")
        if pnl_usd >= 0:
            pnl_lbl.remove_class("red")
            pnl_lbl.add_class("green")
        else:
            pnl_lbl.remove_class("green")
            pnl_lbl.add_class("red")

        self.query_one(f"#{self.prefix}_usdc", Label).update(
            f"Cash: ${data.balance_usdc:,.2f}"
        )
        self.query_one(f"#{self.prefix}_sol", Label).update(
            f"SOL: {data.balance_sol:.3f}"
        )
        self.query_one(f"#{self.prefix}_gas", Label).update(f"Gas: {data.gas_sol:.3f}")


class WalletWidget(Static):
    """Container for Live/Paper wallets."""

    def compose(self) -> ComposeResult:
        # Side-by-side Institutional View
        container = Container(
            WalletDisplay("PAPER WALLET", "paper"),
            WalletDisplay("REAL WALLET", "live"),
            id="dual_wallet_container",
            classes="horizontal_layout",
        )
        container.border_title = "SIMULATION"
        yield container

    def update_wallets(self):
        for widget in self.query(WalletDisplay):
            if widget.prefix == "paper":
                widget.update_data(state.wallet_paper)
            elif widget.prefix == "live":
                widget.update_data(state.wallet_live)
