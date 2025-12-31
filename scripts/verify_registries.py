"""
Verify Persistence Registries
=============================
Phase 22/23 Verification Script

Objectives:
1. Populate 'Hot' SQLite DB with Mock Tokens & Pools.
2. Trigger Dehydration (Save to JSON).
3. Force Nuke of 'Hot' DB.
4. Trigger Rehydration (Restore from JSON).
5. Verify Tokens and Pools exist in restored DB.
"""

import sys
import os
import shutil
import time

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.shared.system.hydration_manager import HydrationManager
from src.shared.system.database.core import DatabaseCore
from src.shared.state.app_state import TokenIdentity, TokenRisk

DB_PATH = DatabaseCore.DB_PATH

def run_verify():
    print("🕵️ Starting Persistence Registry Verification...")
    
    # 0. Setup: Clean Slate
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    
    manager = HydrationManager()
    
    # Initialize Repos (Tables)
    print("   🔨 Initializing Tables...")
    manager.token_registry.repo.init_table()
    manager.market_manager.repo.init_table()
    
    # 1. Populate Hot DB
    print("   🌱 Seeding Mock Data...")
    
    # Token: 'MOCK'
    mock_token = TokenIdentity(
        mint="MockMintAddress123456789",
        symbol="MOCK",
        name="Mock Token",
        decimals=6,
        program_id="Tokenkeg..."
    )
    manager.token_registry.repo.save_token(mock_token)
    
    # Pool: 'MOCK/USDC' - High Liquidity (Should Persist)
    manager.market_manager.repo.save_pool(
        address="MockPoolAddress123",
        token_a="MockMintAddress123456789",
        token_b="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", # USDC
        dex_label="Raydium",
        liquidity_usd=50000.0,
        vol_24h=12000.0
    )
    
    # Pool: 'DUST/SOL' - Low Liquidity (Should be Pruned)
    manager.market_manager.repo.save_pool(
        address="DustPoolAddress456",
        token_a="DustMint", 
        token_b="So11111111111111111111111111111111111111112",
        dex_label="Orca",
        liquidity_usd=10.0, # < $500 threshold
        vol_24h=5.0
    )
    
    print("   ✅ Seed Complete.")
    
    # 2. Dehydrate
    print("   🧊 Dehydrating...")
    manager.dehydrate()
    
    # 3. NUKE DB
    print("   💣 NUKING DATABASE (Simulating Station Move)...")
    manager.db.get_connection().close()
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print("      - DB File Deleted.")
        
    # 4. Rehydrate
    print("   💧 Rehydrating (New Station)...")
    # Re-init manager to get fresh DB connection
    new_manager = HydrationManager()
    
    # Ensure tables exist (normally app startup does this)
    new_manager.token_registry.repo.init_table()
    new_manager.market_manager.repo.init_table()
    
    # Find latest archive to pass to rehydrate (even though registers are separate)
    # Registry methods are called inside rehydrate().
    # We can just call registry.rehydrate() directly or via manager.rehydrate().
    # manager.rehydrate checks for mission archives, but registers are global.
    # So we call manager.rehydrate BUT we need a dummy mission archive path if we use that signature
    # OR we rely on the fact that manager.rehydrate() calls self.token_registry.rehydrate() unconditionally.
    # Actually, verify logic:
    # rehydrate(archive_path) -> calls registries -> calls mission load.
    # So we need a dummy mission archive?
    # Actually, wait. dehydrate() created a mission archive too.
    archives = new_manager.list_archives()
    if archives:
        new_manager.rehydrate(archives[0])
    else:
        print("   ❌ No Mission Archive found implicitly.")
        
    # 5. Verify Content
    print("   🔍 Verifying Content...")
    
    # Check Token
    token = new_manager.token_registry.repo.get_token("MockMintAddress123456789")
    if token and token['identity'].symbol == "MOCK":
        print("   ✅ Token Restored: MOCK")
    else:
        print("   ❌ Token MOCK Missing!")
        
    # Check Pools
    pools = new_manager.market_manager.repo.get_all_pools()
    pool_dict = {p['address']: p for p in pools}
    
    if "MockPoolAddress123" in pool_dict:
        print("   ✅ High-Liq Pool Restored.")
    else:
        print("   ❌ High-Liq Pool Missing!")
        
    if "DustPoolAddress456" not in pool_dict:
        print("   ✅ Dust Pool Pruned (Correct).")
    else:
        print("   ❌ Dust Pool Persisted (Failed Pruning)!")
        
    print("\n   🎉 Verification Complete.")

if __name__ == "__main__":
    run_verify()
