import argparse
import os
import sys
import requests
import time
import urllib3
from typing import List, Dict

# Suppress insecure request warnings for CLI environment
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Add project root to path so 'src' can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from src.shared.system.logging import Logger
from src.shared.system.db_manager import db_manager
from config.settings import Settings

# Force disable silent mode for CLI tool feedback
Settings.SILENT_MODE = False
Logger.set_silent(False)

class DeepScout:
    """
    V116: DeepScout Large-Scale Data Harvester
    Populates DB with pools, alpha wallets, and historical calibration.
    """
    
    def __init__(self):
        self.jupiter_url = "https://token.jup.ag/all"
        self.dexscreener_url = "https://api.dexscreener.com/latest/dex/tokens/"
        
    def harvest_pools(self, token_mints: List[str]):
        """Find and register all available liquid pools (Bulk Mode)."""
        valid_mints = [m for m in token_mints if m]
        Logger.info(f"🔎 [SCOUT] Harvesting pools for {len(valid_mints)} tokens (Bulk)...")
        
        USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        SOL = "So11111111111111111111111111111111111111112"
        USDT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
        CITADEL_TOKENS = {USDC, SOL, USDT}
        
        count = 0
        CHUNK_SIZE = 30 # DexScreener bulk limit
        
        for i in range(0, len(valid_mints), CHUNK_SIZE):
            chunk = valid_mints[i:i + CHUNK_SIZE]
            mint_str = ",".join(chunk)
            Logger.info(f"⚡ [SCOUT] Syncing batch {i//CHUNK_SIZE + 1} ({len(chunk)} tokens)...")
            
            try:
                # V117.5: Bulk API execution
                resp = requests.get(f"{self.dexscreener_url}{mint_str}", timeout=20, verify=False)
                if resp.status_code == 200:
                    data = resp.json()
                    pairs = data.get("pairs", [])
                    
                    for p in pairs:
                        if p.get("chainId") == "solana":
                            mint = p.get("baseToken", {}).get("address")
                            raw_dex = p.get("dexId", "").lower()
                            
                            mapped_dex = None
                            if "raydium" in raw_dex: mapped_dex = "RAYDIUM"
                            elif "orca" in raw_dex: mapped_dex = "ORCA"
                            elif "meteora" in raw_dex: mapped_dex = "METEORA"
                            elif "jupiter" in raw_dex: mapped_dex = "JUPITER"
                            
                            quote_token = p.get("quoteToken", {}).get("address")
                            
                            if mapped_dex and quote_token in CITADEL_TOKENS:
                                db_manager.register_pool(
                                    mint=mint,
                                    dex=mapped_dex,
                                    symbol=p.get("baseToken", {}).get("symbol", "UNK")
                                )
                                count += 1
                
                # Small pulse between batches to avoid IP bans
                if i + CHUNK_SIZE < len(valid_mints):
                    time.sleep(1.0)
            except Exception as e:
                Logger.debug(f"Bulk sync failed: {e}")
                
        Logger.info(f"✅ [SCOUT] Bulk Registered {count} pools.")

    def harvest_global_trending(self, min_vol=10000):
        """V117: Find high-volume pools across the entire network."""
        Logger.info(f"🌐 [SCOUT] Scanning global network for volume spikes (>${min_vol})...")
        try:
            url = "https://api.dexscreener.com/latest/dex/search?q=solana"
            Logger.info(f"📡 [SCOUT] Connecting to {url}...")
            resp = requests.get(url, timeout=15, verify=False)
            if resp.status_code == 200:
                data = resp.json()
                pairs = data.get("pairs", [])
                Logger.info(f"📊 [SCOUT] Found {len(pairs)} candidates. Filtering for volume...")
                mints = []
                for p in pairs[:500]: # Deep scan top 500
                    vol = float(p.get("volume", {}).get("h24", 0) or 0)
                    if vol >= min_vol:
                        mint = p.get("baseToken", {}).get("address")
                        symbol = p.get("baseToken", {}).get("symbol", "UNK")
                        if mint: 
                            mints.append(mint)
                            Logger.debug(f"[SCOUT] Target Found: {symbol} (Vol: ${vol:,.0f})")
                
                if mints:
                    self.harvest_pools(list(set(mints)))
        except Exception as e:
            Logger.debug(f"Global harvest failed: {e}")

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
    parser = argparse.ArgumentParser(description="DeepScout V117")
    parser.add_argument("--mode", choices=["pools", "alpha", "full", "global"], default="full")
    parser.add_argument("--token", help="Specific token mint for targeted scouting")
    args = parser.parse_args()
    
    scout = DeepScout()
    Logger.section(f"DeepScout V117 - {args.mode.upper()} Mode")
    
    if args.mode == "full":
        scout.run_full_sync()
    elif args.mode == "global":
        scout.harvest_global_trending()
    elif args.mode == "pools":
        targets = [args.token] if args.token else list(Settings.ASSETS.values())
        scout.harvest_pools(targets)
    elif args.mode == "alpha":
        if args.token:
            scout.harvest_alpha(args.token)
        else:
            print("❌ --token is required for alpha mode")
