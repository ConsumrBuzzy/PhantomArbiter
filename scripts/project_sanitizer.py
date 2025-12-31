"""
Project Sanitizer
=================
Phase 26: Refactor & Cleanup

The "Janitor" script for the PhantomArbiter codebase.
1. Rust Audit (Clippy)
2. Python Audit (Vulture)
3. Data Audit (Orphaned Token Cleanup)
"""

import sys
import os
import subprocess
import shutil

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.shared.persistence.market_manager import MarketManager
from src.shared.persistence.token_registry import TokenRegistry
from src.shared.system.logging import Logger

def run_rust_audit():
    print("\n🦀 Running Rust Audit (Cargo Clippy)...")
    try:
        # Check if cargo exists
        if not shutil.which("cargo"):
            print("   ⚠️ Cargo not found. Skipping Rust audit.")
            return

        result = subprocess.run(
            ["cargo", "clippy", "--", "-D", "warnings"],
            cwd="src_rust",
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("   ✅ Rust Codebase is Clean.")
        else:
            print("   ⚠️ Rust Issues Found:")
            print(result.stderr[:1000]) # truncated
            
    except Exception as e:
        print(f"   ❌ Rust Audit Failed: {e}")

def run_python_audit():
    print("\n🐍 Running Python Audit (Vulture)...")
    try:
        # Check if vulture exists
        if not shutil.which("vulture"):
            print("   ⚠️ Vulture not found. Install with 'pip install vulture' to enable dead code detection.")
            return

        # Scan src and scripts
        result = subprocess.run(
            ["vulture", "src/", "scripts/", "--min-confidence", "80"],
            capture_output=True,
            text=True
        )
        
        # Vulture returns non-zero if issues found
        if not result.stdout:
            print("   ✅ Python Codebase is Clean.")
        else:
            issues = result.stdout.strip().split('\n')
            print(f"   ⚠️ Found {len(issues)} Potential Dead Code issues:")
            for issue in issues[:10]: # Validated limitation
                print(f"      - {issue}")
            if len(issues) > 10:
                print(f"      ... and {len(issues)-10} more.")

    except Exception as e:
        print(f"   ❌ Python Audit Failed: {e}")

def run_data_audit():
    print("\n💾 Running Data Audit (Registry Cleanup)...")
    try:
        market_mgr = MarketManager()
        token_reg = TokenRegistry()
        
        # 1. Get Active Mints from Edges with GraphData
        print("   running graph analysis...")
        graph = market_mgr.get_graph_data()
        
        active_mints = set()
        for node in graph['nodes']:
            active_mints.add(node['id'])
            
        print(f"   found {len(active_mints)} active tokens in market graph.")
        
        # 2. Audit Orphans
        purged = token_reg.audit_orphans(active_mints)
        
        if purged == 0:
            print("   ✅ Registry is Clean (No Orphans).")
        else:
            print(f"   🧹 Cleanup Complete: {purged} tokens removed.")

    except Exception as e:
        print(f"   ❌ Data Audit Failed: {e}")

def main():
    print("🧹 PhantomArbiter Project Sanitizer")
    print("====================================")
    
    run_rust_audit()
    run_python_audit()
    run_data_audit()
    
    print("\n✨ Sanitization Complete.")

if __name__ == "__main__":
    main()
