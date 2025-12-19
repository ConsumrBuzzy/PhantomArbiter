
import os
import base64
import requests
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.api import Client
from solana.rpc.types import TxOpts
from solana.rpc.commitment import Confirmed

from config.settings import Settings
from src.system.logging import Logger
from src.execution.wallet import WalletManager

from src.system.smart_router import SmartRouter

class JupiterSwapper:
    """
    V9.7: SRP-compliant Swap Executor.
    V12.3: Uses JITO private RPC for front-running protection.
    Responsibility: Quoting and Executing Swaps via Jupiter.
    """
    
    def __init__(self, wallet_manager: WalletManager):
        self.wallet = wallet_manager
        self.client = Client(Settings.RPC_URL)
        self.router = SmartRouter()
        
        # V12.3: JITO tip for block inclusion (1000 lamports = 0.000001 SOL)
        self.JITO_TIP_LAMPORTS = 1000
        
        # V12.3: Initialize JITO private RPC for execution
        self.jito_client = None
        self.jito_available = False
        jito_url = self.router.get_jito_execution_url()
        if jito_url:
            try:
                self.jito_client = Client(jito_url)
                self.jito_available = True
                Logger.info("🛡️ JITO Block Engine configured for front-running protection")
            except Exception as e:
                Logger.warning(f"⚠️ JITO unavailable, using standard execution: {e}")
        
    def execute_swap(self, direction, amount_usd, reason, target_mint=None):
        """
        Execute a Swap with Adaptive Slippage.
        """
        if not self.wallet.keypair: return None
        if not Settings.ENABLE_TRADING:
            if getattr(Settings, 'DRY_RUN_MODE', False):
                Logger.info(f"📝 DRY-RUN: Would {direction} ${amount_usd:.2f} of {target_mint or 'TARGET'}... ({reason})")
            else:
                Logger.info(f"🔒 TRADING DISABLED: Would {direction} ${amount_usd} ({reason})")
            return None

        SLIPPAGE_TIERS = Settings.ADAPTIVE_SLIPPAGE_TIERS
        mint = target_mint or Settings.TARGET_MINT
        Logger.info(f"🚀 EXECUTION: {direction} ${amount_usd} ({reason})")
        
        input_mint = Settings.USDC_MINT if direction == "BUY" else mint
        output_mint = mint if direction == "BUY" else Settings.USDC_MINT
        
        # Calculate amount
        if direction == "BUY":
            amount_atomic = int(amount_usd * 1_000_000)
        else:
            token_bal = self.wallet.get_balance(mint)
            if token_bal <= 0:
                Logger.error("❌ Sell Failed: No Balance")
                return None
            amount_atomic = int(token_bal * 1_000_000)
            Logger.info(f"📉 SELLING Entire Bag: {token_bal:.4f} tokens")
        
        for tier_idx, slippage_bps in enumerate(SLIPPAGE_TIERS):
            try:
                Logger.info(f"   📊 Tier {tier_idx+1}: Trying {slippage_bps/100:.1f}% slippage...")
                
                # V9.6: Use SmartRouter for Quote
                quote = self.router.get_jupiter_quote(input_mint, output_mint, amount_atomic, slippage_bps)
                if not quote or "error" in quote: continue
                
                payload = {
                    "quoteResponse": quote,
                    "userPublicKey": self.wallet.get_public_key(),
                    "wrapAndUnwrapSol": True,
                    "computeUnitPriceMicroLamports": Settings.PRIORITY_FEE_MICRO_LAMPORTS,
                    "dynamicSlippage": {"maxBps": slippage_bps + 200}
                }
                
                # V9.6: Use SmartRouter for Swap Tx
                swap_data = self.router.get_swap_transaction(payload)
                if not swap_data or "swapTransaction" not in swap_data: continue
                
                # Sign & Send
                raw_tx = base64.b64decode(swap_data["swapTransaction"])
                tx = VersionedTransaction.from_bytes(raw_tx)
                signed_tx = VersionedTransaction(tx.message, [self.wallet.keypair])
                
                opts = TxOpts(skip_preflight=False, preflight_commitment=Confirmed)
                
                # V12.3: Use JITO private RPC for front-running protection
                if self.jito_available and self.jito_client:
                    try:
                        Logger.info("   🛡️ Sending via JITO private relay...")
                        tx_sig = self.jito_client.send_transaction(signed_tx, opts=opts)
                        Logger.success(f"✅ JITO Tx Sent: https://solscan.io/tx/{tx_sig.value}")
                    except Exception as jito_err:
                        Logger.warning(f"   ⚠️ JITO failed, falling back to standard: {jito_err}")
                        tx_sig = self.client.send_transaction(signed_tx, opts=opts)
                        Logger.success(f"✅ Tx Sent (Standard): https://solscan.io/tx/{tx_sig.value}")
                else:
                    tx_sig = self.client.send_transaction(signed_tx, opts=opts)
                    Logger.success(f"✅ Tx Sent: https://solscan.io/tx/{tx_sig.value}")
                
                # Invalidate Cache
                try:
                    from src.core.shared_cache import SharedPriceCache
                    SharedPriceCache.invalidate_wallet_state()
                except: pass
                
                return str(tx_sig.value)
                
            except Exception as e:
                error_str = str(e)
                if "0x1788" in error_str or "6024" in error_str:
                    if tier_idx < len(SLIPPAGE_TIERS) - 1:
                        Logger.warning(f"   ⚠️ Slippage exceeded at Tier {tier_idx+1}, escalating...")
                        continue
                Logger.error(f"❌ Execution Error: {e}")
                
        Logger.error("❌ All slippage tiers exhausted")
        return None
