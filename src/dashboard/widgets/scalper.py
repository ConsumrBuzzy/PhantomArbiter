from textual.app import ComposeResult
from textual.widgets import DataTable, Static
from textual.containers import Container
from src.shared.state.app_state import state


class ScalpWidget(Container):
    """Displays Scalper Signals (Token Up/Down)."""

    def compose(self) -> ComposeResult:
        # Header
        yield Static("🔪 SCALPER SIGNALS (Trend)", classes="panel_header")

        # Table
        t2 = DataTable(id="scalp_table")
        t2.add_columns("Token", "Signal", "Conf", "Action", "Time")
        t2.cursor_type = "row"
        t2.zebra_stripes = True
        yield t2

    def update_scalps(self):
        t2 = self.query_one("#scalp_table", DataTable)
        current_count = len(state.scalp_signals)

        t2.clear()

        # Show initializing state before signals arrive
        if not state.scalp_signals:
            t2.add_row("Initializing...", "-", "-", "-", "-")
            return

        # Show top 10 recent signals
        for sig in state.scalp_signals[:15]:
            # Stylize Action
            action_style = (
                "[bold green]BUY[/]" if sig.action == "BUY" else "[bold red]SELL[/]"
            )

            # Stylize Confidence
            conf_style = sig.confidence
            if sig.confidence == "HIGH":
                conf_style = "[bold yellow]HIGH[/]"

            # Timestamp (rough metric)
            # time_ago = int(time.time() - sig.timestamp)
            # time_str = f"{time_ago}s ago"

            t2.add_row(
                sig.token,
                sig.signal_type,
                conf_style,
                action_style,
                f"{0}s",  # Placeholder for timestamp diff
            )
