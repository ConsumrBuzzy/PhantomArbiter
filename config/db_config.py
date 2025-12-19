"""
V44.0: Database Configuration
=============================
Environment-aware database backend selection.

Supports:
- SQLite (local development/fallback)
- PostgreSQL + TimescaleDB (production)

Usage:
    Set DB_BACKEND in .env to "sqlite" or "postgres"
    Set DATABASE_URL for PostgreSQL connection string
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ═══════════════════════════════════════════════════════════════════════════
# BACKEND SELECTION
# ═══════════════════════════════════════════════════════════════════════════

DB_BACKEND = os.getenv("DB_BACKEND", "sqlite").lower()  # "sqlite" or "postgres"
POSTGRES_URL = os.getenv("DATABASE_URL", "")

# ═══════════════════════════════════════════════════════════════════════════
# SCHEMA DEFINITIONS (Shared across backends)
# ═══════════════════════════════════════════════════════════════════════════

# SQLite Schema
SQLITE_MARKET_DATA_SCHEMA = """
CREATE TABLE IF NOT EXISTS market_data (
    timestamp REAL NOT NULL,
    token_mint TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume_h1 REAL,
    liquidity_usd REAL,
    latency_ms INTEGER,
    PRIMARY KEY (timestamp, token_mint)
)
"""

# PostgreSQL Schema (with TimescaleDB hypertable support)
POSTGRES_MARKET_DATA_SCHEMA = """
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
"""

# ═══════════════════════════════════════════════════════════════════════════
# CONNECTION SETTINGS
# ═══════════════════════════════════════════════════════════════════════════

# PostgreSQL Pool Settings
PG_POOL_MIN_CONN = 1
PG_POOL_MAX_CONN = 10

# SQLite Settings
SQLITE_DB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "market_data.db"
)


def get_backend_info() -> dict:
    """Get current database backend information."""
    return {
        "backend": DB_BACKEND,
        "postgres_configured": bool(POSTGRES_URL),
        "sqlite_path": SQLITE_DB_PATH if DB_BACKEND == "sqlite" else None,
    }


def validate_config() -> bool:
    """Validate database configuration."""
    if DB_BACKEND == "postgres" and not POSTGRES_URL:
        raise EnvironmentError(
            "DATABASE_URL environment variable is required for PostgreSQL backend.\n"
            "Set DB_BACKEND=sqlite to use local SQLite instead."
        )
    return True
