#!/usr/bin/env python3
"""
V44.0: SQLite to PostgreSQL Migration Script
=============================================
One-time migration of market_data.db to PostgreSQL/TimescaleDB.

Features:
- Batch transfers for efficiency
- Progress tracking
- Validation of migrated data
- Resume capability (skips existing records)

Prerequisites:
1. PostgreSQL server running with TimescaleDB extension
2. DATABASE_URL set in .env
3. pip install psycopg2-binary

Usage:
    python scripts/migrate_to_postgres.py [--batch-size 5000] [--validate]
"""

import os
import sys
import time
import argparse
import sqlite3
from datetime import datetime
from typing import Tuple

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

try:
    import psycopg2
    from psycopg2.extras import execute_batch
except ImportError:
    print("❌ psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

SQLITE_PATH = os.path.join(PROJECT_ROOT, "data", "market_data.db")
DEFAULT_BATCH_SIZE = 5000


def get_postgres_url() -> str:
    """Get PostgreSQL URL from environment."""
    from dotenv import load_dotenv

    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise EnvironmentError(
            "DATABASE_URL not set in .env\n"
            "Format: postgresql://user:password@host:port/dbname"
        )
    return url


# ═══════════════════════════════════════════════════════════════════════════
# MIGRATION LOGIC
# ═══════════════════════════════════════════════════════════════════════════


def get_sqlite_stats(sqlite_path: str) -> dict:
    """Get statistics from SQLite database."""
    if not os.path.exists(sqlite_path):
        return {"exists": False, "rows": 0}

    conn = sqlite3.connect(sqlite_path)
    cursor = conn.execute("SELECT COUNT(*) FROM market_data")
    row_count = cursor.fetchone()[0]

    cursor = conn.execute("SELECT COUNT(DISTINCT token_mint) FROM market_data")
    token_count = cursor.fetchone()[0]

    cursor = conn.execute("SELECT MIN(timestamp), MAX(timestamp) FROM market_data")
    min_ts, max_ts = cursor.fetchone()

    conn.close()

    return {
        "exists": True,
        "rows": row_count,
        "tokens": token_count,
        "min_timestamp": min_ts,
        "max_timestamp": max_ts,
        "date_range": f"{datetime.fromtimestamp(min_ts)} to {datetime.fromtimestamp(max_ts)}"
        if min_ts
        else "N/A",
    }


def get_postgres_row_count(pg_url: str) -> int:
    """Get current row count in PostgreSQL."""
    try:
        conn = psycopg2.connect(pg_url)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM market_data")
        count = cur.fetchone()[0]
        conn.close()
        return count
    except psycopg2.Error:
        return 0


def migrate_data(
    sqlite_path: str,
    pg_url: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
    resume: bool = True,
) -> Tuple[int, int]:
    """
    Migrate data from SQLite to PostgreSQL.

    Args:
        sqlite_path: Path to SQLite database
        pg_url: PostgreSQL connection URL
        batch_size: Records per batch insert
        resume: Skip records that already exist

    Returns:
        (total_migrated, total_skipped)
    """
    print(f"\n📤 Opening SQLite: {sqlite_path}")
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_cursor = sqlite_conn.cursor()

    print("📥 Connecting to PostgreSQL...")
    pg_conn = psycopg2.connect(pg_url)
    pg_cursor = pg_conn.cursor()

    # Ensure schema exists
    pg_cursor.execute("""
        CREATE TABLE IF NOT EXISTS market_data (
            timestamp TIMESTAMPTZ NOT NULL,
            token_mint TEXT NOT NULL,
            open DOUBLE PRECISION,
            high DOUBLE PRECISION,
            low DOUBLE PRECISION,
            close DOUBLE PRECISION,
            volume_h1 DOUBLE PRECISION,
            liquidity_usd DOUBLE PRECISION,
            latency_ms INTEGER,
            PRIMARY KEY (timestamp, token_mint)
        )
    """)
    pg_conn.commit()

    # Get total rows for progress
    sqlite_cursor.execute("SELECT COUNT(*) FROM market_data")
    total_rows = sqlite_cursor.fetchone()[0]
    print(f"📊 Total rows to migrate: {total_rows:,}")

    # Fetch all data in batches
    sqlite_cursor.execute("""
        SELECT timestamp, token_mint, open, high, low, close, volume_h1, liquidity_usd, latency_ms
        FROM market_data
        ORDER BY timestamp ASC
    """)

    migrated = 0
    skipped = 0
    batch = []
    start_time = time.time()

    while True:
        rows = sqlite_cursor.fetchmany(batch_size)
        if not rows:
            break

        # Convert Unix timestamp to datetime for PostgreSQL
        pg_rows = []
        for row in rows:
            ts = datetime.utcfromtimestamp(row[0])
            pg_rows.append(
                (ts, row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8])
            )

        try:
            execute_batch(
                pg_cursor,
                """
                INSERT INTO market_data 
                (timestamp, token_mint, open, high, low, close, volume_h1, liquidity_usd, latency_ms)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (timestamp, token_mint) DO NOTHING
            """,
                pg_rows,
            )

            pg_conn.commit()
            migrated += len(pg_rows)

            # Progress update
            pct = (migrated / total_rows) * 100
            elapsed = time.time() - start_time
            rate = migrated / elapsed if elapsed > 0 else 0
            eta = (total_rows - migrated) / rate if rate > 0 else 0

            print(
                f"\r   ⏳ Progress: {migrated:,}/{total_rows:,} ({pct:.1f}%) | {rate:.0f} rows/s | ETA: {eta:.0f}s  ",
                end="",
                flush=True,
            )

        except psycopg2.Error as e:
            print(f"\n   ⚠️ Batch error: {e}")
            pg_conn.rollback()
            skipped += len(pg_rows)

    print("\n\n✅ Migration complete!")
    print(f"   Migrated: {migrated:,}")
    print(f"   Skipped: {skipped:,}")
    print(f"   Duration: {time.time() - start_time:.1f}s")

    sqlite_conn.close()
    pg_conn.close()

    return migrated, skipped


def validate_migration(sqlite_path: str, pg_url: str) -> bool:
    """Validate that PostgreSQL has same data as SQLite."""
    print("\n🔍 Validating migration...")

    sqlite_stats = get_sqlite_stats(sqlite_path)
    pg_count = get_postgres_row_count(pg_url)

    print(f"   SQLite rows: {sqlite_stats['rows']:,}")
    print(f"   PostgreSQL rows: {pg_count:,}")

    if pg_count >= sqlite_stats["rows"]:
        print("   ✅ Validation PASSED - All data migrated")
        return True
    else:
        diff = sqlite_stats["rows"] - pg_count
        print(f"   ⚠️ Validation WARNING - Missing {diff:,} rows")
        return False


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(description="V44.0 SQLite to PostgreSQL Migration")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Records per batch (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--validate", action="store_true", help="Validate migration after completion"
    )
    parser.add_argument(
        "--stats-only", action="store_true", help="Only show statistics, do not migrate"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("V44.0: SQLite to PostgreSQL Migration")
    print("=" * 60)

    # Check SQLite
    sqlite_stats = get_sqlite_stats(SQLITE_PATH)
    if not sqlite_stats["exists"]:
        print(f"\n❌ SQLite database not found: {SQLITE_PATH}")
        return 1

    print("\n📊 Source: SQLite")
    print(f"   Path: {SQLITE_PATH}")
    print(f"   Rows: {sqlite_stats['rows']:,}")
    print(f"   Tokens: {sqlite_stats['tokens']:,}")
    print(f"   Date Range: {sqlite_stats['date_range']}")

    # Get PostgreSQL URL
    try:
        pg_url = get_postgres_url()
        print("\n📊 Target: PostgreSQL")
        print(f"   URL: {pg_url[:30]}...")
        print(f"   Existing Rows: {get_postgres_row_count(pg_url):,}")
    except EnvironmentError as e:
        print(f"\n❌ {e}")
        return 1

    if args.stats_only:
        return 0

    # Confirm
    print("\n" + "=" * 60)
    response = input("Proceed with migration? [y/N]: ")
    if response.lower() != "y":
        print("Migration cancelled.")
        return 0

    # Migrate
    migrated, skipped = migrate_data(SQLITE_PATH, pg_url, args.batch_size)

    # Validate
    if args.validate:
        validate_migration(SQLITE_PATH, pg_url)

    print("\n" + "=" * 60)
    print("Migration Complete!")
    print("=" * 60)
    print("\n📝 Next Steps:")
    print("   1. Set DB_BACKEND=postgres in .env")
    print("   2. Restart all engines")
    print("   3. Monitor logs for PostgreSQL connections")

    return 0


if __name__ == "__main__":
    sys.exit(main())
