import sys
import os
import asyncio
import unittest
from unittest.mock import MagicMock

sys.path.append(os.getcwd())

from src.discovery.discovery_engine import DiscoveryEngine


class TestDiscoveryEngine(unittest.TestCase):
    def setUp(self):
        # Mock RPC
        self.mock_rpc = MagicMock()
        self.engine = DiscoveryEngine()
        self.engine.rpc = self.mock_rpc
        self.engine.watchlist = {}

    def test_calculate_performance_smart(self):
        """Test auditing a smart wallet."""
        # Mock 50 signatures
        self.mock_rpc.call.side_effect = self._mock_rpc_call_smart

        loop = asyncio.new_event_loop()
        score = loop.run_until_complete(
            self.engine.calculate_wallet_performance("WalletSmart")
        )
        loop.close()

        print(f"\n🧠 Smart Wallet Score: {score}")
        self.assertIsNotNone(score)
        self.assertTrue(score["is_smart_money"])
        self.assertGreaterEqual(score["win_rate"], 0.70)

    def _mock_rpc_call_smart(self, method, params):
        if method == "getSignaturesForAddress":
            # Return 10 sigs
            return [{"signature": f"sig{i}"} for i in range(10)], None

        if method == "getTransaction":
            # Return a TX that looks like a "Win"
            # _analyze_tx_pnl returns 1.0 placeholder
            return {
                "result": {
                    "meta": {
                        "preBalances": [100],
                        "postBalances": [200],
                        "logMessages": ["Swap"],
                    },
                    "transaction": {"message": {"accountKeys": ["WalletSmart"]}},
                }
            }, None

        return None, "Unknown"

    def test_scan_token(self):
        """Test scanning a token for smart money interest."""
        # Add a smart wallet to watchlist
        self.engine.watchlist["SmartGuy"] = {"score": 100}

        self.mock_rpc.call.side_effect = self._mock_rpc_call_scan

        loop = asyncio.new_event_loop()
        score = loop.run_until_complete(
            self.engine.scan_token_for_smart_money("TokenMoon")
        )
        loop.close()

        print(f"\n🕵️ Scan Score: {score}")
        self.assertEqual(score, 1.0)  # 3+ hits mocked

    def _mock_rpc_call_scan(self, method, params):
        if method == "getSignaturesForAddress":
            return [{"signature": f"sig{i}"} for i in range(10)], None
        if method == "getTransaction":
            # Return a TX signed by SmartGuy
            return {
                "result": {"transaction": {"message": {"accountKeys": ["SmartGuy"]}}}
            }, None
        return None, "Error"


if __name__ == "__main__":
    unittest.main()
