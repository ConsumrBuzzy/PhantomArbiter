"""
Configuration Manager
=====================
Handles session initialization via JSON or Interactive Prompt.
Part of Phase 18: Command Center.
"""

import os
import json
from dataclasses import dataclass
from typing import Optional, Dict, Any
import questionary
from rich.console import Console

console = Console()

@dataclass
class SessionContext:
    """Defines the mission profile for the current session."""
    strategy_mode: str  # e.g., "NARROW_PATH", "SCAVENGER", "CUSTOM"
    execution_mode: str # "GHOST", "PAPER", "LIVE"
    budget_sol: float
    params: Dict[str, Any]

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
        # For now, default to GHOST as per plan, but let's offer PAPER check
        mode = questionary.select(
            "Select Deployment Mode:",
            choices=[
                questionary.Choice("👻 GHOST (Simulated Jito + Verification)", value="GHOST"),
                questionary.Choice("📄 PAPER (Standard Simulation)", value="PAPER"),
                # Live is hidden/disabled for safety in this phase
            ]
        ).ask()
        
        # 3. Budget
        budget = questionary.text(
            "📉 Set Session Budget (SOL):", 
            default="10.0",
            validate=lambda text: text.replace('.', '', 1).isdigit() or "Please enter a number"
        ).ask()
        
        return SessionContext(
            strategy_mode=strategy,
            execution_mode=mode,
            budget_sol=float(budget),
            params={}
        )
