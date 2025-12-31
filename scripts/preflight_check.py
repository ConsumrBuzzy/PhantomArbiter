
"""
Pre-Flight Diagnostics
======================
Verifies all systems are GO for launch.
Checks infrastructure, wallet, core availability, and agent loading.
"""

import sys
import os
import time
import asyncio
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.shared.system.logging import Logger
from src.shared.infrastructure.rpc_manager import RpcConnectionManager
from src.shared.execution.wallet import WalletManager
from config.settings import Settings

console = Console()

async def check_infrastructure() -> dict:
    results = {}
    console.print("[bold yellow]1. Checking Infrastructure...[/bold yellow]")
    
    # RPC Check
    try:
        rpc = RpcConnectionManager() 
        # Force benchmark
        rpc.benchmark_providers()
        active = rpc.get_active_url()
        latencies = [s['avg_latency'] for s in rpc.stats.values() if s['avg_latency'] > 0]
        avg_lat = sum(latencies)/len(latencies) if latencies else 0
        
        results["RPC"] = f"✅ ONLINE ({active} @ {avg_lat:.0f}ms)"
    except Exception as e:
        results["RPC"] = f"❌ FAILED: {e}"

    # Wallet Check
    try:
        w = WalletManager()
        bal = w.get_sol_balance()
        if bal is None:
             results["Wallet"] = "❌ FAILED (RPC Error?)"
        elif bal < 0.02:
             results["Wallet"] = f"⚠️ LOW BALANCE ({bal:.4f} SOL)"
        else:
             results["Wallet"] = f"✅ READY ({bal:.4f} SOL)"
    except Exception as e:
        results["Wallet"] = f"❌ FAILED: {e}"
        
    return results

async def check_components() -> dict:
    results = {}
    console.print("\n[bold yellow]2. Checking Components...[/bold yellow]")
    
    components = [
        ("Core", "src.engine.trading_core", "TradingCore"),
        ("Decision", "src.engine.decision_engine", "DecisionEngine"),
        ("Shadow", "src.engine.shadow_manager", "ShadowManager"),
        ("Director", "src.engine.director", "Director"),
        ("WhaleWatcher", "src.scraper.agents.whale_watcher_agent", "WhaleWatcherAgent"),
        ("Scout", "src.scraper.agents.scout_agent", "ScoutAgent"),
    ]
    
    for name, module_path, class_name in components:
        try:
            # Dynamic import check
            mod = __import__(module_path, fromlist=[class_name])
            cls = getattr(mod, class_name)
            results[name] = "✅ LOADED"
        except ImportError as e:
            results[name] = f"❌ MISSING: {e}"
        except AttributeError:
             results[name] = f"❌ BROKEN (Class not found)"
        except Exception as e:
            results[name] = f"⚠️ ERROR: {e}"
            
    # Special Check: PhantomCore (Rust)
    try:
        import phantom_core
        results["RustCore"] = "✅ ENABLED (Native)"
    except ImportError:
        results["RustCore"] = "⚠️ DISABLED (Using Python Fallback)"
        
    return results

async def run_diagnostics():
    console.print(Panel("[bold cyan]🚀 PHANTOM ARBITER: PRE-FLIGHT DIAGNOSTICS[/bold cyan]"))
    
    infra_res = await check_infrastructure()
    comp_res = await check_components()
    
    # Display Table
    table = Table(title="System Status")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")
    
    for k, v in infra_res.items():
        style = "red" if "❌" in v else ("yellow" if "⚠️" in v else "green")
        table.add_row(k, f"[{style}]{v}[/{style}]")
        
    table.add_section()
    
    for k, v in comp_res.items():
        style = "red" if "❌" in v else ("yellow" if "⚠️" in v else "green")
        table.add_row(k, f"[{style}]{v}[/{style}]")
        
    console.print(table)
    
    # Final Verdict
    errors = sum(1 for v in {**infra_res, **comp_res}.values() if "❌" in v)
    if errors == 0:
        console.print("\n[bold green]✅ SYSTEM GO FOR LAUNCH[/bold green]")
    else:
        console.print(f"\n[bold red]🛑 SYSTEM NO-GO: {errors} Critical Failures[/bold red]")

if __name__ == "__main__":
    try:
        asyncio.run(run_diagnostics())
    except KeyboardInterrupt:
        pass
