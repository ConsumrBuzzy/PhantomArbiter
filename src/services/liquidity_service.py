import asyncio
from src.shared.system.logging import Logger
from config.settings import Settings
from src.utils.boot_utils import BootTimer
from src.shared.system.comms_daemon import send_telegram

# Imports for loop
from src.liquidity.liquidity_manager import get_liquidity_manager, MarketRegime
from src.shared.system.capital_manager import get_capital_manager

SHUTDOWN_EVENT = asyncio.Event()


def set_shutdown_event(event: asyncio.Event):
    global SHUTDOWN_EVENT
    SHUTDOWN_EVENT = event


async def liquidity_cycle_loop():
    """
    V49.0: Orca CLMM Market Making Cycle.
    """

    # Check if Orca is enabled
    if not getattr(Settings, "ORCA_ENABLED", False):
        Logger.info("[LIQUIDITY] 🐋 Orca CLMM disabled in settings")
        return

    CYCLE_INTERVAL = 5 * 60  # 5 minutes for testing

    Logger.info("[LIQUIDITY] 🐋 Orca Market Maker Started (Interval: 5m)")
    send_telegram(
        "🐋 Orca CLMM Started (SIMULATION MODE)", source="ORCA", priority="HIGH"
    )

    # Init Manager
    liquidity_manager = get_liquidity_manager()
    cap_man = get_capital_manager()

    BootTimer.mark("Liquidity Service Init")

    # Short initial delay (10s) to allow other systems to init
    await asyncio.sleep(10)

    first_run = True

    first_run = True

    # V23: Use Supervisor Pattern (Task Cancellation)
    try:
        while True:  # Run until cancelled
            cycle_start = (
                "[LIQUIDITY] 🐋 "
                + ("Initial" if first_run else "Running")
                + " Liquidity Cycle..."
            )
            Logger.info(cycle_start)

            # 1. Determine current market regime
            current_regime = MarketRegime.NEUTRAL

            # 2. Execute harvesting cycle
            results = liquidity_manager.execute_harvesting_cycle(current_regime)

            # 3. Log results
            if results.get("positions_closed", 0) > 0:
                msg = f"🐋 Closed {results['positions_closed']} positions"
                Logger.warning(f"[LIQUIDITY] {msg}")
                send_telegram(msg, source="ORCA", priority="MEDIUM")

            if results.get("fees_harvested", 0) > 0:
                msg = f"🐋 Harvested ${results['fees_harvested']:.2f}"
                Logger.success(f"[LIQUIDITY] {msg}")
                send_telegram(msg, source="ORCA", priority="LOW")

            # 4. Check if we should deploy new liquidity
            active_positions = len(
                [p for p in liquidity_manager.positions.values() if p.is_active]
            )

            if active_positions == 0:
                available = (
                    cap_man.get_available_cash("UNIFIED")
                    if hasattr(cap_man, "get_available_cash")
                    else 100
                )
                should_deploy, reason = liquidity_manager.should_deploy(
                    current_regime, available
                )

                if should_deploy:
                    pool = getattr(Settings, "ORCA_DEFAULT_POOL", "")
                    deploy_amount = min(available * 0.20, 50)  # Max 20% or $50

                    msg = f"🐋 Deploying ${deploy_amount:.2f} (SOL/USDC)"
                    Logger.info(f"[LIQUIDITY] {msg}")
                    send_telegram(msg, source="ORCA", priority="MEDIUM")

                    position = liquidity_manager.deploy_position(
                        pool_address=pool,
                        capital_usd=deploy_amount,
                        regime=current_regime,
                    )

                    if position:
                        msg = f"🐋 Position OPEN: ±{position.range_pct}% range"
                        Logger.success(f"[LIQUIDITY] {msg}")
                        send_telegram(msg, source="ORCA", priority="HIGH")
                else:
                    Logger.debug(f"[LIQUIDITY] 🐋 Skip deploy: {reason}")

            first_run = False
            await asyncio.sleep(CYCLE_INTERVAL)

    except asyncio.CancelledError:
        Logger.info("[LIQUIDITY] 🛑 Cancellation received")
        raise  # Rethrow
    except Exception as e:
        Logger.error(f"[LIQUIDITY] ❌ Cycle failed: {e}")
        await asyncio.sleep(60)

    # Graceful shutdown
    Logger.info("[LIQUIDITY] 🐋 Closing all positions on shutdown...")
    liquidity_manager.close_all_positions(reason="System shutdown")
