"""
Database Hydration/Dehydration System
======================================
Portable JSON-based persistence for moving between stations.

Solves the problem of large/corrupted SQLite files in Git by:
1. Exporting all DB data to JSON archives
2. Recreating DB from JSON on boot
3. Keeping JSON files small and Git-friendly

Usage:
    # Export DB to JSON (before committing)
    python -m src.shared.system.db_hydration dehydrate
    
    # Import JSON to DB (after cloning)
    python -m src.shared.system.db_hydration hydrate
    
    # Auto-fix corrupted DB
    python -m src.shared.system.db_hydration fix
"""

import os
import json
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

from src.shared.system.logging import Logger


class DBHydrationManager:
    """
    Manages JSON export/import for SQLite databases.
    
    Architecture:
    - data/*.db → data/json_archives/*.json
    - On boot: Check if DB exists, if not/corrupted → hydrate from JSON
    - On shutdown: Dehydrate to JSON for portability
    """
    
    DATA_DIR = Path("data")
    ARCHIVE_DIR = DATA_DIR / "json_archives"
    
    # Database files to manage
    DB_FILES = [
        "trading_journal.db",
        "arbiter.db",
        "market_data.db",
    ]
    
    def __init__(self):
        self.ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    
    # ═══════════════════════════════════════════════════════════════
    # DEHYDRATION: DB → JSON
    # ═══════════════════════════════════════════════════════════════
    
    def dehydrate_all(self) -> Dict[str, Any]:
        """
        Export all databases to JSON archives.
        
        Returns:
            Summary of dehydration results
        """
        Logger.info("💧 [Dehydration] Starting DB → JSON export...")
        
        # Ensure archive directory exists
        self.ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "databases": {},
            "total_tables": 0,
            "total_rows": 0,
            "errors": []
        }
        
        for db_file in self.DB_FILES:
            db_path = self.DATA_DIR / db_file
            
            if not db_path.exists():
                Logger.debug(f"💧 [Dehydration] Skipping {db_file} (not found)")
                continue
            
            try:
                db_result = self._dehydrate_database(db_path)
                results["databases"][db_file] = db_result
                results["total_tables"] += db_result["tables_exported"]
                results["total_rows"] += db_result["total_rows"]
                
                Logger.success(
                    f"💧 [Dehydration] {db_file}: "
                    f"{db_result['tables_exported']} tables, "
                    f"{db_result['total_rows']} rows"
                )
                
            except Exception as e:
                error_msg = f"Failed to dehydrate {db_file}: {e}"
                results["errors"].append(error_msg)
                Logger.error(f"💧 [Dehydration] {error_msg}")
        
        # Save dehydration manifest
        manifest_path = self.ARCHIVE_DIR / "manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(results, f, indent=2)
        
        Logger.success(
            f"💧 [Dehydration] Complete: "
            f"{results['total_tables']} tables, "
            f"{results['total_rows']} rows exported"
        )
        
        return results
    
    def _dehydrate_database(self, db_path: Path) -> Dict[str, Any]:
        """Export a single database to JSON."""
        db_name = db_path.stem
        archive_path = self.ARCHIVE_DIR / f"{db_name}.json"
        
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = [row[0] for row in cursor.fetchall()]
        
        # Export each table
        archive_data = {
            "database": db_name,
            "exported_at": datetime.now().isoformat(),
            "tables": {}
        }
        
        total_rows = 0
        
        for table in tables:
            try:
                # Get table schema
                cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,))
                schema = cursor.fetchone()[0]
                
                # Get all rows
                cursor.execute(f"SELECT * FROM {table}")
                rows = cursor.fetchall()
                
                # Convert rows to dicts
                rows_data = [dict(row) for row in rows]
                
                archive_data["tables"][table] = {
                    "schema": schema,
                    "row_count": len(rows_data),
                    "rows": rows_data
                }
                
                total_rows += len(rows_data)
                
            except Exception as e:
                Logger.warning(f"💧 [Dehydration] Failed to export table {table}: {e}")
                continue
        
        conn.close()
        
        # Save to JSON
        with open(archive_path, 'w') as f:
            json.dump(archive_data, f, indent=2, default=str)
        
        return {
            "archive_path": str(archive_path),
            "tables_exported": len(archive_data["tables"]),
            "total_rows": total_rows
        }
    
    # ═══════════════════════════════════════════════════════════════
    # HYDRATION: JSON → DB
    # ═══════════════════════════════════════════════════════════════
    
    def hydrate_all(self, force: bool = False) -> Dict[str, Any]:
        """
        Import all databases from JSON archives.
        
        Args:
            force: If True, recreate DBs even if they exist
        
        Returns:
            Summary of hydration results
        """
        Logger.info("🌊 [Hydration] Starting JSON → DB import...")
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "databases": {},
            "total_tables": 0,
            "total_rows": 0,
            "errors": []
        }
        
        for db_file in self.DB_FILES:
            db_path = self.DATA_DIR / db_file
            archive_path = self.ARCHIVE_DIR / f"{db_path.stem}.json"
            
            if not archive_path.exists():
                Logger.debug(f"🌊 [Hydration] Skipping {db_file} (no archive found)")
                continue
            
            # Check if DB exists and is valid
            if db_path.exists() and not force:
                if self._is_db_valid(db_path):
                    Logger.debug(f"🌊 [Hydration] Skipping {db_file} (already exists and valid)")
                    continue
                else:
                    Logger.warning(f"🌊 [Hydration] {db_file} is corrupted, will recreate")
            
            try:
                db_result = self._hydrate_database(db_path, archive_path, force)
                results["databases"][db_file] = db_result
                results["total_tables"] += db_result["tables_imported"]
                results["total_rows"] += db_result["total_rows"]
                
                Logger.success(
                    f"🌊 [Hydration] {db_file}: "
                    f"{db_result['tables_imported']} tables, "
                    f"{db_result['total_rows']} rows"
                )
                
            except Exception as e:
                error_msg = f"Failed to hydrate {db_file}: {e}"
                results["errors"].append(error_msg)
                Logger.error(f"🌊 [Hydration] {error_msg}")
        
        Logger.success(
            f"🌊 [Hydration] Complete: "
            f"{results['total_tables']} tables, "
            f"{results['total_rows']} rows imported"
        )
        
        return results
    
    def _hydrate_database(self, db_path: Path, archive_path: Path, force: bool) -> Dict[str, Any]:
        """Import a single database from JSON."""
        # Backup existing DB if it exists
        if db_path.exists():
            backup_path = db_path.with_suffix(f".db.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            shutil.move(str(db_path), str(backup_path))
            Logger.info(f"🌊 [Hydration] Backed up existing DB to {backup_path.name}")
        
        # Load archive
        with open(archive_path, 'r') as f:
            archive_data = json.load(f)
        
        # Create new DB
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        total_rows = 0
        tables_imported = 0
        
        for table_name, table_data in archive_data["tables"].items():
            try:
                # Create table
                cursor.execute(table_data["schema"])
                
                # Insert rows
                if table_data["rows"]:
                    # Get column names from first row
                    columns = list(table_data["rows"][0].keys())
                    placeholders = ','.join(['?' for _ in columns])
                    insert_sql = f"INSERT INTO {table_name} ({','.join(columns)}) VALUES ({placeholders})"
                    
                    # Batch insert
                    for row in table_data["rows"]:
                        values = [row[col] for col in columns]
                        cursor.execute(insert_sql, values)
                    
                    total_rows += len(table_data["rows"])
                
                tables_imported += 1
                
            except Exception as e:
                Logger.warning(f"🌊 [Hydration] Failed to import table {table_name}: {e}")
                continue
        
        conn.commit()
        conn.close()
        
        return {
            "db_path": str(db_path),
            "tables_imported": tables_imported,
            "total_rows": total_rows
        }
    
    # ═══════════════════════════════════════════════════════════════
    # UTILITIES
    # ═══════════════════════════════════════════════════════════════
    
    def _is_db_valid(self, db_path: Path) -> bool:
        """Check if a database file is valid and not corrupted."""
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            cursor.fetchall()
            conn.close()
            return True
        except Exception:
            return False
    
    def fix_corrupted_dbs(self) -> Dict[str, Any]:
        """
        Auto-fix corrupted databases by hydrating from JSON.
        
        Returns:
            Summary of fixes applied
        """
        Logger.info("🔧 [Fix] Checking for corrupted databases...")
        
        results = {
            "checked": [],
            "corrupted": [],
            "fixed": [],
            "errors": []
        }
        
        for db_file in self.DB_FILES:
            db_path = self.DATA_DIR / db_file
            
            if not db_path.exists():
                continue
            
            results["checked"].append(db_file)
            
            if not self._is_db_valid(db_path):
                results["corrupted"].append(db_file)
                Logger.warning(f"🔧 [Fix] {db_file} is corrupted")
                
                # Try to fix from JSON
                archive_path = self.ARCHIVE_DIR / f"{db_path.stem}.json"
                
                if archive_path.exists():
                    try:
                        self._hydrate_database(db_path, archive_path, force=True)
                        results["fixed"].append(db_file)
                        Logger.success(f"🔧 [Fix] {db_file} restored from JSON")
                    except Exception as e:
                        error_msg = f"Failed to fix {db_file}: {e}"
                        results["errors"].append(error_msg)
                        Logger.error(f"🔧 [Fix] {error_msg}")
                else:
                    error_msg = f"No JSON archive found for {db_file}"
                    results["errors"].append(error_msg)
                    Logger.error(f"🔧 [Fix] {error_msg}")
        
        if results["fixed"]:
            Logger.success(f"🔧 [Fix] Fixed {len(results['fixed'])} corrupted databases")
        elif results["corrupted"]:
            Logger.error(f"🔧 [Fix] {len(results['corrupted'])} corrupted databases could not be fixed")
        else:
            Logger.success("🔧 [Fix] All databases are healthy")
        
        return results
    
    def get_archive_stats(self) -> Dict[str, Any]:
        """Get statistics about JSON archives."""
        stats = {
            "archive_dir": str(self.ARCHIVE_DIR),
            "archives": []
        }
        
        for db_file in self.DB_FILES:
            archive_path = self.ARCHIVE_DIR / f"{Path(db_file).stem}.json"
            
            if archive_path.exists():
                with open(archive_path, 'r') as f:
                    archive_data = json.load(f)
                
                stats["archives"].append({
                    "database": archive_data["database"],
                    "exported_at": archive_data["exported_at"],
                    "tables": len(archive_data["tables"]),
                    "total_rows": sum(t["row_count"] for t in archive_data["tables"].values()),
                    "file_size_mb": archive_path.stat().st_size / (1024 * 1024)
                })
        
        return stats


# ═══════════════════════════════════════════════════════════════
# GLOBAL INSTANCE
# ═══════════════════════════════════════════════════════════════

_manager: Optional[DBHydrationManager] = None


def get_hydration_manager() -> DBHydrationManager:
    """Get or create the global hydration manager."""
    global _manager
    if _manager is None:
        _manager = DBHydrationManager()
    return _manager


# ═══════════════════════════════════════════════════════════════
# CLI INTERFACE
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    
    manager = get_hydration_manager()
    
    if len(sys.argv) < 2:
        print("Usage: python -m src.shared.system.db_hydration [dehydrate|hydrate|fix|stats]")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "dehydrate":
        results = manager.dehydrate_all()
        print(f"\n✅ Dehydrated {results['total_tables']} tables, {results['total_rows']} rows")
        
    elif command == "hydrate":
        force = "--force" in sys.argv
        results = manager.hydrate_all(force=force)
        print(f"\n✅ Hydrated {results['total_tables']} tables, {results['total_rows']} rows")
        
    elif command == "fix":
        results = manager.fix_corrupted_dbs()
        print(f"\n✅ Fixed {len(results['fixed'])} corrupted databases")
        
    elif command == "stats":
        stats = manager.get_archive_stats()
        print("\n📊 Archive Statistics:")
        for archive in stats["archives"]:
            print(f"  {archive['database']}: {archive['tables']} tables, {archive['total_rows']} rows, {archive['file_size_mb']:.2f} MB")
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
