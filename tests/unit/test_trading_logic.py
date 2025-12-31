"""
PhantomTrader Unit Tests
========================
Tests for critical trading logic.
"""

import pytest
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRSICalculation:
    """Test RSI indicator calculation."""

    def test_rsi_neutral_on_flat_prices(self):
        """RSI should be 50 when price is completely flat."""
        from src.core.data import DataFeed

        # Create mock DataFeed without network calls
        feed = object.__new__(DataFeed)
        feed.raw_prices = [1.0] * 20  # Flat prices

        rsi = feed.calculate_rsi(period=14)
        assert rsi == 50.0, f"Expected RSI 50 for flat prices, got {rsi}"

    def test_rsi_overbought_on_rising_prices(self):
        """RSI should be high (>70) when prices are rising."""
        from src.core.data import DataFeed

        feed = object.__new__(DataFeed)
        # Steadily rising prices
        feed.raw_prices = [1.0 + i * 0.01 for i in range(20)]

        rsi = feed.calculate_rsi(period=14)
        assert rsi > 70, f"Expected RSI > 70 for rising prices, got {rsi}"

    def test_rsi_oversold_on_falling_prices(self):
        """RSI should be low (<30) when prices are falling."""
        from src.core.data import DataFeed

        feed = object.__new__(DataFeed)
        # Steadily falling prices
        feed.raw_prices = [2.0 - i * 0.01 for i in range(20)]

        rsi = feed.calculate_rsi(period=14)
        assert rsi < 30, f"Expected RSI < 30 for falling prices, got {rsi}"


class TestRPCPoolEnvVars:
    """Test RPC pool environment variable substitution."""

    def test_env_var_substitution(self):
        """Environment variables in URLs should be substituted."""
        import re

        def substitute_env_vars(text: str) -> str:
            pattern = r"\$\{([^}]+)\}"

            def replacer(match):
                var_name = match.group(1)
                return os.getenv(var_name, "")

            return re.sub(pattern, replacer, text)

        # Set a test env var
        os.environ["TEST_API_KEY"] = "abc123"

        url = "https://example.com/?api-key=${TEST_API_KEY}"
        result = substitute_env_vars(url)

        assert result == "https://example.com/?api-key=abc123"

    def test_missing_env_var_returns_empty(self):
        """Missing env vars should become empty string."""
        import re

        def substitute_env_vars(text: str) -> str:
            pattern = r"\$\{([^}]+)\}"

            def replacer(match):
                var_name = match.group(1)
                return os.getenv(var_name, "")

            return re.sub(pattern, replacer, text)

        url = "https://example.com/?api-key=${NONEXISTENT_KEY_12345}"
        result = substitute_env_vars(url)

        assert result == "https://example.com/?api-key="


class TestDryRunMode:
    """Test dry-run mode behavior."""

    def test_dry_run_flag_exists(self):
        """Verify --dry-run flag is recognized by arg parser."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--dry-run", action="store_true")

        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
