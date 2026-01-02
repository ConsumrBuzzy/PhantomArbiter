"""
Hierarchical Taxonomy Intelligence
==================================
The "Brain" of the PhantomArbiter.
Provides standardized 3-Tier classification for all tokens.

Architecture:
- Tier 1: Macro-Sector (Galaxy Island Placement)
- Tier 2: Niche/Group (Usage & Strategy)
- Tier 3: Heuristics (Discovery & Inference)
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple
from src.shared.core.pod_system import pod_system

class TokenSector(str, Enum):
    """Tier 1: Macro-Sectors (The Islands)."""
    MEME = "MEME"               # High Volatility, Cultural
    AI = "AI"                   # Agents, Compute, LLM
    DEFI = "DEFI"               # DEX, Lending, Yield
    INFRA = "INFRA"             # L1, Oracle, Bridge, RPC
    RWA = "RWA"                 # Real World Assets, LST
    GAMING = "GAMING"           # GameFi, Metaverse
    STABLE = "STABLE"           # Pegged Assets
    UNKNOWN = "UNKNOWN"         # Unclassified / New

@dataclass
class Classification:
    """Standardized classification result."""
    sector: TokenSector         # Tier 1 (Island)
    niche: str                  # Tier 2 (Sub-group, e.g. "DOG_COIN")
    confidence: float           # 0.0 - 1.0
    source: str                 # "POD", "SYMBOL", "INFERENCE"
    
    def __str__(self):
        return f"[{self.sector.value}/{self.niche}] ({self.source})"

# --- Tier 2: Pod Mappings ---
# Maps specific Pod Names to (Sector, Niche)
POD_MAPPINGS: Dict[str, Tuple[TokenSector, str]] = {
    "OG_A": (TokenSector.MEME, "bluechip_meme"),
    "OG_B": (TokenSector.MEME, "established_meme"),
    "VIRAL": (TokenSector.MEME, "viral_momentum"),
    "AI_A": (TokenSector.AI, "ai_agent"),
    "DEFI_CORE": (TokenSector.DEFI, "dex_aggregator"),
    "LST_CORE": (TokenSector.RWA, "liquid_staking"),
}

# --- Tier 3: Heuristics ---
# Keywords mapping to (Sector, Niche)
KEYWORD_MAPPINGS: List[Tuple[TokenSector, str, List[str]]] = [
    (TokenSector.MEME, "dog_coin", ["dog", "shib", "bonk", "wif", "floki", "puppy"]),
    (TokenSector.MEME, "cat_coin", ["cat", "meow", "purr", "popcat", "mew"]),
    (TokenSector.MEME, "cult_meme", ["pepe", "wojak", "chad", "giga", "mog"]),
    (TokenSector.MEME, "politi_fi", ["trump", "biden", "tremp", "boden", "usa"]),
    
    (TokenSector.AI, "ai_agent", ["ai", "gpt", "agent", "bot", "sentient", "virtual"]),
    (TokenSector.AI, "compute", ["gpu", "render", "compute", "cloud", "depin"]),
    
    (TokenSector.DEFI, "dex", ["swap", "dex", "amm", "exchange", "jup", "ray"]),
    (TokenSector.DEFI, "yield", ["yield", "farm", "stake", "earn"]),
    
    (TokenSector.INFRA, "l1_token", ["sol", "eth", "btc", "layer"]),
    (TokenSector.INFRA, "oracle", ["pyth", "oracle", "price", "data"]),
    
    (TokenSector.RWA, "lst", ["msol", "bsol", "jitosol", "stsol"]),
]

class TaxonomyService:
    """Intelligence provided as a service."""
    
    @staticmethod
    def classify(symbol: str, mint: str = "", tags: Optional[List[str]] = None) -> Classification:
        """
        Classify a token into Sector and Niche.
        """
        if not symbol:
            return Classification(TokenSector.UNKNOWN, "unknown", 0.0, "EMPTY")
            
        symbol_upper = symbol.upper()
        
        # 1. Tier 1: Pod Truth (Primary)
        # Check if the token belongs to any known pod
        active_pods = pod_system.get_pods_for_pair(f"{symbol_upper}/USDC")
        for pod_name in active_pods:
            if pod_name in POD_MAPPINGS:
                sector, niche = POD_MAPPINGS[pod_name]
                return Classification(sector, niche, 1.0, f"POD:{pod_name}")
            
            # Heuristic Pod Match
            if "AI" in pod_name:
                return Classification(TokenSector.AI, "ai_general", 0.9, "POD_HINT")
            if "MEME" in pod_name:
                return Classification(TokenSector.MEME, "meme_general", 0.9, "POD_HINT")

        # 2. Tier 2: Symbol Map (Direct)
        # (Could use a static map here if desired, but skipping to Heuristics for brevity/dynamicism)
        if symbol_upper == "SOL":
            return Classification(TokenSector.INFRA, "native", 1.0, "STATIC")
        if symbol_upper == "USDC" or symbol_upper == "USDT":
            return Classification(TokenSector.STABLE, "fiat_peg", 1.0, "STATIC")
            
        # 3. Tier 3: Inference (Heuristics)
        search_text = symbol.lower()
        if tags:
            search_text += " " + " ".join(t.lower() for t in tags)
            
        for sector, niche, keywords in KEYWORD_MAPPINGS:
            for keyword in keywords:
                if keyword in search_text:
                    return Classification(sector, niche, 0.7, f"KEYWORD:{keyword}")
                    
        # 4. Fallback
        return Classification(TokenSector.UNKNOWN, "uncategorized", 0.0, "FALLBACK")

# Global Instance
taxonomy = TaxonomyService()
