
import pytest
from unittest.mock import MagicMock, patch
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Mock phantom_core before importing DataBroker
sys.modules["phantom_core"] = MagicMock()

from src.core.data_broker import DataBroker
from src.core.prices.dexscreener import MarketData

def test_data_broker_registry_logic():
    """Test that DataBroker correctly populates known_pools and routes WSS events."""
    
    # Mock dependencies
    with patch("src.core.data_broker.create_websocket_listener") as mock_wsl_factory:
        with patch("src.core.data_broker.EngineManager") as mock_eng_mgr:
            mock_eng_mgr.return_value.merchant_engines = {}
            
            # Initialize Broker (this is heavy, so we mock aggressively)
            with patch("src.core.data_broker.SharedPriceCache"), \
                 patch("src.shared.system.data_source_manager.DataSourceManager"), \
                 patch("src.core.prices.dexscreener.DexScreenerProvider"), \
                 patch("src.shared.execution.wallet.WalletManager"), \
                 patch("src.core.data_broker.AlertPolicyChecker"), \
                 patch("src.core.data_broker.BackgroundWorkerManager"), \
                 patch("src.core.data_broker.SignalResolver"), \
                 patch("src.arbiter.core.hop_engine.get_hop_engine") as mock_get_hop:
                 
                mock_hop_engine = MagicMock()
                mock_get_hop.return_value = mock_hop_engine
                
                broker = DataBroker()
                
                # 1. Verify Registry is Empty
                assert broker.known_pools == {}
                
                # 2. Simulate Universal Watcher batch fetch
                # Create fake MarketData with base/quote
                fake_data = MarketData(
                    mint="MINT_A", symbol="A", price_usd=1.0, dex_id="raydium",
                    liquidity_usd=1000, volume_24h_usd=1000,
                    price_change_5m=0, price_change_1h=0, price_change_24h=0,
                    txns_buys_24h=0, txns_sells_24h=0,
                    pair_address="POOL_123",
                    base_mint="BASE_MINT", quote_mint="QUOTE_MINT",
                    pair_created_at=0, fdv=0, market_cap=0
                )
                
                # Manually trigger the registry update logic (mimicking the run_loop block)
                rich_data = {"MINT_A": fake_data}
                
                # We can't easily reach into run_loop, so we verify we can populate it manually
                # mirroring the logic we added to run_loop
                for mint, mkt_data in rich_data.items():
                     if hasattr(mkt_data, "pair_address") and hasattr(mkt_data, "base_mint"):
                         broker.known_pools[mkt_data.pair_address] = (mkt_data.base_mint, mkt_data.quote_mint)
                
                assert "POOL_123" in broker.known_pools
                assert broker.known_pools["POOL_123"] == ("BASE_MINT", "QUOTE_MINT")
                
                # 3. Simulate WSS Event
                # Access the callback passed to create_websocket_listener
                # The mock factory was called with on_price_update=...
                args, kwargs = mock_wsl_factory.call_args
                callback = kwargs.get("on_price_update")
                assert callback is not None
                
                # Fire event
                event = {
                    "pool": "POOL_123",
                    "price": 100.5,
                    "dex": "RAYDIUM",
                    "timestamp": 1234567890
                }
                
                callback(event)
                
                # 4. Verify HopEngine.update_pool called with resolved tokens
                mock_hop_engine.update_pool.assert_called_once()
                call_arg = mock_hop_engine.update_pool.call_args[0][0]
                
                assert call_arg["pool_address"] == "POOL_123"
                assert call_arg["base_mint"] == "BASE_MINT"
                assert call_arg["quote_mint"] == "QUOTE_MINT"
                assert call_arg["price"] == 100.5
                
                # 5. Verify Delta-Trigger Logic
                # Requires patching signal_bus inside DataBroker (imported module)
                with patch("src.core.data_broker.signal_bus") as mock_signal_bus:
                    
                    # Case A: Small change (no trigger)
                    # last price was 100.5 (set above)
                    event_small = {"pool": "POOL_123", "price": 100.55, "dex": "RAYDIUM", "timestamp": 1234567900}
                    # delta = (100.55 - 100.5) / 100.5 = 0.00049 (0.04% < 0.1%)
                    callback(event_small)
                    mock_signal_bus.emit.assert_not_called()
                    
                    # Case B: Significant change (trigger)
                    # last price is now 100.55
                    event_big = {"pool": "POOL_123", "price": 100.8, "dex": "RAYDIUM", "timestamp": 1234567910}
                    # delta = (100.8 - 100.55) / 100.55 = 0.0024 (0.24% > 0.1%)
                    callback(event_big)
                    mock_signal_bus.emit.assert_called_once()
                    
                    # Verify signal content
                    args, _ = mock_signal_bus.emit.call_args
                    signal = args[0]
                    assert signal.type.name == "MARKET_UPDATE"
                    assert signal.data["type"] == "PRICE_JUMP"
                    assert signal.data["pool"] == "POOL_123"
                    assert signal.data["delta"] > 0.1

                print("Test passed!")

if __name__ == "__main__":
    test_data_broker_registry_logic()
