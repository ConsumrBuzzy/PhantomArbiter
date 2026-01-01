"""
V133: WatcherManager - Extracted from TacticalStrategy (SRP Refactor)
=================================================================
Encapsulates Watcher lifecycle and position tracking.

Responsibilities:
- Initialize watchers from config
- Ingest discovery tokens into scout watchers
- Reconcile open positions with CapitalManager
- Sync position state to SharedPriceCache
"""

import time
import threading
from typing import Dict, List, Optional

from config.settings import Settings
from src.shared.system.logging import Logger
from src.shared.system.priority_queue import priority_queue
from src.strategy.watcher import Watcher
from src.core.shared_cache import SharedPriceCache


class WatcherManager:
    """
    V133: Manages Watcher lifecycle and position tracking.

    This component was extracted from TacticalStrategy to follow SRP.
    It handles all watcher-related operations including initialization,
    discovery ingestion, and position synchronization.
    """

    def __init__(self, validator, engine_name: str = "PRIMARY"):
        """
        Initialize WatcherManager.

        Args:
            validator: TokenValidator instance for token validation
            engine_name: Identifier for this engine instance
        """
        self.validator = validator
        self.engine_name = engine_name

        # Watcher containers
        self.watchers: Dict[str, Watcher] = {}
        self.scout_watchers: Dict[str, Watcher] = {}
        self.watchlist: List[str] = []
        self._pending_scouts: Dict[str, str] = {}

    def init_watchers(self) -> None:
        """Initialize active watchers from config. V11.4: Scouts deferred to background."""
        active, volatile, watch, scout, all_assets, raw_data, watcher_pairs = (
            Settings.load_assets()
        )

        # V32.1: Legacy Strategy Filtering Removed (V45.5 Unified)
        # All Active assets are loaded for the MerchantEnsemble to manage.

        # V11.4: Active tokens ONLY (P0 critical path - must wait for these)
        for symbol, mint in active.items():
            self.watchers[symbol] = Watcher(
                symbol, mint, validator=self.validator, is_critical=True
            )
            Logger.info(f"   ✅ Watcher Loaded: {symbol}")

        # Store scouts for background init
        self._pending_scouts = scout
        if scout:
            Logger.info(f"⏳ {len(scout)} Scout tokens queued for background init")
            self._start_scout_init_thread()

    def _start_scout_init_thread(self) -> None:
        """Start background thread to initialize scout watchers."""

        def init_scouts_bg():
            time.sleep(2)  # Wait for startup to settle
            for symbol, mint in self._pending_scouts.items():
                if symbol in self.watchers:
                    continue
                # V45.4: Scouts are full watchers but tracked separately
                self.scout_watchers[symbol] = Watcher(
                    symbol, mint, validator=self.validator, is_critical=False
                )
                time.sleep(0.1)  # Don't spam

            priority_queue.add(
                3,
                "LOG",
                {
                    "level": "INFO",
                    "message": f"✅ {len(self.scout_watchers)} Scouts Initialized",
                },
            )

        t = threading.Thread(
            target=init_scouts_bg, daemon=True, name=f"ScoutInit-{self.engine_name}"
        )
        t.start()

    def process_discovery_watchlist(self) -> None:
        """V132: Ingest tokens from discovery watchlist into scout_watchers."""
        if not self.watchlist:
            return

        from src.shared.infrastructure.token_scraper import get_token_scraper

        scraper = get_token_scraper()

        # Limit processing to prevent blocking
        to_process = self.watchlist[:5]
        self.watchlist = self.watchlist[5:]

        for mint in to_process:
            # Skip if already being watched
            all_watchers = {**self.watchers, **self.scout_watchers}
            if any(w.mint == mint for w in all_watchers.values()):
                continue

            info = scraper.lookup(mint)
            symbol = info.get("symbol", f"UNK_{mint[:4]}")

            # Add to scout watchers (Low priority tracking)
            self.scout_watchers[symbol] = Watcher(
                symbol, mint, validator=self.validator, is_critical=False
            )
            Logger.info(
                f"   🔭 [{self.engine_name}] Scout Watcher added: {symbol} ({mint[:8]})"
            )

    def reconcile_open_positions(self) -> None:
        """
        V47.6: Position Reconciliation on Startup.

        Syncs CapitalManager.positions with Watcher.in_position to prevent zombie bags.
        For any position in CapitalManager that doesn't have a matching watcher with
        in_position=True, we either:
        1. Find the watcher and set in_position=True
        2. Create a temporary watcher for the orphaned position
        """
        try:
            from src.shared.system.capital_manager import CapitalManager

            capital = CapitalManager()

            # Get all positions from all engines
            for engine_name in capital.ENGINE_NAMES:
                positions = capital.get_all_positions(engine_name)

                for symbol, pos_data in positions.items():
                    if pos_data.get("balance", 0) <= 0:
                        continue

                    # Try to find existing watcher
                    watcher = self.get_watcher(symbol)

                    if watcher:
                        # Watcher exists - sync state
                        if not watcher.in_position:
                            watcher.in_position = True
                            watcher.entry_price = pos_data.get("avg_price", 0.0)
                            watcher.token_balance = pos_data.get("balance", 0.0)
                            watcher.cost_basis = pos_data.get("size_usd", 0.0)
                            Logger.info(
                                f"   🔄 [{self.engine_name}] Reconciled: {symbol}"
                            )
                    else:
                        # No watcher - create orphan watcher
                        mint = pos_data.get("mint", "")
                        if mint:
                            orphan = Watcher(
                                symbol,
                                mint,
                                validator=self.validator,
                                is_critical=False,
                            )
                            orphan.in_position = True
                            orphan.entry_price = pos_data.get("avg_price", 0.0)
                            orphan.token_balance = pos_data.get("balance", 0.0)
                            orphan.cost_basis = pos_data.get("size_usd", 0.0)
                            self.scout_watchers[symbol] = orphan
                            Logger.warning(
                                f"   ⚠️ [{self.engine_name}] Orphan position recovered: {symbol}"
                            )

        except Exception as e:
            priority_queue.add(
                3,
                "LOG",
                {"level": "ERROR", "message": f"[V47.6] Reconciliation Error: {e}"},
            )

    def sync_active_positions(self) -> None:
        """V12.5: Share active position state with Data Broker."""
        active_list = []

        # Check all watchers (Primary + Scout)
        all_watchers = list(self.watchers.values()) + list(self.scout_watchers.values())

        for watcher in all_watchers:
            if watcher.in_position:
                curr_price = watcher.get_price() or 0.0
                entry_price = watcher.entry_price or 0.0
                cost_basis = watcher.cost_basis or 0.0
                token_balance = watcher.token_balance or 0.0

                if entry_price > 0:
                    pnl_pct = ((curr_price - entry_price) / entry_price) * 100
                    pnl_usd = (curr_price * token_balance) - cost_basis
                else:
                    pnl_pct = 0.0
                    pnl_usd = 0.0

                active_list.append(
                    {
                        "symbol": watcher.symbol,
                        "entry": watcher.entry_price,
                        "current": curr_price,
                        "pnl_pct": pnl_pct,
                        "pnl_usd": pnl_usd,
                        "size_usd": watcher.cost_basis,
                        "timestamp": time.time(),
                    }
                )

        # Write to shared cache
        SharedPriceCache.write_active_positions(active_list)

    # =========================================================================
    # ACCESSORS
    # =========================================================================

    def get_all_watchers(self) -> Dict[str, Watcher]:
        """Get combined dictionary of all watchers (primary + scout)."""
        return {**self.watchers, **self.scout_watchers}

    def get_watcher(self, symbol: str) -> Optional[Watcher]:
        """Get a specific watcher by symbol."""
        if symbol in self.watchers:
            return self.watchers[symbol]
        return self.scout_watchers.get(symbol)

    def add_to_watchlist(self, mint: str) -> None:
        """Add a mint to the discovery watchlist for processing."""
        if mint not in self.watchlist:
            self.watchlist.append(mint)

    def get_active_position_count(self) -> tuple:
        """Return (primary_positions, scout_positions) counts."""
        primary = sum(1 for w in self.watchers.values() if w.in_position)
        scout = sum(1 for w in self.scout_watchers.values() if w.in_position)
        return primary, scout

    def get_total_watcher_count(self) -> int:
        """Return total number of watchers."""
        return len(self.watchers) + len(self.scout_watchers)
