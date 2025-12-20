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
        "--interval", type=int, default=2,
        help="Scan interval in seconds (default: 2)"
    )
    arbiter_parser.add_argument(
        "--min-spread", type=float, default=0.50,
        help="Minimum spread percent to trade (default: 0.50)"
    )
    arbiter_parser.add_argument(
        "--max-trade", type=float, default=0,
        help="Maximum trade size in USD (default: 0 = use full budget)"
    )
    arbiter_parser.add_argument(
        "--gas-budget", type=float, default=5.0,
        help="Gas budget in USD (SOL for fees, default: 5)"
    )
    arbiter_parser.add_argument(
        "--full-wallet", action="store_true",
        help="Use entire wallet balance (up to max-trade)"
    )
    arbiter_parser.add_argument(
        "--risk-tier", type=str, default="all",
        choices=["all", "low", "mid", "high", "trending"],
        help="Pair risk tier: all (default), low, mid, high, or trending"
    )
    arbiter_parser.add_argument(
        "--smart-pods", action="store_true",
        help="Enable smart pod rotation (focus 1 pod per scan, auto-promote/demote)"
    )
    arbiter_parser.add_argument(
        "--unified-engine", action="store_true",
        help="Use unified execution engine (Meteora + Orca atomic, bypasses Jupiter)"
    )
    arbiter_parser.add_argument(
        "--pool-scan", action="store_true",
        help="Run pool discovery on startup (finds Meteora + Orca pools for all tokens)"
    )
    arbiter_parser.add_argument(
        "--landlord", action="store_true",
        help="Enable Landlord strategy (delta-neutral yield on Drift during idle)"
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
    
    # ═══════════════════════════════════════════════════════════════
    # CLEAN SUBCOMMAND (Panic Button)
    # ═══════════════════════════════════════════════════════════════
    clean_parser = subparsers.add_parser(
        "clean",
        help="Liquidity Panic Button: Sell tokens for USDC/SOL"
    )
    clean_parser.add_argument("--token", type=str, help="Token Symbol (BONK) or Mint Address")
    clean_parser.add_argument("--all", action="store_true", help="SELL EVERYTHING (Except USDC)")
    
    return parser


async def cmd_arbiter(args: argparse.Namespace) -> None:
    """Handle arbiter subcommand."""
    from src.arbiter.arbiter import PhantomArbiter, ArbiterConfig
    
    if args.live:
        confirm = input("\n   ⚠️ LIVE MODE - Type 'I UNDERSTAND' to proceed: ")
        if confirm.strip() != "I UNDERSTAND":
            print("   Cancelled.")
            return
    
    # Select pairs based on risk tier
    from src.arbiter.core.pod_engine import LOW_RISK_PAIRS, MID_RISK_PAIRS, HIGH_RISK_PAIRS, TRENDING_PAIRS, CORE_PAIRS
    tier_map = {
        "all": CORE_PAIRS,
        "low": LOW_RISK_PAIRS,
        "mid": MID_RISK_PAIRS,
        "high": HIGH_RISK_PAIRS,
        "trending": TRENDING_PAIRS,
    }
    selected_pairs = tier_map.get(args.risk_tier, CORE_PAIRS)
    
    config = ArbiterConfig(
        budget=args.budget,
        gas_budget=args.gas_budget,
        min_spread=args.min_spread,
        max_trade=args.max_trade,
        live_mode=args.live,
        full_wallet=args.full_wallet,
        pairs=selected_pairs,
        use_unified_engine=getattr(args, 'unified_engine', False)
    )
    
    smart_pods_mode = getattr(args, 'smart_pods', False)
    if smart_pods_mode:
        print(f"   🔀 Smart Pod Rotation: ENABLED")
    print(f"   📊 Risk Tier: {args.risk_tier.upper()} ({len(selected_pairs)} pairs)")
    
    # Pool discovery on startup
    if getattr(args, 'pool_scan', False):
        print(f"   🔍 Running pool discovery...")
        from src.shared.execution.pool_scanner import PoolScanner
        scanner = PoolScanner()
        count = await scanner.discover_all()
        print(f"   ✅ Discovered {count} Meteora/Orca pools")
    
    # Landlord (Drift hedging) initialization
    landlord = None
    if getattr(args, 'landlord', False):
        print(f"   🏠 Landlord Strategy: ENABLED")
        try:
            from src.arbiter.strategies.landlord import Landlord
            landlord = Landlord()
            landlord_ready = await landlord.initialize()
            if landlord_ready:
                funding = await landlord.get_funding_snapshot()
                if funding:
                    print(f"   📊 SOL Funding: {funding.rate_hourly:.3f}%/h ({funding.rate_annual:.0f}% APY)")
                    print(f"   💰 Direction: {'Shorts earn ✅' if funding.is_positive else 'Longs earn'}")
            else:
                print(f"   ⚠️ Landlord init failed - continuing without hedging")
                landlord = None
        except Exception as e:
            print(f"   ⚠️ Landlord error: {e}")
            landlord = None
    
    arbiter = PhantomArbiter(config)
    await arbiter.run(duration_minutes=args.duration, scan_interval=args.interval, smart_pods=smart_pods_mode, landlord=landlord)


async def cmd_scan(args: argparse.Namespace) -> None:
    """Handle scan subcommand - quick one-shot opportunity scan."""
    from src.arbiter.arbiter import PhantomArbiter, ArbiterConfig
    
    config = ArbiterConfig(min_spread=args.min_spread)
    arbiter = PhantomArbiter(config)
    
    print("\n" + "="*60)
    print("   PHANTOM ARBITER - Opportunity Scan")
    print("="*60)
    
    opportunities = await arbiter.scan_opportunities(verbose=True)
    
    print("\n" + "="*60)
    print(f"   Found {len(opportunities)} tradeable opportunities")
    print("="*60)


async def cmd_discover(args: argparse.Namespace) -> None:
    """Handle discover subcommand - find trending meme coins."""
    from src.scraper.scout.scraper import TokenScraper
    
    print("\n" + "="*60)
    print("   PHANTOM ARBITER - Token Discovery")
    print("="*60)
    
    scraper = TokenScraper()
    candidates = scraper.get_candidates()
    
    if candidates:
        print(f"\n   🎯 Found {len(candidates)} trending tokens:\n")
        print(f"   {'Symbol':<12} {'Source':<20} {'Address'}")
        print("   " + "-"*70)
        for c in candidates[:args.limit]:
            print(f"   {c.get('symbol', 'UNKNOWN'):<12} {c.get('source', ''):<20} {c['address'][:20]}...")
    else:
        print("\n   ⚠️ No candidates found")
    
    print("\n" + "="*60)


async def cmd_watch(args: argparse.Namespace) -> None:
    """Handle watch subcommand - monitor launchpads for new tokens."""
    import time
    from src.scraper.discovery.launchpad_monitor import LaunchpadMonitor, LaunchEvent, MigrationEvent
    
    print("\n" + "="*60)
    print("   PHANTOM ARBITER - Launchpad Watcher")
    print("="*60)
    print(f"   Platforms:  {args.platforms}")
    print(f"   Duration:   {args.duration} minutes")
    print("="*60)
    print("\n   Watching for new launches... (Ctrl+C to stop)\n")
    
    monitor = LaunchpadMonitor()
    
    # Event handlers
    @monitor.on_launch
    async def handle_launch(event: LaunchEvent):
        print(f"   🚀 NEW LAUNCH: {event.symbol or event.mint[:16]}...")
        print(f"      Platform: {event.platform.value}")
        print(f"      Creator:  {event.creator[:16]}...")
        print()
    
    @monitor.on_migration
    async def handle_migration(event: MigrationEvent):
        print(f"   🎓 MIGRATION: {event.mint[:16]}...")
        print(f"      DEX:      {event.destination_dex}")
        print(f"      Pool:     {event.destination_pool[:16]}...")
        print()
    
    try:
        end_time = time.time() + (args.duration * 60) if args.duration > 0 else float('inf')
        await monitor.start()
        
        while time.time() < end_time:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        pass
    finally:
        monitor.stop()
    
    print("\n   Watcher stopped.")


async def cmd_scout(args: argparse.Namespace) -> None:
    """Handle scout subcommand - analyze smart money."""
    from src.scraper.agents.scout_agent import ScoutAgent
    
    print("\n" + "="*60)
    print("   PHANTOM ARBITER - Smart Money Scout")
    print("="*60)
    
    scout = ScoutAgent()
    
    if args.token:
        print(f"\n   Auditing token: {args.token[:20]}...")
        result = await scout.flash_audit(args.token)
        
        if result:
            print(f"\n   📊 Audit Results:")
            print(f"      Smart Money Count: {result.get('smart_money_count', 0)}")
            print(f"      Rug Risk:          {'⚠️ YES' if result.get('rug_risk') else '✅ NO'}")
            print(f"      Source:            {result.get('source', 'unknown')}")
            if result.get('wallets'):
                print(f"      Top Wallets:       {len(result['wallets'])}")
        else:
            print("\n   ⚠️ Audit failed or no data available")
            
    elif args.wallet:
        print(f"\n   Analyzing wallet: {args.wallet[:20]}...")
        perf = await scout.calculate_wallet_performance(args.wallet)
        
        if perf:
            print(f"\n   📊 Wallet Performance:")
            print(f"      Win Rate:  {perf.get('win_rate', 0)*100:.1f}%")
            print(f"      Total PnL: ${perf.get('total_pnl', 0):.2f}")
        else:
            print("\n   ⚠️ Analysis failed or no data available")
    else:
        print("\n   Usage:")
        print("     python main.py scout --token <MINT>")
        print("     python main.py scout --wallet <ADDRESS>")
    
    print("\n" + "="*60)


async def cmd_monitor(args: argparse.Namespace) -> None:
    """Handle monitor subcommand."""
    try:
        from run_profitability_monitor import ProfitabilityMonitor
        monitor = ProfitabilityMonitor(budget=args.budget)
        await monitor.run_loop(interval_seconds=args.interval)
    except ImportError:
        print("❌ Monitor module not available")
        print("   Run: python run_profitability_monitor.py directly")


async def cmd_clean(args: argparse.Namespace) -> None:
    """
    Emergency cleanup tool.
    Dumps tokens to USDC/SOL.
    """
    from src.shared.execution.wallet import WalletManager
    from src.shared.execution.swapper import JupiterSwapper
    from config.settings import Settings
    from src.shared.system.logging import Logger
    
    print("\\n" + "="*60)
    print("   PHANTOM ARBITER - Wallet Cleaner 🧹")
    print("="*60)
    
    # 1. Setup
    Settings.ENABLE_TRADING = True
    wallet = WalletManager()
    if not wallet.keypair:
        print("❌ No Private Key found. Cannot clean.")
        return
        
    swapper = JupiterSwapper(wallet)
    
    # 2. Identify Targets
    targets = [] # List of mints
    
    if args.all:
        print("⚠️  WARNING: CLEANING ALL ASSETS (Except USDC)...")
        confirm = input("   Type 'CONFIRM' to dump all bags: ")
        if confirm.strip() != "CONFIRM":
            print("   Cancelled.")
            return
            
        print("   Scanning wallet...")
        tokens = wallet.get_all_token_accounts()
        for mint, bal in tokens.items():
            if mint != Settings.USDC_MINT and bal > 0:
                targets.append(mint)
    
    elif args.token:
        # Resolve Symbol -> Mint
        token_input = args.token.upper()
        target_mint = None
        
        # Check Settings.ASSETS
        if token_input in Settings.ASSETS:
            target_mint = Settings.ASSETS[token_input]
        elif len(token_input) > 30: # Assume Mint Address
            target_mint = token_input
        else:
            print(f"❌ Unknown token symbol: {token_input}")
            return
            
        targets.append(target_mint)
        
    else:
        print("❌ Must specify --token <SYMBOL> or --all")
        return
        
    if not targets:
        print("✨ Wallet is clean! No targets found.")
        return
        
    # 3. Execute Dumps
    print(f"🔥 Dumping {len(targets)} assets...")
    
    for mint in targets:
        info = wallet.get_token_info(mint)
        if not info: continue
            
        symbol = "UNKNOWN"
        # Reverse lookup logic or just use mint
        for k, v in Settings.ASSETS.items():
            if v == mint:
                symbol = k
                break
                
        bal = float(info["uiAmount"])
        print(f"📉 Selling {bal:,.4f} {symbol or mint[:6]}...")
        
        # Use execute_swap with 0 amount -> Sells ALL
        tx = swapper.execute_swap(
            direction="SELL", 
            amount_usd=0, 
            reason="Clean Command", 
            target_mint=mint,
            priority_fee=100000 
        )
        
        if tx:
            print(f"✅ Sold: {tx}")
        else:
            print(f"❌ Failed to sell {symbol}")
            
        await asyncio.sleep(1.0) # Rate limit protection

    print("🧹 Cleanup Complete.")


async def main() -> None:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return
    
    command_handlers = {
        "arbiter": cmd_arbiter,
        "scan": cmd_scan,
        "discover": cmd_discover,
        "watch": cmd_watch,
        "scout": cmd_scout,
        "monitor": cmd_monitor,
        "clean": cmd_clean,
    }
    
    handler = command_handlers.get(args.command)
    if handler:
        await handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n   Goodbye!")
