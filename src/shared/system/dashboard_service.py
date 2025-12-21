"""
V77.0: Glass Cockpit Dashboard Service
=======================================
Non-blocking dashboard that prints a structured "State of the Union" every 60 seconds.
Replaces chaotic scrolling logs with a clean, glanceable summary.

Output Format:
┌──────────────────────────────────────────────────────────────────┐
│ 🎛️  PHANTOM TRADER DASHBOARD  │  10:34:21  │  Uptime: 45m       │
├───────────────┬───────────────┬───────────────┬──────────────────┤
│ 🐝 SWARM      │ 📈 MARKET     │ 💰 PAPER      │ 🔧 INFRA         │
│ Scout: ACTIVE │ Regime: UP    │ $25.04 Cash   │ RPC: 14ms        │
│ Whale: POLL   │ VIX: QUIET    │ 0/0 W/L       │ WSS: 142 swaps   │
│ Sniper: READY │ SOL: $180.42  │ $0.00 PnL     │ DB: OK           │
└───────────────┴───────────────┴───────────────┴──────────────────┘
"""

import threading
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass
from src.shared.system.logging import Logger
from config.settings import Settings


@dataclass
class DashboardState:
    """Current state snapshot for dashboard."""
    # Swarm
    scout_status: str = "IDLE"
    whale_status: str = "IDLE"
    sniper_status: str = "IDLE"
    sniper_count: int = 0
    scout_watchlist: int = 0
    
    # Market
    regime: str = "UNKNOWN"
    vix: str = "UNKNOWN"
    sol_price: float = 0.0
    top_gainers: str = ""  # V77.0: Green tokens
    top_losers: str = ""   # V77.0: Red tokens
    
    # Paper Trading (V78.0: Enhanced with Heartbeat data)
    cash_balance: float = 0.0
    sol_balance: float = 0.0
    gas_value_usd: float = 0.0  # V77.0: SOL × price
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    open_positions: int = 0
    position_value: float = 0.0  # V78.0: Total value of open positions
    total_value: float = 0.0     # V78.0: Cash + Gas + Positions
    total_fees: float = 0.0      # V78.0: Fees paid
    tick_count: int = 0          # V78.0: From heartbeat
    engine_mode: str = "NORMAL"  # V78.0: DSA mode
    
    # V80.0: Active Positions (list of dicts: {symbol, entry, current, pnl_pct, size})
    positions_list: list = None  # Will be initialized to []
    exposure_pct: float = 0.0    # Current exposure as % of budget
    
    # Infrastructure
    rpc_latency_ms: int = 0
    wss_swaps: int = 0
    wss_connected: bool = False
    db_ok: bool = True
    sauron_discoveries: int = 0
    threads_active: int = 0      # V81.0: Active thread count
    sol_is_cached: bool = False  # V78.1: True if SOL price from cache
    
    # V85.1: Intelligence
    whale_alerts: int = 0        # Whale swaps detected
    scrape_queue: int = 0        # Pending scrapes
    paper_pnl_today: float = 0.0 # Paper trading PnL today
    
    def __post_init__(self):
        if self.positions_list is None:
            self.positions_list = []


class DashboardService:
    """
    V77.0: Non-blocking rich console dashboard.
    
    Prints a structured status update every interval (default 60s).
    Collects state from all subsystems without blocking.
    """
    
    print("   📊 [CMD] Processing STATUS_REPORT...")
    
    def __init__(self, interval: int = 30):
        self.interval = interval
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.start_time = time.time()
        
        # References to subsystems (set by DataBroker)
        self.broker = None
        self.capital_manager = None
        self.threshold_manager = None
        
    def set_broker(self, broker):
        """Link to DataBroker for state access."""
        self.broker = broker
        
    def start(self):
        """Start the dashboard thread."""
        if self.running:
            return
            
        self.running = True
        self.start_time = time.time()
        self.thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="DashboardService"
        )
        self.thread.start()
        Logger.info("🎛️ [DASHBOARD] Glass Cockpit started (60s refresh)")
    
    def stop(self):
        """Stop the dashboard thread."""
        self.running = False
        
    def _run_loop(self):
        """Main loop - print dashboard every interval."""
        while self.running:
            try:
                state = self._collect_state()
                self._print_dashboard(state)
            except Exception as e:
                Logger.error(f"[DASHBOARD] CRITICAL ERROR: {e}")
                import traceback
                traceback.print_exc()
            
            # Sleep in small chunks for responsive shutdown
            for _ in range(self.interval * 2):
                if not self.running:
                    break
                time.sleep(0.5)
    
    def _collect_state(self) -> DashboardState:
        """Collect current state from all subsystems."""
        state = DashboardState()
        
        # === Swarm Status ===
        if self.broker:
            # Scout
            if hasattr(self.broker, 'scout_agent'):
                scout = self.broker.scout_agent
                state.scout_status = "ACTIVE"
                state.scout_watchlist = len(scout.watchlist) if hasattr(scout, 'watchlist') else 0
            
            # Whale Watcher
            if hasattr(self.broker, 'whale_watcher'):
                state.whale_status = "POLLING"
            
            # Sniper
            if hasattr(self.broker, 'sniper'):
                sniper = self.broker.sniper
                state.sniper_status = "READY"
                stats = sniper.get_stats() if hasattr(sniper, 'get_stats') else {}
                state.sniper_count = stats.get('sniped_count', 0)
            
            # WSS Stats
            if hasattr(self.broker, 'ws_listener'):
                wss = self.broker.ws_listener
                wss_stats = wss.get_stats() if hasattr(wss, 'get_stats') else {}
                state.wss_swaps = wss_stats.get('swaps_detected', 0)
                state.wss_connected = wss_stats.get('connection_status') == 'connected'
            
            # Sauron
            if hasattr(self.broker, 'sauron'):
                state.sauron_discoveries = getattr(self.broker.sauron, 'discovery_count', 0)
        
        # === Market Regime + SOL Price ===
        try:
            from src.core.threshold_manager import get_threshold_manager
            tm = get_threshold_manager()
            state.regime = tm.current_regime
            state.vix = "QUIET" if tm.pnl_multiplier >= 0.8 else "STRESSED"
        except:
            pass
        
        # SOL Price from cache (with fallbacks)
        try:
            from src.core.shared_cache import SharedPriceCache
            sol_price, _ = SharedPriceCache.get_price("SOL", max_age=300)
            if sol_price:
                state.sol_price = sol_price
                state.sol_is_cached = True  # V78.1: Mark as cached
            else:
                # Fallback 1: Try Jupiter direct
                from src.data_source.smart_router import get_jupiter_price
                sol_price = get_jupiter_price("So11111111111111111111111111111111111111112")  # SOL mint
                state.sol_price = sol_price if sol_price else 150.0  # Fallback: $150
                state.sol_is_cached = False if sol_price else True  # Live if Jupiter worked
        except:
            state.sol_price = 150.0  # Conservative fallback
            state.sol_is_cached = True
        
        # V89.2: Unified Market Snapshot (Top Movers)
        try:
            from src.analysis.market_snap import MarketSnapshot
            snap = MarketSnapshot.get_snapshot()
            state.top_gainers = snap.get("top_gainers", "—")
            state.top_losers = snap.get("top_losers", "—")
            # V89.13: List format for vertical display
            state.snapshot_gainers = snap.get("snapshot_gainers", [])
            state.snapshot_losers = snap.get("snapshot_losers", [])
        except:
            state.top_gainers = "—"
            state.top_losers = "—"
            state.snapshot_gainers = []
            state.snapshot_losers = []
        
        # === Paper Trading (V78.0: With Heartbeat data) ===
        try:
            from src.shared.system.capital_manager import get_capital_manager
            from config.settings import Settings
            cm = get_capital_manager()
            
            # Get first engine (PAPER MERCHANT)
            for engine_name in cm.state.get("engines", {}):
                engine = cm.get_engine_state(engine_name)
                if engine:
                    state.cash_balance = engine.get("cash_balance", 0)
                    state.sol_balance = engine.get("sol_balance", 0)
                    state.gas_value_usd = state.sol_balance * state.sol_price if state.sol_price else 0
                    positions = engine.get("positions", {})
                    state.open_positions = len(positions)
                    stats = engine.get("stats", {})
                    state.wins = stats.get("wins", 0)
                    state.losses = stats.get("losses", 0)
                    state.total_pnl = stats.get("total_pnl_usd", 0)
                    state.total_fees = stats.get("total_fees_usd", 0)
                    
                    # V78.0: Calculate position value and total value
                    pos_value = sum(p.get("current_value", 0) for p in positions.values())
                    state.position_value = pos_value
                    state.total_value = state.cash_balance + state.gas_value_usd + pos_value
                    
                    # V80.0: Collect position details for display
                    for symbol, pos in positions.items():
                        entry_price = pos.get("entry_price", 0)
                        current_price = pos.get("current_price", entry_price)
                        size_usd = pos.get("size_usd", 0)
                        current_value = pos.get("current_value", size_usd)
                        
                        # Calculate PnL %
                        pnl_pct = ((current_value - size_usd) / size_usd * 100) if size_usd > 0 else 0
                        
                        state.positions_list.append({
                            "symbol": symbol[:6],  # Truncate for display
                            "entry": entry_price,
                            "current": current_price,
                            "pnl_pct": pnl_pct,
                            "size": size_usd
                        })
                    
                    # V80.0: Calculate exposure as % of budget
                    budget = Settings.MAX_TOTAL_EXPOSURE_USD
                    state.exposure_pct = (pos_value / budget * 100) if budget > 0 else 0
                    
                break  # Just first engine for now
            
            # V78.0: Get tick count from broker if available
            if self.broker and hasattr(self.broker, 'batch_count'):
                state.tick_count = self.broker.batch_count
                
        except:
            pass
        
        # === Infrastructure ===
        state.db_ok = True  # Assume OK unless proven otherwise
        
        # V81.0: Get thread stats
        try:
            from src.shared.system.thread_manager import get_thread_manager
            tm = get_thread_manager()
            state.threads_active = tm.get_active_count()
        except:
            pass
        
        # V85.1: Get intelligence stats
        try:
            from src.discovery.scrape_intelligence import get_scrape_intelligence
            scrape = get_scrape_intelligence()
            intel_stats = scrape.get_stats()
            state.whale_alerts = intel_stats.get("whales_detected", 0)
            state.scrape_queue = intel_stats.get("queue_size", 0)
        except:
            pass
        
        # V85.1: Get paper trading PnL today
        try:
            from src.shared.system.db_manager import db_manager
            state.paper_pnl_today = db_manager.get_pnl_today() or 0.0
        except:
            pass
        
        return state
    
    def _print_dashboard(self, state: DashboardState):
        """Print the formatted dashboard to console."""
        uptime_seconds = int(time.time() - self.start_time)
        uptime_str = f"{uptime_seconds // 60}m {uptime_seconds % 60}s"
        timestamp = time.strftime("%H:%M:%S")
        
        # Emoji/status formatting
        regime_emoji = "📈" if "UP" in state.regime else "📉" if "DOWN" in state.regime else "↔️"
        wss_status = "✅" if state.wss_connected else "❌"
        pnl_emoji = "💚" if state.total_pnl >= 0 else "❤️"
        
        # Format SOL price (with cache indicator)
        cache_tag = "©" if state.sol_is_cached else ""
        sol_str = f"${state.sol_price:.0f}{cache_tag}" if state.sol_price else "—"
        gas_str = f"${state.gas_value_usd:.2f}" if state.gas_value_usd else "—"
        
        # V78.0: Format total value
        total_val = state.total_value if state.total_value > 0 else (state.cash_balance + state.gas_value_usd)
        
        # V80.0: Exposure bar
        exp_bar = "█" * int(state.exposure_pct / 10) + "░" * (10 - int(state.exposure_pct / 10))
        
        # Build the dashboard
        lines = [
            "",
            "┌" + "─" * 68 + "┐",
            f"│ 🎛️  PHANTOM TRADER DASHBOARD  │  {timestamp}  │  Uptime: {uptime_str:<10}│",
            "├" + "─" * 17 + "┬" + "─" * 17 + "┬" + "─" * 17 + "┬" + "─" * 14 + "┤",
            f"│ 🐝 SWARM        │ {regime_emoji} MARKET      │ 💰 PAPER        │ 🔧 INFRA      │",
            f"│ Scout: {state.scout_status:<8} │ SOL: {sol_str:<10} │ Val: ${total_val:<9.2f} │ WSS: {wss_status:<7}  │",
            f"│ Whale: {state.whale_status:<8} │ Regime: {state.regime:<7} │ 💵{state.cash_balance:<6.2f}⛽{gas_str:<5}│ Swaps: {state.wss_swaps:<4}  │",
            f"│ Sniper: {state.sniper_count:<7} │ VIX: {state.vix:<10} │ W/L: {state.wins}/{state.losses} Pos:{state.open_positions:<3}│ Disc: {state.sauron_discoveries:<5} │",
            f"│ Watch: {state.scout_watchlist:<8} │ Ticks: {state.tick_count:<8} │ {pnl_emoji} ${state.total_pnl:<+9.2f} │ Threads: {state.threads_active:<5}│",
            "├" + "─" * 68 + "┤",
            f"│ 🧠 INTELLIGENCE (PAPER_AGGRESSIVE: {'ON' if getattr(Settings, 'PAPER_AGGRESSIVE_MODE', False) else 'OFF'})                    │",
            f"│ Whales: {state.whale_alerts:<7}  │ Queue: {state.scrape_queue:<8}  │ Today: ${state.paper_pnl_today:<+10.2f}              │",
            "├" + "─" * 68 + "┤",
            "│ 📊 MARKET SNAPSHOT                                               │",
            "├─────────────────────────────────┬────────────────────────────────┤",
            "│ 🚀 TOP GAINERS                  │ 🩸 TOP LOSERS                  │",
        ]
        
        # V89.13: Vertical list format for market snapshot
        if hasattr(state, 'snapshot_gainers') and hasattr(state, 'snapshot_losers'):
            gainers = state.snapshot_gainers if state.snapshot_gainers else []
            losers = state.snapshot_losers if state.snapshot_losers else []
            
            # Show up to 3 of each
            max_rows = max(len(gainers), len(losers), 1)
            for i in range(min(max_rows, 3)):
                g_line = gainers[i] if i < len(gainers) else ""
                l_line = losers[i] if i < len(losers) else ""
                lines.append(f"│ {g_line:<31} │ {l_line:<30} │")
        else:
            # Fallback to old format
            lines.append(f"│ {state.top_gainers:<31} │ {state.top_losers:<30} │")
        
        lines.extend([
            "├─────────────────────────────────┴────────────────────────────────┤",
        ])
        
        # V80.0: Add positions table if any exist
        if state.positions_list:
            lines.append("├" + "─" * 68 + "┤")
            lines.append(f"│ 📊 POSITIONS ({state.open_positions}) │ Exposure: [{exp_bar}] {state.exposure_pct:.0f}%         │")
            lines.append("├" + "─" * 10 + "┬" + "─" * 12 + "┬" + "─" * 12 + "┬" + "─" * 10 + "┬" + "─" * 20 + "┤")
            lines.append("│ Symbol   │ Entry $     │ Current $   │ Size $   │ PnL                │")
            lines.append("├" + "─" * 10 + "┼" + "─" * 12 + "┼" + "─" * 12 + "┼" + "─" * 10 + "┼" + "─" * 20 + "┤")
            
            for pos in state.positions_list[:5]:  # Show top 5
                pnl_str = f"{pos['pnl_pct']:+.1f}%"
                pnl_bar = "🟢" if pos['pnl_pct'] >= 0 else "🔴"
                lines.append(f"│ {pos['symbol']:<8} │ ${pos['entry']:<10.4f} │ ${pos['current']:<10.4f} │ ${pos['size']:<7.2f} │ {pnl_bar} {pnl_str:<16} │")
            
            if len(state.positions_list) > 5:
                lines.append(f"│ ... and {len(state.positions_list) - 5} more positions                                        │")
        
        lines.append("└" + "─" * 68 + "┘")
        lines.append("")
        
        # Filter empty lines
        lines = [l for l in lines if l]
        
        # Print all lines
        for line in lines:
            print(line)
    
    def force_update(self):
        """Force an immediate dashboard update."""
        try:
            state = self._collect_state()
            self._print_dashboard(state)
        except Exception as e:
            Logger.debug(f"[DASHBOARD] Force update error: {e}")


# Singleton
_dashboard_service = None

def get_dashboard_service() -> DashboardService:
    """Get singleton dashboard service."""
    global _dashboard_service
    if _dashboard_service is None:
        _dashboard_service = DashboardService()
    return _dashboard_service


# Test
if __name__ == "__main__":
    dash = get_dashboard_service()
    state = DashboardState(
        scout_status="ACTIVE",
        whale_status="POLLING",
        sniper_status="READY",
        sniper_count=3,
        scout_watchlist=25,
        regime="TRENDING_UP",
        vix="QUIET",
        cash_balance=25.04,
        sol_balance=0.038,
        wins=2,
        losses=1,
        total_pnl=4.50,
        wss_swaps=142,
        wss_connected=True,
        sauron_discoveries=17
    )
    dash._print_dashboard(state)
