"""
Token Metadata Persistence Bridge
=================================
Phase 22: Token Memory

Manages the bidirectional flow of Token Metadata between:
1. "Hot" SQLite Cache (TokenRepository)
2. "Cold" JSON Registry (archives/token_registry.json)
"""

import json
import os
import time
from typing import Set
from src.shared.system.logging import Logger
from src.shared.system.database.core import DatabaseCore
from src.shared.system.database.repositories.token_repo import TokenRepository
from src.shared.state.app_state import TokenIdentity, TokenRisk


class TokenRegistry:
    """Archivist for the Token Metadata Library."""

    REGISTRY_PATH = "archives/token_registry.json"

    def __init__(self):
        self.db = DatabaseCore()
        self.repo = TokenRepository(self.db)

    def rehydrate(self) -> int:
        """
        Loads metadata from JSON archive into SQLite.
        Returns count of tokens restored.
        """
        if not os.path.exists(self.REGISTRY_PATH):
            Logger.info("   ℹ️ No Token Registry found. Starting fresh.")
            return 0

        try:
            with open(self.REGISTRY_PATH, "r") as f:
                data = json.load(f)

            tokens = data.get("tokens", [])
            if not tokens:
                return 0

            count = 0
            for t in tokens:
                # Reconstruct Identity
                identity = TokenIdentity(
                    mint=t.get("mint"),
                    symbol=t.get("symbol"),
                    name=t.get("name"),
                    decimals=t.get("decimals", 6),
                    program_id=t.get("program_id"),
                )

                # Reconstruct Risk
                risk_data = t.get("risk", {})
                risk = TokenRisk(
                    mint_authority=risk_data.get("mint_authority"),
                    freeze_authority=risk_data.get("freeze_authority"),
                    is_mutable=risk_data.get("is_mutable", True),
                    safety_score=risk_data.get("safety_score", 0.0),
                )

                self.repo.save_token(identity, risk)
                count += 1

            Logger.info(f"   📚 Token Memory: Restored {count} tokens from registry.")
            return count

        except Exception as e:
            Logger.error(f"❌ Token Rehydration Failed: {e}")
            return 0

    def dehydrate(self) -> bool:
        """
        Saves current SQLite token data to JSON.
        Implements 'Alpha Filter': Only saves tokens with valid symbols.
        """
        try:
            tokens = self.repo.get_all_tokens()

            # Smart Pruning / Alpha Filter
            # 1. Must have a symbol (not empty)
            # 2. (Optional) Could filter by safety score > 0
            filtered_tokens = [
                t for t in tokens if t.get("symbol") and len(t["symbol"]) > 0
            ]

            data = {
                "meta": {
                    "timestamp": time.time(),
                    "count": len(filtered_tokens),
                    "version": "1.0",
                },
                "tokens": filtered_tokens,
            }

            # Atomic Write (write tmp then rename) to prevent corruption
            tmp_path = self.REGISTRY_PATH + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump(data, f, indent=2)

            if os.path.exists(self.REGISTRY_PATH):
                os.remove(self.REGISTRY_PATH)
            os.rename(tmp_path, self.REGISTRY_PATH)

            Logger.info(f"   💾 Token Memory: Archived {len(filtered_tokens)} tokens.")
            return True

        except Exception as e:
            Logger.error(f"❌ Token Dehydration Failed: {e}")
            return False

    def audit_orphans(self, active_mints: Set[str]) -> int:
        """
        Garbage Collection: Deletes tokens that are not part of any active pool.
        Returns the number of tokens purged.
        """
        try:
            # 1. Get all known tokens
            all_tokens = self.repo.get_all_tokens()
            existing_mints = {t["mint"] for t in all_tokens}

            # 2. Identify Orphans (Exist in DB but NOT in active_mints)
            # We must be careful not to delete tokens that might be useful but momentarily disconnected.
            # However, for 'Sanitizer' mode, we assume strict cleanup.

            # Special Case: Always keep USDC/SOL to be safe
            whitelist = {
                "So11111111111111111111111111111111111111112",
                "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
            }

            orphans = existing_mints - active_mints - whitelist

            if not orphans:
                return 0

            # 3. Purge
            count = 0
            with self.repo.db.cursor(commit=True) as c:
                for mint in orphans:
                    c.execute("DELETE FROM tokens WHERE mint = ?", (mint,))
                    count += 1

            Logger.info(f"   🧹 Registry Audit: Purged {count} orphaned tokens.")
            return count

        except Exception as e:
            Logger.error(f"❌ Registry Audit Failed: {e}")
            return 0
