"""
V48.0: Heartbeat Reporter Module
================================
Extracted from trading_core.py to improve SRP compliance.

Handles:
- Periodic heartbeat logging (every 60 seconds)
- Console output formatting
- Telegram notifications
- Paper wallet status display

Dependencies are injected via constructor for testability.
"""

import time
from typing import Dict, Optional, Any, TYPE_CHECKING
from dataclasses import dataclass

from config.settings import Settings
from src.shared.system.priority_queue import priority_queue

if TYPE_CHECKING:
    from src.shared.execution.paper_wallet import PaperWallet


@dataclass
class HeartbeatData:
    """Data collected for heartbeat display."""
    tick_count: int
    active_positions: int
    scout_positions: int
    total_watchers: int
    engine_name: str
    uptime_min: int
    dsa_mode: str
    usdc_bal: float
    sol_bal: float
    top_bags_str: str
    paper_section: str
    cex_section: str


class HeartbeatReporter:
    """
    V48.0: Dedicated heartbeat and status reporting.
    
    Extracted from TradingCore to isolate display/formatting logic.
    """
    
    # Heartbeat interval in seconds
    HEARTBEAT_INTERVAL = 60
    SYNC_INTERVAL = 5
    
    def __init__(
        self,
        engine_name: str,
        paper_wallet: 'PaperWallet',
        portfolio: Any,
        wallet: Any,
        decision_engine: Any,
        dydx_adapter: Optional[Any] = None
    ):
        """
        Initialize HeartbeatReporter.
        
        Args:
            engine_name: Engine identifier
            paper_wallet: Paper trading wallet
            portfolio: Portfolio manager
            wallet: Wallet manager
            decision_engine: Decision engine (for mode)
            dydx_adapter: Optional dYdX adapter for CEX prices
        """
        self.engine_name = engine_name
        self.paper_wallet = paper_wallet
        self.portfolio = portfolio
        self.wallet = wallet
        self.decision_engine = decision_engine
        self.dydx_adapter = dydx_adapter
        
        # Timing
        self.last_heartbeat = 0
        self.last_sync_active = 0
        self.start_time = time.time()
    
    def should_send_heartbeat(self) -> bool:
        """Check if heartbeat should be sent now."""
        now = time.time()
        if now - self.last_heartbeat >= self.HEARTBEAT_INTERVAL:
            return True
        return False
    
    def send_heartbeat(
        self,
        tick_count: int,
        watchers: Dict,
        scout_watchers: Dict,
        sync_positions_callback: Optional[callable] = None
    ) -> None:
        """
        Send periodic heartbeat with status information.
        
        Args:
            tick_count: Current tick count
            watchers: Active watchers dict
            scout_watchers: Scout watchers dict
            sync_positions_callback: Optional callback to sync positions
        """
        now = time.time()
        
        # Sync active positions periodically
        if sync_positions_callback and now - self.last_sync_active >= self.SYNC_INTERVAL:
            self.last_sync_active = now
            sync_positions_callback()
        
        # Check if heartbeat is due
        if now - self.last_heartbeat < self.HEARTBEAT_INTERVAL:
            return
        
        self.last_heartbeat = now
        
        # Collect data
        data = self._collect_heartbeat_data(tick_count, watchers, scout_watchers)
        
        # Format and send
        self._log_to_console(data)
        self._log_to_priority_queue(data)
        self._send_to_telegram(data)
    
    def _collect_heartbeat_data(
        self,
        tick_count: int,
        watchers: Dict,
        scout_watchers: Dict
    ) -> HeartbeatData:
        """Collect all data needed for heartbeat."""
        now = time.time()
        
        # Position counts
        active_positions = sum(1 for w in watchers.values() if w.in_position)
        scout_positions = sum(1 for w in scout_watchers.values() if w.in_position)
        total_watchers = len(watchers) + len(scout_watchers)
        
        # Engine info
        uptime_min = int((now - self.start_time) / 60)
        dsa_mode = getattr(self.decision_engine, 'mode', 'NORMAL')
        
        # Wallet state
        wallet_state = self.wallet.get_current_live_usd_balance()
        usdc_bal = wallet_state.get('breakdown', {}).get('USDC', 0.0)
        sol_bal = wallet_state.get('breakdown', {}).get('SOL', 0.0)
        bags = wallet_state.get('assets', [])
        
        # Format top bags
        top_bags_str = ""
        if bags:
            top_bags = bags[:3]
            bag_list = [f"{b['symbol']} (${b['usd_value']:.0f})" for b in top_bags]
            top_bags_str = f"\n• Bags: {', '.join(bag_list)}"
            if len(bags) > 3:
                top_bags_str += f" +{len(bags)-3}"
        
        # Paper wallet section
        paper_section = self._format_paper_section(watchers, scout_watchers, wallet_state)
        
        # CEX section
        cex_section = self._format_cex_section()
        
        return HeartbeatData(
            tick_count=tick_count,
            active_positions=active_positions,
            scout_positions=scout_positions,
            total_watchers=total_watchers,
            engine_name=self.engine_name,
            uptime_min=uptime_min,
            dsa_mode=dsa_mode,
            usdc_bal=usdc_bal,
            sol_bal=sol_bal,
            top_bags_str=top_bags_str,
            paper_section=paper_section,
            cex_section=cex_section
        )
    
    def _format_paper_section(
        self,
        watchers: Dict,
        scout_watchers: Dict,
        wallet_state: Dict
    ) -> str:
        """Format paper wallet status section."""
        if Settings.ENABLE_TRADING or not self.paper_wallet.initialized:
            return ""
        
        # Build price map
        price_map = {}
        for s, w in watchers.items():
            price_map[s] = w.get_price()
        for s, w in scout_watchers.items():
            price_map[s] = w.get_price()
        
        paper_val = self.paper_wallet.get_total_value(price_map)
        real_val = wallet_state.get('total_usd', 0.0)
        
        # PnL comparison
        diff = paper_val - self.paper_wallet.initial_capital
        pct = (diff / self.paper_wallet.initial_capital) * 100 if self.paper_wallet.initial_capital > 0 else 0
        emoji = "📈" if diff >= 0 else "📉"
        
        # Paper bags
        paper_bags_str = ""
        if self.paper_wallet.assets:
            paper_bags = []
            for sym, asset in list(self.paper_wallet.assets.items())[:5]:
                asset_price = price_map.get(sym, asset.avg_price)
                asset_val = asset.balance * asset_price
                pnl_pct = ((asset_price - asset.avg_price) / asset.avg_price * 100) if asset.avg_price > 0 else 0.0
                emoji_bag = "🟢" if pnl_pct > 0 else "🔴" if pnl_pct < 0 else "⚪"
                qty_str = f"{asset.balance:.0f}" if asset.balance > 100 else f"{asset.balance:.3f}"
                paper_bags.append(f"{emoji_bag} {sym}: {qty_str} (${asset_val:.2f}) {pnl_pct:+.1f}%")
            paper_bags_str = f"\n• 📦 Bags: {', '.join(paper_bags)}"
            if len(self.paper_wallet.assets) > 5:
                paper_bags_str += f" +{len(self.paper_wallet.assets)-5}"
        
        # Detailed breakdown
        details = self.paper_wallet.get_detailed_balance(price_map)
        
        # Log to priority queue
        bag_count = len(self.paper_wallet.assets)
        gas_bal = self.paper_wallet.sol_balance
        priority_queue.add(4, 'LOG', {
            'level': 'INFO',
            'message': f"[{self.engine_name}] 🎰 PAPER: ${paper_val:.2f} ({pct:+.2f}%) | Bags: {bag_count} | Gas: {gas_bal:.3f} SOL | REAL: ${real_val:.2f}"
        })
        
        return (
            f"\n🎰 **PAPER {self.paper_wallet.engine_name}**\n"
            f"• Value: ${details['total_equity']:.2f} ({emoji} {pct:+.2f}%)\n"
            f"• 💵 ${details['cash']:.2f} | ⛽ ${details['gas_usd']:.2f} | 📦 ${details['assets_usd']:.2f}\n"
            f"• W/L: {self.paper_wallet.stats['wins']}/{self.paper_wallet.stats['losses']} | Fees: ${self.paper_wallet.stats['fees_paid_usd']:.2f}"
            f"{paper_bags_str}"
        )
    
    def _format_cex_section(self) -> str:
        """Format CEX prices section."""
        if not self.dydx_adapter or not getattr(self.dydx_adapter, 'is_connected', False):
            return ""
        
        try:
            eth = self.dydx_adapter.get_ticker_sync("ETH-USD")
            btc = self.dydx_adapter.get_ticker_sync("BTC-USD")
            sol = self.dydx_adapter.get_ticker_sync("SOL-USD")
            if eth or btc or sol:
                cex_prices = []
                if eth:
                    cex_prices.append(f"ETH ${eth['price']:,.0f}")
                if btc:
                    cex_prices.append(f"BTC ${btc['price']:,.0f}")
                if sol:
                    cex_prices.append(f"SOL ${sol['price']:.2f}")
                return f"\n🌐 CEX: {' | '.join(cex_prices)}"
        except:
            pass
        return ""
    
    def _log_to_console(self, data: HeartbeatData) -> None:
        """Print heartbeat to console."""
        from src.shared.system.logging import Logger
        if getattr(Settings, "SILENT_MODE", False) or getattr(Logger, "_silent_mode", False):
            return

        print(f"\n────────────────────────────────────────────────────────────")
        print(f"💓 HEARTBEAT [{data.engine_name}] - {data.uptime_min}m Uptime")
        print(f"   • Ticks: {data.tick_count} | Mode: {data.dsa_mode}")
        print(f"   • Wallet: ${data.usdc_bal:.2f} (USDC) | {data.sol_bal:.3f} SOL")
        if data.top_bags_str:
            print(f"   {data.top_bags_str.strip()}")
        if data.paper_section:
            p_clean = data.paper_section.replace("**", "").replace("\n", "\n   ")
            print(f"   PAPER TRADING:{p_clean}")
        print(f"────────────────────────────────────────────────────────────\n")
    
    def _log_to_priority_queue(self, data: HeartbeatData) -> None:
        """Log heartbeat to priority queue."""
        if not data.paper_section:
            priority_queue.add(4, 'LOG', {
                'level': 'INFO',
                'message': f"[{data.engine_name}] 💓 {data.tick_count}t | {data.active_positions}A/{data.scout_positions}S | ${data.usdc_bal:.0f} | {data.sol_bal:.2f} SOL"
            })
    
    def _send_to_telegram(self, data: HeartbeatData) -> None:
        """Send heartbeat to Telegram."""
        from src.shared.system.comms_daemon import send_telegram
        
        heartbeat_msg = (
            f"💓 Heartbeat\n"
            f"• Ticks: {data.tick_count} | Watchers: {data.total_watchers}\n"
            f"• Positions: {data.active_positions}A / {data.scout_positions}S\n"
            f"• DSA: {data.dsa_mode} | Cash: ${data.usdc_bal:.2f}\n"
            f"• Wallet: ${data.usdc_bal:.2f} (USDC) | {data.sol_bal:.3f} SOL{data.top_bags_str}"
            f"{data.cex_section}\n"
            f"• Uptime: {data.uptime_min}m"
            f"{data.paper_section}"
        )
        
        send_telegram(heartbeat_msg, source=data.engine_name, priority="LOW")
