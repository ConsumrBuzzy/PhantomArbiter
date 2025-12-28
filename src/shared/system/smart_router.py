
import json
import os
import requests
import time
import random
from config.settings import Settings
from src.shared.system.logging import Logger

class SmartRouter:
    """
    V9.6 Free-Tier Smart Router.
    Responsibility: Reliable routing of external API calls (RPC & Jupiter).
    Features:
    - Round-Robin RPC Rotation (Redundancy)
    - Jupiter Rate Limit Management (Cooldowns)
    - Centralized Error Handling
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SmartRouter, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized: return
        self._initialized = True
        
        self.config = self._load_config()
        
        # V11.9: Load and filter endpoints (skip disabled, filter missing keys)
        self.endpoints = self._get_valid_endpoints()
        # V12.0: Use official api.jup.ag endpoint (resolvable)
        self.jupiter_url = self.config.get("JUPITER_API_BASE", "https://api.jup.ag/swap/v1")
        
        # Load and clean API Key
        self.jupiter_api_key = os.getenv("JUPITER_API_KEY", "").strip("'\" ")
        
        self.current_rpc_index = 0
        self.jupiter_cooldown_until = 0
        
        # V131: Persistent HTTP session with connection pooling
        # Reuses TCP connections for ~50-100ms savings per request
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})
        if self.jupiter_api_key:
            self._session.headers.update({"x-api-key": self.jupiter_api_key})
        
        Logger.info(f"🌐 SmartRouter initialized with {len(self.endpoints)} RPC endpoints.")
        if self.jupiter_api_key:
             Logger.info("   🔑 Jupiter API Key loaded")

    def _load_config(self):
        """Load rpc_pool.json or return defaults."""
        config_path = os.path.join(os.path.dirname(__file__), "../../config/rpc_pool.json")
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            Logger.error(f"Failed to load rpc_pool.json: {e}")
        return {}
    
    def _get_valid_endpoints(self):
        """V11.9: Filter endpoints - only enabled with valid env vars."""
        import re
        
        def substitute_env_vars(text: str) -> str:
            """Replace ${VAR} patterns with environment variable values."""
            pattern = r'\$\{([^}]+)\}'
            def replacer(match):
                var_name = match.group(1)
                return os.getenv(var_name, '')
            return re.sub(pattern, replacer, text)
        
        valid = []
        
        # Check for 'endpoints' key (new format) or 'PUBLIC_RPC_POOL' key (legacy)
        raw_endpoints = self.config.get("endpoints", [])
        if not raw_endpoints:
            # Legacy format: just an array of URLs
            legacy = self.config.get("PUBLIC_RPC_POOL", [])
            if legacy:
                return legacy if legacy else [Settings.RPC_URL]
        
        for ep in raw_endpoints:
            # Skip disabled endpoints
            if not ep.get("enabled", True):
                continue
            
            # V12.3-FIX: Skip execution_only endpoints (JITO) from main pool
            # These are reserved exclusively for transaction submission
            if ep.get("execution_only", False):
                Logger.debug(f"   🛡️ {ep.get('name', 'Unknown')} reserved for execution only")
                continue
            
            url = ep.get("url", "")
            
            # Substitute env vars
            resolved_url = substitute_env_vars(url)
            
            # Skip if env var wasn't resolved (still has empty key part)
            if "api-key=" in url and "api-key=" in resolved_url:
                key_part = resolved_url.split("api-key=")[-1].split("&")[0]
                if not key_part:
                    Logger.debug(f"   ⚠️ Skipping {ep.get('name', 'Unknown')} - missing API key")
                    continue
            
            valid.append(resolved_url)
        
        if not valid:
            Logger.warning("   ⚠️ No valid RPC endpoints - using default Solana Mainnet")
            return [Settings.RPC_URL]
        
        return valid

    def get_rpc_url(self):
        """Get current RPC URL (Round Robin)."""
        url = self.endpoints[self.current_rpc_index]
        return url
    
    def get_jito_execution_url(self):
        """
        V12.3: Get JITO block engine URL for private transaction execution.
        Returns None if JITO is not configured.
        """
        config = self._load_config()
        for endpoint in config.get('endpoints', []):
            if endpoint.get('execution_only') and endpoint.get('enabled'):
                return endpoint.get('url')
        return None

    def rotate_rpc(self):
        """Switch to next RPC endpoint on failure."""
        old = self.endpoints[self.current_rpc_index]
        self.current_rpc_index = (self.current_rpc_index + 1) % len(self.endpoints)
        new = self.endpoints[self.current_rpc_index]
        Logger.warning(f"♻️ Rotating RPC: {old} -> {new}")
        
    def check_jupiter_cooldown(self):
        """Raise exception if in cool-down."""
        now = time.time()
        if now < self.jupiter_cooldown_until:
            wait = self.jupiter_cooldown_until - now
            raise Exception(f"Jupiter Rate Limited - Cooldown {wait:.1f}s")

    def trigger_jupiter_cooldown(self, seconds=10):
        """Trigger a cool-down period for Jupiter API."""
        self.jupiter_cooldown_until = time.time() + seconds
        Logger.warning(f"🛑 Jupiter Rate Limit Hit! Cooling down for {seconds}s...")

    def json_rpc_call(self, method, params, retries=3):
        """
        Execute a standard JSON-RPC call with failover.
        """
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        }
        headers = {"Content-Type": "application/json"}
        
        for i in range(retries):
            endpoint = self.get_rpc_url()
            try:
                resp = self._session.post(endpoint, json=payload, timeout=5)
                if resp.status_code == 429:
                    Logger.warning(f"⚠️ RPC 429 (Rate Limit) on {endpoint}")
                    self.rotate_rpc()
                    time.sleep(1)
                    continue
                    
                resp.raise_for_status()
                return resp.json()
                
            except Exception as e:
                Logger.warning(f"⚠️ RPC Fail ({endpoint}): {str(e)[:50]}")
                self.rotate_rpc()
        
        return None # Failed all retries

    def get_jupiter_quote(self, input_mint, output_mint, amount, slippage_bps=50):
        """
        Fetch quote from Jupiter with rate-limit protection.
        """
        try:
            self.check_jupiter_cooldown()
            
            url = f"{self.jupiter_url}/quote"
            params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": int(amount),
                "slippageBps": slippage_bps
            }
            
            resp = self._session.get(url, params=params, timeout=10)
            
            if resp.status_code == 429:
                self.trigger_jupiter_cooldown(15)  # 15s cooldown
                return None
            
            if resp.status_code != 200:
                Logger.error(f"Jupiter API Error: {resp.status_code} - {resp.text}")
                return None
            
            return resp.json()
            
        except Exception as e:
            Logger.error(f"Jupiter Quote Failed: {e}")
            return None

    def get_jupiter_price_v2(self, ids, vs_token="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"):
        """
        Fetch price from Jupiter V2 Price API (Official & Fast).
        Support batch requests: ids="mint1,mint2,mint3"
        """
        try:
            self.check_jupiter_cooldown()
            
            # V2 Endpoint
            url = "https://api.jup.ag/price/v2"
            params = {"ids": ids, "vsToken": vs_token}
            
            resp = self._session.get(url, params=params, timeout=5)
            
            if resp.status_code == 429:
                self.trigger_jupiter_cooldown(5)
                return None
                
            if resp.status_code != 200:
                Logger.warning(f"⚠️ Jupiter Price API {resp.status_code}")
                return None
            
            # V2 returns {"data": {"mint": {"id":..., "price":...}}}
            return resp.json().get("data", {})
            
        except Exception as e:
            Logger.debug(f"Jupiter Price V2 Failed: {e}")
            return None

    def get_jupiter_price(self, mint: str) -> Optional[float]:
        """Legacy alias for get_jupiter_price_v2 (single token)."""
        data = self.get_jupiter_price_v2(mint)
        if data and mint in data:
            price_str = data[mint].get("price", "0")
            return float(price_str) if price_str else 0.0
        return 0.0

    def get_swap_transaction(self, payload):
        """
        Fetch swap transaction from Jupiter V6 Swap API.
        """
        try:
            self.check_jupiter_cooldown()
            
            url = f"{self.jupiter_url}/swap"
            
            resp = self._session.post(url, json=payload, timeout=15)
            
            if resp.status_code == 429:
                self.trigger_jupiter_cooldown(15)
                return None
                
            if resp.status_code != 200:
                Logger.error(f"Jupiter Swap Error: {resp.status_code} - {resp.text}")
                return None
                
            return resp.json()
            
        except Exception as e:
            Logger.error(f"Jupiter Swap Failed: {e}")
            return None
