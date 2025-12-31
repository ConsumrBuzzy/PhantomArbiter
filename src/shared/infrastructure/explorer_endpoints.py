"""
V77.0: Solana Explorer Endpoints Adapter
========================================
Light-weight adapters for multiple Solana explorers.
No API keys needed for basic token info.

Supported:
- SolanaFM: Token info, transfers (5 req/s free)
- Solscan: Token page scraping (no API)
- Helius: DAS API (with key), RPC
- SolanaBeach: Alternative explorer

Links:
- https://api.solana.fm/v0/tokens/{hash}
- https://solscan.io/token/{mint}
- https://solana.fm/address/{mint}
- https://orb.helius.dev/address/{mint}
"""

import requests
import time
from typing import Dict, Optional, List
from dataclasses import dataclass


@dataclass
class TokenInfo:
    """Standard token info across all sources."""

    mint: str
    symbol: str
    name: str
    decimals: int = 9
    logo: str = ""
    verified: bool = False
    source: str = "UNKNOWN"


class ExplorerEndpoints:
    """
    V77.0: Multi-source Solana explorer adapter.

    Priority:
    1. SolanaFM (free, 5 req/s)
    2. Solscan scrape (no API)
    3. Helius DAS (with key)
    """

    # API Endpoints
    SOLANAFM_TOKEN_URL = "https://api.solana.fm/v0/tokens/{mint}"
    SOLANAFM_TRANSFERS_URL = "https://api.solana.fm/v0/transfers/{hash}"
    SOLSCAN_TOKEN_URL = "https://public-api.solscan.io/token/meta?tokenAddress={mint}"

    # Explorer Links (for UI)
    EXPLORER_LINKS = {
        "solscan": "https://solscan.io/token/{mint}",
        "solanafm": "https://solana.fm/address/{mint}",
        "helius_orb": "https://orb.helius.dev/address/{mint}",
        "solana_explorer": "https://explorer.solana.com/address/{mint}",
        "solanabeach": "https://solanabeach.io/address/{mint}",
    }

    def __init__(self):
        self.last_request = 0
        self.rate_limit = 0.2  # 5 req/s for SolanaFM
        self.cache: Dict[str, TokenInfo] = {}
        self.cache_ttl = 3600  # 1 hour

    def _rate_limit(self):
        """Enforce rate limit."""
        elapsed = time.time() - self.last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self.last_request = time.time()

    def get_token_info(self, mint: str) -> Optional[TokenInfo]:
        """
        Get token info from best available source.

        Priority: Cache -> SolanaFM -> Solscan -> None
        """
        # Check cache
        if mint in self.cache:
            cached = self.cache[mint]
            return cached

        # Try SolanaFM (free, no key)
        info = self._get_from_solanafm(mint)
        if info:
            self.cache[mint] = info
            return info

        # Try Solscan public API
        info = self._get_from_solscan(mint)
        if info:
            self.cache[mint] = info
            return info

        return None

    def _get_from_solanafm(self, mint: str) -> Optional[TokenInfo]:
        """Fetch from SolanaFM (free, 5 req/s)."""
        self._rate_limit()

        try:
            url = self.SOLANAFM_TOKEN_URL.format(mint=mint)
            resp = requests.get(url, timeout=5)

            if resp.status_code == 200:
                data = resp.json()
                token_data = data.get("data", {})

                if token_data:
                    return TokenInfo(
                        mint=mint,
                        symbol=token_data.get("symbol", "???"),
                        name=token_data.get("tokenName", "Unknown"),
                        decimals=token_data.get("decimals", 9),
                        logo=token_data.get("logo", ""),
                        verified=token_data.get("verified", False),
                        source="SOLANAFM",
                    )
        except Exception:
            pass  # Silent fail

        return None

    def _get_from_solscan(self, mint: str) -> Optional[TokenInfo]:
        """Fetch from Solscan public API."""
        self._rate_limit()

        try:
            url = self.SOLSCAN_TOKEN_URL.format(mint=mint)
            resp = requests.get(url, timeout=5)

            if resp.status_code == 200:
                data = resp.json()

                if data:
                    return TokenInfo(
                        mint=mint,
                        symbol=data.get("symbol", "???"),
                        name=data.get("name", "Unknown"),
                        decimals=data.get("decimals", 9),
                        logo=data.get("icon", ""),
                        verified=False,  # Solscan doesn't have this
                        source="SOLSCAN",
                    )
        except Exception:
            pass  # Silent fail

        return None

    def get_transaction_transfers(self, tx_hash: str) -> List[Dict]:
        """
        Get parsed transfers from a transaction (SolanaFM).

        Returns list of {action, source, destination, token, amount}
        """
        self._rate_limit()

        try:
            url = self.SOLANAFM_TRANSFERS_URL.format(hash=tx_hash)
            resp = requests.get(url, timeout=5)

            if resp.status_code == 200:
                data = resp.json()
                return data.get("data", [])
        except Exception:
            pass

        return []

    def get_explorer_links(self, mint: str) -> Dict[str, str]:
        """Generate explorer links for a mint address."""
        return {
            name: url.format(mint=mint) for name, url in self.EXPLORER_LINKS.items()
        }

    def format_explorer_message(self, mint: str, symbol: str = None) -> str:
        """Format explorer links for Telegram message."""
        links = self.get_explorer_links(mint)
        symbol_str = f" ({symbol})" if symbol else ""

        return f"""🔗 *Explorer Links*{symbol_str}
• [Solscan]({links["solscan"]})
• [SolanaFM]({links["solanafm"]})
• [Helius Orb]({links["helius_orb"]})
• [Explorer]({links["solana_explorer"]})
"""


# Singleton instance
_explorer_endpoints = None


def get_explorer_endpoints() -> ExplorerEndpoints:
    """Get singleton explorer endpoints instance."""
    global _explorer_endpoints
    if _explorer_endpoints is None:
        _explorer_endpoints = ExplorerEndpoints()
    return _explorer_endpoints


# Quick test
if __name__ == "__main__":
    explorer = get_explorer_endpoints()

    # Test with SOL (wrapped)
    mint = "So11111111111111111111111111111111111111112"
    info = explorer.get_token_info(mint)
    if info:
        print(f"Token: {info.symbol} ({info.name})")
        print(f"Source: {info.source}")
        print(f"Verified: {info.verified}")

    # Get links
    links = explorer.get_explorer_links(mint)
    print("\nExplorer Links:")
    for name, url in links.items():
        print(f"  {name}: {url}")
