import os
from dataclasses import dataclass

@dataclass
class InfrastructureConfig:
    rpc_url: str = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
    wss_url: str = os.getenv("WSS_URL", "wss://api.mainnet-beta.solana.com")
    jito_api_url: str = "https://mainnet.block-engine.jito.wtf"
    jupiter_quote_api: str = "https://quote-api.jup.ag/v6"
    jito_tip_account: str = "96g9sAg9CeGguRiYp9YmNTSUky1F9p7hYy1B52B7WAbA"
    
    # API Keys
    coingecko_key: str = os.getenv("COINGECKO_API_KEY", "")
    bitquery_key: str = os.getenv("BITQUERY_API_KEY", "")
    
    # Network Limits
    thread_pool_workers: int = 4
    init_delay_sec: int = 5
