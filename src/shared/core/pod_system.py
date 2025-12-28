"""
Universal Pod System
====================
Shared infrastructure for managing groups of tokens (Pods).
Used by Arbiter, Scalper, and WhaleWatcher.

migrated from src.arbiter.core.pod_engine
"""

import time
import random
from dataclasses import dataclass, field
from typing import Dict, List, Any, Tuple, Optional

# ═══════════════════════════════════════════════════════════════════
# CONSTANTS & PAIR DEFINITIONS
# ═══════════════════════════════════════════════════════════════════
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOL_MINT = "So11111111111111111111111111111111111111112"

# PRE-DEFINED PODS (Legacy Support)
POD_DEFI_CORE = [
    ("JUP", "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"),
    ("RAY", "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"),
    ("ORCA", "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE"),
]

POD_OG_A = [
    ("BONK", "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"),
    ("WIF", "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"),
    ("POPCAT", "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr"),
]

POD_OG_B = [
    ("PENGU", "2zMMhcVQEXDtdE6vsFS7S7D5oUodfJHE8vd1gnBouauv"),
    ("MOODENG", "ED5nyyWEzpPPiWimP8vYm7sD7TD3LAt3Q3gRTWHzPJBY"),
    ("CHILLGUY", "Df6yfrKC8kZE3KNkrHERKzAetSxbrWeniQfyJY4Jpump"),
]

POD_VIRAL = [
    ("PNUT", "2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump"),
    ("TRUMP", "6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN"),
]

POD_AI_A = [
    ("GOAT", "CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump"),
    ("ACT", "GJAFwWjJ3vnTsrQVabjBVK2TYB1YtRCQXRDfDgUnpump"),
    ("AI16Z", "4ptu2LhxRTERJNJWqnYZ681srxquMBumTHD3XQvDRTjt"),
]

# ... we can keep adding more or load dynamically

ALL_NAMED_PODS = {
    "DEFI_CORE": POD_DEFI_CORE,
    "OG_A": POD_OG_A,
    "OG_B": POD_OG_B,
    "VIRAL": POD_VIRAL,
    "AI_A": POD_AI_A,
}

# ═══════════════════════════════════════════════════════════════════
# CORE DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Pod:
    """Represents a group of tokens with shared strategy characteristics."""
    name: str
    tokens: List[Tuple[str, str]] # List of (Symbol, Mint)
    priority: float = 5.0
    tags: List[str] = field(default_factory=list) # e.g. ["MEME", "VOLATILE"]
    smart_sizing_multiplier: float = 1.0 # V28: Smart Sizing (0.5x for risk, 2.0x for conviction)
    
    # Runtime State
    last_scan: float = 0
    success_count: int = 0
    fail_count: int = 0
    cooldown_until: float = 0
    
    def is_active(self) -> bool:
        return time.time() >= self.cooldown_until

    def get_pairs(self) -> List[Tuple[str, str, str]]:
        """Return tradeable pairs for this pod (default USDC & SOL)."""
        pairs = []
        for symbol, mint in self.tokens:
            pairs.append((f"{symbol}/USDC", mint, USDC_MINT))
            pairs.append((f"{symbol}/SOL", mint, SOL_MINT))
        return pairs

# ═══════════════════════════════════════════════════════════════════
# POD BUILDER (Factory)
# ═══════════════════════════════════════════════════════════════════

class PodBuilder:
    """Factory for creating dynamic pods."""
    
    @staticmethod
    def from_named_list(name: str, token_list: List[Tuple[str, str]], tags: List[str] = None) -> Pod:
        # Auto-size based on tags
        multiplier = 1.0
        if tags:
            if "MEME" in tags or "VOLATILE" in tags: multiplier = 0.5
            if "STABLE" in tags or "BLUE_CHIP" in tags: multiplier = 1.5
            
        return Pod(name=name, tokens=token_list, tags=tags or ["STATIC"], smart_sizing_multiplier=multiplier)

    @staticmethod
    def create_smart_money_pod(name: str, tokens: List[Dict], min_score: float = 0.8) -> Pod:
        """Create a pod from Discovery/Scout data."""
        # tokens is list of dicts {symbol, mint, trust_score}
        valid_tokens = []
        for t in tokens:
            if t.get('trust_score', 0) >= min_score:
                valid_tokens.append((t['symbol'], t['mint']))
        
        return Pod(name=name, tokens=valid_tokens, priority=1, tags=["SMART_MONEY", "DYNAMIC"])

    @staticmethod
    def create_momentum_pod(name: str, tickers: List[Dict]) -> Pod:
        """Create pod from high-volume tickers."""
        # tickers: {symbol, mint, volume_24h...}
        valid = [(t['symbol'], t['mint']) for t in tickers]
        return Pod(name=name, tokens=valid, priority=2, tags=["MOMENTUM"])

# ═══════════════════════════════════════════════════════════════════
# POD MANAGER (Shared Singleton)
# ═══════════════════════════════════════════════════════════════════

class PodManager:
    """
    Central registry for all active pods.
    """
    
    def __init__(self):
        self.pods: Dict[str, Pod] = {}
        self._init_defaults()
        
    def _init_defaults(self):
        """Load default static pods."""
        # Legacy mapping (simplified)
        for name, tokens in ALL_NAMED_PODS.items():
            # Heuristic tagging
            tags = ["STATIC"]
            if "OG" in name or "VIRAL" in name: tags.append("MEME")
            if "DEFI" in name: tags.append("STABLE")
            if "AI" in name: tags.append("VOLATILE")
            
            self.pods[name] = PodBuilder.from_named_list(name, tokens, tags=tags)

    def register_pod(self, pod: Pod):
        """Register a new dynamic pod."""
        self.pods[pod.name] = pod
        
    def get_active_pods(self, limit: int = 3) -> List[Pod]:
        """Get best pods to scan based on priority & time."""
        now = time.time()
        candidates = [p for p in self.pods.values() if p.is_active()]
        
        # Effective Priority = Base - TimeBonus + Random
        def score(p: Pod):
            time_bonus = min((now - p.last_scan) / 60.0, 5.0) # Bonus for staying idle
            return p.priority - time_bonus + random.uniform(0, 0.5)
            
        candidates.sort(key=score)
        
        # Mark as scanned
        selected = candidates[:limit]
        for p in selected:
            p.last_scan = now
            
        return selected

    def report_result(self, pod_name: str, success: bool, major_win: bool = False):
        """Feedback loop."""
        if pod_name not in self.pods: return
        
        pod = self.pods[pod_name]
        
        if success:
            pod.success_count += 1
            pod.fail_count = 0
            pod.priority = max(1, pod.priority - 1) # Boost
            if major_win:
                pod.priority = 1 # VIP
                pod.last_scan = 0 # Scan again immediately
        else:
            pod.fail_count += 1
            pod.priority = min(10, pod.priority + 0.5) # Demote
            if pod.fail_count >= 3:
                pod.cooldown_until = time.time() + 300 # 5 min penalty
                pod.fail_count = 0

    def get_status_string(self) -> str:
        """Format status for TUI."""
        # Top 4 by priority
        top = sorted(self.pods.values(), key=lambda p: p.priority)[:4]
        parts = []
        for p in top:
            icon = "🟢" if p.is_active() else "🔴"
            parts.append(f"{p.name}:{p.priority:.1f}{icon}")
        return " | ".join(parts)

    # Helper for legacy Arbiter compatibility
    def get_pods_for_pair(self, pair_name: str) -> List[str]:
        """Find names of pods containing this pair."""
        symbol = pair_name.split('/')[0]
        found = []
        for p in self.pods.values():
            for t_symbol, _ in p.tokens:
                if t_symbol == symbol:
                    found.append(p.name)
                    break
        return found
        
    def get_smart_size_multiplier(self, pair_name: str) -> float:
        """Get the safe trade size multiplier based on the pod."""
        pods = self.get_pods_for_pair(pair_name)
        if not pods: return 1.0
        # Return the most conservative multiplier if in multiple pods (min)
        return min(self.pods[p].smart_sizing_multiplier for p in pods)

    def get_all_pairs(self) -> List[Tuple[str, str, str]]:
        """Get ALL tradeable pairs from ALL pods (deduped)."""
        seen = set()
        pairs = []
        for pod in self.pods.values():
            for p in pod.get_pairs():
                key = (p[0], p[1])
                if key not in seen:
                    seen.add(key)
                    pairs.append(p)
        return pairs

    def inject_priority_token(self, mint: str, symbol: str = "AUTO", tag: str = "PRIORITY"):
        """V33: Inject a token from sensory signals (Whale/Scout) with high priority."""
        pod_name = f"SIGNAL_{tag}_{mint[:4]}"
        if pod_name not in self.pods:
            # Create a dynamic pod for this token
            new_pod = Pod(
                name=pod_name,
                tokens=[(symbol, mint)],
                priority=1.0, # High Priority
                tags=[tag, "DYNAMIC"],
                smart_sizing_multiplier=1.2 # Slightly more conviction
            )
            self.register_pod(new_pod)
            # Ensure it scans immediately
            new_pod.last_scan = 0
            new_pod.cooldown_until = 0
        else:
            # Refresh priority if already exists
            self.pods[pod_name].priority = 1.0
            self.pods[pod_name].last_scan = 0

# Global Instance
pod_system = PodManager()
