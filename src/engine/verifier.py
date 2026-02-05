import logging
import base64
from typing import Tuple
from src.shared.infrastructure.rpc_balancer import get_rpc_balancer

# Logger setup using the system logger if available, else standard
try:
    from src.shared.system.logging import Logger
    logger = Logger
except ImportError:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("Verifier")

TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
RENT_EXEMPT_MIN = 0.00203928  # SOL (Approx for 165 bytes)

def verify_target_viability(owner_pubkey: str) -> Tuple[int, float]:
    """
    Verifies if a target account has 'zombie' token accounts (0 balance).
    Uses the RPCBalancer framework for rate limiting and failover.
    
    Args:
        owner_pubkey: The Public Key of the target wallet.
        
    Returns:
        Tuple[count, total_reclaimable_value]
    """
    balancer = get_rpc_balancer()
    
    # Filter 1: Data Size = 165 bytes (Token Account)
    # Filter 2: Owner = owner_pubkey
    # Filter 3: Amount = 0 (The 8 bytes at offset 64 must be all 0s)
    
    filters = [
        {"dataSize": 165},
        {
            "memcmp": {
                "offset": 32, # Owner offset in Token Account
                "bytes": owner_pubkey
            }
        },
        # Check for 0 balance (u64 at offset 64)
        {
            "memcmp": {
                "offset": 64,
                "bytes": "11111111111" # Base58 for 8 zero bytes.
            }
        }
    ]
    
    params = [
        TOKEN_PROGRAM_ID,
        {
            "encoding": "jsonParsed",
            "filters": filters
        }
    ]
    
    try:
        # RPCBalancer.call is synchronous
        result, error = balancer.call("getProgramAccounts", params=params)
        
        if error:
            logger.error(f"RPC Error for {owner_pubkey}: {error}")
            return 0, 0.0
            
        accounts = result.get("result", [])
        if not accounts:
            return 0, 0.0
            
        zombie_count = 0
        total_rent = 0.0
        
        for acc in accounts:
            try:
                # Double check balance if jsonParsed
                # parsing might depend on RPC provider response format
                # If jsonParsed is strictly enforced:
                info = acc.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
                token_amount = info.get("tokenAmount", {}).get("amount", "0")
                
                if int(token_amount) == 0:
                    zombie_count += 1
                    total_rent += RENT_EXEMPT_MIN 
            except Exception:
                continue
                
        return zombie_count, total_rent

    except Exception as e:
        logger.error(f"Verification crashed for {owner_pubkey}: {e}")
        return 0, 0.0
