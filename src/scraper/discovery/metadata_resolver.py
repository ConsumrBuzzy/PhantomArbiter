"""
V77.0: Metadata Background Resolver
===================================
Resolves "Unknown" tokens by waiting for indexers (DexScreener, Jupiter)
to catch up, then retrying the metadata lookup.

Flow:
1. Token discovered -> Lookup fails -> Add to resolution queue
2. Wait 60 seconds (indexer delay)
3. Retry lookup from TokenScraper
4. If successful -> Log and optionally update Telegram
"""

import time
import threading
from typing import Dict, Optional, Set
from dataclasses import dataclass
from collections import deque
from src.shared.system.logging import Logger


@dataclass
class PendingToken:
    """Token pending metadata resolution."""

    mint: str
    source: str  # e.g., "PUMPFUN", "RAYDIUM"
    discovered_at: float
    retry_at: float
    attempts: int = 0
    is_priority: bool = False  # V85.1: High priority (whales)


class MetadataBackgroundResolver:
    """
    V77.0: Background service that retries metadata resolution.
    V82.0: Added 3-hour permanent fail timeout and multi-source resolution.

    Tokens discovered without names are queued and retried after delay.
    """

    # Resolution Settings
    INITIAL_DELAY = 60  # Wait 60s before first retry
    MAX_ATTEMPTS = 3  # Max retries per token
    RETRY_INTERVAL = 120  # 2 mins between retries
    MAX_QUEUE_SIZE = 100  # Don't queue more than this
    MAX_RESOLUTION_TIME = 10800  # V82.0: 3 hours (10800s) then permanent fail

    def __init__(self):
        self.pending: deque = deque(maxlen=self.MAX_QUEUE_SIZE)
        self.resolved: Dict[str, Dict] = {}  # {mint: {symbol, name, ...}}
        self.failed: Set[str] = set()  # Permanently failed mints

        self.running = False
        self.thread: Optional[threading.Thread] = None

        # Stats
        self.stats = {"queued": 0, "resolved": 0, "failed": 0}

    def start(self):
        """Start the background resolver thread."""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(
            target=self._run_loop, daemon=True, name="MetadataResolver"
        )
        self.thread.start()
        Logger.info("📝 [RESOLVER] Metadata Background Resolver started")

    def stop(self):
        """Stop the resolver."""
        self.running = False

    def queue_token(self, mint: str, source: str = "UNKNOWN"):
        """
        Queue a token for delayed resolution.

        Args:
            mint: Token mint address
            source: Discovery source (PUMPFUN, RAYDIUM, etc.)
        """
        # Skip if already queued, resolved, or failed
        if any(p.mint == mint for p in self.pending):
            return
        if mint in self.resolved:
            return
        if mint in self.failed:
            return

        now = time.time()

        # V85.1: Intelligence Handshake (Prioritize Whale Activity)
        is_priority = "WHALE" in (source or "").upper()
        delay = 5 if is_priority else self.INITIAL_DELAY

        pending = PendingToken(
            mint=mint,
            source=source,
            discovered_at=now,
            retry_at=now + delay,
            is_priority=is_priority,
        )

        if is_priority:
            self.pending.appendleft(pending)  # Front of queue
        else:
            self.pending.append(pending)

        self.stats["queued"] += 1
        Logger.debug(
            f"[RESOLVER] Queued {mint[:8]}... from {source} (Priority: {is_priority}, retry in {delay}s)"
        )

    def _run_loop(self):
        """Main processing loop."""
        while self.running:
            try:
                self._process_pending()
            except Exception as e:
                Logger.debug(f"[RESOLVER] Error: {e}")

            time.sleep(5)  # Check every 5 seconds

    def _process_pending(self):
        """Process tokens ready for resolution."""
        now = time.time()
        to_remove = []

        for pending in self.pending:
            # V82.0: Check 3-hour timeout first
            if now - pending.discovered_at > self.MAX_RESOLUTION_TIME:
                self.failed.add(pending.mint)
                self.stats["failed"] += 1
                to_remove.append(pending)
                Logger.debug(f"[RESOLVER] Timed out (3hr): {pending.mint[:8]}...")
                continue

            if pending.retry_at > now:
                continue  # Not ready yet

            # Try to resolve using multiple sources
            metadata = self._try_resolve_all(pending.mint)

            if (
                metadata
                and metadata.get("symbol")
                and not metadata["symbol"].startswith("UNK_")
            ):
                # Success!
                self.resolved[pending.mint] = metadata
                self.stats["resolved"] += 1
                to_remove.append(pending)

                Logger.info(
                    f"✅ [RESOLVER] Resolved {pending.mint[:8]}: {metadata['symbol']} ({metadata.get('name', '?')}) via {metadata.get('source', '?')}"
                )

                # Optional: Send Telegram update
                self._notify_resolution(pending, metadata)

            else:
                # Failed - schedule retry or mark as failed
                pending.attempts += 1

                if pending.attempts >= self.MAX_ATTEMPTS:
                    self.failed.add(pending.mint)
                    self.stats["failed"] += 1
                    to_remove.append(pending)
                    Logger.debug(
                        f"[RESOLVER] Failed permanently: {pending.mint[:8]}... after {pending.attempts} attempts"
                    )
                else:
                    pending.retry_at = now + self.RETRY_INTERVAL
                    Logger.debug(
                        f"[RESOLVER] Retry scheduled for {pending.mint[:8]}... (attempt {pending.attempts})"
                    )

        # Remove processed items
        for item in to_remove:
            try:
                self.pending.remove(item)
            except ValueError:
                pass

    def _try_resolve_all(self, mint: str) -> Optional[Dict]:
        """
        V82.0: Try multiple sources for token metadata.

        Sources (in order):
        1. TokenScraper (DexScreener)
        2. Jupiter Token List API
        3. Solscan Token Info
        """
        # Source 1: TokenScraper (DexScreener)
        metadata = self._try_dexscreener(mint)
        if (
            metadata
            and metadata.get("symbol")
            and not metadata["symbol"].startswith("UNK_")
        ):
            metadata["source"] = "DexScreener"
            self._add_token_standard(mint, metadata)
            return metadata

        # Source 2: Jupiter Token List
        metadata = self._try_jupiter(mint)
        if metadata and metadata.get("symbol"):
            metadata["source"] = "Jupiter"
            self._add_token_standard(mint, metadata)
            return metadata

        # Source 3: Solscan (if available)
        metadata = self._try_solscan(mint)
        if metadata and metadata.get("symbol"):
            metadata["source"] = "Solscan"
            self._add_token_standard(mint, metadata)
            return metadata

        return None

    def _add_token_standard(self, mint: str, metadata: Dict):
        """V83.0: Detect and add token standard to metadata."""
        try:
            from src.shared.infrastructure.token_standards import (
                get_cached_standard,
                TokenStandard,
            )

            standard = get_cached_standard(mint)
            metadata["token_standard"] = standard.value
            if standard == TokenStandard.TOKEN_2022:
                Logger.debug(f"[RESOLVER] {mint[:8]}... is Token-2022")
        except:
            metadata["token_standard"] = "SPL_TOKEN"  # Default

    def _try_dexscreener(self, mint: str) -> Optional[Dict]:
        """Try DexScreener via TokenScraper."""
        try:
            from src.infrastructure.token_scraper import get_token_scraper

            scraper = get_token_scraper()
            return scraper.lookup(mint)
        except Exception as e:
            Logger.debug(f"[RESOLVER] DexScreener error: {e}")
            return None

    def _try_jupiter(self, mint: str) -> Optional[Dict]:
        """Try Jupiter Token List API."""
        try:
            import requests

            url = "https://token.jup.ag/all"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                tokens = resp.json()
                for token in tokens:
                    if token.get("address") == mint:
                        return {
                            "symbol": token.get("symbol"),
                            "name": token.get("name"),
                            "decimals": token.get("decimals", 9),
                        }
        except Exception as e:
            Logger.debug(f"[RESOLVER] Jupiter error: {e}")
        return None

    def _try_solscan(self, mint: str) -> Optional[Dict]:
        """Try Solscan Token Info API."""
        try:
            import requests

            url = f"https://public-api.solscan.io/token/meta?tokenAddress={mint}"
            headers = {"Accept": "application/json"}
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("symbol"):
                    return {
                        "symbol": data.get("symbol"),
                        "name": data.get("name"),
                        "decimals": data.get("decimals", 9),
                    }
        except Exception as e:
            Logger.debug(f"[RESOLVER] Solscan error: {e}")
        return None

    def _notify_resolution(self, pending: PendingToken, metadata: Dict):
        """Optionally notify via Telegram when a token is resolved."""
        try:
            from src.shared.system.comms_daemon import send_telegram

            symbol = metadata.get("symbol", "???")
            name = metadata.get("name", "Unknown")
            liquidity = metadata.get("liquidity", 0)

            # Only notify if it's a meaningful token
            if liquidity > 500:
                msg = f"📝 *Resolved*: {symbol} ({name})\n"
                msg += f"• Source: {pending.source}\n"
                msg += f"• Liq: ${liquidity:,.0f}\n"
                msg += f"• Delay: {int(time.time() - pending.discovered_at)}s"

                send_telegram(msg, source="RESOLVER", priority="LOW")
        except:
            pass  # Silent fail

    def get_stats(self) -> Dict:
        """Get resolver statistics."""
        return {
            **self.stats,
            "pending": len(self.pending),
            "resolved_total": len(self.resolved),
            "failed_total": len(self.failed),
        }


# Singleton
_resolver = None


def get_metadata_resolver() -> MetadataBackgroundResolver:
    """Get singleton metadata resolver."""
    global _resolver
    if _resolver is None:
        _resolver = MetadataBackgroundResolver()
    return _resolver
