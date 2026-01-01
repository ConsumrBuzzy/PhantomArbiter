"""
V84.0: Swap Intelligence Module
================================
Scrape-based swap intelligence that extracts wallet and token data
from Solscan without consuming RPC credits.

Flow:
1. WSS detects swap → Queue signature
2. Batch scrape Solscan every few seconds
3. Extract wallet + mints from response
4. Feed to Whale Watcher for tracking
5. Cross-agent broadcast for opportunities
"""

import time
import threading
from collections import deque
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from src.shared.system.logging import Logger


@dataclass
class SwapIntel:
    """Extracted intelligence from a swap transaction."""

    signature: str
    timestamp: float

    # Who
    signer_wallet: str

    # What
    token_in: str  # Mint sold
    token_out: str  # Mint bought

    # How much
    amount_in: float
    amount_out: float

    # Derived
    is_whale: bool = False
    is_known_wallet: bool = False
    dex: str = "UNKNOWN"


class ScrapeIntelligence:
    """
    V84.0: Non-blocking swap intelligence via Solscan scraping.

    Queues signatures from WSS and batch-scrapes for wallet/token data.
    """

    # Configuration
    MAX_QUEUE_SIZE = 500  # Max signatures to queue
    BATCH_SIZE = 10  # Signatures per batch
    SCRAPE_INTERVAL = 3.0  # Seconds between batches
    SOLSCAN_DELAY = 0.5  # Delay between API calls (rate limit)

    # Whale detection thresholds
    WHALE_MIN_USD = 5000  # $5k+ = potential whale

    def __init__(self):
        self.sig_queue: deque = deque(maxlen=self.MAX_QUEUE_SIZE)
        self.processed: Set[str] = set()  # Already processed sigs
        self.running = False
        self.thread: Optional[threading.Thread] = None

        # Stats
        self.stats = {
            "queued": 0,
            "scraped": 0,
            "whales_detected": 0,
            "errors": 0,
            "last_scrape": 0,
        }

        # Whale wallet tracking (fed from Whale Watcher)
        self.known_whale_wallets: Set[str] = set()

        # Intel cache (last N results)
        self.intel_cache: deque = deque(maxlen=100)

    def start(self):
        """Start the scrape intelligence loop."""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(
            target=self._scrape_loop, daemon=True, name="ScrapeIntel"
        )
        self.thread.start()
        Logger.info("🔍 [V84.0] Swap Intelligence started")

    def stop(self):
        """Stop the scraper."""
        self.running = False

    def add_signature(self, signature: str, dex: str = "UNKNOWN"):
        """Queue a signature for scraping."""
        if signature in self.processed:
            return
        if len(signature) < 40:  # Invalid sig
            return

        self.sig_queue.append((signature, dex, time.time()))
        self.stats["queued"] += 1

    def add_known_whale(self, wallet: str):
        """Add a known whale wallet to track."""
        self.known_whale_wallets.add(wallet)

    def _scrape_loop(self):
        """Main scraping loop."""
        while self.running:
            try:
                if len(self.sig_queue) >= self.BATCH_SIZE:
                    batch = []
                    for _ in range(self.BATCH_SIZE):
                        if self.sig_queue:
                            batch.append(self.sig_queue.popleft())

                    # Process batch
                    self._process_batch(batch)
                    self.stats["last_scrape"] = time.time()

            except Exception as e:
                Logger.debug(f"[V84.0] Scrape error: {e}")
                self.stats["errors"] += 1

            time.sleep(self.SCRAPE_INTERVAL)

    def _process_batch(self, batch: List[tuple]):
        """Process a batch of signatures."""
        for sig, dex, queued_at in batch:
            try:
                intel = self._scrape_signature(sig, dex)
                if intel:
                    self.intel_cache.append(intel)
                    self.processed.add(sig)
                    self.stats["scraped"] += 1

                    # Check for whale
                    if intel.is_whale or intel.is_known_wallet:
                        self.stats["whales_detected"] += 1
                        self._broadcast_whale_signal(intel)

            except Exception as e:
                Logger.debug(f"[V84.0] Sig {sig[:8]} error: {e}")

            time.sleep(self.SOLSCAN_DELAY)  # Rate limit

    def _scrape_signature(self, signature: str, dex: str) -> Optional[SwapIntel]:
        """Scrape a single transaction from Solscan using SmartScraper."""
        try:
            # V84.1: Use SmartScraper with Cloudflare bypass
            from src.infrastructure.smart_scraper import get_smart_scraper

            scraper = get_smart_scraper()

            url = f"https://public-api.solscan.io/transaction/{signature}"
            result = scraper.scrape(url, timeout=10)

            if not result.success:
                if result.status_code == 429:
                    Logger.debug("[V84.0] Solscan rate limit - backing off")
                    time.sleep(5)
                return None

            data = result.data
            if not isinstance(data, dict):
                return None

            # Extract signer
            signer = (
                data.get("signer", [""])[0]
                if isinstance(data.get("signer"), list)
                else data.get("signer", "")
            )

            # Extract token changes
            token_in = ""
            token_out = ""
            amount_in = 0.0
            amount_out = 0.0

            # Check tokenBalances for changes
            token_balances = data.get("tokenBalances", []) or []
            for tb in token_balances:
                change = tb.get("amount", {})
                if isinstance(change, dict):
                    pre = float(change.get("preBalance", 0) or 0)
                    post = float(change.get("postBalance", 0) or 0)
                    delta = post - pre
                else:
                    delta = float(change or 0)

                mint = tb.get("mint", "")
                if delta > 0:
                    token_out = mint
                    amount_out = delta
                elif delta < 0:
                    token_in = mint
                    amount_in = abs(delta)

            # Check if whale
            is_whale = False
            is_known = signer in self.known_whale_wallets

            # Rough USD estimate (would need price lookup)
            # For now, just mark large token amounts
            if amount_out > 1000000 or amount_in > 1000000:  # 1M+ tokens
                is_whale = True

            return SwapIntel(
                signature=signature,
                timestamp=time.time(),
                signer_wallet=signer,
                token_in=token_in,
                token_out=token_out,
                amount_in=amount_in,
                amount_out=amount_out,
                is_whale=is_whale,
                is_known_wallet=is_known,
                dex=dex,
            )

        except Exception as e:
            Logger.debug(f"[V84.0] Scrape error: {e}")
            return None

    def _broadcast_whale_signal(self, intel: SwapIntel):
        """
        V85.1: Broadcast whale detection to other agents with cross-talk.

        Agent Handshake Flow:
        1. Log whale detection
        2. Prioritize MetadataResolver (whale vouch)
        3. Trigger Scout audit
        4. Store vouch for confidence bonus
        """

        Logger.info(
            f"🐋 [V84.0] WHALE: {intel.signer_wallet[:8]}... bought {intel.token_out[:8]}... on {intel.dex}"
        )

        # V85.1: Store vouch for this token (used by consensus engine)
        self._register_whale_vouch(intel.token_out)

        # Queue for MetadataResolver with HIGH PRIORITY (whale vouch)
        try:
            from src.core.scout.discovery.metadata_resolver import get_metadata_resolver

            resolver = get_metadata_resolver()
            if intel.token_out:
                # V85.1: Prioritize whale-spotted tokens
                resolver.queue_token(intel.token_out, source=f"WHALE-{intel.dex}")
                Logger.debug(
                    f"[V85.1] MetadataResolver: Prioritizing {intel.token_out[:8]}... (whale vouch)"
                )
        except:
            pass

        # Feed to Scout Agent for OFI analysis
        try:
            scout = get_scout_agent()
            if scout and hasattr(scout, "trigger_audit"):
                # Async trigger in thread
                import asyncio

                def run_trigger():
                    try:
                        asyncio.run(scout.trigger_audit(intel.token_out))
                    except:
                        pass

                t = threading.Thread(target=run_trigger, daemon=True)
                t.start()
        except:
            pass

    def _register_whale_vouch(self, mint: str):
        """V85.1: Register a whale vouch for confidence bonus."""
        if not hasattr(self, "whale_vouches"):
            self.whale_vouches: Dict[str, float] = {}
        self.whale_vouches[mint] = time.time()

    def has_whale_vouch(self, mint: str, max_age: int = 300) -> bool:
        """
        V85.1: Check if a token has recent whale activity.

        Args:
            mint: Token mint address
            max_age: Max seconds since vouch (default 5 min)

        Returns:
            True if whale vouched for this token recently
        """
        if not hasattr(self, "whale_vouches"):
            return False
        vouch_time = self.whale_vouches.get(mint, 0)
        return time.time() - vouch_time < max_age

    def get_stats(self) -> Dict:
        """Get intelligence stats."""
        return {
            **self.stats,
            "queue_size": len(self.sig_queue),
            "cache_size": len(self.intel_cache),
            "known_whales": len(self.known_whale_wallets),
        }

    def get_recent_intel(self, limit: int = 10) -> List[SwapIntel]:
        """Get recent intel entries."""
        return list(self.intel_cache)[-limit:]


# Singleton
_scrape_intel = None


def get_scrape_intelligence() -> ScrapeIntelligence:
    """Get singleton scrape intelligence instance."""
    global _scrape_intel
    if _scrape_intel is None:
        _scrape_intel = ScrapeIntelligence()
    return _scrape_intel
