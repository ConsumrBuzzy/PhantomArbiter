
import os
import asyncio
from src.shared.system.logging import Logger
from src.shared.system.comms_daemon import send_telegram

class CommandProcessor:
    """
    V45.2: Handles Telegram commands dispatched by the DataBroker.
    Encapsulates command logic to prevent DataBroker bloat.
    """
    
    def __init__(self, broker):
        self.broker = broker
        # We access components via broker:
        # broker.market_aggregator, broker.reporter, broker.dsm, etc.

    def process(self, cmd_type: str, cmd_value: str = None):
        """
        Process a single command.
        """
        try:
            if cmd_type == "CMD_STATUS_REPORT":
                # V89.5: Use unified StatusGenerator (Matches Heartbeat) (Confirmed)
                print("   📊 [CMD] Processing STATUS_REPORT...")
                Logger.info("👋 STATUS_REPORT requested via Telegram")
                
                try:
                    from src.analysis.status_generator import StatusGenerator
                    
                    # 1. Main Report
                    main_report = StatusGenerator.generate_report(self.broker)
                    send_telegram(main_report, source="STATUS", priority="HIGH")
                    
                    # 2. Market Snapshot (Second Bubble)
                    snap_msg = StatusGenerator.generate_snapshot_msg()
                    if snap_msg:
                        send_telegram(snap_msg, source="STATUS", priority="HIGH")
                    
                except Exception as e:
                    Logger.error(f"Status report error: {e}")
                    send_telegram(f"❌ Status Error: {e}", source="STATUS", priority="HIGH")
                    
                # Also trigger the periodic report on next tick
                self.broker.reporter.last_report_time = 0
                self.broker.forced_report_pending = True
                
            elif cmd_type == "CMD_STOP_ENGINE":
                Logger.critical("🛑 STOP CMD RECEIVED. Shutting down...")
                self.broker.running = False

            elif cmd_type.startswith("CMD_SET_MODE"):
                # "CMD_SET_MODE:live"
                mode = cmd_type.split(":")[1]
                is_live = (mode == "live")
                
                # Update all engines
                for engine_name, engine in self.broker.merchant_engines.items():
                    engine.set_trading_mode(is_live)
                
                status = "LIVE 🟢" if is_live else "MONITOR ⚪"
                send_telegram(f"⚙️ MARKET MODE: {status}", source="BROKER", priority="HIGH")

            elif cmd_type.startswith("CMD_SET_SIZE"):
                # "CMD_SET_SIZE:50.0"
                try:
                    amount = float(cmd_type.split(":")[1])
                    from src.core.capital_manager import get_capital_manager
                    cm = get_capital_manager()
                    cm.update_config(size=amount)
                    send_telegram(f"📉 Position Size Updated: ${amount:.2f}", source="BROKER", priority="HIGH")
                except:
                    pass

            elif cmd_type.startswith("CMD_SET_BUDGET"):
                try:
                    amount = float(cmd_type.split(":")[1])
                    from src.core.capital_manager import get_capital_manager
                    cm = get_capital_manager()
                    cm.update_config(budget=amount)
                    send_telegram(f"💰 Risk Budget Updated: ${amount:.2f}", source="BROKER", priority="HIGH")
                except:
                    pass

            # V44.0: CEX Tunnel Test
            elif cmd_type == "CMD_TEST_CEX":
                self._handle_test_cex()

            # Drift Protocol Commands
            elif cmd_type == "CMD_TEST_DRIFT":
                self._handle_test_drift()
                
            elif cmd_type == "CMD_CHECK_DRIFT":
                self._handle_check_drift()
                
            # V45.0: Landlord Strategy
            elif cmd_type.startswith("CMD_START_LANDLORD"):
                self._handle_start_landlord(cmd_value if cmd_value else cmd_type)
            
            elif cmd_type == "CMD_CLOSE_LANDLORD":
                self._handle_close_landlord()
                
            elif cmd_type == "CMD_LANDLORD_STATUS":
                self._handle_landlord_status()
                
            # JLP Commands
            elif cmd_type.startswith("CMD_SET_JLP"):
                self._handle_set_jlp(cmd_value if cmd_value else cmd_type)
                
            elif cmd_type == "CMD_JLP_STATUS":
                self._handle_jlp_status()
            
            # V67.7: Swarm Status
            elif cmd_type == "CMD_SWARM_STATUS":
                self._handle_swarm_status()

        except Exception as e:
            Logger.error(f"❌ Command Error ({cmd_type}): {e}")
            send_telegram(f"❌ Command Failed: {e}", source="BROKER", priority="HIGH")

    # --- Specific Handlers ---

    def _handle_test_cex(self):
        send_telegram("🧪 CEX Test Starting...", source="BROKER", priority="HIGH")
        agg = self.broker.market_aggregator
        
        if not agg:
            send_telegram("❌ MarketAggregator missing", source="BROKER", priority="HIGH")
            return
            
        adapter = agg.dydx_adapter
        if not adapter or not adapter.is_connected:
            send_telegram("❌ dYdX Adapter not connected", source="BROKER", priority="HIGH")
            return
            
        result = adapter.execute_tiny_market_test_sync("ETH-USD", 0.001)
        if result.get("success"):
            send_telegram(f"✅ CEX Test OK\nCost: ${result.get('cost',0):.4f}", source="BROKER", priority="HIGH")
        else:
            send_telegram(f"❌ CEX Test Failed: {result.get('error')}", source="BROKER", priority="HIGH")

    def _handle_test_drift(self):
        send_telegram("🧪 Drift Test Starting...", source="BROKER", priority="HIGH")
        try:
            from src.infrastructure.drift_adapter import DriftAdapter
            adapter = DriftAdapter("devnet")
            pk = os.getenv("PHANTOM_PRIVATE_KEY")
            if not pk:
                send_telegram("❌ No Private Key", source="BROKER", priority="HIGH")
                return
            
            adapter.connect_sync()
            result = adapter.execute_tunnel_test_sync("SOL-PERP", 0.001)
            if result.get("success"):
                send_telegram("✅ Drift Test OK", source="BROKER", priority="HIGH")
            else:
                send_telegram(f"❌ Drift Test Failed: {result.get('error')}", source="BROKER", priority="HIGH")
        except Exception as e:
            send_telegram(f"❌ Drift Error: {e}", source="BROKER", priority="HIGH")

    def _handle_check_drift(self):
        send_telegram("🔍 Checking Drift...", source="BROKER", priority="HIGH")
        try:
            from src.infrastructure.drift_adapter import DriftAdapter
            adapter = DriftAdapter("mainnet")
            pk = os.getenv("PHANTOM_PRIVATE_KEY")
            if not pk: 
                 send_telegram("❌ No Private Key", source="BROKER", priority="HIGH")
                 return
            
            adapter.connect_sync()
            result = adapter.verify_drift_account_sync()
            status = "✅ Ready" if result.get('ready') else "⚠️ Not Ready"
            send_telegram(f"{status}\nCollateral: ${result.get('collateral',0):.2f}", source="BROKER", priority="HIGH")
        except Exception as e:
             send_telegram(f"❌ Drift Check Error: {e}", source="BROKER", priority="HIGH")

    def _handle_start_landlord(self, cmd_string):
        # Format: CMD_START_LANDLORD:100.0
        parts = cmd_string.split(":")
        size = 100.0
        if len(parts) > 1:
            try: size = float(parts[1])
            except: pass
            
        send_telegram(f"🏠 Start Landlord ${size}...", source="BROKER", priority="HIGH")
        try:
            from src.engine.landlord_core import get_landlord
            res = get_landlord().start_landlord_sync(size)
            send_telegram(res.get("message", "Done"), source="BROKER", priority="HIGH")
        except Exception as e:
            send_telegram(f"❌ Landlord Error: {e}", source="BROKER", priority="HIGH")

    def _handle_close_landlord(self):
        send_telegram("🏠 Closing Landlord...", source="BROKER", priority="HIGH")
        try:
            from src.engine.landlord_core import get_landlord
            res = get_landlord().close_landlord_sync()
            send_telegram(res.get("message", "Done"), source="BROKER", priority="HIGH")
        except Exception as e:
            send_telegram(f"❌ Landlord Error: {e}", source="BROKER", priority="HIGH")

    def _handle_landlord_status(self):
        try:
            from src.engine.landlord_core import get_landlord
            status = get_landlord().get_status()
            msg = (
                f"🏠 Landlord Status\n"
                f"State: {status.get('state')}\n"
                f"Hedge Ratio: {status.get('hedge_ratio', 0):.2f}\n"
                f"Funding: ${status.get('funding_collected', 0):.4f}"
            )
            send_telegram(msg, source="BROKER", priority="HIGH")
        except Exception as e:
             send_telegram(f"❌ Status Error: {e}", source="BROKER", priority="HIGH")

    def _handle_set_jlp(self, cmd_string):
        # CMD_SET_JLP:price:quantity
        parts = cmd_string.split(":")
        if len(parts) < 3: return
        
        try:
            price = float(parts[1])
            qty = float(parts[2])
            from src.core.capital_manager import get_capital_manager
            get_capital_manager().update_jlp_state(price, qty)
            send_telegram(f"🏠 JLP Set: {qty} @ ${price}", source="BROKER", priority="HIGH")
        except:
             send_telegram("❌ Invalid JLP Params", source="BROKER", priority="HIGH")

    def _handle_jlp_status(self):
        try:
            from src.core.capital_manager import get_capital_manager
            from src.core.market_aggregator import MarketAggregator
            cm = get_capital_manager()
            state = cm.get_jlp_state()
            
            # Need async loop for aggregator check
            agg = MarketAggregator()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                res = loop.run_until_complete(agg.get_jlp_status(state))
                send_telegram(res.get("message"), source="BROKER", priority="HIGH")
            finally:
                loop.close()
        except Exception as e:
             send_telegram(f"❌ JLP Error: {e}", source="BROKER", priority="HIGH")
    
    def _handle_swarm_status(self):
        """V67.7: Generate swarm status report for all agents."""
        try:
            # Scout Status
            scout = self.broker.scout_agent
            scout_count = len(scout.watchlist) if scout else 0
            scout_status = f"✓{scout_count} Wallets"
            
            # Whale Status
            whale = self.broker.whale_watcher
            whale_status = "LISTENING" if whale and whale.running else "OFF"
            
            # Sauron Status
            sauron = getattr(self.broker, 'sauron', None)
            sauron_status = "WATCHING" if sauron and sauron.running else "OFF"
            
            msg = (
                "🐝 **SWARM STATUS**\n"
                "━━━━━━━━━━━━━━━\n"
                f"• Scout: {scout_status}\n"
                f"• Whale Watcher: {whale_status}\n"
                f"• Sauron: {sauron_status}\n"
            )
            send_telegram(msg, source="BROKER", priority="HIGH")
        except Exception as e:
            send_telegram(f"❌ Swarm Error: {e}", source="BROKER", priority="HIGH")
