"""
Stuck Token Guard
==================
V120: Detects unexpected tokens in wallet and attempts auto-recovery.

Features:
- Scans wallet for SPL tokens (besides USDC/SOL)
- Alerts on detection
- Attempts auto-sell back to USDC via Jupiter

Usage:
    from src.arbiter.core.stuck_token_guard import StuckTokenGuard
    
    guard = StuckTokenGuard()
    stuck = guard.check_wallet()  # Returns list of stuck tokens
    
    if stuck:
        guard.attempt_recovery(stuck)  # Try to sell back to USDC
"""

import os
import time
import requests
from typing import List, Dict, Optional
from dataclasses import dataclass

from config.settings import Settings
from src.shared.system.logging import Logger
from src.shared.system.smart_router import SmartRouter


# Known "safe" tokens we expect to hold
SAFE_MINTS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "So11111111111111111111111111111111111111112",   # Wrapped SOL
}


@dataclass
class StuckToken:
    """Represents a token that shouldn't be in the wallet."""
    mint: str
    symbol: str
    balance: float
    decimals: int
    value_usd: float


class StuckTokenGuard:
    """
    V120: Monitors wallet for stuck tokens and attempts recovery.
    
    Stuck tokens occur when:
    - Buy leg of arb succeeds but sell leg fails
    - Manual testing leaves residual tokens
    - Emergency situations
    """
    
    def __init__(self):
        self.router = SmartRouter()
        self.rpc_url = os.getenv("RPC_URL", Settings.RPC_URLS[0] if hasattr(Settings, 'RPC_URLS') else "")
        self.wallet_pubkey = self._get_wallet_pubkey()
        
        # Recovery settings
        self.MIN_VALUE_TO_RECOVER = 0.10  # Don't bother with dust < $0.10
        self.SLIPPAGE_BPS = 300  # 3% slippage for emergency sells
        
    def _get_wallet_pubkey(self) -> Optional[str]:
        """Get wallet public key from environment."""
        try:
            private_key = os.getenv("SOLANA_PRIVATE_KEY", "")
            if not private_key:
                return None
            
            from solders.keypair import Keypair
            import base58
            
            keypair = Keypair.from_bytes(base58.b58decode(private_key))
            return str(keypair.pubkey())
        except Exception as e:
            Logger.warning(f"[GUARD] Could not load wallet: {e}")
            return None
    
    def check_wallet(self) -> List[StuckToken]:
        """
        Scan wallet for unexpected SPL tokens.
        
        Returns:
            List of StuckToken objects for tokens that shouldn't be there
        """
        if not self.wallet_pubkey:
            Logger.warning("[GUARD] No wallet configured, skipping stuck token check")
            return []
        
        stuck_tokens = []
        
        try:
            # Fetch all token accounts
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [
                    self.wallet_pubkey,
                    {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                    {"encoding": "jsonParsed"}
                ]
            }
            
            response = requests.post(self.rpc_url, json=payload, timeout=10)
            data = response.json()
            
            accounts = data.get("result", {}).get("value", [])
            
            for account in accounts:
                parsed = account.get("account", {}).get("data", {}).get("parsed", {})
                info = parsed.get("info", {})
                
                mint = info.get("mint", "")
                token_amount = info.get("tokenAmount", {})
                balance = float(token_amount.get("uiAmount", 0) or 0)
                decimals = token_amount.get("decimals", 9)
                
                # Skip if no balance or safe token
                if balance <= 0 or mint in SAFE_MINTS:
                    continue
                
                # This is a stuck token!
                symbol = self._get_symbol(mint)
                value_usd = self._get_value_usd(mint, balance)
                
                stuck_tokens.append(StuckToken(
                    mint=mint,
                    symbol=symbol,
                    balance=balance,
                    decimals=decimals,
                    value_usd=value_usd
                ))
                
                Logger.warning(f"[GUARD] 🚨 STUCK TOKEN: {balance:.4f} {symbol} (${value_usd:.2f})")
        
        except Exception as e:
            Logger.error(f"[GUARD] Error checking wallet: {e}")
        
        return stuck_tokens
    
    def _get_symbol(self, mint: str) -> str:
        """Get token symbol from mint."""
        try:
            from src.shared.infrastructure.token_registry import TokenRegistry
            registry = TokenRegistry()
            result = registry.get_symbol(mint)
            if result:
                return result[0]
        except:
            pass
        return mint[:8] + "..."
    
    def _get_value_usd(self, mint: str, balance: float) -> float:
        """Get USD value of token balance."""
        try:
            price_data = self.router.get_jupiter_price_v2(mint)
            if price_data and "data" in price_data:
                price = float(price_data["data"].get(mint, {}).get("price", 0))
                return balance * price
        except:
            pass
        return 0.0
    
    def attempt_recovery(self, stuck_tokens: List[StuckToken]) -> Dict[str, bool]:
        """
        Attempt to sell stuck tokens back to USDC.
        
        Args:
            stuck_tokens: List of StuckToken to recover
            
        Returns:
            Dict of {mint: success} for each attempt
        """
        results = {}
        USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        
        for token in stuck_tokens:
            if token.value_usd < self.MIN_VALUE_TO_RECOVER:
                Logger.info(f"[GUARD] Skipping {token.symbol} (value ${token.value_usd:.2f} < min ${self.MIN_VALUE_TO_RECOVER})")
                results[token.mint] = False
                continue
            
            Logger.info(f"[GUARD] 🔄 Attempting recovery: {token.balance:.4f} {token.symbol} → USDC")
            
            try:
                # Get amount in smallest units
                amount = int(token.balance * (10 ** token.decimals))
                
                # Get quote
                quote = self.router.get_jupiter_quote(
                    token.mint,
                    USDC_MINT,
                    amount,
                    slippage_bps=self.SLIPPAGE_BPS
                )
                
                if not quote:
                    Logger.warning(f"[GUARD] No quote available for {token.symbol}")
                    results[token.mint] = False
                    continue
                
                expected_usdc = int(quote.get("outAmount", 0)) / 1_000_000
                Logger.info(f"[GUARD] Quote: {token.balance:.4f} {token.symbol} → ${expected_usdc:.2f} USDC")
                
                # V131: Actually execute the swap
                try:
                    import base64
                    from solders.keypair import Keypair
                    from solders.transaction import VersionedTransaction
                    
                    # Get swap transaction
                    swap_data = self.router.get_swap_transaction({
                        "quoteResponse": quote,
                        "userPublicKey": self.wallet_pubkey,
                        "wrapAndUnwrapSol": True,
                        "dynamicComputeUnitLimit": True,
                        "prioritizationFeeLamports": 100000
                    })
                    
                    if not swap_data or 'swapTransaction' not in swap_data:
                        Logger.warning(f"[GUARD] Could not get swap tx for {token.symbol}")
                        results[token.mint] = False
                        continue
                    
                    # Sign and send
                    private_key = os.getenv("SOLANA_PRIVATE_KEY", "")
                    keypair = Keypair.from_base58_string(private_key)
                    
                    tx_bytes = base64.b64decode(swap_data['swapTransaction'])
                    tx = VersionedTransaction.from_bytes(tx_bytes)
                    signed_tx = VersionedTransaction(tx.message, [keypair])
                    signed_b64 = base64.b64encode(bytes(signed_tx)).decode()
                    
                    # Send via RPC
                    send_result = requests.post(self.rpc_url, json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "sendTransaction",
                        "params": [signed_b64, {"encoding": "base64", "skipPreflight": False}]
                    }, timeout=15)
                    
                    if send_result.status_code == 200:
                        result_json = send_result.json()
                        if "result" in result_json:
                            sig = result_json["result"]
                            Logger.info(f"[GUARD] ✅ Recovery SUCCESS: {token.symbol} → USDC | Tx: {sig[:20]}...")
                            print(f"   ✅ [GUARD] Recovered {token.symbol} → ${expected_usdc:.2f} USDC")
                            results[token.mint] = True
                            continue
                        elif "error" in result_json:
                            Logger.warning(f"[GUARD] RPC error: {result_json['error']}")
                    
                    Logger.warning(f"[GUARD] Recovery send failed for {token.symbol}")
                    results[token.mint] = False
                    
                except Exception as swap_error:
                    Logger.error(f"[GUARD] Swap execution error: {swap_error}")
                    results[token.mint] = False
                
            except Exception as e:
                Logger.error(f"[GUARD] Recovery failed for {token.symbol}: {e}")
                results[token.mint] = False
        
        return results
    
    def run_check(self) -> int:
        """
        Run a single stuck token check and recovery attempt.
        
        Returns:
            Number of stuck tokens found
        """
        stuck = self.check_wallet()
        
        if not stuck:
            Logger.debug("[GUARD] ✅ No stuck tokens detected")
            return 0
        
        Logger.warning(f"[GUARD] 🚨 Found {len(stuck)} stuck token(s)")
        
        # Attempt recovery
        self.attempt_recovery(stuck)
        
        return len(stuck)


# ═══════════════════════════════════════════════════════════════════
# Test
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    print("=" * 60)
    print("Stuck Token Guard - Test")
    print("=" * 60)
    
    guard = StuckTokenGuard()
    
    print(f"\nWallet: {guard.wallet_pubkey}")
    print(f"RPC: {guard.rpc_url[:40]}...")
    
    print("\nChecking for stuck tokens...")
    stuck = guard.check_wallet()
    
    if stuck:
        print(f"\n🚨 Found {len(stuck)} stuck token(s):")
        for t in stuck:
            print(f"   - {t.balance:.4f} {t.symbol} = ${t.value_usd:.2f}")
        
        print("\nAttempting recovery...")
        results = guard.attempt_recovery(stuck)
        print(f"Results: {results}")
    else:
        print("\n✅ No stuck tokens found!")
    
    print("\n" + "=" * 60)
