
"""
V89.3: Status Generator
Central logic for generating the "Broker Status" report.
Used by CommandProcessor (On-Demand) and ReportingService (Scheduled Heartbeat).
"""

from src.shared.system.capital_manager import get_capital_manager
from src.analysis.market_snap import MarketSnapshot

class StatusGenerator:
    """Generates standardized status reports."""
    
    @staticmethod
    def generate_report(broker) -> str:
        """
        Generate the full status report string.
        Returns the main status block. Snapshot should be sent separately if desired.
        """
        cm = get_capital_manager()
        
        status_parts = ["📊 *PHANTOM TRADER STATUS*", "━" * 20]
        
        # Summarize ALL engines
        engines_found = False
        for engine_name in cm.state.get("engines", {}):
            engine = cm.get_engine_state(engine_name)
            if engine:
                engines_found = True
                cash = engine.get("cash_balance", 0)
                sol = engine.get("sol_balance", 0)
                positions = engine.get("positions", {})
                stats = engine.get("stats", {})
                
                wins = stats.get("wins", 0)
                losses = stats.get("losses", 0)
                total_pnl = stats.get("total_pnl_usd", 0)
                pnl_emoji = "📈" if total_pnl >= 0 else "📉"
                
                status_parts.append(f"\n🎰 *{engine_name}*")
                status_parts.append(f"💵 ${cash:.2f} | ⛽ {sol:.4f} SOL")
                status_parts.append(f"📦 {len(positions)} positions")
                status_parts.append(f"W/L: {wins}/{losses} | {pnl_emoji} ${total_pnl:.2f}")
        
        if not engines_found:
             status_parts.append("\n_No active engines_")

        # Agent status summary
        if hasattr(broker, 'sniper'):
            sniper_stats = broker.sniper.get_stats()
            status_parts.append(f"\n🎯 *Sniper*: {sniper_stats.get('sniped_count', 0)} snipes")
        
        if hasattr(broker, 'scout_agent'):
            status_parts.append(f"🔍 *Scout*: {len(broker.scout_agent.watchlist)} wallets")
            
        if hasattr(broker, 'whale_watcher'):
             status_parts.append(f"🐋 *Whale*: {'Active' if broker.whale_watcher.running else 'Off'}")
             
        if hasattr(broker, 'sauron'):
             disc_count = getattr(broker.sauron, 'discovery_count', 0)
             status_parts.append(f"👁️ *Sauron*: {disc_count} discoveries")
        
        if hasattr(broker, 'sauron'):
             disc_count = getattr(broker.sauron, 'discovery_count', 0)
             status_parts.append(f"👁️ *Sauron*: {disc_count} discoveries")
        
        status_parts.append(f"\n_Uptime: {broker.batch_count // 2}s_")
        
        return "\n".join(status_parts)

    @staticmethod
    def generate_snapshot_msg() -> str:
        """Generate the standalone snapshot message."""
        try:
            snap = MarketSnapshot.get_snapshot()
            if snap.get("summary_line"):
                return snap.get("summary_line")
        except:
            pass
        return None
