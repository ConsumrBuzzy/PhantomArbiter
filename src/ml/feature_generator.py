
import sqlite3
import pandas as pd
import numpy as np
import os
import sys

# Add root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.data_storage.db_manager import db_manager

class FeatureGenerator:
    """
    V36.0: ML Feature Engineering.
    Transforms raw SQLite ticks into labeled dataset for training.
    """
    
    def __init__(self, db_path=None):
        if db_path:
            self.conn = sqlite3.connect(db_path)
        else:
            # Use default from DBManager
            self.conn = db_manager._get_conn()
            
    def load_raw_data(self, mint=None, limit=10000):
        """Load raw ticks from DB."""
        query = "SELECT timestamp, token_mint, open, volume_h1, liquidity_usd, latency_ms FROM market_data"
        params = []
        
        if mint:
            query += " WHERE token_mint = ?"
            params.append(mint)
            
        query += f" ORDER BY timestamp ASC LIMIT {limit}"
        
        try:
            df = pd.read_sql_query(query, self.conn, params=params)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
            return df
        except Exception as e:
            print(f"❌ Load Error: {e}")
            return pd.DataFrame()

    def create_features(self, df, timeframe='1min'):
        """
        Resample to candles and add indicators.
        target = 1 if High(next 5 mins) > Close * 1.002
        """
        if df.empty: return pd.DataFrame()
        
        # Resample to Candles
        df.set_index('timestamp', inplace=True)
        
        # Group by Mint if mixed, but usually we process one mint or handle groupby
        # Simplified: Assume single mint for MVP training or group by mint
        
        resampled_dfs = []
        
        for mint, group in df.groupby('token_mint'):
            # Resample logic
            candles = group['open'].resample(timeframe).ohlc()
            # Restore other cols (mean)
            candles['volume'] = group['volume_h1'].resample(timeframe).mean() # Propagate Vol
            candles['liquidity'] = group['liquidity_usd'].resample(timeframe).min() # Conservative Liq
            candles['latency'] = group['latency_ms'].resample(timeframe).mean()
            
            # Forward fill missing candles (illiquid periods)
            candles.ffill(inplace=True)
            candles.dropna(inplace=True)
            
            # --- Feature Engineering ---
            
            # 1. RSI (14)
            delta = candles['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            candles['rsi'] = 100 - (100 / (1 + rs))
            
            # V62.0: RSI Delta (Momentum Acceleration)
            # Change in RSI over last 5 minutes
            candles['rsi_delta'] = candles['rsi'].diff(5)
            
            # 2. Volatility (ATR-ish: High-Low / Open)
            # V62.0: Renaming/Aliasing as Spread Variance proxy for clarity
            candles['spread_var'] = ((candles['high'] - candles['low']) / candles['open']) * 100
            
            # 3. Liquidity Score (Log scale)
            candles['log_liquidity'] = np.log1p(candles['liquidity'])
            
            # V62.0: Bar Pressure (OBI Proxy)
            # (Close - Open) / (High - Low)
            # Range: -1.0 to 1.0. Measures who won the candle.
            candle_range = candles['high'] - candles['low']
            # Avoid division by zero
            candles['bar_pressure'] = (candles['close'] - candles['open']) / candle_range.replace(0, 1)
            
            # 4. Latency
            candles['latency_smooth'] = candles['latency'].rolling(5).mean()
            
            # --- Labeling (The Oracle) ---
            # Predict: Will price hit +0.3% in next 5 candles?
            LOOKAHEAD = 5
            TARGET_PROFIT = 0.003 # 0.3% (covers fee 0.1% * 2 + profit)
            
            # Rolling max of 'high' shifted backwards
            future_high = candles['high'].rolling(window=LOOKAHEAD).max().shift(-LOOKAHEAD)
            
            # Label: 1 if future high > current close * (1 + target)
            candles['target'] = (future_high > candles['close'] * (1 + TARGET_PROFIT)).astype(int)
            
            # Add Mint col back
            candles['mint'] = mint
            
            resampled_dfs.append(candles)
            
        if not resampled_dfs: return pd.DataFrame()
        
        final_df = pd.concat(resampled_dfs)
        final_df.dropna(inplace=True) # Drop rows where RSI/Label is NaN
        
        return final_df

if __name__ == "__main__":
    # Test Run
    gen = FeatureGenerator()
    print("Loading Data...")
    raw = gen.load_raw_data(limit=5000)
    print(f"   Raw Ticks: {len(raw)}")
    
    print("Generating Features...")
    feat = gen.create_features(raw)
    print(f"   Labeled Samples: {len(feat)}")
    if not feat.empty:
        print(feat[['close', 'rsi', 'rsi_delta', 'bar_pressure', 'spread_var', 'target']].tail())
        print(f"   Positive Samples: {feat['target'].sum()} ({feat['target'].mean()*100:.1f}%)")
