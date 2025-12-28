from textual.app import ComposeResult
from textual.widgets import DataTable, Static
from textual.containers import Container
from src.shared.state.app_state import state

class OpportunityWidget(Container):
    """Displays Arbitrage and Scalp opportunities."""
    
    def compose(self) -> ComposeResult:
        # MARKET PULSE (Ticker)
        yield Static("📈 MARKET PULSE", id="market_pulse", classes="panel_header")
        
        # ARB TABLE
        yield Static("🌀 ARB OPPORTUNITIES", classes="panel_header")
        t1 = DataTable(id="arb_table")
        t1.add_columns("Token", "Route", "Profit %", "Est. SOL")
        yield t1
        
        # SCALP TABLE
        yield Static("🔪 SCALP TARGETS", classes="panel_header")
        t2 = DataTable(id="scalp_table")
        t2.add_columns("Token", "Signal", "Confidence", "Action")
        yield t2

    def update_opps(self):
        # 1. Update Market Pulse Ticker
        try:
            pulse = self.query_one("#market_pulse", Static)
            pulse_items = [f"[bold]{s}[/]: ${p:.4f}" for s, p in list(state.market_pulse.items())[:8]]
            pulse.update("📈 MARKET PULSE: " + " | ".join(pulse_items))
        except: pass

        # 2. Update Arb Table
        t1 = self.query_one("#arb_table", DataTable)
        t1.clear()
        for opp in state.opportunities[:10]:
            t1.add_row(opp.token, opp.route, f"{opp.profit_pct:.2f}%", f"{opp.est_profit_sol:.4f}")
            
        # 3. Update Scalp Table
        t2 = self.query_one("#scalp_table", DataTable)
        t2.clear()
        for sig in state.scalp_signals[:10]:
            t2.add_row(sig.token, sig.signal_type, sig.confidence, sig.action)
