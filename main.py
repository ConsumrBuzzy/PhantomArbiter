"""
PhantomArbiter - Unified CLI Entrypoint
=======================================
Single entrypoint with subcommands for all trading modes.

Arbitrage Commands:
    python main.py arbiter --duration 60
    python main.py arbiter --live --full-wallet
    python main.py scan --min-spread 0.9

Meme Coin Scraper Commands:
    python main.py discover
    python main.py watch --duration 60
    python main.py scout --token <MINT>

Monitoring:
    python main.py monitor --budget 500
"""

import argparse
import asyncio


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="PhantomArbiter",
        description="Solana DEX Arbitrage & Meme Coin Discovery System"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # ═══════════════════════════════════════════════════════════════
    # ARBITER SUBCOMMAND
    # ═══════════════════════════════════════════════════════════════
    arbiter_parser = subparsers.add_parser(
        "arbiter",
        help="Run spatial arbitrage scanner and trader"
    )
    arbiter_parser.add_argument(
        "--live", action="store_true",
        help="Enable LIVE trading (REAL MONEY!)"
    )
    arbiter_parser.add_argument(
        "--budget", type=float, default=50.0,
        help="Starting budget in USD (default: 50)"
    )
    arbiter_parser.add_argument(
        "--duration", type=int, default=10,
        help="Duration in minutes (default: 10, 0 for infinite)"
    )
    arbiter_parser.add_argument(
        "--interval", type=int, default=5,
        help="Scan interval in seconds (default: 5)"
    )
    arbiter_parser.add_argument(
        "--min-spread", type=float, default=0.50,
        help="Minimum spread percent to trade (default: 0.50)"
    )
    arbiter_parser.add_argument(
        "--max-trade", type=float, default=10.0,
        help="Maximum trade size in USD (default: 10)"
    )
    arbiter_parser.add_argument(
        "--full-wallet", action="store_true",
        help="Use entire wallet balance (up to max-trade)"
    )
    
    # ═══════════════════════════════════════════════════════════════
    # SCAN SUBCOMMAND (Quick one-shot opportunity scan)
    # ═══════════════════════════════════════════════════════════════
    scan_parser = subparsers.add_parser(
        "scan",
        help="Quick one-shot arbitrage opportunity scan"
    )
    scan_parser.add_argument(
        "--min-spread", type=float, default=0.20,
        help="Minimum spread to show (default: 0.20)"
    )
    
    # ═══════════════════════════════════════════════════════════════
    # DISCOVER SUBCOMMAND (Meme Coin Scraper)
    # ═══════════════════════════════════════════════════════════════
    discover_parser = subparsers.add_parser(
        "discover",
        help="Discover trending meme coins (Birdeye/DexScreener)"
    )
    discover_parser.add_argument(
        "--source", type=str, choices=["birdeye", "dexscreener", "auto"], default="auto",
        help="Data source (default: auto)"
    )
    discover_parser.add_argument(
        "--limit", type=int, default=20,
        help="Number of tokens to fetch (default: 20)"
    )
    
    # ═══════════════════════════════════════════════════════════════
    # WATCH SUBCOMMAND (Launchpad Monitor)
    # ═══════════════════════════════════════════════════════════════
    watch_parser = subparsers.add_parser(
        "watch",
        help="Watch launchpads for new token launches (pump.fun, Raydium, etc.)"
    )
    watch_parser.add_argument(
        "--duration", type=int, default=60,
        help="Duration in minutes (default: 60, 0 for infinite)"
    )
    watch_parser.add_argument(
        "--platforms", type=str, default="all",
        help="Platforms to monitor: all, pumpfun, raydium, meteora (default: all)"
    )
    
    # ═══════════════════════════════════════════════════════════════
    # SCOUT SUBCOMMAND (Smart Money Tracker)
    # ═══════════════════════════════════════════════════════════════
    scout_parser = subparsers.add_parser(
        "scout",
        help="Scout smart money wallets and audit tokens"
    )
    scout_parser.add_argument(
        "--token", type=str, default=None,
        help="Token mint to audit for smart money"
    )
    scout_parser.add_argument(
        "--wallet", type=str, default=None,
        help="Wallet address to analyze performance"
    )
    
    # ═══════════════════════════════════════════════════════════════
    # MONITOR SUBCOMMAND (Profitability Dashboard)
    # ═══════════════════════════════════════════════════════════════
    monitor_parser = subparsers.add_parser(
        "monitor",
        help="Run profitability monitor dashboard"
    )
    monitor_parser.add_argument(
        "--budget", type=float, default=500.0,
        help="Budget for profit calculations (default: 500)"
    )
    monitor_parser.add_argument(
        "--interval", type=int, default=600,
        help="Scan interval in seconds (default: 600)"
    )
    
    return parser


async def cmd_arbiter(args: argparse.Namespace) -> None:
    """Handle arbiter subcommand."""
    from src.arbitrage.arbiter import PhantomArbiter, ArbiterConfig
    
    if args.live:
        print("\n" + "⚠️ "*20)
        print("   WARNING: LIVE MODE ENABLED!")
        print("   This will execute REAL transactions with REAL money!")
        print("⚠️ "*20)
        confirm = input("\n   Type 'I UNDERSTAND' to proceed: ")
        if confirm.strip() != "I UNDERSTAND":
            print("   Cancelled.")
            return
    
    config = ArbiterConfig(
        budget=args.budget,
        min_spread=args.min_spread,
        max_trade=args.max_trade,
        live_mode=args.live,
        full_wallet=args.full_wallet
    )
    
    arbiter = PhantomArbiter(config)
    await arbiter.run(duration_minutes=args.duration, scan_interval=args.interval)


async def cmd_monitor(args: argparse.Namespace) -> None:
    """Handle monitor subcommand."""
    # Import from existing run_profitability_monitor.py
    try:
        from run_profitability_monitor import ProfitabilityMonitor
        monitor = ProfitabilityMonitor(budget=args.budget)
        await monitor.run_loop(interval_seconds=args.interval)
    except ImportError:
        print("❌ Monitor module not available")
        print("   Run: python run_profitability_monitor.py directly")


async def cmd_scan(args: argparse.Namespace) -> None:
    """Handle scan subcommand - quick one-shot opportunity scan."""
    from src.arbitrage.arbiter import PhantomArbiter, ArbiterConfig
    
    config = ArbiterConfig(min_spread=args.min_spread)
    arbiter = PhantomArbiter(config)
    
    print("\n" + "="*60)
    print("   PHANTOM ARBITER - Opportunity Scan")
    print("="*60)
    
    opportunities = await arbiter.scan_opportunities(verbose=True)
    
    print("\n" + "="*60)
    print(f"   Found {len(opportunities)} tradeable opportunities")
    print("="*60)


async def main() -> None:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return
    
    if args.command == "arbiter":
        await cmd_arbiter(args)
    elif args.command == "monitor":
        await cmd_monitor(args)
    elif args.command == "scan":
        await cmd_scan(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
