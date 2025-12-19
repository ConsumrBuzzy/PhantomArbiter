
import unittest
from unittest.mock import MagicMock, patch
import os
import sys

sys.path.append(os.getcwd())

from config.settings import Settings
from src.engine.trade_executor import TradeExecutor

class TestSimulation(unittest.TestCase):
    def setUp(self):
        # Force DRY_RUN
        Settings.DRY_RUN = True
        self.test_log = "test_sim_trades.csv"
        Settings.SIMULATION_LOG_FILE = self.test_log
        
        # Mocks
        self.mock_wallet = MagicMock()
        self.mock_wallet.get_balance.return_value = 1000.0
        self.mock_watcher = MagicMock()
        self.mock_watcher.symbol = "SOL"
        self.mock_watcher.mint = "So11111111111111111111111111111111111111112"
        self.mock_watcher.get_liquidity.return_value = 500000
        
        self.executor = TradeExecutor(
            engine_name="TestEngine",
            capital_mgr=MagicMock(),
            paper_wallet=self.mock_wallet,
            swapper=MagicMock(),
            portfolio=MagicMock()
        )
        # Pass preflight
        self.executor.paper_wallet.cash_balance = 1000.0
        self.executor.paper_wallet.sol_balance = 1.0 # Fix: Set SOL balance as float


    def tearDown(self):
        if os.path.exists(self.test_log):
            os.remove(self.test_log)

    def test_simulated_buy(self):
        """Test that DRY_RUN intercepts buy and logs to CSV."""
        try:
            result = self.executor.execute_buy(
                watcher=self.mock_watcher,
                price=150.0,
                reason="Test Simulation",
                size_usd=100.0
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.fail(f"Execution failed with exception: {e}")

        
        print(f"\n🧪 Result: {result}")
        
        self.assertTrue(result.success)
        self.assertIn("SIMULATED", result.message)
        self.assertIn("sim_tx_id", result.tx_id)
        
        # Verify Log File
        self.assertTrue(os.path.exists(self.test_log))
        with open(self.test_log, "r") as f:
            content = f.read()
            print(f"📝 Log Content:\n{content}")
            self.assertIn("SOL", content)
            self.assertIn("Test Simulation", content)

if __name__ == "__main__":
    unittest.main()
