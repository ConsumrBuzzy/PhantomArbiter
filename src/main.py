"""
PhantomArbiter - Unified CLI Entrypoint
=======================================
Single entrypoint with subcommands for all trading modes.

V140: Updated to use ConfigManager for "Mission Control".
"""

import argparse
import asyncio
import sys
import logging
from config.settings import Settings
from src.shared.system.logging import Logger
from src.shared.system.config_manager import ConfigManager, SessionContext

# Initialize rich console for startup messages
from rich.console import Console
console = Console()

async def run_arbiter_session(context: SessionContext):
    """
    Launch the Arbitrage Director with the given Session Context.
    """
    console.print(f"[bold green]Starting Mission: {context.strategy_mode}[/bold green]")
    console.print(f"[dim]Mode: {context.execution_mode} | Budget: {context.budget_sol} SOL[/dim]")
    
    # Update Global Settings based on Context
    # This acts as the bridge between Dynamic Context and Static Global Settings
    if context.execution_mode == "GHOST":
        # Force ghost settings
        pass 
        
    if context.strategy_mode == "NARROW_PATH":
        Settings.HOP_ENGINE_ENABLED = True
    else:
        Settings.HOP_ENGINE_ENABLED = False
        
    # Start the Director
    from src.arbiter.director import Director
    director = Director(
        simulation_mode=True if context.execution_mode != "LIVE" else False,
        budget=float(context.budget_sol * 200), # Approx USD conversion for now, TODO: Fetch price
        duration=60 # Default duration, maybe add to context?
    )
    
    # Inject context into Director if needed, or Director reads Settings
    # For now, Director reads Settings which we just patched.
    
    await director.start_monitoring()


def main():
    """Main entry point."""
    # 1. Parse minimal args to see if we're bypassing the menu
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--headless", action="store_true", help="Skip interactive menu")
    args, unknown = parser.parse_known_args()
    
    # 2. Get Session Context
    if args.headless:
        # Load from JSON defaults if headless
        console.print("[yellow]Headless mode detected. Loading defaults...[/yellow]")
        context = ConfigManager.get_session_context() # Will try JSON first
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
    except Exception as e:
        console.print_exception()
        sys.exit(1)

if __name__ == "__main__":
    main()
