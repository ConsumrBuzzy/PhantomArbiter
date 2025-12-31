"""
Configuration Manager
=====================
Handles session initialization via JSON or Interactive Prompt.
Part of Phase 18: Command Center.
"""

import os
import json
import time
import subprocess
import getpass
from dataclasses import dataclass
from typing import Optional, Dict, Any
import questionary
from rich.console import Console

from src.shared.system.hydration_manager import HydrationManager

console = Console()

@dataclass
class SessionContext:
    """Defines the mission profile for the current session."""
    strategy_mode: str  # e.g., "NARROW_PATH", "SCAVENGER", "CUSTOM"
    execution_mode: str # "GHOST", "PAPER", "LIVE"
    budget_sol: float
    params: Dict[str, Any]
    wallet_key: Optional[bytes] = None # Ephemeral Key (Privacy Shield)

class ConfigManager:
    """
    Orchestrates the startup configuration.
    Priority:
    1. CLI Args (Not impl yet)
    2. session_config.json (Automation)
    3. Interactive Prompt (User)
    """
    
    @staticmethod
    def get_session_context() -> SessionContext:
        """Determines the session context."""
        # 1. Check for automated config
        if os.path.exists("session_config.json"):
            console.print("[dim]Loading session_config.json...[/dim]")
            return ConfigManager._load_json("session_config.json")
            
        # 2. Interactive Menu
        return ConfigManager._prompt_user_menu()

    @staticmethod
    def _load_json(path: str) -> SessionContext:
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            return SessionContext(
                strategy_mode=data.get("strategy_mode", "NARROW_PATH"),
                execution_mode=data.get("execution_mode", "GHOST"),
                budget_sol=float(data.get("budget_sol", 10.0)),
                params=data.get("params", {})
            )
        except Exception as e:
            console.print(f"[bold red]Failed to load config:[/bold red] {e}")
            return ConfigManager._prompt_user_menu()

    @staticmethod
    def _prompt_user_menu() -> SessionContext:
        """Launches the Mission Control interactive menu."""
        console.print("\n[bold cyan]🚀 PHANTOM ARBITER: COMMAND CENTER[/bold cyan]")
        
        # 1. Mission Profile
        strategy = questionary.select(
            "Select Mission Profile:",
            choices=[
                questionary.Choice("Pair Hopping (Narrow Path)", value="NARROW_PATH"),
                questionary.Choice("Scavenger (Pool Recoils)", value="SCAVENGER"),
                questionary.Choice("Custom / Manual", value="CUSTOM"),
            ],
            style=questionary.Style([('answer', 'fg:cyan bold')])
        ).ask()
        
        # 2. Execution Mode
        mode = questionary.select(
            "Select Deployment Mode:",
            choices=[
                questionary.Choice("🔥 LIVE (Money on the Line)", value="LIVE"),
                questionary.Choice("👻 GHOST (Simulated Jito + Verification)", value="GHOST"),
                questionary.Choice("📄 PAPER (Standard Simulation)", value="PAPER"),
            ]
        ).ask()
        
        # Privacy Shield: Inject Key if needed
        wallet_key = None
        if mode == "LIVE":
            console.print("\n[bold red]🔐 PRIVACY SHIELD ACTIVE[/bold red]")
            console.print("   The Private Key will be injected into RAM only.")
            console.print("   It will NEVER be written to disk or logs.")
            
            try:
                # getpass hides input on most systems
                key_input = getpass.getpass("🔑 Inject Private Key (Base58): ")
                if not key_input or len(key_input) < 10:
                    console.print("[red]❌ Invalid Key Injection. Aborting.[/red]")
                    sys.exit(1)
                
                # Convert Base58 to bytes (mocking validation here for now)
                # In real impl, we'd validate against solders.keypair
                wallet_key = key_input.encode('utf-8') 
                console.print("[green]   ✅ Key Injected into Volatile Memory[/green]")
                
            except Exception as e:
                console.print(f"[red]❌ Key Injection Failed: {e}[/red]")
                sys.exit(1)
        
        # 3. Risk Profile (Advanced)
        risk = questionary.select(
            "Select Risk Profile:",
            choices=[
                questionary.Choice("🛡️ Conservative (Low Size, High Confidence)", value="CONSERVATIVE"),
                questionary.Choice("⚖️ Balanced (Standard)", value="BALANCED"),
                questionary.Choice("⚔️ Aggressive (Max Size, Speed)", value="AGGRESSIVE"),
            ]
        ).ask()
        
        # 4. Budget
        budget = questionary.text(
            "📉 Set Session Budget (SOL):", 
            default="10.0",
            validate=lambda text: text.replace('.', '', 1).isdigit() or "Please enter a number"
        ).ask()
        
        # 5. Pre-Flight Latency Check
        ConfigManager._check_latency()
        
        return SessionContext(
            strategy_mode=strategy,
            execution_mode=mode,
            budget_sol=float(budget),
            params={"risk_profile": risk},
            wallet_key=wallet_key
        )

    @staticmethod
    def _check_latency():
        """
        Performs a Pre-Flight Connectivity Check.
        Pings Public DNS (8.8.8.8) as a proxy for network health.
        """
        console.print("\n[dim]🛰️ Performing Pre-Flight Checks...[/dim]")
        try:
            # Windows ping command
            start = time.time()
            subprocess.run(["ping", "-n", "1", "8.8.8.8"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            end = time.time()
            latency_ms = (end - start) * 1000
            
            if latency_ms > 500:
                console.print(f"[bold red]⚠️ WARNING: High Network Latency Detected: {latency_ms:.0f}ms[/bold red]")
                console.print("[red]   Ghost results may be overly optimistic due to lag.[/red]")
                time.sleep(1) # Let user see warning
            else:
                console.print(f"[green]✅ Network Latency: {latency_ms:.0f}ms (Nominal)[/green]")
                
        except Exception:
            console.print("[yellow]⚠️ Could not verify latency. Assuming offline/restricted.[/yellow]")
