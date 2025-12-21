import requests
import time
from config.settings import Settings
from src.shared.system.logging import Logger
from .base import PriceProvider

class JupiterProvider(PriceProvider):
    def get_name(self):
        return "Jupiter"
        
    def fetch_prices(self, mints: list) -> dict:
        """
        Fetch prices using Jupiter v6 API.
        Handles chunking to respect limits.
        """
        if not mints:
            return {}
            
        # Jupiter seems to handle ~100 ok, but we stick to 30 for safety/consistency
        CHUNK_SIZE = 30 
        all_results = {}
        
        chunks = [mints[i:i + CHUNK_SIZE] for i in range(0, len(mints), CHUNK_SIZE)]
        
        for chunk in chunks:
            ids = ",".join(chunk)
            url = f"https://price.jup.ag/v6/price?ids={ids}&vsToken={Settings.USDC_MINT}"
            
            # Simple retry logic within the provider
            for attempt in range(2):
                try:
                    resp = requests.get(url, timeout=5)
                    if resp.status_code == 200:
                        data = resp.json()
                        for mint, info in data.get('data', {}).items():
                            all_results[mint] = float(info.get('price', 0.0))
                        break # Success
                    elif resp.status_code == 429:
                        if attempt == 0: time.sleep(1)
                        else: raise Exception(f"Jupiter 429 Rate Limit")
                    else:
                        if attempt == 1: raise Exception(f"Jupiter Status {resp.status_code}")
                except Exception as e:
                    if attempt == 0: time.sleep(0.5)
                    else: raise e # Re-raise on last attempt
                    
        return all_results
