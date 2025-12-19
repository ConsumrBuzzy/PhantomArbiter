"""
V83.0: Token Standards Module
=============================
Centralized constants and detection for Solana token programs.

Supports:
- SPL Token (Original) - 95%+ of tokens
- Token-2022 (Extensions) - Newer tokens with features
"""

from typing import Optional, Dict, Tuple
from enum import Enum
from src.system.logging import Logger


class TokenStandard(Enum):
    """Token program standards."""
    SPL_TOKEN = "SPL_TOKEN"
    TOKEN_2022 = "TOKEN_2022"
    UNKNOWN = "UNKNOWN"


# Program IDs
SPL_TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

# Associated Token Program (same for both)
ASSOCIATED_TOKEN_PROGRAM_ID = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"

# Well-known tokens (for quick lookup)
KNOWN_TOKEN_STANDARDS: Dict[str, TokenStandard] = {
    # SOL wrapped
    "So11111111111111111111111111111111111111112": TokenStandard.SPL_TOKEN,
    # USDC
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": TokenStandard.SPL_TOKEN,
    # USDT
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": TokenStandard.SPL_TOKEN,
}


def detect_token_standard(mint: str, rpc_response: Optional[Dict] = None) -> TokenStandard:
    """
    Detect token standard from mint address.
    
    Args:
        mint: Token mint address
        rpc_response: Optional pre-fetched account info
        
    Returns:
        TokenStandard enum
    """
    # Check known tokens first
    if mint in KNOWN_TOKEN_STANDARDS:
        return KNOWN_TOKEN_STANDARDS[mint]
    
    # If we have RPC response, check owner
    if rpc_response and isinstance(rpc_response, dict):
        owner = rpc_response.get("owner")
        if owner == SPL_TOKEN_PROGRAM_ID:
            return TokenStandard.SPL_TOKEN
        elif owner == TOKEN_2022_PROGRAM_ID:
            return TokenStandard.TOKEN_2022
    
    # Default to SPL Token (most common)
    return TokenStandard.SPL_TOKEN


def detect_token_standard_rpc(mint: str) -> Tuple[TokenStandard, Optional[Dict]]:
    """
    Detect token standard by querying RPC.
    
    Returns:
        (TokenStandard, account_info)
    """
    # Check known tokens first
    if mint in KNOWN_TOKEN_STANDARDS:
        return KNOWN_TOKEN_STANDARDS[mint], None
    
    try:
        from src.infrastructure.rpc_balancer import get_rpc_balancer
        rpc = get_rpc_balancer()
        
        # Get account info
        response = rpc.post({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getAccountInfo",
            "params": [mint, {"encoding": "jsonParsed"}]
        })
        
        if response and "result" in response:
            value = response["result"].get("value")
            if value:
                owner = value.get("owner")
                if owner == TOKEN_2022_PROGRAM_ID:
                    Logger.debug(f"[TOKEN] {mint[:8]}... is Token-2022")
                    return TokenStandard.TOKEN_2022, value
                elif owner == SPL_TOKEN_PROGRAM_ID:
                    return TokenStandard.SPL_TOKEN, value
        
        return TokenStandard.SPL_TOKEN, None
        
    except Exception as e:
        Logger.debug(f"[TOKEN] Detection error for {mint[:8]}: {e}")
        return TokenStandard.SPL_TOKEN, None


def get_program_id(standard: TokenStandard) -> str:
    """Get program ID for token standard."""
    if standard == TokenStandard.TOKEN_2022:
        return TOKEN_2022_PROGRAM_ID
    return SPL_TOKEN_PROGRAM_ID


def is_token_2022(mint: str) -> bool:
    """Quick check if token uses Token-2022 program."""
    standard, _ = detect_token_standard_rpc(mint)
    return standard == TokenStandard.TOKEN_2022


# Cache for detected standards (avoid repeated RPC calls)
_token_standard_cache: Dict[str, TokenStandard] = {}

def get_cached_standard(mint: str) -> TokenStandard:
    """Get token standard with caching."""
    if mint not in _token_standard_cache:
        standard, _ = detect_token_standard_rpc(mint)
        _token_standard_cache[mint] = standard
    return _token_standard_cache[mint]


def cache_token_standard(mint: str, standard: TokenStandard):
    """Cache a token standard for future lookups."""
    _token_standard_cache[mint] = standard


# ═══════════════════════════════════════════════════════════════════
# V83.2: Transfer Fee Detection (Tax Token Support)
# ═══════════════════════════════════════════════════════════════════

# Known tax tokens (mints with transfer fees)
_known_tax_tokens: Dict[str, float] = {}  # {mint: fee_bps}


def has_transfer_fee(mint: str) -> Tuple[bool, float]:
    """
    V83.2: Check if a Token-2022 has transfer fees.
    
    Returns:
        (has_fee, fee_bps) - fee_bps is basis points (100 = 1%)
    """
    # Check cache first
    if mint in _known_tax_tokens:
        return True, _known_tax_tokens[mint]
    
    # Only Token-2022 can have transfer fees
    standard = get_cached_standard(mint)
    if standard != TokenStandard.TOKEN_2022:
        return False, 0.0
    
    # Query mint extensions for transfer fee
    try:
        from src.infrastructure.rpc_balancer import get_rpc_balancer
        rpc = get_rpc_balancer()
        
        response = rpc.post({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getAccountInfo",
            "params": [mint, {"encoding": "jsonParsed"}]
        })
        
        if response and "result" in response:
            value = response["result"].get("value", {})
            data = value.get("data", {})
            parsed = data.get("parsed", {}) if isinstance(data, dict) else {}
            info = parsed.get("info", {})
            extensions = info.get("extensions", [])
            
            for ext in extensions:
                if ext.get("extension") == "transferFeeConfig":
                    state = ext.get("state", {})
                    # Fee is in basis points (e.g., 500 = 5%)
                    fee_bps = state.get("newerTransferFee", {}).get("transferFeeBasisPoints", 0)
                    if fee_bps > 0:
                        _known_tax_tokens[mint] = fee_bps
                        Logger.info(f"⚠️ [TOKEN] {mint[:8]}... has {fee_bps/100:.1f}% transfer fee!")
                        return True, fee_bps
        
        return False, 0.0
        
    except Exception as e:
        Logger.debug(f"[TOKEN] Fee detection error: {e}")
        return False, 0.0


def get_effective_amount(mint: str, gross_amount: float) -> float:
    """
    V83.2: Calculate amount after transfer fee.
    
    Use this for PnL calculations on tax tokens.
    
    Args:
        mint: Token mint address
        gross_amount: Amount before fees
        
    Returns:
        Net amount after fees
    """
    has_fee, fee_bps = has_transfer_fee(mint)
    if not has_fee:
        return gross_amount
    
    # fee_bps is basis points (100 = 1%)
    fee_pct = fee_bps / 10000
    return gross_amount * (1 - fee_pct)


def is_high_risk_token(mint: str) -> Tuple[bool, str]:
    """
    V83.2: Flag tokens that may be high risk.
    
    Checks for:
    - Transfer fees (tax tokens)
    - Token-2022 extensions that affect trading
    
    Returns:
        (is_high_risk, reason)
    """
    has_fee, fee_bps = has_transfer_fee(mint)
    if has_fee:
        return True, f"Transfer fee: {fee_bps/100:.1f}%"
    
    standard = get_cached_standard(mint)
    if standard == TokenStandard.TOKEN_2022:
        # Token-2022 may have other risky extensions
        return False, "Token-2022 (no fee)"
    
    return False, "SPL Token (standard)"

