
import asyncio
from src.shared.system.logging import Logger
from src.analysis.performance_reporter import get_performance_reporter

SHUTDOWN_EVENT = asyncio.Event()

def set_shutdown_event(event: asyncio.Event):
    global SHUTDOWN_EVENT
    SHUTDOWN_EVENT = event

async def performance_reporting_loop():
    """
    V48.0: Scheduled Performance Reporting (every 6 hours).
    Generates and logs key metrics for Model Health, Execution, and Finance.
    """
    REPORT_INTERVAL = 6 * 60 * 60  # 6 hours
    
    Logger.info("[REPORT] 📊 Scheduler Started (Interval: 6h)")
    
    # Wait initially to allow data to accumulate
    await asyncio.sleep(60) 
    
    while not SHUTDOWN_EVENT.is_set():
        try:
            reporter = get_performance_reporter()
            
            # Generate Report
            Logger.info("[REPORT] 📊 Generating Scheduled Performance Report...")
            report = reporter.generate_report()
            
            # Log to Console
            Logger.info("\n" + report + "\n")
            
            # Reset counters for next period
            reporter.reset_counters()
            
            # Wait for next cycle
            await asyncio.sleep(REPORT_INTERVAL)
            
        except Exception as e:
            Logger.error(f"[REPORT] ❌ Reporting failed: {e}")
            await asyncio.sleep(300)

async def heartbeat_loop(broker):
    """
    V89.3: TG Heartbeat Dashboard (Frequent Status Updates).
    Sends the '/status' report automatically every 5 minutes.
    """
    HEARTBEAT_INTERVAL = 300  # 5 minutes (Standard Heartbeat)
    
    Logger.info(f"[HEARTBEAT] 💓 Scheduler Started (Interval: {HEARTBEAT_INTERVAL}s)")
    
    # Wait for initial data
    await asyncio.sleep(60)
    
    from src.analysis.status_generator import StatusGenerator
    from src.shared.system.comms_daemon import send_telegram
    
    while not SHUTDOWN_EVENT.is_set():
        try:
            # 1. Main Status
            report = StatusGenerator.generate_report(broker)
            send_telegram(report, source="HEARTBEAT", priority="HIGH")
            
            # 2. Market Snapshot (Second Bubble)
            snap_msg = StatusGenerator.generate_snapshot_msg()
            if snap_msg:
                send_telegram(snap_msg, source="HEARTBEAT", priority="HIGH")
            
            Logger.info("[HEARTBEAT] 💓 Sent Telegram Dashboard")
            
            # Wait loop with shutdown check
            for _ in range(HEARTBEAT_INTERVAL):
                if SHUTDOWN_EVENT.is_set(): break
                await asyncio.sleep(1)
                
        except Exception as e:
            Logger.error(f"[HEARTBEAT] ❌ Failed: {e}")
            await asyncio.sleep(60)
