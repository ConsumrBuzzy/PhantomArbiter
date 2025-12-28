from textual.app import ComposeResult
from textual.widgets import Static, Label
from textual.containers import Container, Grid
from src.shared.state.app_state import state, WalletData

class WalletDisplay(Static):
    """Single wallet display component."""
    
    def __init__(self, title: str, id_prefix: str):
        super().__init__()
        self.title = title
        self.prefix = id_prefix

    def compose(self) -> ComposeResult:
        yield Label(self.title, classes="wallet_header")
        yield Label("$0.00", id=f"{self.prefix}_total", classes="wallet_total")
        
        yield Grid(
            Label("USDC: $0.00", id=f"{self.prefix}_usdc"),
            Label("SOL: 0.000", id=f"{self.prefix}_sol"),
            Label("Gas: 0.000", id=f"{self.prefix}_gas"),
            id=f"{self.prefix}_grid",
            classes="wallet_grid_inner"
        )

    def update_data(self, data: WalletData):
        self.query_one(f"#{self.prefix}_total", Label).update(f"${data.total_value_usd:,.2f}")
        self.query_one(f"#{self.prefix}_usdc", Label).update(f"USDC: ${data.balance_usdc:,.2f}")
        self.query_one(f"#{self.prefix}_sol", Label).update(f"SOL: {data.balance_sol:.3f}")
        self.query_one(f"#{self.prefix}_gas", Label).update(f"Gas: {data.gas_sol:.3f}")

class WalletWidget(Static):
    """Container for Live/Paper wallets."""
    
    def compose(self) -> ComposeResult:
        # We display both if in Paper/Dev mode, or just Live if in Live.
        # But dynamic composition is tricky. Let's just create both and hide/show via CSS?
        # Or just show both side-by-side for now as requested "Live alongside Paper in Sim".
        
        yield Container(
            WalletDisplay("📜 PAPER WALLET", "paper"),
            WalletDisplay("🔥 LIVE WALLET", "live"),
            id="dual_wallet_container",
            classes="horizontal_layout"
        )

    def update_wallets(self):
        # Update Paper
        self.query_one("#paper_total", Label).update(f"${state.wallet_paper.total_value_usd:,.2f}")
        
        # Access sub-widgets directly? No, query inside.
        # Let's iterate.
        paper_display = self.query(WalletDisplay).first() # Finds paper first?
        # Better: Query by ID/Class is hard across custom widgets relative to self.
        
        # Actually, let's just make WalletDisplay self-managing if passed data?
        # Or just manually update here.
        
        # Update Paper
        self.query_one(WalletDisplay).filter(lambda w: w.prefix == "paper").first().update_data(state.wallet_paper)
        
        # Update Live
        # Only show live data if meaningful? Or always show 0.00?
        self.query_one(WalletDisplay).filter(lambda w: w.prefix == "live").first().update_data(state.wallet_live)
