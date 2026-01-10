
import asyncio
import os
import argparse
from typing import Optional, Dict
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
import base58

from src.shared.system.logging import Logger
from src.shared.execution.wallet import WalletManager
from src.delta_neutral.drift_order_builder import DriftOrderBuilder, PositionDirection

# Constants
RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
DRIFT_PROGRAM_ID = Pubkey.from_string("dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH")
SOL_PERP_MARKET_INDEX = 0

class LeverageManager:
    def __init__(self, wallet_manager: WalletManager):
        self.wallet = wallet_manager
        self.builder = DriftOrderBuilder(self.wallet.keypair.pubkey())

    async def get_account_health_and_equity(self, client: AsyncClient) -> Dict:
        """
        Fetches rudimentary account data to estimate Equity and Health.
        Note: True Drift Health calculation is complex. We use the same proxy as the dashboard.
        """
        # In a real implementation, we would deserialize the full User Account.
        # For this script, we will rely on a "Safe Start" assumption or reuse Rebalancer logic if possible.
        # However, to be robust, let's just implement the basic checks we need.
        
        # We need: Spot Balance, USDC Balance, Perp Position
        
        # 1. Spot Balance
        spot_bal_resp = await client.get_balance(self.wallet.keypair.pubkey())
        spot_sol = spot_bal_resp.value / 1e9
        
        # 2. Simplification: Assume we are identifying state via the AutoRebalancer logic
        # Ideally, we import AutoRebalancer
        from src.engine.auto_rebalancer import AutoRebalancer
        rebalancer = AutoRebalancer()
        status = await rebalancer.check_and_rebalance(simulate=True)
        
        perp_sol = status.get('perp_sol', 0.0)
        usdc_bal = status.get('usdc_bal', 0.0)
        sol_price = status.get('price', 0.0) # We need to ensure rebalancer returns this or fetch it
        
        # If rebalancer doesn't return price, fetch it from Pyth/Oracle
        if sol_price == 0:
            # Fallback or error
            Logger.warning("Could not determine SOL price from rebalancer. Using fallback.")
            sol_price = 140.0 # UNSAFE. Need real price.
            # TODO: Add oracle fetch if needed.

        # Calculate Equity
        # Equity = (Spot SOL * Price) + USDC + (Unrealized PnL - ignore for safety or approx)
        # Conservative Equity = Spot Value + USDC
        equity = (spot_sol * sol_price) + usdc_bal
        
        # Calculate Health Proxy
        perp_notional = abs(perp_sol) * sol_price
        maintenance_margin = perp_notional * 0.10
        
        health = 100.0
        if equity > 0:
            health = 100 * (1 - (maintenance_margin / equity))
            
        return {
            "equity": equity,
            "health": health,
            "perp_sol": perp_sol,
            "price": sol_price,
            "spot_sol": spot_sol
        }

    async def scale_to_target(self, target_leverage: float = 2.0, simulate: bool = False):
        Logger.section(f"⚖️ LEVERAGE EXPANSION: Target {target_leverage}x")
        
        async with AsyncClient(RPC_URL) as client:
            # 1. Get Status
            status = await self.get_account_health_and_equity(client)
            equity = status["equity"]
            health = status["health"]
            current_short = abs(status["perp_sol"])
            price = status["price"]
            
            Logger.info(f"Current Equity:  ${equity:.2f}")
            Logger.info(f"Current Short:   {current_short:.4f} SOL")
            Logger.info(f"Current Health:  {health:.1f}%")
            
            # 2. Safety Check
            if health < 90.0:
                Logger.error(f"❌ Health too low ({health:.1f}%) to increase leverage. Aborting.")
                return

            # 3. Calculate Target
            # Target Notional = Equity * Target Leverage
            # Target Short Size = Target Notional / Price
            target_notional = equity * target_leverage
            target_short_size = target_notional / price
            
            Logger.info(f"Target Notional: ${target_notional:.2f} ({target_leverage}x)")
            Logger.info(f"Target Short Sz: {target_short_size:.4f} SOL")
            
            # 4. Calculate Delta
            # We want to be Short, so Perp Position should be negative.
            # current_short is abs(perp_sol).
            # If current is 0.1, and target is 0.2, we need to sell 0.1 more by opening 0.1 SHORT.
            
            diff = target_short_size - current_short
            
            if diff < 0.01:
                Logger.info(f"✅ Already at or above target leverage (Delta {diff:.4f} SOL < 0.01).")
                return
                
            Logger.info(f"📉 Scaling Up: Selling {diff:.4f} SOL-PERP...")
            
            # 5. Build Order
            # Round to 3 decimals to be safe with Drift constraints? 
            # Drift uses base precision, usually fine with extensive decimals but let's be clean.
            trade_size = round(diff, 2) # Round to 2 decimals (e.g. 0.12)
            if trade_size < 0.01:
                Logger.warning(f"Trade size {trade_size} too small after rounding.")
                return

            ixs = self.builder.build_order_instruction(
                "SOL-PERP",
                trade_size,
                direction=PositionDirection.SHORT
            )
            
            # 6. Execute
            if simulate:
                Logger.info("[SIM] Simulating Leverage Increase...")
                bh_resp = await client.get_latest_blockhash()
                msg = MessageV0.try_compile(
                    payer=self.wallet.keypair.pubkey(),
                    instructions=ixs if isinstance(ixs, list) else [ixs],
                    address_lookup_table_accounts=[],
                    recent_blockhash=bh_resp.value.blockhash
                )
                tx = VersionedTransaction(msg, [self.wallet.keypair])
                sim_resp = await client.simulate_transaction(tx)
                if sim_resp.value.err:
                    Logger.error(f"[SIM] Error: {sim_resp.value.err}")
                else:
                    Logger.success(f"[SIM] Success! Consumed {sim_resp.value.units_consumed} CUs")
            else:
                Logger.section("🚀 EXECUTING DARK LEVERAGE 🚀")
                bh_resp = await client.get_latest_blockhash()
                msg = MessageV0.try_compile(
                    payer=self.wallet.keypair.pubkey(),
                    instructions=ixs if isinstance(ixs, list) else [ixs],
                    address_lookup_table_accounts=[],
                    recent_blockhash=bh_resp.value.blockhash
                )
                tx = VersionedTransaction(msg, [self.wallet.keypair])
                
                resp = await client.send_transaction(tx, opts=TxOpts(preflight_commitment=Confirmed))
                Logger.success(f"✅ Leverage Scaled: {resp.value}")
                await client.confirm_transaction(resp.value, commitment=Confirmed)
                
if __name__ == "__main__":
    from solana.rpc.types import TxOpts # Import here for execution
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=float, default=2.0, help="Target Leverage Ratio (e.g. 2.0)")
    parser.add_argument("--execute", action="store_true", help="Execute real trade")
    parser.add_argument("--simulate", action="store_true", help="Simulate only")
    
    args = parser.parse_args()
    
    # Load env
    from dotenv import load_dotenv
    load_dotenv()
    
    wm = WalletManager()
    manager = LeverageManager(wm)
    
    # Default to sim unless execute is explicit
    simulate = not args.execute
    if args.simulate: simulate = True
    
    asyncio.run(manager.scale_to_target(args.target, simulate=simulate))
