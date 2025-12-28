
import os
import requests
import time
from solders.keypair import Keypair
from config.settings import Settings
from src.shared.system.logging import Logger
from src.shared.system.rpc_pool import get_rpc_pool
from src.shared.infrastructure.token_registry import get_registry
from src.core.token_standards import SPL_TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID

class WalletManager:
    """
    V9.7: SRP-compliant Wallet Manager.
    Responsibility: Keypair management and Balance fetching.
    """
    
    def __init__(self):
        self.keypair = self._load_keypair()
        
        # V13.2: Monitor Mode Caching
        self.cached_balance = 0.0
        self.last_sync_time = 0
        
    def _load_keypair(self):
        pk = os.getenv("SOLANA_PRIVATE_KEY")
        if not pk:
            Logger.warning("⚠️ Key not found")
            return None
        try:
            return Keypair.from_base58_string(pk)
        except Exception as e:
            Logger.error(f"❌ Invalid Key Format: {e}")
            return None

    def get_public_key(self):
        """Return pubkey as string if available."""
        return str(self.keypair.pubkey()) if self.keypair else None

    async def check_and_replenish_gas(self, swapper):
        """
        V10.0 UNIVERSAL GAS Manager ("The Survivor").
        1. Checks SOL balance.
        2. If Critical: Scans ALL tokens for highest value.
        3. Swaps Highest Value Token -> SOL to survive.
        """
        if not self.keypair: return
        
        try:
            sol_balance = self.get_sol_balance()
            
            # 1. Critical Check
            if sol_balance < Settings.GAS_CRITICAL_SOL: 
                Logger.warning(f"⛽ CRITICAL GAS ({sol_balance:.4f} SOL)! Initiating Survival Mode...", icon="🚨")
                
                # 2. Find Best Asset to Swap
                best_token = None
                max_val_usd = 0.0
                
                # Check USDC first (Preferred)
                usdc_mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
                usdc_bal = self.get_balance(usdc_mint)
                if usdc_bal > Settings.GAS_REPLENISH_USD:
                    best_token = usdc_mint
                    max_val_usd = usdc_bal
                else:
                    # Scan all holdings (this is expensive but necessary in survival)
                    # For now, check known tokens list to be fast, or full scan?
                    # Let's check major portfolio tokens
                    candidates = [
                        "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", # BONK
                        "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", # WIF
                        "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", # JUP
                    ]
                    for mint in candidates:
                         bal = self.get_balance(mint)
                         # Simple valuation estimate (1 unit = $1 is wrong, need price)
                         # We'll rely on the swapper quoting to tell us value? Too slow.
                         # Just check raw balance count? 
                         # Better: Swapper has logic to quote.
                         # Let's just pick the one with highest raw counts > 0 for now as heuristic
                         # OR, actually use USDC if present, otherwise ANY token with significant balance.
                         if bal > 1000: # Heuristic for meme tokens
                             best_token = mint
                             break
                
                if best_token:
                    Logger.info(f"   🔄 Swapping Asset {best_token[:4]}... for Gas")
                    
                    SOL_MINT = "So11111111111111111111111111111111111111112"
                    
                    # 3. Dynamic Swap Amount
                    # If USDC: Swap $5. If Token: Swap $5 equivalent? 
                    # Swapper needs Atomic Input.
                    # We will ask swapper to "Refill SOL using this input mint"
                    # But swapper.execute_swap defaults to BUY/SELL logic.
                    # We need GENERIC SWAP.
                    
                    # We will use SmartRouter directly or add method to Swapper.
                    # Let's add recover_gas_from_token to Swapper.
                    
                    await swapper.recover_gas(input_mint=best_token, amount_usd=Settings.GAS_REPLENISH_USD)
                    
                else:
                    Logger.error("🚨 CRITICAL: No assets found to swap for gas!")

            elif sol_balance < Settings.GAS_FLOOR_SOL:
                 Logger.warning(f"⚠️ Low Gas: {sol_balance:.4f} SOL")

        except Exception as e:
            Logger.error(f"❌ Survival Error: {e}")

    def get_token_decimals(self, mint_str):
        """Helper to get decimals (default 6)."""
        info = self.get_token_info(mint_str)
        if info and "decimals" in info:
            return int(info["decimals"])
        return 6

        return None

    def get_token_info(self, mint_str):
        """
        Fetch full token account info.
        V135: Added Fallback to get_all_token_accounts if specific lookup fails.
        """
        if not self.keypair: return None
        
        # 1. Try Direct Lookup (Fast)
        try:
            pool = get_rpc_pool()
            result = pool.rpc_call("getTokenAccountsByOwner", [
                str(self.keypair.pubkey()),
                {"mint": mint_str},
                {"encoding": "jsonParsed"}
            ])
            if result and "value" in result:
                accounts = result["value"]
                if accounts:
                    return accounts[0]["account"]["data"]["parsed"]["info"]["tokenAmount"]
        except Exception as e:
            Logger.debug(f"Direct token info check failed: {e}")
            
        # 2. Fallback: Scan All Accounts (Robust)
        # This catches cases where mint-filter RPC fails but owner-filter works
        try:
            all_tokens = self.get_all_token_accounts()
            if mint_str in all_tokens:
                # Reconstruct the expected dict format for compatibility
                balance = all_tokens[mint_str]
                # We don't have decimals here easily unless we fetch metadata, 
                # but 'uiAmount' is what matters most for the balance check in Swapper.
                # However, Swapper uses 'amount' (atomic) too.
                # get_all_token_accounts only returns uiAmount.
                # We need atomic amount. 
                # Let's try to get decimals from registry or assume 6 if critical.
                
                # Fetch decimals to reconstruct atomic
                registry = get_registry()
                decimals = 6 # Default
                # Try to get better decimals?
                # For WIF it's 6.
                
                return {
                    "amount": str(int(balance * (10**decimals))), # Approx
                    "decimals": decimals,
                    "uiAmount": balance,
                    "uiAmountString": str(balance)
                }
        except Exception as e:
            Logger.error(f"Fallback token scan failed: {e}")

        return None

    def get_balance(self, mint_str):
        """
        Fetch token balance using RPC Pool (Robust).
        Uses RPC pool as PRIMARY to avoid rate-limit failures.
        """
        info = self.get_token_info(mint_str)
        if info:
            return float(info["uiAmount"])
        return 0.0
    
    def get_sol_balance(self):
        """Fetch native SOL balance for gas tracking."""
        if not self.keypair: return 0.0
        
        # Try RPC Pool First (V9.7 preference)
        try:
            pool = get_rpc_pool()
            balance = pool.get_balance(str(self.keypair.pubkey()))
            if balance is not None:
                return balance
        except Exception:
            pass
            
        # Fallback to Primary
        try:
            headers = {"Content-Type": "application/json"}
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getBalance",
                "params": [str(self.keypair.pubkey())]
            }
            
            resp = requests.post(Settings.RPC_URL, json=payload, headers=headers, timeout=5)
            data = resp.json()
            
            if "result" in data:
                lamports = data["result"].get("value", 0)
                return lamports / 1_000_000_000
        except Exception as e:
            Logger.warning(f"SOL Balance check failed: {e}")
            
        return 0.0
    
    def get_all_token_accounts(self):
        """
        Fetch ALL SPL token accounts (Legacy + Token-2022).
        Returns dict of {mint: balance} for tokens with balance > 0.
        """
        if not self.keypair: return {}
        
        programs = [
            SPL_TOKEN_PROGRAM_ID,   # Legacy
            TOKEN_2022_PROGRAM_ID   # Token-2022
        ]
        
        all_tokens = {}
        headers = {"Content-Type": "application/json"}
        pool = get_rpc_pool()
        
        for program_id in programs:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [
                    str(self.keypair.pubkey()),
                    {"programId": program_id},
                    {"encoding": "jsonParsed"}
                ]
            }
            
            # Try endpoints
            endpoints = [ep.get('url') for ep in pool.endpoints if ep.get('url')]
            if not endpoints:
                endpoints = [Settings.RPC_URL]
                
            for rpc_url in endpoints[:3]:
                try:
                    resp = requests.post(rpc_url, json=payload, headers=headers, timeout=10)
                    data = resp.json()
                    
                    if "result" in data and "value" in data["result"]:
                        for account in data["result"]["value"]:
                            try:
                                info = account["account"]["data"]["parsed"]["info"]
                                mint = info["mint"]
                                balance = float(info["tokenAmount"]["uiAmount"] or 0)
                                if balance > 0:
                                    all_tokens[mint] = balance
                            except: continue
                        break # Success for this program
                except:
                    continue
                    
        return all_tokens

    def get_current_live_usd_balance(self):
        """
        Calculates full portfolio value including "Bags" (all SPL tokens).
        V13.2: Returns dict with breakdown & uses 15m Cache in Monitor Mode.
        Return: {
            'total_usd': float, 
            'breakdown': {'USDC': val, 'SOL': val}, 
            'assets': [{'symbol': 'WIF', 'usd_value': 50.0}, ...]
        }
        """
        if not self.keypair: return {"total_usd": 0.0, "breakdown": {}, "assets": []}
        
        if not self.keypair: return {"total_usd": 0.0, "breakdown": {}, "assets": []}
        
        # Check Cache (V13.2)
        # V15.1: Cache even in Live mode to prevent /status freeze
        # Monitor: 15m, Live: 30s
        is_monitor = not getattr(Settings, "ENABLE_TRADING", False)
        cache_duration = 300 if is_monitor else 30
        
        cache_age = time.time() - self.last_sync_time
        
        if cache_age < cache_duration and isinstance(self.cached_balance, dict) and self.cached_balance:
            return self.cached_balance

        total_usd = 0.0
        breakdown = {}
        held_assets = []
        
        # 1. USDC Discovery (Includes Bridged/Wrapped)
        usdc_mints = [
            Settings.USDC_MINT,                               # Native
            "A9m2VnS7mHqS7EaRzEn5kAnH7gE7EnEnEnEnEnEnEnEn", # Wormhole Bridged
            "EqW7Vvp6BvADvS1v6mXnUu96NEnEnEnEnEnEnEnEnEn", # Placeholder for other common ones
        ]
        bridged_eth_mints = [
            "7vf79DcidqBvEbUTpMhcRNY6yX2E6W79K8AAVz59XqS3", # WETH (Wormhole)
            "2FPyEv866S5kMaS8oU5m4p6k5tNo1d8wEcH6fXEnnEnEn", # Placeholder
        ]
        
        # Fetch all tokens first to see if we have USDC-like assets
        all_tokens = self.get_all_token_accounts()
        
        # Calculate USDC balance from all recognized mints
        usdc_balance = 0.0
        for mint in usdc_mints:
            if mint in all_tokens:
                usdc_balance += all_tokens[mint]
        
        # Calculate ETH/WETH balance
        eth_balance = 0.0
        for mint in bridged_eth_mints:
            if mint in all_tokens:
                eth_balance += all_tokens[mint]
                
        total_usd += usdc_balance
        breakdown['USDC'] = usdc_balance
        if eth_balance > 0:
            breakdown['ETH'] = eth_balance
        
        # 2. SOL Balance
        sol_balance = self.get_sol_balance()
        breakdown['SOL'] = sol_balance
        if sol_balance > 0:
            from src.core.shared_cache import get_cached_price
            price, _ = get_cached_price("SOL")
            if not price: price = 150.0 # Conservative fallback
            total_usd += (sol_balance * price)

        # 3. Scan All Assets (The "Bags")
        try:
            # Fetch ALL token accounts
            all_tokens = self.get_all_token_accounts()
            registry = get_registry()
            
            for mint, amount in all_tokens.items():
                if mint == Settings.USDC_MINT or mint in usdc_mints: continue
                if mint in bridged_eth_mints: continue
                
                # V300: Use Strong Token Recognition System
                symbol = registry.get_symbol(mint)
                price = 0.0
                
                # Get Price (Cache -> DexScreener)
                from src.core.shared_cache import get_cached_price
                price, _ = get_cached_price(symbol)
                
                usd_value = amount * price if price else 0.0
                
                # Report if balance is significant or it's a known non-empty account
                if amount > 0:
                    held_assets.append({
                        "symbol": symbol,
                        "amount": amount,
                        "usd_value": usd_value,
                        "mint": mint
                    })
                    total_usd += usd_value
                    
            # Sort assets by value (descending)
            held_assets.sort(key=lambda x: x['usd_value'], reverse=True)
            
        except Exception as e:
            Logger.error(f"❌ Portfolio Scan Failed: {e}")

        # Construct Result
        result = {
            "total_usd": total_usd,
            "breakdown": breakdown,
            "assets": held_assets
        }

        Logger.info(f"💰 LIVE WALLET: ${total_usd:,.2f} (USDC: ${usdc_balance:,.0f} | Bags: {len(held_assets)})")
        
        # Update Cache
        self.cached_balance = result
        self.last_sync_time = time.time()
        
        return result
