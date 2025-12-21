
import asyncio
from src.shared.system.logging import Logger
from config.settings import Settings
from src.utils.boot_utils import BootTimer
from src.shared.system.capital_manager import get_capital_manager

SHUTDOWN_EVENT = asyncio.Event()

def set_shutdown_event(event: asyncio.Event):
    global SHUTDOWN_EVENT
    SHUTDOWN_EVENT = event

async def ml_retraining_loop(broker):
    """
    V86.3: "ML On-Demand" Monitor.
    Passive mode: Checks for new data and alerts user.
    Active mode: Only if Settings.ML_AUTO_RETRAIN is True.
    """
    cap_man = get_capital_manager()
    RETRAIN_INTERVAL = 3600 # 1 hour
    
    # Check Active/Passive Mode
    auto_retrain = getattr(Settings, 'ML_AUTO_RETRAIN', False)
    mode_str = "ACTIVE (Auto-Retrain)" if auto_retrain else "PASSIVE (Alert Only)"
    
    Logger.info(f"[ML] 🧠 On-Demand Monitor Started ({mode_str})")
    
    # Boot Timer Mark
    BootTimer.mark("ML Monitor Started")
    
    first_run = True
    
    while not SHUTDOWN_EVENT.is_set():
        try:
            if not first_run:
                # Wait for next cycle
                await asyncio.sleep(RETRAIN_INTERVAL)
            else:
                # First run: minor delay to let system settle
                await asyncio.sleep(10) 
                first_run = False
                
            if SHUTDOWN_EVENT.is_set(): break
            
            # 1. Wallet Maintenance (V47.3)
            # Check all engines for bankruptcy/gas issues
            Logger.info("[MAINTENANCE] 🛠️ Performing Hourly Wallet Check...")
            for engine_name in cap_man.ENGINE_NAMES:
                cap_man.perform_maintenance(engine_name)
            
            # 2. Check for New Data (V86.3)
            # Heuristic: Check size of trade journal (simple file check)
            # TODO: Link to actual TradeJournal class count
            try:
                # Placeholder: In future, get actual count from DB or Journal
                pass
            except: pass
            
            # Logic: If Passive, just alert. If Active, run pipeline.
            if auto_retrain:
                Logger.info("[ML] 🧠 Starting scheduled model retraining...")
                from src.ml.trainer_supervisor import run_retraining_pipeline
                loop = asyncio.get_running_loop()
                success = await loop.run_in_executor(None, lambda: run_retraining_pipeline(force=False))
                
                if success:
                    Logger.success("[ML] ✅ Model retrained/verified successfully")
                    if hasattr(broker, 'merchant_engines'):
                         for engine in broker.merchant_engines.values():
                             if hasattr(engine, 'reload_ml_model'):
                                 engine.reload_ml_model()
            else:
                # Passive Mode: Alert if significant new data (Placeholder logic)
                # For now, we just log a reminder daily or if data changed
                # Logger.info("[ML] 🧠 System healthy. Run /retrain_ml if market conditions changed.")
                pass
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            Logger.error(f"[ML] ❌ Monitor execution failed: {e}")
            await asyncio.sleep(300)
