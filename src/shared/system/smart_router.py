import json
import os
import requests
import time
from config.settings import Settings
from src.shared.system.logging import Logger
from typing import Optional, Dict


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
        self._initialized = True

        self.config = self._load_config()
        self.enabled = getattr(Settings, "ENABLE_SMART_ROUTING", True)

        # V41.1: Hybrid loading - Prefers Settings, falls back to JSON config
        self.endpoints = getattr(Settings, "jito_endpoints", [])
        if not self.endpoints and self.config:
            self.endpoints = self.config.get("endpoints", [])

        self.health_map = {}
        self.latency_map = {}

        # V11.9: Load and filter endpoints (skip disabled, filter missing keys)
        # DEPRECATED: self.endpoints = self._get_valid_endpoints()
        # V12.0: Use official api.jup.ag endpoint (resolvable)
        self.jupiter_url = self.config.get(
            "JUPITER_API_BASE", "https://api.jup.ag/swap/v1"
        )

        # Load and clean API Key
        self.jupiter_api_key = os.getenv("JUPITER_API_KEY", "").strip("'\" ")
        if (
            self.jupiter_api_key.lower() in ["none", "null", ""]
            or len(self.jupiter_api_key) < 5
        ):
            self.jupiter_api_key = ""

        self.jupiter_cooldown_until = 0

        # V131: Persistent HTTP session with connection pooling
        # Reuses TCP connections for ~50-100ms savings per request
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})
        if self.jupiter_api_key:
            self._session.headers.update({"x-api-key": self.jupiter_api_key})

        Logger.info(
            f"🌐 SmartRouter initialized with {len(self.endpoints)} RPC endpoints."
        )
        if self.jupiter_api_key:
            Logger.info("   🔑 Jupiter API Key loaded")

    def _load_config(self):
        """Load rpc_pool.json or return defaults."""
        config_path = os.path.join(
            os.path.dirname(__file__), "../../../config/rpc_pool.json"
        )
        try:
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    return json.load(f)
        except Exception as e:
            Logger.error(f"Failed to load rpc_pool.json: {e}")
        return {}

    def _get_valid_endpoints(self):
        """Deprecated: Logic moved to RPCBalancer."""
        return []

    def get_rpc_url(self):
        """Deprecated: Use RPCBalancer."""
        return Settings.RPC_URL

    def get_jito_execution_url(self):
        """
        V12.3: Get JITO block engine URL for private transaction execution.
        Supports regional pinning via JITO_REGION env var.
        """
        region = os.getenv("JITO_REGION", "").lower()
        config = self._load_config()

        # If region is specified, try to find matching regional Jito
        if region:
            for endpoint in config.get("endpoints", []):
                if endpoint.get("execution_only") and endpoint.get("enabled"):
                    if region in endpoint.get("name", "").lower():
                        return endpoint.get("url")

        # Fallback to first enabled Jito endpoint
        for endpoint in config.get("endpoints", []):
            if endpoint.get("execution_only") and endpoint.get("enabled"):
                return endpoint.get("url")
        return None

    def rotate_rpc(self):
        """Deprecated: Handled by RPCBalancer."""
        pass

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

    def json_rpc_call(self, method, params, retries=None):
        """
        Execute a standard JSON-RPC call via RPCBalancer.
        """
        # Delegate to the shared RPC Balancer
        from src.shared.infrastructure.rpc_balancer import get_rpc_balancer

        balancer = get_rpc_balancer()

        result, error = balancer.call(method, params, retries=retries)

        if error:
            Logger.warning(f"⚠️ RPC Fail: {error}")
            return None

        return result.get("result") if result else None

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
                "slippageBps": slippage_bps,
            }

            resp = self._session.get(url, params=params, timeout=10)

            if resp.status_code == 429:
                self.trigger_jupiter_cooldown(15)  # 15s cooldown
                return None

            # V41.2: Auto-Fallback for Invalid Key (401)
            if resp.status_code == 401 and self.jupiter_api_key:
                Logger.warning("⚠️ Jupiter 401 Unauthorized. Removing invalid API key and retrying...")
                self.jupiter_api_key = ""
                if "x-api-key" in self._session.headers:
                    del self._session.headers["x-api-key"]
                
                # Retry without key
                return self.get_jupiter_quote(input_mint, output_mint, amount, slippage_bps)

            if resp.status_code != 200:
                Logger.error(f"Jupiter API Error: {resp.status_code} - {resp.text}")
                return None

            return resp.json()

        except Exception as e:
            Logger.error(f"Jupiter Quote Failed: {e}")
            return None

    def get_jupiter_price_v2(
        self, ids, vs_token="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    ):
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

    def get_jupiter_price(self, ids: str, vs_token: str = None) -> Optional[Dict]:
        """Legacy alias for get_jupiter_price_v2. Supports ids='mint1,mint2'."""
        data = self.get_jupiter_price_v2(ids, vs_token)
        if data:
            return {"data": data}
        return {"data": {}}

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

            # V41.2: Auto-Fallback for Invalid Key (401)
            if resp.status_code == 401 and self.jupiter_api_key:
                Logger.warning("⚠️ Jupiter Swap 401 Unauthorized. Retrying without key...")
                self.jupiter_api_key = ""
                if "x-api-key" in self._session.headers:
                    del self._session.headers["x-api-key"]
                
                # Retry
                return self.get_swap_transaction(payload)

            if resp.status_code != 200:
                Logger.error(f"Jupiter Swap Error: {resp.status_code} - {resp.text}")
                return None

            return resp.json()

        except Exception as e:
            Logger.error(f"Jupiter Swap Failed: {e}")
            return None
