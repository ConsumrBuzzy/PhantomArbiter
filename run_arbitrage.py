#!/usr/bin/env python
"""
Arbitrage Engine - Main Entry Point
====================================

Usage:
    python run_arbitrage.py                    # Default: FUNDING mode
    python run_arbitrage.py --mode SPATIAL     # Cross-DEX arbitrage
    python run_arbitrage.py --mode ALL         # All strategies
    python run_arbitrage.py --duration 300     # Run for 5 minutes

Environment Variables:
    ARBITRAGE_MODE     - Default mode (SPATIAL | TRIANGULAR | FUNDING | ALL)
    ARBITRAGE_BUDGET   - Budget in USD (default: 500)
"""

import argparse
import asyncio
import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import Settings
from src.arbitrage.core.orchestrator import ArbitrageOrchestrator, ArbitrageConfig
from src.system.logging import Logger


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Arbitrage Engine - Multi-Strategy Crypto Arbitrage Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_arbitrage.py                      Run with default settings
  python run_arbitrage.py --mode SPATIAL       Focus on cross-DEX arbitrage
  python run_arbitrage.py --demo               Run demo with fake data
  python run_arbitrage.py --duration 3600      Run for 1 hour then exit
        """
    )
    
    parser.add_argument(
        '--mode', 
        type=str, 
        choices=['SPATIAL', 'TRIANGULAR', 'FUNDING', 'ALL'],
        default=Settings.ARBITRAGE_MODE,
        help='Arbitrage strategy mode'
    )
    
    parser.add_argument(
        '--budget',
        type=float,
        default=Settings.ARBITRAGE_BUDGET_USD,
        help='Budget in USD'
    )
    
    parser.add_argument(
        '--duration',
        type=float,
        default=None,
        help='Duration to run in seconds (None = forever)'
    )
    
    parser.add_argument(
        '--tick',
        type=float,
        default=Settings.DASHBOARD_REFRESH_SEC,
        help='Dashboard refresh interval in seconds'
    )
    
    parser.add_argument(
        '--live',
        action='store_true',
        help='Enable live execution (default: paper mode)'
    )
    
    parser.add_argument(
        '--demo',
        action='store_true',
        help='Run demo mode with fake data'
    )
    
    parser.add_argument(
        '--no-telegram',
        action='store_true',
        help='Disable Telegram alerts'
    )
    
    return parser.parse_args()


def run_demo():
    """Run a demo with fake data to show the dashboard."""
    from src.arbitrage.monitoring.live_dashboard import LiveDashboard, SpreadInfo
    import time
    
    print("\n🎮 Running Arbitrage Engine DEMO...")
    print("    This shows fake data to demonstrate the dashboard.")
    print("    Press Ctrl+C to exit.\n")
    
    time.sleep(2)
    
    dashboard = LiveDashboard(budget=500.0)
    dashboard.mode = "DEMO"
    
    # Fake spreads
    spreads = [
        SpreadInfo(
            pair="SOL/USDC",
            prices={"Jupiter": 95.42, "Raydium": 95.51, "Orca": 95.48},
            best_buy="Jupiter",
            best_sell="Raydium",
            spread_pct=0.09,
            estimated_profit_usd=0.09,
            status="MONITOR"
        ),
        SpreadInfo(
            pair="BONK/USDC",
            prices={"Jupiter": 0.0000234, "Raydium": 0.0000235, "Orca": 0.0},
            best_buy="Jupiter",
            best_sell="Raydium",
            spread_pct=0.03,
            estimated_profit_usd=0.03,
            status="LOW"
        ),
        SpreadInfo(
            pair="WIF/USDC",
            prices={"Jupiter": 2.34, "Raydium": 2.35, "Orca": 2.34},
            best_buy="Jupiter",
            best_sell="Raydium",
            spread_pct=0.42,
            estimated_profit_usd=0.84,
            status="READY"
        ),
    ]
    
    dashboard.update_spreads(spreads)
    dashboard.update_funding_rates({"SOL-PERP": 0.0125, "BTC-PERP": 0.0089, "ETH-PERP": -0.0042})
    
    # Simulate some trades
    dashboard.record_trade(200.0, 0.84)
    dashboard.record_trade(150.0, 0.45)
    dashboard.record_trade(100.0, -0.12)
    
    try:
        while True:
            dashboard.render(clear=True)
            time.sleep(2)
            
            # Slightly randomize spreads to show activity
            import random
            for spread in spreads:
                spread.spread_pct += random.uniform(-0.02, 0.02)
                spread.spread_pct = max(0.01, spread.spread_pct)
                
            dashboard.update_spreads(spreads)
            
    except KeyboardInterrupt:
        print("\n\n🛑 Demo stopped.")


async def main():
    """Main entry point."""
    args = parse_args()
    
    # Demo mode
    if args.demo:
        run_demo()
        return
    
    # Banner
    print("""
    ╔═══════════════════════════════════════════════════════════════════╗
    ║           ARBITRAGE ENGINE v1.0                                   ║
    ║           Multi-Strategy Crypto Arbitrage Bot                     ║
    ╚═══════════════════════════════════════════════════════════════════╝
    """)
    
    Logger.info(f"🚀 Starting Arbitrage Engine")
    Logger.info(f"   Mode: {args.mode}")
    Logger.info(f"   Budget: ${args.budget}")
    Logger.info(f"   Execution: {'LIVE' if args.live else 'PAPER'}")
    Logger.info(f"   Telegram: {'ON' if not args.no_telegram else 'OFF'}")
    
    # Configure
    config = ArbitrageConfig(
        mode=args.mode,
        budget=args.budget,
        tick_interval=args.tick,
        enable_execution=args.live,
        telegram_enabled=not args.no_telegram
    )
    
    # Create orchestrator
    orchestrator = ArbitrageOrchestrator(config)
    
    # Run
    try:
        await orchestrator.run(duration=args.duration)
    except KeyboardInterrupt:
        Logger.info("🛑 Stopped by user")
    finally:
        orchestrator.stop()
        Logger.info("👋 Arbitrage Engine stopped.")


if __name__ == "__main__":
    asyncio.run(main())
