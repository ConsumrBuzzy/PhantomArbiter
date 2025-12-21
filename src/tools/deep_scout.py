
import requests
import time
import json
import argparse
from typing import List, Dict
from src.shared.system.logging import Logger
from src.shared.system.db_manager import db_manager
from config.settings import Settings

class DeepScout:
    """
    V116: DeepScout Large-Scale Data Harvester
    Populates DB with pools, alpha wallets, and historical calibration.
    """
    
    def __init__(self):
        self.jupiter_url = "https://token.jup.ag/all"
        self.dexscreener_url = "https://api.dexscreener.com/latest/dex/tokens/"
        
    def harvest_pools(self, token_mints: List[str]):
        """Find and register all available liquid pools for target tokens."""
        Logger.info(f"🔎 [SCOUT] Harvesting pools for {len(token_mints)} tokens...")
        
        USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        SOL = "So11111111111111111111111111111111111111112"
        
        count = 0
        for mint in token_mints:
            try:
                # DexScreener is faster for pool discovery than Jupiter indexing
                resp = requests.get(f"{self.dexscreener_url}{mint}", timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    pairs = data.get("pairs", [])
                    for p in pairs:
                        if p.get("chainId") == "solana":
                            # Register pool in DB
                            # V116 Note: This uses the existing registry schema
                            dex = p.get("dexId", "").upper()
                            pool_addr = p.get("pairAddress")
                            quote_token = p.get("quoteToken", {}).get("address")
                            
                            # Only care about USDC/SOL routes for now
                            if quote_token in [USDC, SOL]:
                                db_manager.register_pool(
                                    symbol=p.get("baseToken", {}).get("symbol", "UNK"),
                                    dex=dex,
                                    pool_id=pool_addr,
                                    pair_address=pool_addr,
                                    fee=0.003 # Placeholder, usually 0.01% - 1%
                                )
                                count += 1
                time.sleep(0.5) # Rate limit protection
            except Exception as e:
                Logger.debug(f"Failed to harvest pools for {mint}: {e}")
                
        Logger.info(f"✅ [SCOUT] Registered {count} pools across target assets.")

    def harvest_alpha(self, token_mint: str):
        """Scrape Recent Profitable Wallets (Smart Money)."""
        Logger.info(f"🕵️ [SCOUT] Scouting Alpha Wallets for {token_mint[:8]}...")
        # In V116, we use Bitquery to find the 'Early Buyers' (potential insiders/alpha)
        from src.shared.infrastructure.bitquery_adapter import BitqueryAdapter
        bq = BitqueryAdapter()
        wallets = bq.get_first_100_buyers(token_mint)
        
        if wallets:
            for addr in wallets[:20]: # Only track Top 20 for signal quality
                db_manager.add_target_wallet(addr, tags="EARLY_BUYER")
            Logger.info(f"✅ [SCOUT] Added {len(wallets[:20])} Alpha Wallets to watchlist.")
        else:
            Logger.warning("⚠️ [SCOUT] No Bitquery data available for alpha scrape.")

    def run_full_sync(self):
        """Perform a full system warm-up."""
        targets = list(Settings.ASSETS.values())
        self.harvest_pools(targets)
        for t in targets[:10]: # Deep dive into top 10
            self.harvest_alpha(t)
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DeepScout V116")
    parser.add_argument("--mode", choices=["pools", "alpha", "full"], default="full")
    parser.add_argument("--token", help="Specific token mint for targeted scouting")
    args = parser.parse_args()
    
    scout = DeepScout()
    if args.mode == "full":
        scout.run_full_sync()
    elif args.mode == "pools":
        targets = [args.token] if args.token else list(Settings.ASSETS.values())
        scout.harvest_pools(targets)
    elif args.mode == "alpha":
        if args.token:
            scout.harvest_alpha(args.token)
        else:
            print("❌ --token is required for alpha mode")
