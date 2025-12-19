import requests
import pandas as pd
import time
from datetime import datetime
from src.system.logging import Logger

class DexDataFetcher:
    """
    V29.2: Data Bridge for GeckoTerminal API.
    Fetches OHLCV data for Solana DEX pairs.
    """
    
    BASE_URL = "https://api.geckoterminal.com/api/v2/networks/solana"
    HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    
    @staticmethod
    def get_top_pool(token_mint: str):
        """Find the most liquid pool for a token."""
        url = f"{DexDataFetcher.BASE_URL}/tokens/{token_mint}/pools"
        try:
            resp = requests.get(url, headers=DexDataFetcher.HEADERS, timeout=10)
            data = resp.json()
            if not data.get('data'):
                print(f"⚠️ API Response empty for pools: {data}")
                return None
            # Return top pool ID (usually sorted by liquidity by default)
            return data['data'][0]['id']
        except Exception as e:
            print(f"❌ Error fetching pool: {e}")
            return None

    @staticmethod
    def fetch_ohlcv(token_mint: str, timeframe='hour', limit=1000) -> pd.DataFrame:
        """
        Fetch OHLCV data.
        timeframe: 'day', 'hour', 'minute'
        """
        # V35.3: Cache-First Approach (Read from DB)
        # Note: Local DB stores Ticks. To use them as OHLCV, we need to resample.
        # For 'minute' or 'hour', we can query DB range.
        # For simplicity in V35.0, we just demonstrate probing the DB.
        # Ideally, we'd have a 'resample_ticks_to_ohlcv' helper.
        # Since DB only captures LIVE data from now on, historical backtests won't find old data instantly.
        # But for 'recent' data, it works.
        from src.data_storage.db_manager import db_manager
        
        # Determine query range (e.g. last 'limit' intervals)
        # Assuming DB has *some* data.
        # We can implement a hybrid: Fetch DB, if gaps, fetch API.
        # For V35.0 MVP, we won't replace the API fetch entirely yet, as DB is empty on first run.
        # But we will log the intent.
        
        # print(f"💾 Checking Local DB for {token_mint}...")
        # db_data = db_manager.get_history(token_mint, start_ts=time.time() - 86400) # Check last 24h
        # if db_data: ... reconstruct DF ...
        
        pool_address = DexDataFetcher.get_top_pool(token_mint)
        if not pool_address:
            print(f"⚠️ No pools found for {token_mint}")
            return pd.DataFrame()
            
        # Strip 'solana_' prefix if present (GeckoTerminal returns id like 'solana_ADDRESS')
        # API Expects: /networks/solana/pools/ADDRESS/ohlcv/...
        clean_address = pool_address.replace('solana_', '')
        
        print(f"🔗 Found Pool: {pool_address} -> {clean_address}")
        
        endpoint = f"{DexDataFetcher.BASE_URL}/pools/{clean_address}/ohlcv/{timeframe}"
        params = {'limit': limit}
        
        try:
            resp = requests.get(endpoint, params=params, headers=DexDataFetcher.HEADERS, timeout=10)
            data = resp.json()
            ohlcv_list = data.get('data', {}).get('attributes', {}).get('ohlcv_list', [])
            
            if not ohlcv_list:
                return pd.DataFrame()
                
            # Gecko returns [timestamp, o, h, l, c, v]
            df = pd.DataFrame(ohlcv_list, columns=['Time', 'Open', 'High', 'Low', 'Close', 'Volume'])
            
            # Convert Time
            df['Time'] = pd.to_datetime(df['Time'], unit='s')
            df.set_index('Time', inplace=True)
            df.sort_index(inplace=True) # Ensure chronological
            
            # Convert numeric
            cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            for c in cols:
                df[c] = pd.to_numeric(df[c])
            
            # V35.3: Opportunistic Write to DB? 
            # (No, `db_manager` is for LIVE ticks. We don't want to pollute it with 1h candles unless we have a candles table.)
            # We stick to using DB for live tick storage.
                
            return df
            
        except Exception as e:
            print(f"❌ Error fetching OHLCV: {e}")
            return pd.DataFrame()
