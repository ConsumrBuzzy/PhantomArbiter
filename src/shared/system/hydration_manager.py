"""
Nomad Persistence Bridge (Hydration Manager)
============================================
Phase 19: Nomad Persistence & Hydration

Manages the bidirectional flow of data between the high-performance
local SQLite database (Hot Connection) and portable JSON archives (Cold Storage).

Core Functions:
- Dehydrate: Exports active mission state to a compressed JSON archive.
- Rehydrate: Restores mission state from a JSON archive to the local DB.
- Smart Pruning: Discards ephemeral logs, keeping only financial/audit data.
"""

import os
import json
import time
import glob
from typing import Optional, List, Dict
from datetime import datetime

from src.shared.system.logging import Logger
from src.shared.system.database.core import DatabaseCore
# Phase 22/23: Persistence Bridges
from src.shared.persistence.token_registry import TokenRegistry
from src.shared.persistence.market_manager import MarketManager

class HydrationManager:
    """Refits the ship for new waters by moving cargo between holds."""
    
    ARCHIVE_DIR = "archives"
    
    def __init__(self):
        self.db = DatabaseCore()
        os.makedirs(self.ARCHIVE_DIR, exist_ok=True)
        # Bridges
        self.token_registry = TokenRegistry()
        self.market_manager = MarketManager()

    def _get_connection(self):
        """Get DB connection from Core."""
        return self.db.get_connection()

    def db_exists(self) -> bool:
        """Checks if the Hot DB exists locally."""
        return os.path.exists(self.db.DB_PATH)

    def dehydrate(self, context: dict = None) -> Optional[str]:
        """
        Compresses the current hot database into a JSON archive.
        Applies 'Smart Pruning' to discard noise.
        
        Also triggers Registry Dehydration (Token Memory & Market Map).
        """
        Logger.info("🧊 Initiating Dehydration Protocol...")
        
        # Phase 22 & 23: Registry Sync
        self.token_registry.dehydrate()
        self.market_manager.dehydrate()
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 1. Extract Trades (The Gold)
            # Check if table exists first to avoid crashes on fresh install
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
            if not cursor.fetchone():
                Logger.warning("   ⚠️ No 'trades' table found. Skipping trade export.")
                trades = []
            else:
                cursor.execute("SELECT * FROM trades")
                columns = [description[0] for description in cursor.description]
                trades = [dict(zip(columns, row)) for row in cursor.fetchall()]

            # 2. Extract Session Metadata
            timestamp = int(time.time())
            
            # Phase 21: Privacy Shield - Context Scrubbing
            safe_context = {}
            if context:
                # Handle dataclass or dict
                if hasattr(context, '__dict__'):
                    safe_context = context.__dict__.copy()
                elif isinstance(context, dict):
                    safe_context = context.copy()
                
                # SCRUB SENSITIVE DATA
                if 'wallet_key' in safe_context:
                    safe_context.pop('wallet_key')
                    Logger.info("   🔐 Privacy Shield: Wallet Key scrubbed from archive.")
            
            archive_data = {
                "meta": {
                    "timestamp": timestamp,
                    "date": datetime.now().isoformat(),
                    "context": safe_context,
                    "version": "1.0"
                },
                "stats": {
                    "trade_count": len(trades),
                    # Calculate approximate PnL if possible
                    "net_pnl": sum(t.get('profit_amount', 0) for t in trades) if trades else 0.0
                },
                "ledger": trades,
                # Future: Add snapshots or critical error logs
            }
            
            # 3. Save to Cold Storage
            filename = f"{self.ARCHIVE_DIR}/mission_{timestamp}.json"
            with open(filename, 'w') as f:
                json.dump(archive_data, f, indent=2)
                
            Logger.info(f"   ✅ Dehydration Complete: {filename} ({len(trades)} trades archived)")
            return filename
            
        except Exception as e:
            Logger.error(f"❌ Dehydration Failed: {e}")
            import traceback
            Logger.error(traceback.format_exc())
            return None
        finally:
            if 'conn' in locals():
                conn.close()

    def rehydrate(self, archive_path: str) -> bool:
        """
        Restores a mission state from a JSON archive into the local DB.
        WARNING: This assumes the schema exists.
        
        Also triggers Registry Rehydration (Token Memory & Market Map).
        """
        Logger.info(f"💧 Initiating Rehydration from {archive_path}...")
        
        # Phase 22 & 23: Registry Sync
        self.token_registry.rehydrate()
        self.market_manager.rehydrate()
        
        try:
            with open(archive_path, 'r') as f:
                data = json.load(f)
                
            trades = data.get('ledger', [])
            if not trades:
                Logger.warning("   ⚠️ Archive contains no trades.")
                return True # Technically successful, just nothing to do
            
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 1. Ensure Table Exists
            # We assume the app initialization/repositories handle creation, 
            # but for safety we might check. For now, rely on existing schema.
            
            # 2. Bulk Insert Trades
            # We need to construct the INSERT statement dynamically based on keys
            success_count = 0
            
            cursor.execute("BEGIN TRANSACTION")
            
            for trade in trades:
                keys = list(trade.keys())
                values = list(trade.values())
                placeholders = ', '.join(['?'] * len(keys))
                columns = ', '.join(keys)
                
                sql = f"INSERT OR IGNORE INTO trades ({columns}) VALUES ({placeholders})"
                cursor.execute(sql, values)
                success_count += 1
                
            conn.commit()
            Logger.info(f"   ✅ Rehydration Complete: Restored {success_count} trades.")
            return True
            
        except Exception as e:
            conn.rollback()
            Logger.error(f"❌ Rehydration Failed: {e}")
            return False
        finally:
            if 'conn' in locals():
                conn.close()

    def list_archives(self) -> List[str]:
        """List available mission archives, sorted new to old."""
        files = glob.glob(f"{self.ARCHIVE_DIR}/mission_*.json")
        files.sort(key=os.path.getmtime, reverse=True)
        return files
