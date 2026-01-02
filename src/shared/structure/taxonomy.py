"""
Unified Token Taxonomy Service
==============================
Single source of truth for token categorization.
Bridges the Strategy Engine (Smart Pods) and Visualization (Galaxy).

Logic Flow:
1. Pod System Check: If token is in a known Pod, inherit that category.
2. Direct Mapping: Check static SYMBOL_CATEGORY_MAP.
3. Keyword Discovery: Heuristic analysis of symbol/tags.
"""

from typing import Optional, List, Dict
from enum import Enum
from src.shared.core.pod_system import pod_system, PodManager

class TokenCategory(str, Enum):
    """Token category classifications."""
    MEME = "MEME"               # WIF, BONK, High Volatility
    AI = "AI"                   # Agents, LLMs
    DEFI = "DEFI"               # Protocols, DEXs
    INFRASTRUCTURE = "INFRA"    # L1s, Oracles, Bridges
    GAMING = "GAMING"           # GameFi, NFT
    STABLECOIN = "STABLE"       # Pegged assets
    LST = "LST"                 # Liquid Staking
    NEW = "NEW"                 # Recent discovery
    UNKNOWN = "UNKNOWN"

# Mapping from Pod Names (Strategy) to Categories (Taxonomy)
POD_TO_CATEGORY: Dict[str, TokenCategory] = {
    "OG_A": TokenCategory.MEME,
    "OG_B": TokenCategory.MEME,
    "VIRAL": TokenCategory.MEME,
    "AI_A": TokenCategory.AI,
    "DEFI_CORE": TokenCategory.DEFI,
    "LST_CORE": TokenCategory.LST,
}

# Substring keywords for heuristic discovery
CATEGORY_KEYWORDS: Dict[TokenCategory, List[str]] = {
    TokenCategory.MEME: [
        "meme", "dog", "cat", "pepe", "wojak", "doge", "shib", "bonk", "wif", 
        "popcat", "fart", "frog", "ape", "moon", "elon", "trump", "biden", "jelly",
        "nub", "mini", "capy", "neiro", "pengu", "griffain", "ploi", "dupe",
        "uranus", "buzz", "freya", "kled", "grass", "io", "oil", "spsc",
    ],
    TokenCategory.AI: [
        "ai", "gpt", "agent", "virtual", "pippin", "sentient", "neural", "bot",
        "intelligence", "machine", "llm", "openai", "giga", "67_9avy",
    ],
    TokenCategory.DEFI: [
        "swap", "amm", "dex", "protocol", "yield", "stake", "lend", "borrow",
        "jup", "jupiter", "ray", "raydium", "orca", "marinade", "drift", "met",
        "ondo", "zeus", "core",
    ],
    TokenCategory.INFRASTRUCTURE: [
        "sol", "pyth", "jto", "jito", "wormhole", "bridge", "oracle", "infra",
        "render", "helium", "hnt", "mobile", "oi1",
    ],
    TokenCategory.GAMING: [
        "game", "nft", "play", "metaverse", "arcade", "star", "atlas", "genopets"
    ],
    TokenCategory.LST: [
        "msol", "bsol", "jitosol", "lst", "liquid", "staking"
    ],
    TokenCategory.STABLECOIN: [
        "usd", "usdc", "usdt", "dai", "stable", "peg"
    ],
}

class TaxonomyService:
    """Service to classify tokens into categories."""

    @staticmethod
    def classify(symbol: str, mint: str = "", tags: Optional[List[str]] = None) -> TokenCategory:
        """
        Classify a token into a category.
        
        Args:
            symbol: Token symbol (e.g., "WIF")
            mint: Token address (optional, for partial checks)
            tags: Known tags (e.g., from scraped data)
            
        Returns:
            TokenCategory
        """
        if not symbol:
            return TokenCategory.UNKNOWN

        symbol_upper = symbol.upper()

        # 1. Strategy check (Pod System is Truth)
        # Check if the token belongs to any known pod
        active_pods = pod_system.get_pods_for_pair(f"{symbol_upper}/USDC") # Heuristic check
        for pod_name in active_pods:
            # Map Pod -> Category
            for p_key, cat in POD_TO_CATEGORY.items():
                if p_key in pod_name:
                    return cat
            
            # Heuristic mapping from Pod Name
            if "MEME" in pod_name or "VIRAL" in pod_name:
                return TokenCategory.MEME
            if "AI" in pod_name:
                return TokenCategory.AI
        
        # 2. Keyword/Heuristic Discovery
        search_text = symbol.lower()
        if tags:
            search_text += " " + " ".join(t.lower() for t in tags)
        
        for cat, keywords in CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in search_text:
                    return cat # Return first match

        # 3. Default fallback
        return TokenCategory.UNKNOWN

# Singleton access
taxonomy = TaxonomyService()
