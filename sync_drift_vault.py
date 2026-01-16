"""
Sync Drift Vault
=================

Syncs the funding engine vault from your actual Drift account.
"""

import asyncio
from src.shared.state.vault_manager import get_engine_vault
from src.engines.funding.drift_adapter import DriftAdapter
from src.drivers.wallet_manager import WalletManager
from src.shared.system.logging import Logger


async def sync_vault():
    """Sync vault from Drift account."""
    
    Logger.info("=" * 80)
    Logger.info("SYNCING VAULT FROM DRIFT")
    Logger.info("=" * 80)
    Logger.info("")
    
    # Get the funding engine vault
    vault = get_engine_vault("funding")
    
    Logger.info(f"Current vault balances:")
    for asset, balance in vault.balances.items():
        Logger.info(f"  {asset}: {balance}")
    Logger.info("")
    
    # Create Drift adapter
    adapter = DriftAdapter(network="mainnet")
    wallet_manager = WalletManager()
    
    # Connect
    success = await adapter.connect(wallet_manager, sub_account=0)
    
    if not success:
        Logger.error("Failed to connect to Drift")
        return
    
    Logger.info("Connected to Drift, fetching account state...")
    
    # Get account state
    state = await adapter.get_account_state()
    
    Logger.info(f"Drift Account State:")
    Logger.info(f"  Collateral: ${state['collateral']:.2f}")
    Logger.info(f"  Health: {state['health_ratio']:.2f}%")
    Logger.info(f"  Leverage: {state['leverage']:.2f}x")
    Logger.info("")
    
    # Sync vault
    Logger.info("Syncing vault...")
    
    # Clear existing balances
    vault._clear_vault()
    
    # Set new balances based on Drift account
    # The collateral is in USD (mostly USDC)
    vault.balances = {
        "USDC": state['collateral'],
        "SOL": 0.0
    }
    
    vault._save_state()
    
    Logger.info("Vault synced!")
    Logger.info(f"New vault balances:")
    for asset, balance in vault.balances.items():
        Logger.info(f"  {asset}: {balance}")
    Logger.info("")
    
    await adapter.disconnect()
    
    Logger.success("✅ Vault sync complete!")


if __name__ == "__main__":
    asyncio.run(sync_vault())
