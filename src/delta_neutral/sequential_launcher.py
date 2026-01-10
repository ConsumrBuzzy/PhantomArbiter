import asyncio
import time
from typing import Optional, List

from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solders.instruction import Instruction
from solana.rpc.commitment import Confirmed
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts

from config.settings import Settings
from src.shared.system.logging import Logger
from src.shared.execution.wallet import WalletManager
from src.shared.execution.swapper import JupiterSwapper
from src.delta_neutral.types import RebalanceSignal, RebalanceDirection
from src.delta_neutral.drift_order_builder import DriftOrderBuilder

class SequentialLauncher:
    """
    Plan B: Sequential Execution (Legacy Mode).
    Bypasses Jito Block Engine.
    Executes Spot -> Wait -> Perp.
    Handles rollback (Panic Sell) if Perp fails.
    """
    
    def __init__(self, wallet_manager: WalletManager):
        self.wallet = wallet_manager
        self.swapper = JupiterSwapper(wallet_manager)
        # self.drift = DriftAdapter(wallet_manager) # Bypass faulty import
        
    async def initialize(self):
        Logger.info("[SEQUENTIAL] Initializing Legacy Mode...")
        # await self.drift.subscribe()
        Logger.info("[SEQUENTIAL] Ready.")

    async def execute_trade_sequence(self, signal: RebalanceSignal, spot_price: float) -> bool:
        """
        Execute trade sequentially with safety rollback.
        Returns True if successful, False if rolled back.
        """
        Logger.info(f"[SEQUENTIAL] Starting sequence for {signal}")
        
        # ---------------------------------------------------------
        # Step 1: Execute Spot Leg (The Lead)
        # ---------------------------------------------------------
        Logger.info("[SEQUENTIAL] Step 1: Executing Spot Leg (Jupiter)...")
        spot_success = await self._execute_spot_leg(signal, spot_price)
        
        if not spot_success:
            Logger.error("[SEQUENTIAL] Spot leg failed. Aborting sequence (No trades made).")
            return False
            
        Logger.info("[SEQUENTIAL] ✅ Spot confirmed. Proceeding to Perp...")
        
        # ---------------------------------------------------------
        # Step 2: Execute Perp Leg (The Follower)
        # ---------------------------------------------------------
        # Retry logic for Perp Leg
        perp_success = False
        for attempt in range(3):
            Logger.info(f"[SEQUENTIAL] Step 2: Executing Perp Leg (Drift) - Attempt {attempt+1}/3...")
            if await self._execute_perp_leg(signal):
                perp_success = True
                break
            await asyncio.sleep(1.0) # Short breath
            
        if perp_success:
            Logger.info("[SEQUENTIAL] ✅ Perp confirmed. Sequence COMPLETE.")
            Logger.info(f"[DNEM] Successfully opened delta-neutral position via Legacy Mode.")
            return True
            
        # ---------------------------------------------------------
        # Step 3: ROLLBACK (Panic Sell)
        # ---------------------------------------------------------
        # If we are here, Spot bought, but Perp failed. We are long unhedged.
        Logger.warning("[SEQUENTIAL] 🚨 CRITICAL: Perp leg failed 3 times! INITIATING ROLLBACK.")
        
        rollback_success = await self._execute_rollback(signal)
        
        if rollback_success:
            Logger.info("[SEQUENTIAL] ✅ Rollback successful. Neutrality restored (minus fees).")
        else:
            Logger.critical("[SEQUENTIAL] 💀 ROLLBACK FAILED! Urgent manual intervention required!")
            
        return False

    async def _execute_spot_leg(self, signal: RebalanceSignal, spot_price: float) -> bool:
        try:
            # 1. Build Jupiter Instructions
            SOL_MINT = "So11111111111111111111111111111111111111112"
            USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            
            if signal.direction == RebalanceDirection.ADD_SPOT:
                input_mint = USDC_MINT
                output_mint = SOL_MINT
                # Amount in USDC atomic units
                amount = int(signal.qty_usd * 1_000_000) 
            else:
                return False 
                
            quote = await self.swapper.get_quote(input_mint, output_mint, amount)
            if not quote:
                return False
                
            ixs = await self.swapper.get_swap_instructions(quote)
            if not ixs:
                return False
                
            # Send
            sig = await self._compile_and_send(ixs)
            return sig is not None
            
        except Exception as e:
            Logger.error(f"[SEQUENTIAL] Spot error: {e}")
            return False

    async def _execute_perp_leg(self, signal: RebalanceSignal) -> bool:
        try:
            # Build Drift Instructions
            builder = DriftOrderBuilder(Pubkey.from_string(self.wallet.get_public_key()))
            market = "SOL-PERP"
            
            # Assuming ADD_SPOT -> ADD_SHORT
            ixs = builder.build_short_order(market, signal.qty)
            
            sig = await self._compile_and_send(ixs)
            return sig is not None
            
        except Exception as e:
            Logger.error(f"[SEQUENTIAL] Perp error: {e}")
            return False

    async def _execute_rollback(self, original_signal: RebalanceSignal) -> bool:
        """Sell the SOL we just bought."""
        try:
            Logger.info("[SEQUENTIAL] Rolling back: SELLING SOL for USDC...")
            SOL_MINT = "So11111111111111111111111111111111111111112"
            USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            
            # Sell the exact qty we bought
            input_mint = SOL_MINT
            output_mint = USDC_MINT
            amount = int(original_signal.qty * 1_000_000_000) # SOL atomic
            
            quote = await self.swapper.get_quote(input_mint, output_mint, amount, slippage=500) # 5% panic slippage
            if not quote:
                return False
            
            ixs = await self.swapper.get_swap_instructions(quote)
            sig = await self._compile_and_send(ixs)
            
            return sig is not None
            
        except Exception as e:
            Logger.error(f"[SEQUENTIAL] Rollback error: {e}")
            return False

    async def _compile_and_send(self, instructions: List[Instruction]) -> Optional[str]:
        """Helper to compile MessageV0, Sign, and Send via RPC."""
        
        async with AsyncClient(Settings.RPC_URL) as client:
            try:
                # 1. Blockhash
                bh = (await client.get_latest_blockhash()).value.blockhash
                
                # 2. Message
                msg = MessageV0.try_compile(
                    payer=Pubkey.from_string(self.wallet.get_public_key()),
                    instructions=instructions,
                    address_lookup_table_accounts=[],
                    recent_blockhash=bh
                )
                
                # 3. Sign
                tx = VersionedTransaction(msg, [self.wallet.keypair])
                
                # 4. Send
                Logger.info("[SEQUENTIAL] Sending transaction...")
                # Create TxOpts properly
                opts = TxOpts(skip_confirmation=False, preflight_commitment=Confirmed)
                resp = await client.send_transaction(tx, opts=opts) 
                
                sig = resp.value
                Logger.info(f"[SEQUENTIAL] Tx Sent: {sig}")
                
                # 5. Confirm
                Logger.info("[SEQUENTIAL] Waiting for confirmation...")
                await client.confirm_transaction(sig, commitment=Confirmed)
                Logger.info("[SEQUENTIAL] Tx Confirmed!")
                
                return str(sig)
                
            except Exception as e:
                Logger.error(f"[SEQUENTIAL] Tx Failed: {e}")
                return None

async def main():
    Logger.info("=== PLAN B: SEQUENTIAL LAUNCHER ===")
    
    # 1. Setup
    wallet = WalletManager()
    launcher = SequentialLauncher(wallet)
    await launcher.initialize()
    
    # 2. Get Price
    Logger.info("Fetching SOL price...")
    async with AsyncClient(Settings.RPC_URL) as client:
        # Just use dummy read to ensure connection
        await client.get_version()
        Logger.info("RPC Connection: OK")
        
    # Assume $150 SOL.
    qty = 0.0033
    qty_usd = 0.50
    
    signal = RebalanceSignal(
        direction=RebalanceDirection.ADD_SPOT,
        qty=qty,
        qty_usd=qty_usd,
        current_drift_pct=0.0,
        reason="Manual Plan B",
        urgency=1
    )
    
    # 3. Execute
    Logger.info(f"Executing Manual Signal: {signal}")
    success = await launcher.execute_trade_sequence(signal, 150.0)
    
    if success:
        Logger.info("MISSION COMPLETE. Bypassed Jito Wall.")
    else:
        Logger.error("MISSION FAILED. Check logs.")

if __name__ == "__main__":
    asyncio.run(main())
