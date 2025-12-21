
import asyncio
import time
from collections import defaultdict
from src.system.logging import Logger
from config.settings import Settings
from src.utils.boot_utils import BootTimer
from src.system.comms_daemon import send_telegram

# Imports for loop
from src.discovery.launchpad_monitor import get_launchpad_monitor, LaunchEvent, MigrationEvent
from src.discovery.migration_sniffer import get_migration_sniffer, MigrationOpportunity, SnipeConfidence
from src.shared.system.capital_manager import get_capital_manager
from src.system.telegram_templates import DiscoveryTemplates

SHUTDOWN_EVENT = asyncio.Event()
discovery_trades = {} # Local tracking

def set_shutdown_event(event: asyncio.Event):
    global SHUTDOWN_EVENT
    SHUTDOWN_EVENT = event

async def discovery_monitor_loop():
    """
    V50.0: Multi-Launchpad Discovery Monitor.
    V50.1: Added paper trading integration for migration opportunities.
    """
    
    # Check if enabled
    if not getattr(Settings, 'MULTIPAD_ENABLED', False):
        Logger.info("[DISCOVERY] 🔍 Multi-Pad Monitor disabled in settings")
        return
    
    Logger.info("[DISCOVERY] 🔍 Multi-Pad Monitor Starting...")
    send_telegram("🔍 Multi-Pad Discovery Started", source="DISCOVERY", priority="HIGH")
    
    # Boot Timer
    BootTimer.mark("Discovery Monitor Init")
    
    monitor = get_launchpad_monitor()
    sniffer = get_migration_sniffer()
    capital_mgr = get_capital_manager()
    
    # V85.3: Silent Launch Reporting (Buffered)
    # Stores tuples of (mint, platform, timestamp)
    silent_buffer = []
    
    async def report_silent_launches():
        """
        Periodically process silent queue, retry metadata, and report.
        """
        from src.infrastructure.token_scraper import get_token_scraper
        scraper = get_token_scraper()
        
        while True:
            await asyncio.sleep(300) # 5 minutes
            
            if not silent_buffer:
                continue
                
            # Take snapshot of buffer and clear it
            batch = silent_buffer[:]
            silent_buffer.clear()
            
            resolved_counts = 0
            still_unknown_counts = defaultdict(int)
            resolved_lines = []
            
            Logger.info(f"[DISCOVERY] 🔭 Processing {len(batch)} silent launches...")
            
            for mint, platform, _ in batch:
                # Retry lookup
                info = scraper.lookup(mint)
                symbol = info.get("symbol", "")
                name = info.get("name", "")
                
                is_resolved = symbol and not symbol.startswith("UNK_") and symbol != "UNKNOWN"
                
                if is_resolved:
                    resolved_counts += 1
                    # Format: • PEPE (Pump.fun)
                    line = f"• <a href='https://dexscreener.com/solana/{mint}'>{symbol}</a> ({platform})"
                    resolved_lines.append(line)
                else:
                    still_unknown_counts[platform] += 1
            
            # Construct Report
            if resolved_counts > 0 or still_unknown_counts:
                msg = f"🔭 <b>DISCOVERY SUMMARY (5m)</b>\n━━━━━━━━━━━━━━━\n"
                
                if resolved_lines:
                    msg += f"<i><b>✅ Resolved ({len(resolved_lines)}):</b></i>\n" + "\n".join(resolved_lines[:15]) # Limit to 15 to avoid huge msgs
                    if len(resolved_lines) > 15:
                        msg += f"\n<i>...and {len(resolved_lines)-15} more</i>"
                    msg += "\n\n"
                    
                if still_unknown_counts:
                    msg += f"<i><b>🌑 Unresolved ({sum(still_unknown_counts.values())}):</b></i>\n"
                    for plat, count in still_unknown_counts.items():
                        msg += f"• {plat}: {count}\n"
                
                send_telegram(msg, source="DISCOVERY", priority="LOW")

    # Start reporter task
    loop = asyncio.get_running_loop()
    reporter_task = loop.create_task(report_silent_launches())
    
    # Register handlers
    @monitor.on_launch
    async def on_launch(event: LaunchEvent):
        # V85.3: Suppress Unknown Tokens
        is_unknown = not event.symbol or event.symbol == "UNKNOWN" or event.mint.startswith("UNKNOWN")
        
        if is_unknown:
            # Buffer for later retry
            silent_buffer.append((event.mint, event.platform.value, time.time()))
            return

        # V51.0: Use Template
        # V54.0: Include name/symbol from tokenizer
        display_name = f"{event.name} ({event.symbol})" if event.name else event.mint[:8]
        
        msg = DiscoveryTemplates.new_launch(
            platform=event.platform.value,
            mint=event.mint,
            symbol=event.symbol or "UNKNOWN"
        )
        Logger.info(f"[DISCOVERY] 🚀 NEW LAUNCH: {display_name} [{event.platform.value}]")
        send_telegram(msg, source="DISCOVERY", priority="MEDIUM")
    
    @monitor.on_migration
    async def on_migration(event: MigrationEvent):
        # V51.0: Use Template
        msg = DiscoveryTemplates.migration(
            mint=event.mint,
            from_platform=event.platform.value,
            to_dex=event.destination_dex,
            liquidity=50000.0  # Placeholder, usually 0 at instant of migration
        )
        Logger.info(f"[DISCOVERY] 🔄 MIGRATION: {event.mint[:8]}... → {event.destination_dex}")
        send_telegram(msg, source="DISCOVERY", priority="HIGH")
    
    @sniffer.on_opportunity
    async def on_opportunity(opp: MigrationOpportunity):
        # Get confidence threshold from settings
        min_confidence = getattr(Settings, 'LAUNCHPAD_MIN_CONFIDENCE', 0.7)
        auto_trade = getattr(Settings, 'LAUNCHPAD_AUTO_TRADE', False)
        trade_size = getattr(Settings, 'LAUNCHPAD_TRADE_SIZE', 10.0)
        
        # Check if this meets our threshold
        confidence_map = {
            SnipeConfidence.HIGH: 1.0,
            SnipeConfidence.MEDIUM: 0.6,
            SnipeConfidence.LOW: 0.3,
            SnipeConfidence.SKIP: 0.0
        }
        confidence_value = confidence_map.get(opp.confidence, 0.0)
        
        if confidence_value >= min_confidence:
            # Log and alert
            msg = DiscoveryTemplates.snipe_opportunity(
                mint=opp.mint,
                confidence=opp.confidence.name,
                suggested_entry=opp.suggested_entry_usd,
                platform=f"{opp.platform.value} -> {opp.destination_dex}"
            )
            Logger.success(f"[DISCOVERY] 🎯 SNIPE OPP: {opp.mint[:8]}... ({opp.confidence.name})")
            send_telegram(msg, source="DISCOVERY", priority="HIGH")
            
            # V50.1: Execute paper trade if enabled
            if auto_trade:
                # V54.0: Try to get symbol from registry if missing in opp
                symbol = opp.symbol
                if not symbol:
                    from src.discovery.token_registry import get_token_registry
                    reg = get_token_registry()
                    token = reg.get_token(opp.mint)
                    symbol = token.symbol if token else f"NEW_{opp.mint[:6]}"
                
                symbol = symbol or f"NEW_{opp.mint[:6]}"
                
                # Fetch current price via DSM (or use 0 for simulation)
                try:
                    from src.system.data_source_manager import DataSourceManager
                    dsm = DataSourceManager()
                    price = dsm.get_price(opp.mint)
                except:
                    price = 0.0001  # Default for new tokens
                
                # Execute paper buy
                success, msg = capital_mgr.execute_buy(
                    engine_name="DISCOVERY",
                    symbol=symbol,
                    mint=opp.mint,
                    price=price,
                    size_usd=min(trade_size, opp.suggested_entry_usd),
                    liquidity_usd=opp.pool_liquidity_usd or 50000,
                    is_volatile=True,  # Launchpad tokens are volatile
                    dex_id=opp.destination_dex.upper() or "UNKNOWN"  # Tag source (e.g. RAYDIUM)
                )
                
                if success:
                    discovery_trades[opp.mint] = {
                        "symbol": symbol,
                        "entry_price": price,
                        "size_usd": trade_size,
                        "timestamp": opp.migration_detected_at
                    }
                    Logger.success(f"[DISCOVERY] 📝 PAPER BUY: {symbol} @ ${price:.6f}")
                    send_telegram(f"📝 PAPER BUY: {symbol} @ ${price:.6f}", source="DISCOVERY", priority="HIGH")
                else:
                    Logger.warning(f"[DISCOVERY] Paper buy failed: {msg}")
    
    # Start monitoring (blocking)
    try:
        await monitor.start()
    except asyncio.CancelledError:
        reporter_task.cancel() # STOP reporter
        monitor.stop()
        Logger.info("[DISCOVERY] 🔍 Monitor stopped")
        send_telegram("🔍 Multi-Pad Discovery Stopped", source="DISCOVERY", priority="MEDIUM")
