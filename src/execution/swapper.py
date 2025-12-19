
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
        
    def execute_swap(self, direction, amount_usd, reason, target_mint=None, priority_fee=None, override_atomic_amount=None):
        """
        Execute a Swap with Adaptive Slippage.
        """
        if not self.wallet.keypair:
            Logger.error("❌ FAILED: No wallet keypair loaded!")
            return None
            
        if not Settings.ENABLE_TRADING:
            Logger.info(f"🔒 TRADING DISABLED: Would {direction} ${amount_usd} ({reason})")
            return None

        # Defines
        mint = target_mint or Settings.TARGET_MINT
        input_mint = Settings.USDC_MINT if direction == "BUY" else mint
        output_mint = mint if direction == "BUY" else Settings.USDC_MINT
        
        # Calculate amount
        amount_atomic = 0
        if direction == "BUY":
            amount_atomic = int(amount_usd * 1_000_000)
        else:
            # SELL Direction (With HODL Protection)
            token_info = self.wallet.get_token_info(mint)
            if not token_info: 
                Logger.error("❌ Sell Failed: No Balance helper")
                return None
            
            avail_atomic = int(token_info["amount"])
            
            if override_atomic_amount:
                # Sell EXACTLY what we bought (Protection)
                amount_atomic = min(avail_atomic, int(override_atomic_amount))
                Logger.info(f"📉 SELLING Acquired Amount: {amount_atomic} units (HODL Protected)")
            elif amount_usd > 0:
                 # Start with ALL if no atomic override provided (Fallback)
                 amount_atomic = avail_atomic 
            else:
                 amount_atomic = avail_atomic
                 Logger.info(f"📉 SELLING Entire Bag: {float(token_info['uiAmount']):.4f} tokens")
                 
        SLIPPAGE_TIERS = Settings.ADAPTIVE_SLIPPAGE_TIERS
        Logger.info(f"🚀 EXECUTION: {direction} ${amount_usd} ({reason})")
        
        for tier_idx, slippage_bps in enumerate(SLIPPAGE_TIERS):
            try:
                Logger.info(f"   📊 Tier {tier_idx+1}: Trying {slippage_bps/100:.1f}% slippage...")
                
                # V9.6: Use SmartRouter for Quote
                quote = self.router.get_jupiter_quote(input_mint, output_mint, amount_atomic, slippage_bps)
                if not quote or "error" in quote: continue
                
                payload = {
                    "quoteResponse": quote,
                    "userPublicKey": str(self.wallet.get_public_key()),
                    "wrapAndUnwrapSol": True,
                    "computeUnitPriceMicroLamports": priority_fee if priority_fee is not None else int(Settings.PRIORITY_FEE_MICRO_LAMPORTS),
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

    async def recover_gas(self, input_mint: str, amount_usd: float):
        """
        Universal Gas Recovery.
        Swaps 'amount_usd' worth of 'input_mint' for SOL.
        Uses 2-step Quote to determine input amount.
        """
        try:
            Logger.info(f"⛽ Universal Recovery: Attempting to swap ${amount_usd} of {input_mint[:4]}... -> SOL")
            
            # Simple heuristic for now: Swap 5% of tokens? No, need precision.
            # Use Token Info to get decimals
            info = self.wallet.get_token_info(input_mint)
            if not info: 
                Logger.error("❌ Token info not found")
                return
                
            decimals = int(info["decimals"])
            avail_atomic = int(info["amount"])
            
            # Strategy: We don't have price. 
            # HEURISTIC: Swap 1000 units?
            # Better: Just try to swap 10% of the bag if it's large?
            # Or use SmartRouter to get quote for 1 unit -> SOL?
            
            router = SmartRouter()
            SOL_MINT = "So11111111111111111111111111111111111111112"
            
            # 1. Price Check (1 unit)
            test_amount = 10 ** decimals
            if test_amount > avail_atomic: test_amount = avail_atomic // 10
            if test_amount == 0: return # Dust
            
            quote = router.get_jupiter_quote(input_mint, SOL_MINT, test_amount)
            if not quote or "outAmount" not in quote:
                Logger.error("❌ Price check failed")
                return
            
            sol_out = int(quote["outAmount"]) / 10**9
            # Price of 1 token in SOL = sol_out
            if sol_out == 0: return
            
            TARGET_SOL = 0.03 # Target ~0.03 SOL ($5-6)
            needed_tokens = TARGET_SOL / sol_out
            amount_atomic = int(needed_tokens * (10**decimals))
            
            if amount_atomic > avail_atomic: amount_atomic = avail_atomic
            
            Logger.info(f"   📉 Converting {amount_atomic / 10**decimals:.4f} tokens to Gas...")
            
            # 2. Execute
            payload = {
                "quoteResponse": router.get_jupiter_quote(input_mint, SOL_MINT, amount_atomic, slippage_bps=500),
                "userPublicKey": str(self.wallet.keypair.pubkey()),
                "wrapAndUnwrapSol": True,
                "computeUnitPriceMicroLamports": 100000 
            }
            
            tx_data = router.get_swap_transaction(payload)
            if tx_data:
                raw_tx = base64.b64decode(tx_data["swapTransaction"])
                tx = VersionedTransaction.from_bytes(raw_tx)
                
                # Sign manually
                signed_tx = VersionedTransaction(tx.message, [self.wallet.keypair])
                
                client = Client(Settings.RPC_URL)
                sig = client.send_transaction(signed_tx, opts=TxOpts(skip_preflight=True)).value
                Logger.success(f"   ✅ Gas Refilled: {sig}")
                return sig
                
        except Exception as e:
            Logger.error(f"❌ Recovery Failed: {e}")
