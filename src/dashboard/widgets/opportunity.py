from textual.app import ComposeResult
from textual.widgets import DataTable, Static
from textual.containers import Container
from src.shared.state.app_state import state

class OpportunityWidget(Container):
    """Displays Arbitrage and Scalp opportunities."""
    
    def compose(self) -> ComposeResult:
        # ARB TABLE
        yield Static("🌀 ARB OPPORTUNITIES", classes="panel_header")
        t1 = DataTable(id="arb_table")
        t1.add_columns("Token", "Route", "Profit %", "Est. SOL")
        yield t1
        
        # SCALP TABLE (Future Hook)
        yield Static("🔪 SCALP TARGETS", classes="panel_header")
        t2 = DataTable(id="scalp_table")
        t2.add_columns("Token", "Signal", "Confidence", "Action")
        yield t2

    def update_opps(self):
        # Update Arb Table
        t1 = self.query_one("#arb_table", DataTable)
        
        # Simple Logic: Clear and Fill from State
        # In production we'd optimize this to avoid flicker
        t1.clear()
        for opp in state.opportunities[:10]: # Top 10
            t1.add_row(opp.token, opp.route, f"{opp.profit_pct:.2f}%", f"{opp.est_profit_sol:.4f}")
            
        # Scalp Table (Mock for now until Scalper module is connected)
        t2 = self.query_one("#scalp_table", DataTable)
        if t2.row_count == 0:
             t2.add_row("BONK", "RSI Oversold", "High", "BUY")
