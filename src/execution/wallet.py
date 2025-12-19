
import os
import requests
import time
from solders.keypair import Keypair
from config.settings import Settings
from src.system.logging import Logger
from src.system.rpc_pool import get_rpc_pool

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

    def check_and_replenish_gas(self, swapper):
        """
        V9.7 Autonomous GAS Manager.
        Checks SOL balance and swaps USDC -> SOL if critical.
        """
        if not self.keypair: return
        
        try:
            sol_balance = self.get_sol_balance()
            
            # Check Critical Threshold
            if sol_balance < Settings.GAS_CRITICAL_SOL:
                # 1. Check if we have enough USDC
                usdc_balance = self.get_balance(Settings.USDC_MINT)
                if usdc_balance >= Settings.GAS_REPLENISH_USD:
                    
                    amount_usd = Settings.GAS_REPLENISH_USD
                    Logger.warning(f"⛽ CRITICAL GAS LOW ({sol_balance:.4f} SOL)! Swapping ${amount_usd} USDC for SOL...", icon="⛽")
                    
                    # 2. Execute Swap (USDC -> SOL)
                    # Force high slippage (1.5%) to guarantee refill
                    # Swapper handles the trade.
                    # Note: We pass internal method for simplicity or rely on swapper instance
                    
                    # Swapper expects direction, amount_usd, reason, target_mint
                    # But execute_swap logic is typically "Buy Target with USDC" or "Sell Target for USDC".
                    # We need "Buy SOL with USDC". 
                    # Our swapper might be hardcoded for Settings.TARGET_MINT if not specified.
                    # We need to pass target_mint="So11111111111111111111111111111111111111112"
                    
                    SOL_MINT = "So11111111111111111111111111111111111111112"
                    
                    # In execute_swap:
                    # if direction == "BUY": input=USDC, output=mint
                    # So we call BUY, target=SOL
                    
                    tx = swapper.execute_swap(
                        direction="BUY",
                        amount_usd=amount_usd,
                        reason="AUTO-REFUEL GAS",
                        target_mint=SOL_MINT
                    )
                    
                    if tx:
                         Logger.success("   ✅ Gas tank refuelled successfully.")
                    else:
                         Logger.error("   ❌ Refuel swap failed.")
                         
                else:
                    # 4. Critical Failure
                    Logger.error(f"🚨 CRITICAL STOP: Out of SOL ({sol_balance:.4f}) and insufficient USDC (${usdc_balance:.2f})!")
                    # In a real app we might raise an exception or set a flag, 
                    # but here we just log primarily. Engine might need to know.
            
            elif sol_balance < Settings.GAS_FLOOR_SOL:
                 Logger.warning(f"⚠️ Low Gas Warning: {sol_balance:.4f} SOL (Floor: {Settings.GAS_FLOOR_SOL})")
                 
        except Exception as e:
            Logger.error(f"❌ Auto-refuel error: {e}")

    def get_token_info(self, mint_str):
        """
        Fetch full token account info (amount, decimals, uiAmount).
        """
        if not self.keypair: return None
        
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
            Logger.debug(f"Token info check failed: {e}")
            
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
        Fetch ALL SPL token accounts in wallet.
        Returns dict of {mint: balance} for tokens with balance > 0.
        """
        if not self.keypair: return {}
        
        headers = {"Content-Type": "application/json"}
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                str(self.keypair.pubkey()),
                {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                {"encoding": "jsonParsed"}
            ]
        }
        
        # Build endpoint list (Pool + Primary)
        pool = get_rpc_pool()
        endpoints = [ep.get('url') for ep in pool.endpoints if ep.get('enabled', True)]
        if Settings.RPC_URL not in endpoints:
            endpoints.append(Settings.RPC_URL)
            
        # Try endpoints
        for rpc_url in endpoints[:3]:
            try:
                resp = requests.post(rpc_url, json=payload, headers=headers, timeout=10)
                data = resp.json()
                
                if "result" in data and "value" in data["result"]:
                    tokens = {}
                    for account in data["result"]["value"]:
                        try:
                            info = account["account"]["data"]["parsed"]["info"]
                            mint = info["mint"]
                            balance = float(info["tokenAmount"]["uiAmount"] or 0)
                            if balance > 0:
                                tokens[mint] = balance
                        except: continue
                    return tokens
            except:
                continue
                
        return {}

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
        
        # 1. USDC Balance
        usdc_balance = self.get_balance(Settings.USDC_MINT)
        total_usd += usdc_balance
        breakdown['USDC'] = usdc_balance
        
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
            mint_to_symbol = {v: k for k, v in Settings.ASSETS.items()}
            
            for mint, amount in all_tokens.items():
                if mint == Settings.USDC_MINT: continue
                
                # Identify Symbol
                symbol = mint_to_symbol.get(mint, "UNKNOWN")
                price = 0.0
                
                # Get Price (Cache -> DexScreener)
                if symbol != "UNKNOWN":
                    price, _ = get_cached_price(symbol)
                
                # If unknown or not in cache, skip synchronous fetch to prevent lag
                # V15.1: Removed synchronous requests.get
                if price <= 0:
                     continue

                usd_value = amount * price
                if usd_value > 1.0: # Filter dust (<$1)
                    held_assets.append({
                        "symbol": symbol,
                        "amount": amount,
                        "usd_value": usd_value
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
