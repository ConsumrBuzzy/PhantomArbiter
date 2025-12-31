"""
Pod Engine
==========
Manages smart pod rotation and trading pair definitions.
Extracted from arbiter.py for modularity.
"""

import time
import random
from typing import List

# ═══════════════════════════════════════════════════════════════════
# CONSTANTS & PAIR DEFINITIONS
# ═══════════════════════════════════════════════════════════════════
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOL_MINT = "So11111111111111111111111111111111111111112"

# LOW RISK: Blue chips, high liquidity, tight spreads (0.05-0.3%)
LOW_RISK_PAIRS = [
    ("SOL/USDC", SOL_MINT, USDC_MINT),
    ("JUP/USDC", "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", USDC_MINT),
    ("RAY/USDC", "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R", USDC_MINT),
    ("ORCA/USDC", "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE", USDC_MINT),
]

# MID RISK: Established tokens, moderate volatility, wider spreads possible (0.2-0.8%)
MID_RISK_PAIRS = [
    ("WIF/USDC", "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", USDC_MINT),
    ("BONK/USDC", "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", USDC_MINT),
    ("PYTH/USDC", "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3", USDC_MINT),
    ("JITO/USDC", "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn", USDC_MINT),
    ("HNT/USDC", "hntyVP6YFm1Hg25TN9WGLqM12b8TQmcknKrdu1oxWux", USDC_MINT),
    ("RENDER/USDC", "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof", USDC_MINT),
    ("TNSR/USDC", "TNSRxcUxoT9xBG3de7PiJyTDYu7kskLqcpddxnEJAS6", USDC_MINT),
]

# HIGH RISK: Memes and small caps, volatile, wide spreads (0.5-2%+)
HIGH_RISK_PAIRS = [
    ("SAMO/USDC", "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU", USDC_MINT),
    ("MNGO/USDC", "MangoCzJ36AjZyKwVj3VnYU4GTonjfVEnJmvvWaxLac", USDC_MINT),
    ("FIDA/USDC", "EchesyfXePKdLtoiZSL8pBe8Myagyy8ZRqsACNCFGnvp", USDC_MINT),
    ("STEP/USDC", "StepWBPggCzpZJz6XHjZpJZGZgRZSAmDkCdMX4sWsmc", USDC_MINT),
    ("COPE/USDC", "8HGyAAB1yoM1ttS7pXjHMa3dukTFGQggnFFH3hJZgzQh", USDC_MINT),
]

# ═══════════════════════════════════════════════════════════════════
# SMART PODS: 3 tokens each = 6 pairs per pod for focused scanning
# ═══════════════════════════════════════════════════════════════════

# POD 1: DeFi Core (Deep liquidity DEX tokens)
POD_DEFI_CORE = [
    ("JUP", "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"),  # Jupiter
    ("RAY", "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"),  # Raydium
    ("ORCA", "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE"),  # Orca
]

# POD 2: DeFi Extended (Other DeFi protocols)
POD_DEFI_EXT = [
    ("JITO", "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn"),  # Jito
    ("PYTH", "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3"),  # Pyth Network
    ("W", "85VBFQZC9TZkfaptBWjvUw7YbZjy52A6mjtPGjstQAmQ"),  # Wormhole
]

# POD 3: Infrastructure (Utility tokens)
POD_INFRA = [
    ("RENDER", "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof"),  # Render
    ("HNT", "hntyVP6YFm1Hg25TN9WGLqM12b8TQmcknKrdu1oxWux"),  # Helium
]

# POD 4: OG Memes A (Top established memes)
POD_OG_A = [
    ("BONK", "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"),  # Bonk
    ("WIF", "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"),  # dogwifhat
    ("POPCAT", "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr"),  # Popcat
]

# POD 5: OG Memes B (Other established memes)
POD_OG_B = [
    ("PENGU", "2zMMhcVQEXDtdE6vsFS7S7D5oUodfJHE8vd1gnBouauv"),  # Pudgy Penguins
    ("MOODENG", "ED5nyyWEzpPPiWimP8vYm7sD7TD3LAt3Q3gRTWHzPJBY"),  # Moo Deng
    ("CHILLGUY", "Df6yfrKC8kZE3KNkrHERKzAetSxbrWeniQfyJY4Jpump"),  # TikTok viral
]

# POD 6: Viral/Political (News-driven tokens)
POD_VIRAL = [
    ("PNUT", "2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump"),  # Peanut Squirrel
    ("TRUMP", "6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN"),  # Official Trump
]

# POD 7: AI Narrative A (Top AI tokens)
POD_AI_A = [
    ("GOAT", "CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump"),  # Goatseus Maximus
    ("ACT", "GJAFwWjJ3vnTsrQVabjBVK2TYB1YtRCQXRDfDgUnpump"),  # AI Prophecy
    ("AI16Z", "4ptu2LhxRTERJNJWqnYZ681srxquMBumTHD3XQvDRTjt"),  # AI16Z
]

# POD 8: AI Narrative B (Other AI tokens)
POD_AI_B = [
    ("FARTCOIN", "9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump"),  # Meteora volatility
]

# POD 9: Pump Graduates (High volatility, thin liquidity)
POD_PUMP = [
    ("PIPPIN", "Dfh5DzRgSvvCFDoYc2ciTkMrbDfRKybA4SoFbPmApump"),  # Pippin
    ("FWOG", "A8C3xuqscfmyLrte3VmTqrAq8kgMASius9AFNANwpump"),  # Fwog
    ("GIGA", "8v8GSr4p7Gz8xw6nF22m1LSfSgY7T2nBv2nK3y7f3z6A"),  # Gigachad
]

# POD 10: Direct Pools (Pre-verified Meteora + Orca high-liquidity pools)
# These bypass aggregator routing for atomic execution
POD_DIRECT_POOLS = [
    ("BONK", "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"),  # Orca Whirlpool
    ("WIF", "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"),  # Orca Whirlpool
    ("JITOSOL", "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn"),  # Orca Whirlpool
    ("MSOL", "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So"),  # Orca Whirlpool
]

# All pods for reference
ALL_PODS = {
    "DEFI_CORE": POD_DEFI_CORE,
    "DEFI_EXT": POD_DEFI_EXT,
    "INFRA": POD_INFRA,
    "OG_A": POD_OG_A,
    "OG_B": POD_OG_B,
    "VIRAL": POD_VIRAL,
    "AI_A": POD_AI_A,
    "AI_B": POD_AI_B,
    "PUMP": POD_PUMP,
    "DIRECT_POOLS": POD_DIRECT_POOLS,
}


# Build pairs from all pods
def _build_pairs_from_pods(pods):
    pairs = []
    for pod_tokens in pods:
        for symbol, mint in pod_tokens:
            pairs.append((f"{symbol}/USDC", mint, USDC_MINT))
            pairs.append((f"{symbol}/SOL", mint, SOL_MINT))
    return pairs


# Default: All pods combined
TRENDING_PAIRS = _build_pairs_from_pods(
    [
        POD_DEFI_CORE,
        POD_DEFI_EXT,
        POD_INFRA,
        POD_OG_A,
        POD_OG_B,
        POD_VIRAL,
        POD_AI_A,
        POD_AI_B,
        POD_PUMP,
    ]
)


# Deduplicate pairs to avoid scanning the same token twice
def _dedupe_pairs(pairs):
    seen = set()
    result = []
    for pair in pairs:
        key = (pair[0], pair[1])  # (name, mint)
        if key not in seen:
            seen.add(key)
            result.append(pair)
    return result


# Combined default - all pairs for maximum opportunity scanning (deduplicated)
CORE_PAIRS = _dedupe_pairs(
    LOW_RISK_PAIRS + MID_RISK_PAIRS + HIGH_RISK_PAIRS + TRENDING_PAIRS
)


# ═══════════════════════════════════════════════════════════════════
# POD MANAGER: Smart rotation with priority + random check-ins
# ═══════════════════════════════════════════════════════════════════


class PodManager:
    """
    Manages smart pod rotation for efficient scanning.
    - Tracks priority per pod
    - Promotes/demotes based on results
    - Random check-ins on dormant pods
    - Watch list for promising pairs (WARM status)
    """

    def __init__(self):
        self.pods = ALL_PODS
        self.state = {}
        self.watch_list = {}  # {pair_name: {"added": timestamp, "reason": "WARM"}}
        self._init_state()
        self._scan_count = 0

    def _init_state(self):
        priority = 1
        # Priority order: DIRECT_POOLS first (atomic execution), then OG memes, viral, AI, DeFi, pump, infra
        for name in [
            "DIRECT_POOLS",
            "OG_A",
            "OG_B",
            "VIRAL",
            "AI_A",
            "AI_B",
            "PUMP",
            "DEFI_CORE",
            "DEFI_EXT",
            "INFRA",
        ]:
            self.state[name] = {
                "priority": priority,
                "last_scan": 0,
                "success_count": 0,
                "fail_count": 0,
                "cooldown_until": 0,
            }
            priority += 1

    def add_to_watch(self, pair_name: str, reason: str = "WARM"):
        """Add a pair to watch list - gets included in every scan."""
        self.watch_list[pair_name] = {"added": time.time(), "reason": reason}

    def remove_from_watch(self, pair_name: str):
        """Remove pair from watch list."""
        if pair_name in self.watch_list:
            del self.watch_list[pair_name]

    def get_watch_pairs(self) -> list:
        """Get all watched pairs (for inclusion in every scan)."""
        # Auto-expire after 5 minutes of no action
        expired = [
            p for p, v in self.watch_list.items() if time.time() - v["added"] > 300
        ]
        for p in expired:
            del self.watch_list[p]
        return list(self.watch_list.keys())

    # V91.0: Category Groups for diversity
    CATEGORY_GROUPS = {
        "STABLE": ["DEFI_CORE", "DEFI_EXT", "DIRECT_POOLS"],  # Low-risk, high-liq
        "MEME": ["OG_A", "OG_B", "VIRAL"],  # Established memes
        "META": ["AI_A", "AI_B", "PUMP", "INFRA"],  # Current narrative
    }

    def get_active_pods(self) -> list:
        """
        V91.0: Get pods to scan this cycle with Category Mixing.
        Ensure we scan a mix of STABLE, MEME, and META pods.
        """

        self._scan_count += 1
        now = time.time()

        active = []

        # 1. Pick one high-priority pod from EACH category group
        # This ensures diversity (e.g., JUP + WIF + GOAT)

        for cat_name, pods in self.CATEGORY_GROUPS.items():
            # Filter pods in this category
            cat_pods = [(name, self.state[name]) for name in pods if name in self.state]

            # V131: Time-based rotation
            # Effective priority = base_priority - time_since_last_scan/60
            # This forces rotation even without trades
            def effective_priority(item):
                name, state = item
                base_prio = state["priority"]
                time_since_scan = now - state["last_scan"]
                # Every 60s without scan reduces effective priority by 1
                time_bonus = min(time_since_scan / 60, 5)  # Cap at -5 priority
                return base_prio - time_bonus + random.uniform(0, 0.5)

            cat_pods.sort(key=effective_priority)

            # Pick best available
            for name, state in cat_pods:
                if now > state["cooldown_until"]:
                    active.append(name)
                    state["last_scan"] = now
                    break

        # 2. Wildcard (20% chance): Add one random neglected pod
        if random.random() < 0.2:
            neglected = [n for n in self.state.keys() if n not in active]
            if neglected:
                # Weighted random choice favoring neglected pods (older last_scan)
                neglected.sort(key=lambda n: self.state[n]["last_scan"])
                victim = neglected[0]  # The most neglected
                active.append(victim)
                self.state[victim]["last_scan"] = now

        return active

    def get_pairs_for_pods(self, pod_names: list) -> list:
        """Convert pod names to tradeable pairs."""
        pairs = []
        for name in pod_names:
            if name in self.pods:
                pairs.extend(_build_pairs_from_pods([self.pods[name]]))
        return pairs

    def get_pods_for_pair(self, pair_name: str) -> List[str]:
        """Find all pods that contain the given pair/symbol."""
        symbol = pair_name.split("/")[0]
        found = []
        for pod_name, tokens in self.pods.items():
            for t_symbol, _ in tokens:
                if t_symbol == symbol:
                    found.append(pod_name)
                    break
        return found

    def penalize_pod(self, pod_name: str, duration_sec: int = 120):
        """Penalize a pod for severe execution failures (e.g. quote loss)."""
        if pod_name not in self.state:
            return

        state = self.state[pod_name]
        state["fail_count"] += 1
        state["cooldown_until"] = time.time() + duration_sec
        # Demote priority significantly
        state["priority"] = min(10, state["priority"] + 2)
        self.save_to_db()

    def report_result(
        self, pod_name: str, found_opportunity: bool, executed: bool, success: bool
    ):
        """Update pod state based on scan/execution results."""

        if pod_name not in self.state:
            return

        state = self.state[pod_name]

        if found_opportunity:
            # Promote for finding opportunities
            state["priority"] = max(1, state["priority"] - 1)

            if executed:
                if success:
                    # Jackpot: Major boost
                    state["success_count"] += 1
                    state["fail_count"] = 0
                    state["priority"] = 1  # Instant VIP status
                    # Reward: keep scanning this pod immediately by clearing last_scan
                    # effectively giving it consecutive turns
                    state["last_scan"] = 0
                else:
                    state["fail_count"] += 1
                    state["priority"] = min(10, state["priority"] + 1)

                    # 2 consecutive execution failures = Penalty Box
                    if state["fail_count"] >= 2:
                        state["cooldown_until"] = time.time() + 120  # 2 mins
                        state["fail_count"] = 0
        else:
            # No opportunities - slight demotion to rotate
            state["priority"] = min(8, state["priority"] + 0.5)
            # Short cooldown to force rotation to other pods
            state["cooldown_until"] = time.time() + 15

        # Auto-save after each update
        self.save_to_db()

    def save_to_db(self):
        """Persist current pod state to database."""
        try:
            from src.shared.system.db_manager import db_manager

            for name, state in self.state.items():
                db_manager.save_pod_state(name, state)
        except Exception:
            pass  # Silently fail - non-critical

    def load_from_db(self):
        """Load pod state from database (restores priorities from previous session)."""
        try:
            from src.shared.system.db_manager import db_manager

            saved = db_manager.load_all_pod_states()
            if saved:
                # Merge saved state with current state (keep new pods, restore known)
                for name, saved_state in saved.items():
                    if name in self.state:
                        self.state[name]["priority"] = saved_state["priority"]
                        self.state[name]["success_count"] = saved_state["success_count"]
                        self.state[name]["fail_count"] = saved_state["fail_count"]
                        self.state[name]["best_spread"] = saved_state.get(
                            "best_spread", 0
                        )
                return True
        except Exception:
            pass
        return False

    def get_status(self) -> str:
        """Get current pod status for logging."""
        parts = []
        for name, state in sorted(self.state.items(), key=lambda x: x[1]["priority"]):
            cd = "🔴" if time.time() < state["cooldown_until"] else "🟢"
            parts.append(f"{name}:{state['priority']:.0f}{cd}")
        return " | ".join(parts)


# Global instance
pod_manager = PodManager()
