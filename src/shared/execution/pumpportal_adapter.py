"""
V52.0: PumpPortal Adapter
=========================
Adapter for direct bonding curve trading via PumpPortal.fun Local API.
Allows sniping tokens before they migrate to Raydium.

Endpoint: POST https://pumpportal.fun/api/trade-local
Docs: https://pumpportal.fun/local-trading-api/trading-api
"""

import requests
import base58
import logging
from config.settings import Settings
from src.shared.system.logging import Logger

# Solana / Solders
from solders.transaction import VersionedTransaction
from solders.keypair import Keypair
from solders.commitment_config import CommitmentLevel
from solders.rpc.config import RpcSendTransactionConfig

# Use solana.rpc for sending if available, otherwise direct RPC request
from solana.rpc.api import Client

class PumpPortalAdapter:
    """
    Adapter for executing trades on Pump.fun bonding curves.
    Uses 'trade-local' API to get unsigned transaction, then signs locally.
    """
    
    def __init__(self, private_key_b58: str = None):
        """
        Initialize adapter with private key for signing.
        
        Args:
            private_key_b58: Base58 encoded private key. If None, loads from Settings.
        """
        self.api_url = getattr(Settings, "PUMP_PORTAL_API_URL", "https://pumpportal.fun/api/trade-local")
        
        # Load Keypair
        pk_str = private_key_b58 or getattr(Settings, "PRIVATE_KEY", None)
        if not pk_str:
            raise ValueError("Private Key required for PumpPortalAdapter")
            
        try:
            # Decode private key
            self.keypair = Keypair.from_base58_string(pk_str)
            self.pubkey_str = str(self.keypair.pubkey())
            Logger.info(f"💊 [PUMP] Adapter initialized for wallet: {self.pubkey_str[:8]}...")
        except Exception as e:
            Logger.error(f"❌ [PUMP] Invalid Private Key: {e}")
            raise
            
        # RPC Client for sending transactions
        self.rpc_client = Client(Settings.GEYSER_RPC_URL or Settings.RPC_URL)

    def generate_transaction(
        self,
        action: str,
        mint: str,
        amount: float,
        slippage_pct: float = 10.0,
        denominated_in_sol: bool = True,
        priority_fee: float = 0.00005,
        pool: str = "pump"
    ) -> VersionedTransaction:
        """
        Fetch unsigned transaction from PumpPortal API.
        
        Args:
            action: 'buy' or 'sell'
            mint: Token CA
            amount: Amount in SOL (if buy) or Tokens (if sell) typically
            slippage_pct: Slippage tolerance (default 10%)
            denominated_in_sol: True if amount is SOL, False if tokens
            priority_fee: Jito/Priority fee in SOL
            pool: 'pump', 'raydium', or 'auto'
            
        Returns:
            VersionedTransaction: Unsigned transaction object
        """
        payload = {
            "publicKey": self.pubkey_str,
            "action": action.lower(),
            "mint": mint,
            "denominatedInSol": "true" if denominated_in_sol else "false",
            "amount": amount,
            "slippage": slippage_pct,
            "priorityFee": priority_fee,
            "pool": pool
        }
        
        try:
            response = requests.post(self.api_url, json=payload, timeout=5)
            
            if response.status_code != 200:
                Logger.error(f"❌ [PUMP] API Error ({response.status_code}): {response.text}")
                return None
                
            # Response is the binary transaction
            tx_bytes = response.content
            
            # Deserialize
            tx = VersionedTransaction.from_bytes(tx_bytes)
            return tx
            
        except Exception as e:
            Logger.error(f"❌ [PUMP] Failed to generate transaction: {e}")
            return None

    def sign_and_send(self, tx: VersionedTransaction) -> str:
        """
        Sign and send the transaction to the network.
        
        Args:
            tx: Unsigned VersionedTransaction
            
        Returns:
            str: Transaction Signature (txid) or None if failed
        """
        if not tx:
            return None
            
        try:
            # Sign
            # message = tx.message
            # recent_blockhash = message.recent_blockhash
            
            # Sign with keypair
            tx = VersionedTransaction(tx.message, [self.keypair])
            
            # Send
            # We use the configured RPC client
            opts = RpcSendTransactionConfig(skip_preflight=True, max_retries=3)
            result = self.rpc_client.send_transaction(tx, opts=opts)
            
            sig = str(result.value)
            Logger.info(f"🚀 [PUMP] Transaction Sent: {sig}")
            return sig
            
        except Exception as e:
            Logger.error(f"❌ [PUMP] Failed to sign/send: {e}")
            return None

    def execute_trade(self, action: str, mint: str, amount: float, **kwargs):
        """Convenience method to generate, sign, and send."""
        Logger.info(f"💊 [PUMP] Generating {action.upper()} for {mint[:8]}... (Amt: {amount})")
        tx = self.generate_transaction(action, mint, amount, **kwargs)
        if tx:
            return self.sign_and_send(tx)
        return None

# Test Block
if __name__ == "__main__":
    import asyncio
    print("Testing PumpPortalAdapter...")
    try:
        # Requires PRIVATE_KEY in .env or Settings
        adapter = PumpPortalAdapter()
        # Example: Fetch price or sim (API doesn't support dry-run read easily without payload)
        print("✅ Adapter initialized successfully")
    except Exception as e:
        print(f"❌ Init failed (expected if no key): {e}")
