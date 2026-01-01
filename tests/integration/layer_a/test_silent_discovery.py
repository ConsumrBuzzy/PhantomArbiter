import asyncio
import sys
import os
import time
from unittest.mock import MagicMock, patch
from collections import defaultdict

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.discovery.launchpad_monitor import LaunchEvent, LaunchPlatform, EventType


async def test_silent_logic_buffered():
    print("🧪 Testing Silent Discovery Logic (Buffered)...")

    # Mock dependencies
    with (
        patch("src.system.comms_daemon.send_telegram") as mock_send,
        patch("src.system.logging.Logger") as mock_logger,
        patch(
            "src.infrastructure.token_scraper.get_token_scraper"
        ) as mock_scraper_getter,
    ):
        # Emulate the logic in main.py
        silent_buffer = []

        # Mock Scraper
        mock_scraper = MagicMock()
        mock_scraper_getter.return_value = mock_scraper

        # Scraper behavior: Resolve one, fail one
        def side_effect(mint):
            if mint == "UNKNOWN_RESOLVED":
                return {"symbol": "FOUND_IT", "name": "Found Token"}
            return {"symbol": "UNK_123", "name": "Unknown"}

        mock_scraper.lookup.side_effect = side_effect

        # Mock Reporter
        async def report_silent_launches():
            print("   ⏰ Reporting Task Running...")
            if not silent_buffer:
                print("   Empty buffer")
                return

            batch = silent_buffer[:]
            silent_buffer.clear()

            resolved_lines = []
            still_unknown_counts = defaultdict(int)

            for mint, platform, _ in batch:
                info = mock_scraper.lookup(mint)
                symbol = info.get("symbol", "")

                is_resolved = (
                    symbol and not symbol.startswith("UNK_") and symbol != "UNKNOWN"
                )

                if is_resolved:
                    print(f"   ✅ Resolved {mint} -> {symbol}")
                    resolved_lines.append(f"• {symbol}")
                else:
                    print(f"   🌑 Unresolved {mint}")
                    still_unknown_counts[platform] += 1

            if resolved_lines or still_unknown_counts:
                mock_send("REPORT SENT")

        # Mock event handler logic
        async def on_launch(event):
            is_unknown = (
                not event.symbol
                or event.symbol == "UNKNOWN"
                or event.mint.startswith("UNKNOWN")
            )

            if is_unknown:
                print(f"   📥 Buffering {event.mint}")
                silent_buffer.append((event.mint, event.platform.value, time.time()))
                return

            print(f"   🚀 Alerting {event.mint}")
            mock_send(f"New Launch: {event.symbol}")

        # Test Case 1: Unknown Token (Should Buffer)
        evt1 = LaunchEvent(
            platform=LaunchPlatform.PUMPFUN,
            event_type=EventType.NEW_LAUNCH,
            mint="UNKNOWN_RESOLVED",  # Will be resolved later
            symbol="UNKNOWN",
        )
        await on_launch(evt1)

        # Test Case 2: Another Unknown (Will stay unknown)
        evt2 = LaunchEvent(
            platform=LaunchPlatform.PUMPFUN,
            event_type=EventType.NEW_LAUNCH,
            mint="UNKNOWN_PERM",
            symbol="UNKNOWN",
        )
        await on_launch(evt2)

        # Verify Buffer
        if len(silent_buffer) == 2:
            print("✅ PASS: Buffered 2 tokens")
        else:
            print(f"❌ FAIL: Buffer size {len(silent_buffer)}")

        # Run Report Task
        await report_silent_launches()

        # Verify Results
        if mock_send.call_count == 1:
            print("✅ PASS: Report sent")
        else:
            print("❌ FAIL: Report not sent")

        print("✅ Test Complete")


if __name__ == "__main__":
    asyncio.run(test_silent_logic_buffered())
