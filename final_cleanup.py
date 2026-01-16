"""
Final Cleanup
=============

Removes all remaining test vaults and shows final state.
"""

from src.shared.state.vault_manager import get_vault_registry
from src.shared.system.persistence import get_db
from src.shared.system.logging import Logger


def final_cleanup():
    """Final cleanup of test vaults."""
    
    Logger.info("=" * 80)
    Logger.info("FINAL VAULT CLEANUP")
    Logger.info("=" * 80)
    Logger.info("")
    
    # Get all vault names
    registry = get_vault_registry()
    names = registry.get_all_vault_names()
    
    Logger.info(f"Current vaults ({len(names)}):")
    for name in names:
        vault = registry.get_vault(name)
        data = vault.get_balances(150.0)
        Logger.info(f"  {name}: ${data['equity']:.2f} - {vault.balances}")
    Logger.info("")
    
    # Delete test vaults
    Logger.info("Deleting test vaults...")
    db = get_db()
    conn = db._get_connection()
    
    test_patterns = [
        "test",
        "test_%",
        "test_engine"
    ]
    
    for pattern in test_patterns:
        count = conn.execute(
            f"DELETE FROM engine_vaults WHERE engine = ? OR engine LIKE ?",
            (pattern, pattern)
        ).rowcount
        if count > 0:
            Logger.info(f"  Deleted {count} vaults matching '{pattern}'")
    
    conn.commit()
    Logger.info("")
    
    # Show final state
    Logger.info("FINAL STATE:")
    names = registry.get_all_vault_names()
    Logger.info(f"Remaining vaults ({len(names)}):")
    
    total = 0.0
    for name in names:
        vault = registry.get_vault(name)
        data = vault.get_balances(150.0)
        equity = data['equity']
        total += equity
        Logger.info(f"  {name}: ${equity:.2f}")
    
    Logger.info("")
    Logger.info(f"Total Equity: ${total:.2f}")
    Logger.info("")
    
    Logger.success("✅ CLEANUP COMPLETE!")


if __name__ == "__main__":
    final_cleanup()
