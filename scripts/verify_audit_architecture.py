
import asyncio
import os
import sys

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest.mock import MagicMock
from src.engine.trading_core import TradingCore
from src.shared.models.trade_result import TradeResult
from config.settings import Settings

async def run_verification():
    print("👻 STARTING GHOST SESSION: VERIFYING AUDIT ARCHITECTURE")
    
    # 1. Setup Environment
    Settings.ENABLE_SHADOW_MODE = True
    Settings.ENABLE_TRADING = True # Mocking Live Mode
    
    # 2. Init Engine
    core = TradingCore(engine_name="TEST_FLIGHT")
    await core.initialize() # Wait for async init (TradeExecutor creation)
    
    # 3. Mock the Live Execution Backend to prevent real spending
    # We want execute_buy -> triggers audit -> calls paper_buy
    mock_backend = MagicMock()
    mock_backend.execute_buy.return_value = TradeResult(
        success=True,
        action="BUY",
        token="SOL",
        fill_price=150.0,
        quantity=1.0, # 1 SOL ($150)
        slippage_pct=0.1,
        tx_id="LIVE_MOCK_TX",
        reason="Test Audit",
        requested_price=149.8,
        source="LIVE"
    )
    
    mock_backend.execute_sell.return_value = TradeResult(
        success=True,
        action="SELL",
        token="SOL",
        fill_price=155.0,
        quantity=1.0,
        slippage_pct=0.0,
        tx_id="LIVE_MOCK_TX_SELL",
        reason="Test Audit Sell",
        requested_price=154.0,
        source="LIVE",
        pnl_usd=5.0
    )
    
    core.executor.execution_backend = mock_backend
    core.executor.live_mode = True # Enforce Live Mode
    
    # Verify Shadow Manager is wired
    if not core.shadow_manager:
        print("❌ FAILURE: Shadow Manager not initialized in core!")
        return
        
    print("✅ Core Initialized & Shadow Manager Detected")
    
    # Funding Paper Wallet for test
    core.executor.paper_wallet.deposit("SOL", 10.0, 150.0)
    core.executor.paper_wallet.deposit("USDC", 1500.0, 1.0)
    print("✅ Paper Wallet Funded")
    
    # 4. Trigger Buy
    from src.strategy.watcher import Watcher
    watcher = Watcher("SOL", "So11111111111111111111111111111111111111112")
    # Mock watcher data feed
    watcher.get_price = MagicMock(return_value=150.0)
    
    print("\n🚀 Executing Mock LIVE Buy...")
    result = core.executor.execute_buy(watcher, 150.0, "Ghost Audit Test", 10.0, None)
    
    print(f"   Live Result: {result.tx_id} (Success: {result.success})")
    
    # 5. Wait for Shadow Audit (Async Task)
    print("   Waiting for Shadow Audit to complete...")
    await asyncio.sleep(2.0)
    
    # 6. Check Audit Logs
    audits = core.shadow_manager.audits
    if len(audits) > 0:
        entry = audits[-1]
        print(f"\n✅ AUDIT CAPTURED!")
        print(f"   Action: {entry.action}")
        print(f"   Live Fill: ${entry.live_fill:.4f}")
        print(f"   Paper Fill: ${entry.paper_fill:.4f}")
        print(f"   Delta: {entry.delta_pct:+.2f}%")
        print(f"   Lag: {entry.execution_lag_ms:.1f}ms")
    else:
        print("\n❌ FAILURE: No audit entry found in ShadowManager.")
        
    # 7. Statistics Check
    stats = core.shadow_manager.get_stats()
    print("\n📊 Shadow Stats:")
    print(stats)
    
    if stats['total_audits'] >= 1:
        print("\n👻 GHOST SESSION SUCCESS: Audit Architecture is Active.")
    else:
        print("\n❌ GHOST SESSION FAILED.")

if __name__ == "__main__":
    asyncio.run(run_verification())
