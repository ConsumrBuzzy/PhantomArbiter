import time
import json
import os
# from src.scout.scraper import TokenScraper
from src.scraper.scout.scraper import TokenScraper
from src.scout.gatekeeper import Gatekeeper
from src.shared.system.logging import Logger
from config.thresholds import (
    HUNTER_INTERVAL_SECONDS,
    MAX_SCOUTS_PER_HUNT,
    SCOUT_EXPIRY_HOURS,
)


class ScoutManager:
    """
    V9.0 Token Hunter Manager.
    Orchestrates the Hunt:
    1. Scrape Candidates
    2. Gatekeep (Security + Profitability)
    3. Update Watchlist
    """

    WATCHLIST_FILE = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../data/watchlist.json")
    )

    def __init__(self):
        self.scraper = TokenScraper()
        self.gatekeeper = Gatekeeper()
        # Use centralized thresholds
        self.poll_interval = HUNTER_INTERVAL_SECONDS
        self.max_scouts_per_hunt = MAX_SCOUTS_PER_HUNT
        self.scout_expiry_hours = SCOUT_EXPIRY_HOURS

    def run_hunt(self):
        """Run a single hunting cycle."""
        Logger.info("[SCOUT] STARTING HUNT cycle...")

        # 1. Scrape
        candidates = self.scraper.get_candidates()
        Logger.info(f"[SCOUT] Found {len(candidates)} candidates")

        # 2. Gatekeep
        accepted = []
        stats_rejected = {"security": 0, "strategy": 0, "other": 0}

        for c in candidates:
            # Skip if already in watchlist (avoid re-checking)
            if self._is_known(c["address"]):
                continue

            is_valid, reason, stats = self.gatekeeper.validate_candidate(
                c["address"], c["symbol"]
            )

            if is_valid:
                Logger.success(f"[SCOUT] ACCEPTED: {c['symbol']} ({reason})")
                accepted.append(c)
                # Limit scouts per cycle
                if len(accepted) >= self.max_scouts_per_hunt:
                    break
            else:
                # V12.10: Tally rejections (Silent Mode)
                if "Security" in reason:
                    stats_rejected["security"] += 1
                elif "Strategy" in reason:
                    stats_rejected["strategy"] += 1
                else:
                    stats_rejected["other"] += 1

        # 3. Update Watchlist
        if accepted:
            self._update_watchlist(accepted)

        # 4. Final Summary (V12.10 Optimization)
        total_rej = sum(stats_rejected.values())
        msg = (
            f"[SCOUT] 🔍 Hunt Cycle Complete: {len(accepted)} Accepted, {total_rej} Rejected "
            f"(Sec: {stats_rejected['security']}, Strat: {stats_rejected['strategy']})"
        )
        Logger.info(msg)

        # V13.3: Ensure visibility in Telegram
        from src.shared.system.comms_daemon import send_telegram

        send_telegram(msg, source="SCOUT", priority="LOW")

        # 4. Prune Old Scouts
        self._prune_watchlist()

    def run_loop(self):
        """Run continuously."""
        Logger.info(f"🔁 Hunter Loop Started (Interval: {self.poll_interval}s)")
        try:
            while True:
                self.run_hunt()
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            Logger.info("🛑 Hunter Stopped")

    def _is_known(self, mint):
        """Check if token is already in watchlist."""
        try:
            with open(self.WATCHLIST_FILE, "r") as f:
                data = json.load(f)

            # Check all categories
            for cat in ["active", "scout", "volatile", "watch"]:
                for sym, info in data.get("assets", {}).items():
                    # Handle both simple mint string (legacy?) or object
                    # Wait, assets.json structure: "WIF": {"mint": "...", ...}
                    # But current settings.py uses it.
                    # Let's check structure.
                    if isinstance(info, dict):
                        if info.get("mint") == mint:
                            return True
                    # Actually settings.py loads it.

            # Check by key (symbol)? No, scrape returns symbol too, but mint is unique.
            return False

        except Exception:
            return False

    def _update_watchlist(self, new_tokens):
        """Add new tokens to watchlist.json."""
        try:
            Logger.info("[SCOUT] Updating Watchlist...")
            with open(self.WATCHLIST_FILE, "r") as f:
                data = json.load(f)

            if "assets" not in data:
                data["assets"] = {}

            for t in new_tokens:
                asset_entry = {
                    "mint": t["address"],
                    "category": "SCOUT",
                    "trading_enabled": False,  # Scouts must verify themselves in Engine first (or Engine monitors them)
                    "description": f"Auto-Scouted from {t.get('source', 'Unknown')}",
                    "added_at": time.time(),
                }
                # Use symbol as key. Ensure unique if collision?
                symbol = t["symbol"]
                if symbol in data["assets"]:
                    symbol = f"{symbol}_{t['address'][:4]}"  # Dedup

                data["assets"][symbol] = asset_entry
                Logger.info(f"       + Added {symbol}")

            with open(self.WATCHLIST_FILE, "w") as f:
                json.dump(data, f, indent=4)

        except Exception as e:
            Logger.error(f"   ❌ Failed to update watchlist: {e}")

    def _prune_watchlist(self):
        """Remove old SCOUT tokens (>48h)."""
        try:
            # Logger.info("   🧹 Pruning Stale Scouts...")
            with open(self.WATCHLIST_FILE, "r") as f:
                data = json.load(f)

            assets = data.get("assets", {})
            to_remove = []

            now = time.time()
            max_age = self.scout_expiry_hours * 3600

            for sym, info in assets.items():
                if info.get("category") == "SCOUT":
                    added_at = info.get("added_at", 0)
                    # If added_at is 0 (legacy), assume safe or give it grace?
                    # If legacy, don't prune.
                    if added_at > 0 and (now - added_at > max_age):
                        to_remove.append(sym)

            if to_remove:
                for sym in to_remove:
                    del assets[sym]
                    Logger.info(f"      - Pruned {sym} (Expired)")

                data["assets"] = assets
                with open(self.WATCHLIST_FILE, "w") as f:
                    json.dump(data, f, indent=4)

        except Exception as e:
            Logger.error(f"   ❌ Failed to prune: {e}")


if __name__ == "__main__":
    manager = ScoutManager()
    manager.run_hunt()  # Single run for test
