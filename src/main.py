"""
PhantomArbiter - Unified CLI Entrypoint
=======================================
Single entrypoint with subcommands for all trading modes.

V140: Updated to use ConfigManager for "Mission Control".
"""

import argparse
import asyncio
import sys
from config.settings import Settings
from src.shared.system.config_manager import ConfigManager, SessionContext
from src.shared.reporting.aar_generator import AARGenerator
from src.shared.system.hydration_manager import HydrationManager

# Initialize rich console for startup messages
from rich.console import Console

console = Console()


async def run_arbiter_session(context: SessionContext):
    """
    Launch the Arbitrage Director with the given Session Context.
    """
    console.print(f"[bold green]Starting Mission: {context.strategy_mode}[/bold green]")
    console.print(
        f"[dim]Mode: {context.execution_mode} | Budget: {context.budget_sol} SOL[/dim]"
    )

    # Update Global Settings based on Context
    # This acts as the bridge between Dynamic Context and Static Global Settings
    if context.execution_mode == "GHOST":
        # Force ghost settings
        pass

    if context.strategy_mode == "NARROW_PATH":
        Settings.HOP_ENGINE_ENABLED = True
    else:
        Settings.HOP_ENGINE_ENABLED = False

    # Initialize AAR Generator
    aar = AARGenerator(context)

    # Start the Director
    from src.arbiter.director import Director

    director = Director(
        simulation_mode=True if context.execution_mode != "LIVE" else False,
        budget=float(context.budget_sol * 200),
        duration=60,
    )

    try:
        await director.start_monitoring()
    finally:
        # Generate Debrief
        console.print("\n[bold cyan]📋 Generatig Mission Debrief (AAR)...[/bold cyan]")
        # TODO: Hydrate AAR with real stats from Director/Pods
        # For now, it captures duration and context
        report_path = aar.generate_report()
        console.print(f"[green]✅ AAR Saved: {report_path}[/green]")


def main():
    """Main entry point."""
    # 1. Parse minimal args to see if we're bypassing the menu
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--headless", action="store_true", help="Skip interactive menu")
    args, unknown = parser.parse_known_args()

    # 0. Nomad Persistence: Auto-Hydration (Startup)
    # This rebuilds the Hot DB from Cold JSON if needed
    try:
        hydration = HydrationManager()
        # In Phase 20, we simply ensure the DB exists if archives are present
        archives = hydration.list_archives()
        if archives and not hydration.db_exists():
            console.print("[dim]💎 Nomad: Rehydrating from latest archive...[/dim]")
            hydration.rehydrate(archives[0])
    except Exception as e:
        console.print(f"[yellow]⚠️ Hydration Warning: {e}[/yellow]")

    # 2. Get Session Context
    if args.headless:
        # Load from JSON defaults if headless
        console.print("[yellow]Headless mode detected. Loading defaults...[/yellow]")
        context = ConfigManager.get_session_context()  # Will try JSON first
    else:
        # Launch Interactive Mission Control
        try:
            context = ConfigManager.get_session_context()
        except KeyboardInterrupt:
            console.print("\n[red]Mission Aborted.[/red]")
            sys.exit(0)

    # 3. Execute Mission
    try:
        asyncio.run(run_arbiter_session(context))
    except KeyboardInterrupt:
        console.print("\n[bold red]System Shutdown Initiated...[/bold red]")
    except Exception:
        console.print_exception()
        sys.exit(1)
    finally:
        # Phase 21: Privacy Shield - RAM Zeroing
        if "context" in locals() and context.wallet_key:
            context.wallet_key = None
            del context.wallet_key
            console.print("[dim]🔐 Privacy Shield: Wallet Key wiped from RAM.[/dim]")


if __name__ == "__main__":
    main()
