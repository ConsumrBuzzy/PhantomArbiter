"""
Sync Vault to $31
==================

Manually syncs the funding vault to $31.56 as shown in Drift UI.
"""

from src.shared.state.vault_manager import get_engine_vault
from src.shared.system.logging import Logger


def sync_to_31():
    """Sync vault to $31.56."""
    
    Logger.info("=" * 80)
    Logger.info("MANUAL VAULT SYNC TO $31.56")
    Logger.info("=" * 80)
    Logger.info("")
    
    # Get funding vault
    vault = get_engine_vault("funding")
    
    Logger.info(f"Current vault: {vault.balances}")
    Logger.info("")
    
    # Clear and set to $31.56
    vault._clear_vault()
    vault.balances = {
        "USDC": 31.56,
        "SOL": 0.0
    }
    vault._save_state()
    
    Logger.success("✅ Vault synced to $31.56 USDC")
    Logger.info("")
    Logger.info(f"New vault: {vault.balances}")
    Logger.info("")
    
    # Verify global snapshot
    from src.shared.state.vault_manager import get_vault_registry
    registry = get_vault_registry()
    snapshot = registry.get_global_snapshot(150.0)
    
    Logger.info("GLOBAL SNAPSHOT:")
    Logger.info(f"  Total Equity: ${snapshot['total_equity']:.2f}")
    Logger.info("")
    
    for name, data in snapshot['vaults'].items():
        Logger.info(f"  {name}: ${data['equity']:.2f}")
    
    Logger.info("")
    Logger.success("✅ Sync complete! Dashboard should now show $31.56")


if __name__ == "__main__":
    sync_to_31()
