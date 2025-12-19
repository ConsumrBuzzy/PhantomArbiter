"""
V51.0: Telegram Message Templates
=================================
Structured message builders for consistent, scannable alerts.

All templates return Telegram Markdown-formatted strings.
Use with send_telegram() from comms_daemon.

Usage:
    from src.shared.system.telegram_templates import TradeTemplates, OrcaTemplates
    
    msg = TradeTemplates.entry("WIF", "BUY", 25.00, 2.45, "MOMENTUM")
    send_telegram(msg, source="TRADE", priority="HIGH")
"""

from typing import Optional
from datetime import datetime


class TradeTemplates:
    """Templates for trade alerts (HTML format)."""
    
    @staticmethod
    def entry(
        symbol: str,
        action: str,
        amount: float,
        price: float,
        engine: str,
        reason: str = ""
    ) -> str:
        """Format a trade entry alert."""
        emoji = "📈" if action.upper() == "BUY" else "📉"
        reason_line = f"\n• Signal: <i>{reason}</i>" if reason else ""
        
        return f"""{emoji} <b>{action.upper()} EXECUTED</b>
━━━━━━━━━━━━━━━
• Token: <code>{symbol}</code>
• Size: ${amount:.2f}
• Price: ${price:.6f}
• Engine: {engine}{reason_line}
"""

    @staticmethod
    def exit(
        symbol: str,
        pnl: float,
        pnl_pct: float,
        hold_time_mins: float,
        exit_reason: str = ""
    ) -> str:
        """Format a position exit alert."""
        emoji = "🟢" if pnl >= 0 else "🔴"
        
        # Format hold time
        if hold_time_mins < 60:
            hold_str = f"{hold_time_mins:.0f}m"
        else:
            hours = hold_time_mins / 60
            hold_str = f"{hours:.1f}h"
        
        return f"""{emoji} <b>POSITION CLOSED</b>
━━━━━━━━━━━━━━━
• Token: <code>{symbol}</code>
• PnL: ${pnl:+.2f} ({pnl_pct:+.1f}%)
• Hold: {hold_str}
• Reason: {exit_reason or "Signal"}
"""

    @staticmethod
    def stop_loss(symbol: str, loss: float, price: float) -> str:
        """Format a stop-loss trigger alert."""
        return f"""🛑 <b>STOP LOSS TRIGGERED</b>
━━━━━━━━━━━━━━━
• Token: <code>{symbol}</code>
• Loss: ${abs(loss):.2f}
• Exit Price: ${price:.6f}
"""


class OrcaTemplates:
    """Templates for Orca CLMM alerts."""
    
    @staticmethod
    def position_open(
        pool: str,
        capital: float,
        range_pct: float,
        tick_lower: int,
        tick_upper: int
    ) -> str:
        """Format position opening alert."""
        return f"""🐋 <b>ORCA POSITION OPENED</b>
━━━━━━━━━━━━━━━
• Pool: <code>{pool[:16]}...</code>
• Capital: ${capital:.2f}
• Range: ±{range_pct:.1f}%
• Ticks: [{tick_lower}, {tick_upper}]
"""

    @staticmethod
    def fees_harvested(fees_usd: float, positions: int) -> str:
        """Format fee harvest alert."""
        return f"""🐋 <b>FEES HARVESTED</b>
━━━━━━━━━━━━━━━
• Amount: ${fees_usd:.2f}
• Positions: {positions}
"""

    @staticmethod
    def position_closed(reason: str, pnl: float = 0) -> str:
        """Format position close alert."""
        emoji = "🟢" if pnl >= 0 else "🔴"
        return f"""{emoji} <b>ORCA POSITION CLOSED</b>
━━━━━━━━━━━━━━━
• Reason: {reason}
• Net: ${pnl:+.2f}
"""

    @staticmethod
    def status(positions: int, total_value: float, pending_fees: float) -> str:
        """Format periodic status update."""
        return f"""🐋 <b>ORCA STATUS</b>
━━━━━━━━━━━━━━━
• Positions: {positions}
• Value: ${total_value:.2f}
• Pending Fees: ${pending_fees:.2f}
"""


class DiscoveryTemplates:
    """Templates for multi-pad discovery alerts."""
    
    @staticmethod
    def new_launch(platform: str, mint: str, symbol: str = "") -> str:
        """Format new token launch alert."""
        # Clean inputs
        symbol = symbol.replace('<', '').replace('>', '')  # Sanitize
        
        # Display logic
        if symbol and symbol != "UNKNOWN":
            header = f"🚀 <b>NEW LAUNCH: {symbol}</b>"
        else:
            header = "🚀 <b>NEW LAUNCH</b>"
            
        return f"""{header}
━━━━━━━━━━━━━━━
• Platform: <i>{platform}</i>
• Mint: <code>{mint}</code>
"""

    @staticmethod
    def migration(mint: str, from_platform: str, to_dex: str, liquidity: float) -> str:
        """Format migration/graduation alert."""
        return f"""🎓 <b>TOKEN GRADUATED</b>
━━━━━━━━━━━━━━━
• Mint: <code>{mint}</code>
• Route: {from_platform} ➔ <b>{to_dex.upper()}</b>
• Liq: ${liquidity:,.0f}
"""

    @staticmethod
    def snipe_opportunity(
        mint: str,
        confidence: str,
        suggested_entry: float,
        platform: str
    ) -> str:
        """Format snipe opportunity alert."""
        emoji = "🎯" if confidence.lower() == "high" else "⚠️"
        return f"""{emoji} <b>SNIPE OPPORTUNITY</b>
━━━━━━━━━━━━━━━
• Token: <code>{mint[:16]}...</code>
• Confidence: {confidence.upper()}
• Suggested: ${suggested_entry:.2f}
• Platform: {platform}
"""


class SystemTemplates:
    """Templates for system status alerts."""
    
    @staticmethod
    def startup(version: str, engines: list) -> str:
        """Format system startup alert."""
        engine_list = ", ".join(engines)
        return f"""🚀 <b>PHANTOM TRADER ONLINE</b>
━━━━━━━━━━━━━━━
• Version: {version}
• Engines: {engine_list}
• Time: {datetime.now().strftime("%H:%M:%S")}
"""

    @staticmethod
    def shutdown(reason: str = "User request") -> str:
        """Format system shutdown alert."""
        return f"""🛑 <b>SYSTEM SHUTDOWN</b>
━━━━━━━━━━━━━━━
• Reason: {reason}
• Time: {datetime.now().strftime("%H:%M:%S")}
"""

    @staticmethod
    def error(component: str, error: str) -> str:
        """Format error alert."""
        return f"""❌ <b>ERROR</b>
━━━━━━━━━━━━━━━
• Component: {component}
• Error: <i>{error[:100]}</i>
"""

    @staticmethod
    def warning(component: str, message: str) -> str:
        """Format warning alert."""
        return f"""⚠️ <b>WARNING</b>
━━━━━━━━━━━━━━━
• Component: {component}
• Message: {message[:100]}
"""


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def format_trade_entry(*args, **kwargs) -> str:
    """Shortcut for TradeTemplates.entry()"""
    return TradeTemplates.entry(*args, **kwargs)

def format_trade_exit(*args, **kwargs) -> str:
    """Shortcut for TradeTemplates.exit()"""
    return TradeTemplates.exit(*args, **kwargs)

def format_orca_status(*args, **kwargs) -> str:
    """Shortcut for OrcaTemplates.status()"""
    return OrcaTemplates.status(*args, **kwargs)


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    print("Telegram Templates Test")
    print("=" * 50)
    
    print("\n1. Trade Entry:")
    print(TradeTemplates.entry("WIF", "BUY", 25.00, 2.4567, "MOMENTUM", "RSI oversold"))
    
    print("\n2. Trade Exit:")
    print(TradeTemplates.exit("BONK", 3.50, 14.0, 45, "Take profit"))
    
    print("\n3. Orca Position:")
    print(OrcaTemplates.position_open("Czfq3xZZ...", 50.0, 5.0, -1000, 1000))
    
    print("\n4. Discovery Launch:")
    print(DiscoveryTemplates.new_launch("pump.fun", "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU", "PEPE2"))
    
    print("\n5. System Startup:")
    print(SystemTemplates.startup("V51.0", ["MOMENTUM", "SCALPER", "ORCA"]))
    
    print("\n✅ Templates working!")
