"""
Rich Pulse Dashboard
====================
A lightweight "Headless TUI" using Rich.live.
Provides Panels and layout without the full application lifecycle of Textual.
"""

from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.console import Console
from rich import box
from datetime import datetime
from typing import List, Dict, Any

from src.arbiter.core.reporter import ArbiterReporter
from src.arbiter.core.spread_detector import SpreadOpportunity

class PulsedDashboard:
    """Layout manager for the Pulse View."""
    
    def __init__(self):
        self.layout = Layout()
        self.layout.split(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3)
        )
        # Main area: Split Left (Arbiter + Signals) and Right (Scalper/Inventory/Stats)
        self.layout["main"].split_row(
            Layout(name="left_container", ratio=3), 
            Layout(name="right", ratio=2)
        )
        
        self.layout["left_container"].split_column(
            Layout(name="left", ratio=2), # Arb Table
            Layout(name="signals", ratio=1), # Signal Audit
            Layout(name="shadow", ratio=1) # Shadow/Drift Pane
        )
        
        # Right Column: Split Top (Scalper), Middle (Inventory), Bottom (Stats)
        self.layout["right"].split_column(
            Layout(name="scalper", ratio=1),
            Layout(name="inventory", ratio=1),
            Layout(name="stats", size=6)
        )
        
    def generate_header(self, state: Any):
        """Render header with Real/Paper split."""
        # Real Wallet
        real_usdc = state.wallet_live.balance_usdc
        real_sol = state.wallet_live.balance_sol
        
        # Paper Wallet
        paper_usdc = state.wallet_paper.balance_usdc
        paper_sol = state.wallet_paper.balance_sol
        
        pod_status = state.stats.get('pod_status', "")
        pod_str = f" | 🔭 {pod_status}" if pod_status else ""
        
        # Layout: REAL [USDC | SOL]  ||  PAPER [USDC | SOL]
        text = (
            f"[bold cyan]PHANTOM PULSE[/bold cyan]{pod_str}   "
            f"🔴 [bold]REAL:[/bold] [green]${real_usdc:,.2f}[/green] / [yellow]{real_sol:.3f} SOL[/yellow]   "
            f"⚪ [dim]PAPER:[/dim] [green]${paper_usdc:,.2f}[/green] / [yellow]{paper_sol:.3f} SOL[/yellow]"
        )
        return Panel(text, style="white on blue", box=box.HEAVY_HEAD)
        
    def generate_opp_table(self, spreads: List[SpreadOpportunity], verified_opps: List[SpreadOpportunity] = None):
        table = Table(box=box.SIMPLE_HEAD, expand=True)
        table.add_column("Pair", style="cyan")
        table.add_column("Spread", justify="right")
        table.add_column("Net Profit", justify="right")
        table.add_column("Route", style="dim")
        table.add_column("Status", justify="center")
        
        verified_map = {op.pair: getattr(op, 'verification_status', None) for op in (verified_opps or [])}
        
        # limit to top 20 to fit screen vertical
        for opp in spreads[:20]:
            status = verified_map.get(opp.pair, "🔍")
            status_color = "white"
            if "LIVE" in str(status) or "READY" in str(status): status_color = "green"
            elif "LIQ" in str(status): status_color = "red"
                
            spread_color = "green" if opp.spread_pct > 0.5 else "yellow"
            if opp.spread_pct < 0: spread_color = "red"
            
            table.add_row(
                opp.pair,
                f"[{spread_color}]{opp.spread_pct:.2f}%[/{spread_color}]",
                f"[bold {spread_color}]${opp.net_profit_usd:+.3f}[/bold {spread_color}]",
                f"{opp.buy_dex}->{opp.sell_dex}",
                f"[{status_color}]{status}[/{status_color}]"
            )
        return Panel(table, title="[bold]Live Market Observer[/bold]", border_style="blue")
        
    def generate_scalper_panel(self, signals: List[Any], market_pulse: Dict[str, Any] = None):
        """Show active scalp signals AND Price Watch.
        V140: In Narrow Path mode, this is replaced by generate_multiverse_panel.
        """
        # V140: Check if we're in hop mode - if so, show placeholder
        from config.settings import Settings
        if getattr(Settings, 'HOP_ENGINE_ENABLED', False):
            return self.generate_multiverse_panel(signals)
        
        # V90.0: Unified Price Watch + Signal View
        table = Table(box=box.SIMPLE, expand=True)
        table.add_column("Token", style="magenta")
        table.add_column("Status", style="cyan")  # V133: Dedicated Status column
        table.add_column("Price", justify="right")
        table.add_column("RSI", justify="right")
        table.add_column("Conf")
        
        # 1. Prioritize Signals
        rows = []
        if signals:
            for s in signals[:3]:
                # Handle both numeric and text-based confidence
                raw_conf = s.confidence
                try:
                    conf = float(raw_conf) if raw_conf else 0.0
                except (ValueError, TypeError):
                    # Map text labels to numeric values
                    conf_map = {'high': 0.9, 'medium': 0.6, 'med': 0.6, 'low': 0.3}
                    conf = conf_map.get(str(raw_conf).lower(), 0.5)
                conf_color = "green" if conf > 0.8 else "yellow"
                # V133: Separate Status and Price columns
                price_val = getattr(s, 'price', None)
                price_str = f"${price_val:.4f}" if price_val else "-"
                status_str = s.signal_type if hasattr(s, 'signal_type') else s.action
                rows.append([
                    f"⚡ {s.token}",
                    status_str,  # V133: Status column
                    price_str,   # V133: Price column 
                    s.action if hasattr(s, 'action') else "SIG", 
                    f"[{conf_color}]{conf:.0%}[/{conf_color}]"
                ])
        
        # 2. Fill with Market Pulse (Top watched)
        if market_pulse:
            # Sort by RSI urgency (close to 30 or 70)
            def rsi_urgency(item):
                rsi = item.get('rsi', 50)
                return abs(rsi - 50)
                
            sorted_pulse = sorted(market_pulse.items(), key=lambda x: rsi_urgency(x[1]), reverse=True)
            
            for symbol, data in sorted_pulse[:7]: # Limit to fit
                price = data.get('price', 0)
                rsi = data.get('rsi', 50)
                conf = data.get('conf', 0)
                
                # RSI Color
                rsi_str = f"{rsi:.1f}"
                if rsi > 70: rsi_str = f"[red]{rsi:.0f}[/red]"
                elif rsi < 30: rsi_str = f"[green]{rsi:.0f}[/green]"
                elif rsi == 0: rsi_str = "-"
                else: rsi_str = f"[dim]{rsi:.0f}[/dim]"
                
                # Deduplicate if already shown as signal
                if any(r[0] == f"⚡ {symbol}" for r in rows): continue
                
                # V133: Add Status column (empty for market data)
                rows.append([symbol, "-", f"${price:.4f}", rsi_str, f"{conf:.0%}"])
                
        if not rows:
             table.add_row("-", "-", "Initializing...", "-", "-")
        else:
            for r in rows[:10]:
                table.add_row(*r)
                
        return Panel(table, title="[magenta]Scalper & Price Watch[/magenta]", border_style="magenta")

    def generate_multiverse_panel(self, hop_data: Any = None):
        """V140: Show Multiverse Hop Cycles grouped by hop count.
        
        Displays cycles found at each hop level (2-5) with profit and liquidity.
        """
        table = Table(box=box.SIMPLE, expand=True)
        table.add_column("Hops", style="cyan", width=4)
        table.add_column("Path", style="white", ratio=2)
        table.add_column("Profit", justify="right", style="green")
        table.add_column("Liq", justify="right", style="dim")
        
        # Try to get multiverse data from app_state
        cycles_by_hops = {}
        if hop_data and hasattr(hop_data, 'get'):
            cycles_by_hops = hop_data.get('cycles_by_hops', {})
        elif isinstance(hop_data, dict):
            cycles_by_hops = hop_data.get('cycles_by_hops', {})
        
        if not cycles_by_hops:
            # Show placeholder with tier descriptions
            table.add_row("2", "[dim]Spatial (High Comp)[/dim]", "-", "-")
            table.add_row("3", "[dim]Triangle (Standard)[/dim]", "-", "-")
            table.add_row("[cyan]4[/cyan]", "[cyan]Long-Tail (Alpha Zone)[/cyan]", "-", "-")
            table.add_row("5", "[dim]Deep Path (Complex)[/dim]", "-", "-")
            return Panel(table, title="[cyan]🌌 Multiverse Hop Scanner[/cyan]", border_style="cyan")
        
        # Show best cycle at each hop level
        for hop_count in [2, 3, 4, 5]:
            cycles = cycles_by_hops.get(hop_count, [])
            if cycles:
                best = cycles[0] if isinstance(cycles, list) else cycles
                path_short = best.get('path', [])[:3]  # First 3 tokens
                path_str = "→".join([p[:6] for p in path_short]) + "..."
                
                profit = best.get('profit_pct', 0)
                profit_color = "green" if profit > 0.3 else "yellow"
                
                liq = best.get('min_liquidity_usd', 0)
                liq_str = f"${liq/1000:.0f}k" if liq > 1000 else f"${liq:.0f}"
                
                # Highlight 4-hop (alpha zone)
                if hop_count == 4:
                    table.add_row(
                        f"[bold cyan]{hop_count}[/bold cyan]",
                        f"[bold]{path_str}[/bold]",
                        f"[bold {profit_color}]+{profit:.2f}%[/bold {profit_color}]",
                        liq_str
                    )
                else:
                    table.add_row(
                        str(hop_count),
                        path_str,
                        f"[{profit_color}]+{profit:.2f}%[/{profit_color}]",
                        liq_str
                    )
            else:
                tier_name = {2: "Spatial", 3: "Triangle", 4: "Long-Tail", 5: "Deep"}
                table.add_row(str(hop_count), f"[dim]{tier_name.get(hop_count, '')}[/dim]", "-", "-")
        
        return Panel(table, title="[cyan]🌌 Multiverse Hop Scanner[/cyan]", border_style="cyan")

    def generate_inventory_panel(self, inventory: List[Any]):
        """Show held bags with Bought and Current prices.
        V140: In Narrow Path mode, shows Graph Stats instead.
        """
        from config.settings import Settings
        if getattr(Settings, 'HOP_ENGINE_ENABLED', False):
            return self.generate_graph_stats_panel(inventory)
        
        table = Table(box=box.SIMPLE, expand=True)
        table.add_column("Token")
        table.add_column("Bought", justify="right")   # V133: Bought Price
        table.add_column("Current", justify="right")  # V133: Current Price
        table.add_column("PnL", justify="right")
        
        if not inventory:
            table.add_row("No positions", "-", "-", "-")
        else:
            for item in inventory[:5]:
                pnl_color = "green" if item.pnl > 0 else "red"
                bought_price = getattr(item, 'bought_price', 0) or getattr(item, 'entry_price', 0)
                current_price = getattr(item, 'current_price', 0) or (item.value_usd / item.quantity if getattr(item, 'quantity', 0) else 0)
                table.add_row(
                    item.symbol, 
                    f"${bought_price:.4f}" if bought_price else "-",
                    f"${current_price:.4f}" if current_price else "-",
                    f"[{pnl_color}]${item.pnl:.2f}[/{pnl_color}]"
                )
                
        return Panel(table, title="Inventory (Held Bags)", border_style="yellow")

    def generate_graph_stats_panel(self, stats_data: Any = None):
        """V140: Show HopGraph engine statistics.
        
        Displays pool count, node count, scan performance metrics.
        """
        from rich.table import Table as RichTable
        
        grid = RichTable.grid(expand=True)
        grid.add_column(ratio=1)
        grid.add_column(ratio=1, justify="right")
        
        # Default stats
        node_count = 0
        edge_count = 0
        scan_ms = 0.0
        cycles_found = 0
        
        # Try to extract stats from app_state
        if stats_data and hasattr(stats_data, 'get'):
            node_count = stats_data.get('node_count', 0)
            edge_count = stats_data.get('edge_count', 0)
            scan_ms = stats_data.get('last_scan_ms', 0.0)
            cycles_found = stats_data.get('cycles_found', 0)
        elif isinstance(stats_data, dict):
            node_count = stats_data.get('node_count', 0)
            edge_count = stats_data.get('edge_count', 0)
            scan_ms = stats_data.get('last_scan_ms', 0.0)
            cycles_found = stats_data.get('cycles_found', 0)
        
        # Color coding
        pool_color = "green" if edge_count > 1000 else "yellow" if edge_count > 100 else "dim"
        scan_color = "green" if scan_ms < 50 else "yellow" if scan_ms < 200 else "red"
        cycle_color = "green" if cycles_found > 0 else "dim"
        
        grid.add_row("Tokens (Nodes):", f"[cyan]{node_count:,}[/cyan]")
        grid.add_row("Pools (Edges):", f"[{pool_color}]{edge_count:,}[/{pool_color}]")
        grid.add_row("Scan Time:", f"[{scan_color}]{scan_ms:.1f}ms[/{scan_color}]")
        grid.add_row("Cycles Found:", f"[{cycle_color}]{cycles_found}[/{cycle_color}]")
        
        return Panel(grid, title="[yellow]📊 Graph Engine Stats[/yellow]", border_style="yellow")

    def generate_signal_panel(self, signals: List[Any]):
        """Show recent system-wide signals."""
        table = Table(box=box.SIMPLE, expand=True)
        table.add_column("Time", style="dim")
        table.add_column("Type")
        table.add_column("Source", style="cyan")
        table.add_column("Summary", ratio=1)
        
        for sig in list(signals)[:10]:
            ts = datetime.fromtimestamp(sig.timestamp).strftime("%H:%M:%S")
            s_type = sig.type.value
            color = "white"
            if s_type == "WHALE": color = "bold blue"
            elif s_type == "SCOUT": color = "bold green"
            elif s_type == "ARB_OPP": color = "cyan"
            
            summary = str(sig.data.get("symbol", sig.data.get("message", "Data...")))
            table.add_row(ts, f"[{color}]{s_type}[/{color}]", sig.source, summary)
            
        return Panel(table, title="Signal Intelligence (Global Feed)", border_style="magenta")

    def generate_stats_panel(self, trades: int, volume: float, turnover: float):
        lines = [
            f"[bold]Session Stats[/bold]",
            f"Trades:   {trades}",
            f"Volume:   ${volume:,.2f}",
            f"Turnover: {turnover:.1f}x",
            "",
            "[dim]Waiting for next cycle...[/dim]"
        ]
        return Panel("\n".join(lines), title="Strategy Engine", border_style="white")

    def generate_shadow_panel(self, stats: Dict[str, Any]):
        """Show Shadow Mode/Drift stats."""
        if not stats:
            return Panel("Waiting for Audit Data...", title="Shadow Audit (The Drift)", border_style="dim")
            
        grid = Table.grid(expand=True)
        grid.add_column()
        grid.add_column(justify="right")
        
        # Summary Stats
        audits = stats.get('total_audits', 0)
        deltas = stats.get('significant_deltas', 0)
        drift = stats.get('avg_delta_pct', 0.0)
        max_drift = stats.get('max_delta_pct', 0.0)
        
        drift_color = "green" if abs(drift) < 0.5 else "yellow"
        if abs(drift) > 1.0: drift_color = "red"
        
        grid.add_row("Audits:", str(audits))
        grid.add_row("Sig. Deltas:", f"[red]{deltas}[/red]" if deltas > 0 else str(deltas))
        grid.add_row("Mean Drift:", f"[{drift_color}]{drift:+.2f}%[/{drift_color}]")
        grid.add_row("Max Drift:", f"{max_drift:+.2f}%")
        
        return Panel(grid, title="Shadow Audit (The Drift)", border_style="cyan")

class RichPulseReporter(ArbiterReporter):
    """Overrides default Reporter to render to Rich Layout."""
    
    def __init__(self, telegram=None):
        super().__init__(telegram)
        from src.shared.system.logging import Logger
        Logger.set_silent(True) # V135: Silence console logs to prevent TUI artifacts
        self.dashboard = PulsedDashboard()
        self.live = Live(self.dashboard.layout, refresh_per_second=2, screen=True)  # V134: Reduced from 4 to prevent stutter
        self.live.start()
        
    def update_from_state(self, app_state):
        """Pull ALL data from AppState (The Global Truth)."""
        # 1. Header
        self.dashboard.layout["header"].update(
            self.dashboard.generate_header(app_state)
        )
        
        # 2. Arbiter (Left)
        # Convert AppState dicts back to objects or use raw?
        # AppState.opportunities is list of ArbOpportunity objects (simplified)
        # We need to adapt them for generate_opp_table
        # Or just rewrite generate_opp_table to accept ArbOpportunity
        self.dashboard.layout["left"].update(
            self._render_arb_table(app_state.opportunities)
        )
        
        # 3. Scalper (Right Top)
        # Pass both signals and market_pulse
        self.dashboard.layout["scalper"].update(
            self.dashboard.generate_scalper_panel(app_state.scalp_signals, app_state.market_pulse)
        )
        
        # 3b. Signals (Left Bottom)
        self.dashboard.layout["signals"].update(
            self.dashboard.generate_signal_panel(app_state.system_signals)
        )
        
        # 3c. Shadow (Left Bottom 2)
        shadow_stats = getattr(app_state, 'shadow_stats', {})
        self.dashboard.layout["shadow"].update(
            self.dashboard.generate_shadow_panel(shadow_stats)
        )
        
        # 4. Inventory (Right Mid)
        self.dashboard.layout["inventory"].update(
            self.dashboard.generate_inventory_panel(app_state.inventory)
        )
        
        # 5. Stats
        self.dashboard.layout["stats"].update(
            self.dashboard.generate_stats_panel(
                trades=app_state.stats.get('total_trades', 0),
                volume=app_state.stats.get('volume', 0),
                turnover=0
            )
        )
        
        # 6. Footer
        now = datetime.now().strftime("%H:%M:%S")
        log_msg = app_state.logs[-1] if app_state.logs else "System Active"
        self.dashboard.layout["footer"].update(
            Panel(f"[{now}] {log_msg}", style="dim")
        )

    def _render_arb_table(self, opportunities):
        """Adapter for AppState ArbOpportunity -> Rich Table."""
        table = Table(box=box.SIMPLE_HEAD, expand=True)
        table.add_column("Pair", style="cyan")
        table.add_column("Spread", justify="right")
        table.add_column("Est Profit", justify="right")
        table.add_column("Route", style="dim")
        
        for opp in opportunities[:20]:
            spread_color = "green" if opp.profit_pct > 0.5 else "yellow"
            table.add_row(
                opp.token,
                f"[{spread_color}]{opp.profit_pct:.2f}%[/{spread_color}]",
                f"[bold {spread_color}]${opp.est_profit_sol:.3f}[/bold {spread_color}]", # Using field name from AppState
                opp.route
            )
        return Panel(table, title="[bold]Live Market Observer[/bold]", border_style="blue")

    def print_dashboard(self, *args, **kwargs):
        # Legacy hook - ignore, we use update_from_state now
        pass
        
    def stop(self):
        self.live.stop()
        from src.shared.system.logging import Logger
        Logger.set_silent(False) # Restore console logs
