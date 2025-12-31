"""
V84.1: Smart Scraper Infrastructure
====================================
Generalized scraping system with Cloudflare bypass capabilities.

Uses curl_cffi to impersonate real Chrome browser TLS fingerprint,
bypassing Cloudflare's bot detection.

Features:
- TLS fingerprint impersonation (Chrome 110+)
- Rate limiting (configurable per-domain)
- Retry with exponential backoff
- Response caching
"""

import time
import threading
from typing import Dict, Optional, Any
from dataclasses import dataclass
from src.shared.system.logging import Logger


@dataclass
class ScrapeResult:
    """Result from a scrape operation."""

    success: bool
    url: str
    status_code: int
    data: Optional[Any] = None
    error: Optional[str] = None
    scraped_at: float = 0.0


class SmartScraper:
    """
    V84.1: Generalized scraper with Cloudflare bypass.

    Uses curl_cffi for TLS fingerprint impersonation.
    Falls back to standard requests if curl_cffi unavailable.
    """

    # Rate limits per domain (requests per minute)
    RATE_LIMITS = {
        "solscan.io": 30,  # 30/min = 1 every 2 seconds
        "api.solscan.io": 30,
        "dexscreener.com": 300,  # Generous
        "jup.ag": 60,
    }

    DEFAULT_RATE_LIMIT = 60  # 1 per second

    def __init__(self):
        self.last_request_time: Dict[str, float] = {}
        self.request_counts: Dict[str, int] = {}
        self.lock = threading.Lock()

        # Check if curl_cffi is available
        self.has_curl_cffi = self._check_curl_cffi()

        # Common headers
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Referer": "https://solscan.io/",
        }

        # Stats
        self.stats = {
            "total_requests": 0,
            "successful": 0,
            "failed": 0,
            "rate_limited": 0,
        }

    def _check_curl_cffi(self) -> bool:
        """Check if curl_cffi is available."""
        try:
            from curl_cffi import requests as cffi_requests

            Logger.debug("[SCRAPER] curl_cffi available - Cloudflare bypass enabled")
            return True
        except ImportError:
            Logger.debug("[SCRAPER] curl_cffi not installed - using standard requests")
            return False

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            return parsed.netloc
        except:
            return "unknown"

    def _check_rate_limit(self, domain: str) -> bool:
        """Check if we can make a request to this domain."""
        with self.lock:
            now = time.time()
            rate_limit = self.RATE_LIMITS.get(domain, self.DEFAULT_RATE_LIMIT)
            min_interval = 60.0 / rate_limit  # Seconds between requests

            last_time = self.last_request_time.get(domain, 0)
            if now - last_time < min_interval:
                self.stats["rate_limited"] += 1
                return False

            self.last_request_time[domain] = now
            return True

    def scrape(self, url: str, timeout: int = 10, max_retries: int = 2) -> ScrapeResult:
        """
        Scrape a URL with Cloudflare bypass.

        Args:
            url: URL to scrape
            timeout: Request timeout in seconds
            max_retries: Number of retries on failure

        Returns:
            ScrapeResult with data or error
        """
        domain = self._get_domain(url)

        # Check rate limit
        if not self._check_rate_limit(domain):
            return ScrapeResult(
                success=False, url=url, status_code=429, error="Rate limited (internal)"
            )

        self.stats["total_requests"] += 1

        for attempt in range(max_retries + 1):
            try:
                if self.has_curl_cffi:
                    result = self._scrape_with_cffi(url, timeout)
                else:
                    result = self._scrape_with_requests(url, timeout)

                if result.success:
                    self.stats["successful"] += 1
                    return result

                # Retry on certain errors
                if result.status_code in [429, 503, 502]:
                    time.sleep(2**attempt)  # Exponential backoff
                    continue

                return result

            except Exception as e:
                if attempt < max_retries:
                    time.sleep(2**attempt)
                    continue
                self.stats["failed"] += 1
                return ScrapeResult(success=False, url=url, status_code=0, error=str(e))

        self.stats["failed"] += 1
        return ScrapeResult(
            success=False, url=url, status_code=0, error="Max retries exceeded"
        )

    def _scrape_with_cffi(self, url: str, timeout: int) -> ScrapeResult:
        """Scrape using curl_cffi with Chrome impersonation."""
        try:
            from curl_cffi import requests as cffi_requests

            response = cffi_requests.get(
                url,
                headers=self.headers,
                timeout=timeout,
                impersonate="chrome120",  # Impersonate Chrome 120
            )

            # Parse JSON if possible
            data = None
            try:
                data = response.json()
            except:
                data = response.text

            return ScrapeResult(
                success=response.status_code == 200,
                url=url,
                status_code=response.status_code,
                data=data,
                scraped_at=time.time(),
            )

        except Exception as e:
            return ScrapeResult(success=False, url=url, status_code=0, error=str(e))

    def _scrape_with_requests(self, url: str, timeout: int) -> ScrapeResult:
        """Fallback scrape using standard requests."""
        try:
            import requests

            response = requests.get(url, headers=self.headers, timeout=timeout)

            # Parse JSON if possible
            data = None
            try:
                data = response.json()
            except:
                data = response.text

            return ScrapeResult(
                success=response.status_code == 200,
                url=url,
                status_code=response.status_code,
                data=data,
                scraped_at=time.time(),
            )

        except Exception as e:
            return ScrapeResult(success=False, url=url, status_code=0, error=str(e))

    def get_stats(self) -> Dict:
        """Get scraper statistics."""
        return {**self.stats, "has_cloudflare_bypass": self.has_curl_cffi}


# Singleton
_smart_scraper = None


def get_smart_scraper() -> SmartScraper:
    """Get singleton smart scraper instance."""
    global _smart_scraper
    if _smart_scraper is None:
        _smart_scraper = SmartScraper()
    return _smart_scraper
