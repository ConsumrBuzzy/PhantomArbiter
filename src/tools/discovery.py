"""
Token Discovery Module
======================
Fetches trending Solana tokens from DexScreener for automated scouting.
"""

import requests
import time
from config.settings import Settings
from src.shared.infrastructure.validator import TokenValidator


class TokenDiscovery:
    """Discovers new tokens from DexScreener trending data."""

    # Rate limiting
    DISCOVERY_COOLDOWN = 600  # 10 minutes between discovery runs
    last_discovery_time = 0

    def __init__(self):
        self.validator = TokenValidator()
        self.discovered_cache = set()  # Avoid re-processing same tokens

    def fetch_trending_solana(self, limit=10):
        """
        Fetch top trending Solana tokens from DexScreener.

        Returns:
            List of dicts: [{symbol, mint, volume_24h, liquidity, price_change}]
        """
        try:
            # DexScreener token boosted/trending endpoint
            url = "https://api.dexscreener.com/token-boosts/top/v1"
            resp = requests.get(url, timeout=10)

            if resp.status_code != 200:
                print(f"   ⚠️ DexScreener API error: {resp.status_code}")
                return []

            data = resp.json()

            # Filter for Solana tokens only
            solana_tokens = []
            for token in data[:50]:  # Check top 50, filter to limit
                if token.get("chainId") == "solana":
                    info = {
                        "symbol": token.get("tokenAddress", "")[
                            :8
                        ],  # Will be resolved later
                        "mint": token.get("tokenAddress"),
                        "url": token.get("url", ""),
                        "description": token.get("description", "")[:50],
                    }
                    solana_tokens.append(info)

                    if len(solana_tokens) >= limit:
                        break

            return solana_tokens

        except Exception as e:
            print(f"   ⚠️ Discovery fetch error: {e}")
            return []

    def fetch_new_pairs(self, min_liquidity=5000, max_age_hours=24):
        """
        Fetch recently created Solana pairs with minimum liquidity.

        Returns:
            List of dicts: [{symbol, mint, liquidity, created_at}]
        """
        try:
            url = "https://api.dexscreener.com/latest/dex/search?q=solana"
            resp = requests.get(url, timeout=10)

            if resp.status_code != 200:
                return []

            data = resp.json()
            new_pairs = []

            current_time = time.time() * 1000  # ms
            max_age_ms = max_age_hours * 3600 * 1000

            for pair in data.get("pairs", [])[:100]:
                if pair.get("chainId") != "solana":
                    continue

                liquidity = float(pair.get("liquidity", {}).get("usd", 0) or 0)
                created_at = pair.get("pairCreatedAt", 0)
                age_ms = current_time - created_at

                if liquidity >= min_liquidity and age_ms <= max_age_ms:
                    base_token = pair.get("baseToken", {})
                    new_pairs.append(
                        {
                            "symbol": base_token.get("symbol", "UNKNOWN"),
                            "mint": base_token.get("address"),
                            "liquidity": liquidity,
                            "volume_24h": float(
                                pair.get("volume", {}).get("h24", 0) or 0
                            ),
                            "price_change_24h": float(
                                pair.get("priceChange", {}).get("h24", 0) or 0
                            ),
                        }
                    )

            return new_pairs[:10]  # Limit results

        except Exception as e:
            print(f"   ⚠️ New pairs fetch error: {e}")
            return []

    def discover_and_validate(self, known_mints: set) -> list:
        """
        Main discovery flow: Fetch trending -> Filter known -> Validate -> Return safe tokens.

        Args:
            known_mints: Set of mint addresses already in assets.json

        Returns:
            List of validated token dicts ready to be added to WATCH
        """
        # Rate limit check
        if time.time() - self.last_discovery_time < self.DISCOVERY_COOLDOWN:
            return []

        self.last_discovery_time = time.time()
        print("   🔭 Running token discovery...")

        # 1. Fetch trending
        trending = self.fetch_trending_solana(limit=5)
        new_pairs = self.fetch_new_pairs(min_liquidity=5000)

        candidates = trending + new_pairs

        # 2. Filter already known
        new_candidates = []
        for token in candidates:
            mint = token.get("mint")
            if mint and mint not in known_mints and mint not in self.discovered_cache:
                new_candidates.append(token)
                self.discovered_cache.add(mint)

        if not new_candidates:
            print("   ✅ No new tokens discovered")
            return []

        print(f"   🔍 Found {len(new_candidates)} new candidates, validating...")

        # 3. Validate each
        validated = []
        for token in new_candidates[:3]:  # Limit to 3 per run (slow/safe)
            mint = token["mint"]
            symbol = token.get("symbol", mint[:6])

            result = self.validator.validate(mint, symbol)

            if result.is_safe:
                # Resolve proper symbol from DexScreener if needed
                resolved_symbol = self._resolve_symbol(mint) or symbol

                validated.append(
                    {
                        "symbol": resolved_symbol,
                        "mint": mint,
                        "liquidity": result.liquidity_usd,
                        "source": "discovery",
                    }
                )
                print(
                    f"   ✅ {resolved_symbol}: SAFE (Liq: ${result.liquidity_usd:,.0f})"
                )
            else:
                print(f"   ⛔ {symbol}: {result.reason}")

        return validated

    def _resolve_symbol(self, mint: str) -> str:
        """Resolve proper symbol from DexScreener."""
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                pairs = data.get("pairs", [])
                if pairs:
                    return pairs[0].get("baseToken", {}).get("symbol", "")
        except:
            pass
        return ""


# CLI for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Token Discovery")
    parser.add_argument(
        "--dry-run", action="store_true", help="Test without adding to assets"
    )
    args = parser.parse_args()

    discovery = TokenDiscovery()

    print("🔭 PHANTOM TRADER - TOKEN DISCOVERY")
    print("=" * 40)

    # Load known mints
    known = set(Settings.ASSETS.values())

    # Discover
    tokens = discovery.discover_and_validate(known)

    print(f"\n📊 Results: {len(tokens)} tokens validated")
    for t in tokens:
        print(f"   {t['symbol']}: {t['mint'][:16]}... (${t['liquidity']:,.0f})")
