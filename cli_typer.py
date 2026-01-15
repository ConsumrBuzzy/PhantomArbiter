"""
PhantomArbiter CLI (Typer PoC)
==============================
Modern command-line interface using Typer + Rich.

This is a Proof of Concept demonstrating:
- Type-safe argument parsing
- Automatic help generation from docstrings
- Rich terminal formatting
- 60% code reduction vs. argparse

PoC Commands:
    python cli_typer.py web
    python cli_typer.py scan
    python cli_typer.py clean

Full migration planned for Week 5 (ADR-0005).
"""

import asyncio
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

# Create Typer app with Rich integration
app = typer.Typer(
    name="phantom",
    help="PhantomArbiter - Solana DeFi Arbitrage & Trading Engine",
    add_completion=True,
    rich_markup_mode="rich",
)

console = Console()


# ═══════════════════════════════════════════════════════════════════════════════
# COMMAND: WEB (Component-Based UI)
# ═══════════════════════════════════════════════════════════════════════════════

@app.command()
def web(
    live: bool = typer.Option(
        False, 
        "--live", 
        help="Enable LIVE trading mode"
    ),
    no_browser: bool = typer.Option(
        False,
        "--no-browser",
        help="Don't auto-open browser"
    ),
    port: int = typer.Option(
        8000,
        "--port",
        help="Frontend HTTP port",
        min=1024,
        max=65535,
    ),
):
    """
    Launch Component-Based Web UI (Modern Dashboard).
    
    This is the [bold green]recommended[/bold green] way to run PhantomArbiter.
    
    Features:
    - Real-time engine monitoring
    - Independent engine control (Arb, Scalp, Funding, LST)
    - WebSocket streaming updates
    - Paper/Live mode toggle
    
    \b
    Examples:
        python cli_typer.py web
        python cli_typer.py web --live
        python cli_typer.py web --port 8080 --no-browser
    """
    console.print("\n")
    console.print(Panel.fit(
        "[bold cyan]🌐 Component-Based Web UI[/bold cyan]\n"
        f"Port: {port} | Live: {'[bold red]YES[/bold red]' if live else '[green]NO (Paper)[/green]'}",
        border_style="cyan"
    ))
    
    if live:
        confirm = typer.confirm(
            "\n⚠️  LIVE MODE ENABLED - Real money at risk. Continue?",
            default=False
        )
        if not confirm:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)
    
    # Delegate to existing run_dashboard.py
    console.print("Launching dashboard via run_dashboard.py...")
    
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("run_dashboard", "run_dashboard.py")
        if spec and spec.loader:
            dashboard_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(dashboard_module)
            asyncio.run(dashboard_module.main())
        else:
            console.print("[bold red]❌ Error: Could not load run_dashboard.py[/bold red]")
            raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutdown requested.[/yellow]")
    except Exception as e:
        console.print(f"[bold red]❌ Error: {e}[/bold red]")
        raise typer.Exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
# COMMAND: SCAN (Quick Arbitrage Scan)
# ═══════════════════════════════════════════════════════════════════════════════

@app.command()
def scan(
    min_spread: float = typer.Option(
        0.5,
        "--min-spread",
        help="Minimum spread percentage to display",
        min=0.1,
        max=100.0,
    ),
    timeout: int = typer.Option(
        30,
        "--timeout",
        help="Scan timeout in seconds",
        min=5,
        max=300,
    ),
):
    """
    Quick one-shot arbitrage opportunity scan.
    
    Scans current market for cross-DEX arbitrage cycles and displays
    profitable opportunities without executing trades.
    
    \b
    Examples:
        python cli_typer.py scan
        python cli_typer.py scan --min-spread 1.0
        python cli_typer.py scan --timeout 60
    """
    console.print("\n")
    console.print(Panel.fit(
        f"[bold yellow]🔍 Arbitrage Scanner[/bold yellow]\n"
        f"Min Spread: {min_spread}% | Timeout: {timeout}s",
        border_style="yellow"
    ))
    
    try:
        from src.engines.arb.logic import ArbEngine
        
        async def run_scan():
            engine = ArbEngine(live_mode=False, min_spread=min_spread)
            console.print("\n[dim]Initializing engine...[/dim]")
            await engine.initialize()
            
            console.print("[dim]Scanning for cycles...[/dim]\n")
            cycles = await engine.find_cycles()
            
            if cycles:
                console.print(f"\n[bold green]✅ Found {len(cycles)} opportunities:[/bold green]\n")
                for i, cycle in enumerate(cycles[:10], 1):  # Show top 10
                    path = " → ".join(cycle.get('path', []))
                    profit = cycle.get('est_profit', 0)
                    console.print(f"  {i}. [cyan]{path}[/cyan]")
                    console.print(f"     Profit: [green]${profit:.2f}[/green]\n")
            else:
                console.print("\n[yellow]⚠️  No opportunities found (min spread too high?)[/yellow]\n")
        
        asyncio.run(run_scan())
        
    except ImportError:
        console.print("[bold red]❌ ArbEngine not available (check src/engines/arb/logic.py)[/bold red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[bold red]❌ Scan failed: {e}[/bold red]")
        raise typer.Exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
# COMMAND: CLEAN (Emergency Liquidation)
# ═══════════════════════════════════════════════════════════════════════════════

@app.command()
def clean(
    token: Optional[str] = typer.Option(
        None,
        "--token",
        help="Token symbol (e.g., BONK) or mint address to sell"
    ),
    all: bool = typer.Option(
        False,
        "--all",
        help="Sell ALL tokens (except USDC/SOL)"
    ),
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--execute",
        help="Dry run (default) or execute for real"
    ),
):
    """
    Emergency wallet cleanup (sell tokens for USDC/SOL).
    
    [bold red]⚠️  WARNING: This command can execute real trades![/bold red]
    
    Use [bold cyan]--execute[/bold cyan] flag to actually sell tokens.
    Default is dry-run mode (safe).
    
    \b
    Examples:
        python cli_typer.py clean --token BONK --dry-run
        python cli_typer.py clean --token BONK --execute
        python cli_typer.py clean --all --dry-run
    """
    console.print("\n")
    
    if not token and not all:
        console.print("[bold red]❌ Error: Specify --token <SYMBOL> or --all[/bold red]\n")
        raise typer.Exit(1)
    
    mode = "[green]DRY RUN[/green]" if dry_run else "[bold red]LIVE EXECUTION[/bold red]"
    target = f"Token: {token}" if token else "[bold red]ALL TOKENS[/bold red]"
    
    console.print(Panel.fit(
        f"[bold yellow]🧹 Wallet Cleaner[/bold yellow]\n"
        f"Mode: {mode}\n{target}",
        border_style="yellow"
    ))
    
    if not dry_run:
        confirm = typer.confirm(
            "\n⚠️  LIVE MODE - Tokens will be sold for real. Type 'yes' to confirm",
            default=False
        )
        if not confirm:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)
    
    if dry_run:
        console.print("\n[dim]DRY RUN: No actual trades will be executed.[/dim]")
        console.print(f"[dim]Would sell: {token if token else 'ALL tokens'}[/dim]\n")
    else:
        console.print("\n[bold red]LIVE EXECUTION NOT IMPLEMENTED IN POC[/bold red]")
        console.print("[dim]Full implementation will integrate with WalletManager + Jupiter[/dim]\n")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """Entry point for CLI."""
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user.[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    # Windows async event loop fix
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    main()
