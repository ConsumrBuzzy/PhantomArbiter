
import asyncio
import base64
import os
from solders.transaction import VersionedTransaction
from solana.rpc.api import Client
from config.settings import Settings
from src.shared.execution.unified_router import UnifiedTradeRouter
from src.shared.config.risk import RiskConfig
from src.shared.system.logging import Logger
from src.shared.system.smart_router import SmartRouter

async def test_mainnet_swap():
    """
    Validation Test: SOL -> USDC Small Swap on Mainnet.
    Uses UnifiedTradeRouter (Rust) via Jito Path.
    """
    Logger.info("🧪 INITIALIZING MAINNET SWAP TEST...")
    
    # 1. Setup
    risk_config = RiskConfig()
    router = UnifiedTradeRouter(risk_config)
    smart_router = SmartRouter()
    
    SOL_MINT = "So11111111111111111111111111111111111111112"
    USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    
    # Amount: 0.001 SOL (~$0.15)
    amount_lamports = 1_000_000 
    
    Logger.info(f"🛒 Quoting 0.001 SOL -> USDC...")
    
    # 2. Get Quote
    quote = smart_router.get_jupiter_quote(SOL_MINT, USDC_MINT, amount_lamports, slippage_bps=50)
    if not quote or "error" in quote:
        Logger.error(f"❌ Quote failed: {quote}")
        return

    # 3. Get Swap Transaction
    public_key = os.getenv("PHANTOM_PUBLIC_KEY") or str(Settings.PUBLIC_KEY) if hasattr(Settings, "PUBLIC_KEY") else "96g9sAg9CeGguRiYp9YmNTSUky1F9p7hYy1B52B7WAbA"
    
    payload = {
        "quoteResponse": quote,
        "userPublicKey": public_key,
        "wrapAndUnwrapSol": True,
        "computeUnitPriceMicroLamports": 5000 # Minimal
    }
    
    swap_data = smart_router.get_swap_transaction(payload)
    if not swap_data or "swapTransaction" not in swap_data:
        Logger.error(f"❌ Swap transaction fetch failed: {swap_data}")
        return

    # 4. Prepare Transaction Bytes
    tx_bytes = base64.b64decode(swap_data["swapTransaction"])
    
    # Note: Jupiter provides a transaction that usually needs a final signature from the user.
    # The Rust router.route_transaction will sign it with the private key configured.
    
    Logger.info("🚀 Executing via UnifiedTradeRouter (Rust + Jito)...")
    
    # 5. Execute
    result = router.execute_transaction(
        path_type="ATOMIC", 
        tx_bytes=tx_bytes,
        tip_lamports=1000 # Jito Tip
    )
    
    if result["success"]:
        Logger.success(f"✅ SWAP SUCCESSFUL!")
        Logger.info(f"🔗 Signature: {result['signature']}")
        Logger.info(f"🔗 View on Solscan: https://solscan.io/tx/{result['signature']}")
    else:
        Logger.error(f"❌ SWAP FAILED: {result['error']}")

if __name__ == "__main__":
    asyncio.run(test_mainnet_swap())
