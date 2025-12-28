from typing import Optional, Dict, Any
import time
from src.shared.system.database.repositories.base import BaseRepository
from src.shared.state.app_state import TokenIdentity, TokenRisk

class TokenRepository(BaseRepository):
    """
    Handles persistent storage for Token Metadata.
    Stores Tier 1 (Identity) and Tier 2 (Risk) data.
    """

    def init_table(self):
        with self.db.cursor(commit=True) as c:
            c.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                mint TEXT PRIMARY KEY,
                symbol TEXT,
                name TEXT,
                decimals INTEGER,
                program_id TEXT,
                logo_uri TEXT,
                
                -- Risk Data
                mint_authority TEXT,
                freeze_authority TEXT,
                is_mutable BOOLEAN,
                is_renounced BOOLEAN,
                transfer_fee_bps INTEGER,
                safety_score REAL,
                
                last_updated REAL
            )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_tokens_symbol ON tokens(symbol)")

    def save_token(self, identity: TokenIdentity, risk: Optional[TokenRisk] = None):
        """Upsert token metadata."""
        if not identity: return

        # Default risk values if not provided
        if not risk:
            risk = TokenRisk()

        with self.db.cursor(commit=True) as c:
            c.execute("""
            INSERT INTO tokens (
                mint, symbol, name, decimals, program_id, logo_uri,
                mint_authority, freeze_authority, is_mutable, is_renounced, 
                transfer_fee_bps, safety_score, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(mint) DO UPDATE SET
                symbol=excluded.symbol,
                name=excluded.name,
                decimals=excluded.decimals,
                mint_authority=excluded.mint_authority,
                freeze_authority=excluded.freeze_authority,
                is_mutable=excluded.is_mutable,
                safety_score=excluded.safety_score,
                last_updated=excluded.last_updated
            """, (
                identity.mint,
                identity.symbol,
                identity.name,
                identity.decimals,
                identity.program_id,
                identity.logo_uri,
                
                risk.mint_authority,
                risk.freeze_authority,
                risk.is_mutable,
                risk.is_renounced,
                risk.transfer_fee_bps,
                risk.safety_score,
                time.time()
            ))

    def get_token(self, mint: str) -> Optional[Dict[str, Any]]:
        """Retrieve token metadata."""
        row = self._fetchone("SELECT * FROM tokens WHERE mint = ?", (mint,))
        if not row: return None
        
        # Reconstruct objects
        identity = TokenIdentity(
            mint=row['mint'],
            symbol=row['symbol'],
            name=row['name'],
            decimals=row['decimals'],
            program_id=row['program_id'],
            logo_uri=row['logo_uri']
        )
        
        risk = TokenRisk(
            mint_authority=row['mint_authority'],
            freeze_authority=row['freeze_authority'],
            is_mutable=bool(row['is_mutable']),
            is_renounced=bool(row['is_renounced']),
            transfer_fee_bps=row['transfer_fee_bps'],
            safety_score=row['safety_score']
        )
        
        return {
            "identity": identity,
            "risk": risk,
            "last_updated": row['last_updated']
        }
