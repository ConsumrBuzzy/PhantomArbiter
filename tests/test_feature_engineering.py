import unittest
import pandas as pd
import numpy as np
import os
import sys
import sqlite3
import time

sys.path.append(os.getcwd())

from src.ml.feature_generator import FeatureGenerator


class TestFeatureEngineering(unittest.TestCase):
    def setUp(self):
        # Create temp DB
        self.db_path = "test_features.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("""
            CREATE TABLE market_data (
                timestamp REAL,
                token_mint TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume_h1 REAL,
                liquidity_usd REAL,
                latency_ms INTEGER,
                PRIMARY KEY (timestamp, token_mint)
            )
        """)

        # Seed Data: 200 minutes of Sine Wave data
        self.mint = "TEST_MINT"
        # Align to minute boundary to prevent tick splitting
        self.base_ts = int(time.time() / 60) * 60 - 200 * 60

        print("🌱 Seeding 200 mins of data (4 ticks/min)...")
        for i in range(200):
            base_t = self.base_ts + (i * 60)
            price = 100 + 10 * np.sin(i * 0.1)

            # Simulate 4 ticks to form a green candle accurately within the minute
            # Minute is [T+0, T+60)
            # 1. Open at T+0
            self._insert_tick(base_t, price - 0.5)
            # 2. Low at T+15
            self._insert_tick(base_t + 15, price - 1.0)
            # 3. High at T+30
            self._insert_tick(base_t + 30, price + 1.0)
            # 4. Close at T+59 (End of candle)
            self._insert_tick(base_t + 59, price + 0.5)

        self.conn.commit()

    def _insert_tick(self, ts, price):
        self.conn.execute(
            """
            INSERT INTO market_data (timestamp, token_mint, open, high, low, close, volume_h1, liquidity_usd, latency_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (ts, self.mint, price, price, price, price, 1000.0, 50000.0, 100),
        )

    def tearDown(self):
        # Ensure connection is closed before removing file
        try:
            self.conn.close()
        except:
            pass

        # Wait a bit for file lock release
        time.sleep(0.1)

        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except PermissionError:
                print("⚠️ Warning: Could not remove test_features.db (File Locked)")

    def test_feature_generation(self):
        """Test full feature pipeline with V62.0 factors."""
        gen = FeatureGenerator(db_path=self.db_path)
        try:
            # 1. Load
            raw = gen.load_raw_data(mint=self.mint, limit=5000)
            self.assertEqual(len(raw), 800, "Should load 800 rows (4 ticks * 200 mins)")

            # 2. Generate
            df = gen.create_features(raw)

            print(f"\n📊 Generated Features: {len(df)}")
            if not df.empty:
                print(df.tail(3)[["close", "rsi", "rsi_delta", "bar_pressure"]])

            # 3. Assertions
            self.assertFalse(df.empty, "Feature generation returned empty DF")

            # Check new V62.0 columns
            self.assertIn("rsi_delta", df.columns)
            self.assertIn("bar_pressure", df.columns)
            self.assertIn("spread_var", df.columns)

            # Validate data
            # We created perfect green candles: (Close > Open)
            # Bar Pressure = (Close - Open) / (High - Low) = (1.0) / (2.0) = 0.5

            last_pressure = df["bar_pressure"].iloc[-1]
            print(f"\n🧪 Last Bar Pressure: {last_pressure}")
            print(f"   OHLC: {df[['open', 'high', 'low', 'close']].iloc[-1].to_dict()}")

            self.assertAlmostEqual(last_pressure, 0.5, places=2)
            print("✅ Bar Pressure Verified")

            # RSI Delta check (should be non-NaN)
            self.assertFalse(pd.isna(df["rsi_delta"].iloc[-1]))
            print("✅ RSI Delta Verified")

        finally:
            # Cleanup generator connection explicitly
            gen.conn.close()


if __name__ == "__main__":
    unittest.main()
