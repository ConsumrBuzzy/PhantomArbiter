from textual.app import ComposeResult
from textual.widgets import DataTable, Static
from textual.containers import Container
from src.shared.state.app_state import state

class ArbWidget(Container):
    """Displays Arbitrage Opportunities (Pair/Trip)."""
    
    def compose(self) -> ComposeResult:
        yield Static("🔭 LIVE MARKET OBSERVER", classes="panel_header")
        t1 = DataTable(id="arb_table")
        t1.add_columns("Token", "Route", "Spread %", "Est. Profit")
        t1.cursor_type = "row"
        t1.zebra_stripes = True
        yield t1

    def update_opps(self):
        t1 = self.query_one("#arb_table", DataTable)
        current_count = len(state.opportunities)
        
        # Simple rebuild for now
        t1.clear()
        
        # Show top 15 arb paths
        if not state.opportunities:
            # Show scanning status
            t1.add_row(
                "SCANNING...", 
                f"Rate: {state.stats.get('cycles_per_sec', 0):.1f}/s", 
                "-", 
                "-"
            )
            return

        for opp in state.opportunities[:15]:
             # Colorize Profit
            profit_str = f"{opp.profit_pct:.2f}%"
            if opp.profit_pct > 0.5:
                profit_str = f"[bold green]{profit_str}[/]"
            elif opp.profit_pct > 0.0:
                profit_str = f"[green]{profit_str}[/]"
            elif opp.profit_pct < -1.0:
                profit_str = f"[red]{profit_str}[/]"
            else:
                 # Near zero / minor loss
                profit_str = f"[white]{profit_str}[/]"
            
            t1.add_row(
                opp.token, 
                opp.route, 
                profit_str, 
                f"{opp.est_profit_sol:.4f}"
            )
            
        # Update Pod Status
        pod_status = state.stats.get("pod_status", "Initializing...")
        self.border_title = f"🔭 OBSERVER | {pod_status}"
