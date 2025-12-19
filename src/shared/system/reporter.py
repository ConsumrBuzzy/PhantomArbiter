
import time
from src.system.logging import Logger
from src.system.comms_daemon import send_telegram_chunked, send_telegram
from src.core.shared_cache import SharedPriceCache

class MarketReporter:
    """
    V45.1: Specialized Reporter for Market Updates.
    Extracts presentation logic from DataBroker to enforce SRP.
    """
    
    def __init__(self, dsm, market_aggregator=None):
        self.dsm = dsm
        self.market_aggregator = market_aggregator
        
        # State
        self.last_report_time = 0
        self.start_time = time.time()
        self.previous_prices = {}
        self.watched_mints = {} # Set by Broker
        
    def set_watched_mints(self, mints: dict):
        self.watched_mints = mints

    def send_market_snapshot(self, batch_prices: dict, wss_stats: dict, priority: str = "LOW"):
        """
        Format and send the comprehensive market snapshot to Telegram.
        """
        now = time.time()
        
        # Rate Limit: 60 Seconds (User Request)
        if now - self.last_report_time < 60:
            return

        self.last_report_time = now
        uptime_min = int((now - self.start_time) / 60)
        tier_info = "Tier2 (DEX)" if self.dsm.use_fallback else "Tier1 (JUP)"
        wss_ok = wss_stats.get('rpc_success', 0)
        
        # V12.5: Get Active Positions from Shared Cache (Primary Source of Truth)
        # ... (rest of logic) ...
        active_pos_list = SharedPriceCache.get_active_positions(max_age=30)
        active_symbols = {p['symbol'] for p in active_pos_list}
        
        # 1. Build Message Sections
        alert_msg = (
            f"📊 MARKET SNAPSHOT\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Source: {tier_info} | WSS: {wss_ok}\n"
            f"Uptime: {uptime_min}m | Tokens: {len(batch_prices)}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
        )
        
        # Section A: CEX Telemetry (dYdX)
        if self.market_aggregator:
            try:
                adapter = self.market_aggregator.dydx_adapter
                if adapter and adapter.is_connected:
                    eth = adapter.get_ticker_sync("ETH-USD")
                    btc = adapter.get_ticker_sync("BTC-USD")
                    sol = adapter.get_ticker_sync("SOL-USD")
                    
                    cex_lines = ["🌐 CEX (dYdX Perpetuals)", "────────────────────"]
                    if eth: cex_lines.append(f"   ETH: ${eth['price']:,.2f}")
                    if btc: cex_lines.append(f"   BTC: ${btc['price']:,.2f}")
                    if sol: cex_lines.append(f"   SOL: ${sol['price']:,.4f}")
                    
                    alert_msg += "\n".join(cex_lines) + "\n\n"
            except Exception as e:
                pass # CEX failure shouldn't block DEX report

        # Section B: Active Positions
        if active_pos_list:
             alert_msg += "🚀 ACTIVE POSITIONS\n────────────────────\n"
             for pos in active_pos_list:
                 emoji = "🟢" if pos['pnl_pct'] > 0 else "🔴"
                 alert_msg += f"{emoji} {pos['symbol']}: ${pos['current']:.6f} ({pos['pnl_pct']:+.2f}%) | Entry: ${pos['entry']:.6f}\n"
             alert_msg += "\n"

        # Section C: Watchlist Status (Movers)
        movers = self._calculate_movers(batch_prices, active_symbols)
        if movers:
            alert_msg += "📋 WATCHLIST STATUS\n────────────────────\n"
            for m in movers:
                alert_msg += f"{m['emoji']} {m['symbol']}: ${m['price']:.6f} ({m['pct']:+.1f}%) | Liq: {m['liq_str']} | Slip: {m['slip_str']} | Vol: {m['vol_str']}\n"

        # Send via Chunked Daemon
        send_telegram_chunked(alert_msg, source="BROKER", priority=priority)
        
        # V12.5: Periodic Legend (Every 5 mins)
        self._check_send_legend(now)

    def _check_send_legend(self, now):
        """Send metric legend periodically."""
        if not hasattr(self, 'last_legend_time'):
             self.last_legend_time = 0
        
        if now - self.last_legend_time >= 300: # 5 min (300s)
             self.last_legend_time = now
             legend_msg = (
                 "ℹ️ METRIC LEGEND (5m)\n"
                 "• Liq: Liquidity Depth (TVL)\n"
                 "• Slip: Est. Slippage ($50 trade)\n"
                 "• Vol: Realized Volatility (1h)\n"
                 "• P&L: Unfinished Profit/Loss"
             )
             send_telegram_chunked(legend_msg, source="BROKER", priority="LOW")

    def _calculate_movers(self, current_prices: dict, exclude_symbols: set) -> list:
        """Calculate price changes and metrics for the watchlist."""
        movers = []
        symbol_to_mint = {v: k for k, v in self.watched_mints.items()}
        
        for symbol, price in current_prices.items():
            if symbol in exclude_symbols: continue
            
            prev = self.previous_prices.get(symbol, price)
            pct_change = ((price - prev) / prev) * 100 if prev > 0 else 0.0
            
            # Metrics
            mint = symbol_to_mint.get(symbol, "")
            liq = self.dsm.get_liquidity(mint) if mint else 0
            slip = self.dsm.get_slippage(mint) if mint else 0
            vol = self.dsm.get_volatility(symbol)
            
            # Formatting
            liq_str = f"${liq/1_000_000:.1f}M" if liq > 1_000_000 else f"${liq/1_000:.0f}K" if liq > 1000 else f"${liq:.0f}"
            slip_str = f"{slip:.2f}%" if slip > 0 else "N/A"
            vol_str = f"{vol:.2f}%" if vol > 0 else "N/A"
            
            emoji = "🟢" if pct_change > 0.5 else "🔴" if pct_change < -0.5 else "⚪"
            
            movers.append({
                "symbol": symbol,
                "price": price,
                "pct": pct_change,
                "emoji": emoji,
                "liq_str": liq_str,
                "slip_str": slip_str,
                "vol_str": vol_str,
                "raw_change": abs(pct_change)
            })
            
        # Store state for next run
        self.previous_prices = current_prices.copy()
        
        # Sort by biggest movers
        movers.sort(key=lambda x: x['raw_change'], reverse=True)
        return movers
