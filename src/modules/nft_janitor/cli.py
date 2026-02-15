"""
NFT Janitor CLI
===============
Command-line interface for Legacy NFT rent reclamation operations.
"""

import argparse
from src.modules.nft_janitor.scanner import NFTScanner
from src.modules.nft_janitor.config import JanitorConfig
from src.shared.system.logging import Logger


def cmd_scan(args):
    """Execute NFT discovery scan."""
    scanner = NFTScanner()

    Logger.info("=" * 60)
    Logger.info("🔍 NFT JANITOR - LEGACY NFT DISCOVERY")
    Logger.info("=" * 60)

    results = scanner.scan_tensor(
        max_price_sol=args.max_price,
        limit=args.limit,
        dry_run=args.dry_run
    )

    # Display results
    Logger.info("\n📊 SCAN RESULTS:")
    Logger.info(f"   Total Scanned:       {results['total_scanned']}")
    Logger.info(f"   Opportunities Found: {results['opportunities_found']}")
    Logger.info(f"   Blocked/Unprofitable: {results['blocked']}")
    Logger.info(f"   Est. Total Profit:   {results['total_estimated_profit_sol']:.4f} SOL")

    if results['opportunities_found'] > 0:
        Logger.success("\n💰 TOP OPPORTUNITIES:")
        for i, opp in enumerate(results['results'][:10], 1):
            Logger.info(f"   {i}. {opp['mint_address'][:12]}... | "
                       f"{opp['collection_name'][:30]} | "
                       f"Price: {opp['floor_price_sol']:.4f} SOL | "
                       f"Profit: {opp['estimated_profit_sol']:.4f} SOL")

    if args.dry_run:
        Logger.warning("\n⚠️  DRY RUN MODE - Nothing saved to database")
    else:
        Logger.success(f"\n✅ Saved {results['opportunities_found']} opportunities to database")


def cmd_stats(args):
    """Display statistics from database."""
    scanner = NFTScanner()
    stats = scanner.get_statistics()

    Logger.info("=" * 60)
    Logger.info("📊 NFT JANITOR - STATISTICS")
    Logger.info("=" * 60)
    Logger.info(f"   Total Targets:          {stats['total_targets']}")
    Logger.info(f"   Discovered (Ready):     {stats['discovered']}")
    Logger.info(f"   Purchased:              {stats['purchased']}")
    Logger.info(f"   Burned:                 {stats['burned']}")
    Logger.info(f"   Failed:                 {stats['failed']}")
    Logger.info(f"   Skipped:                {stats['skipped']}")
    Logger.info(f"   Est. Total Profit:      {stats['total_estimated_profit_sol']:.4f} SOL")
    Logger.info(f"   Actual Total Profit:    {stats['total_actual_profit_sol']:.4f} SOL")
    Logger.info(f"   Success Rate:           {stats['success_rate']:.1f}%")


def main():
    """Main CLI entrypoint for NFT Janitor."""
    parser = argparse.ArgumentParser(
        prog="janitor",
        description="Legacy NFT Rent Reclamation System"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # SCAN COMMAND
    scan_parser = subparsers.add_parser("scan", help="Discover profitable NFTs")
    scan_parser.add_argument(
        "--max-price",
        type=float,
        default=JanitorConfig.MAX_FLOOR_PRICE_SOL,
        help=f"Maximum floor price in SOL (default: {JanitorConfig.MAX_FLOOR_PRICE_SOL})"
    )
    scan_parser.add_argument(
        "--limit",
        type=int,
        default=JanitorConfig.SCAN_BATCH_SIZE,
        help=f"Maximum NFTs to scan (default: {JanitorConfig.SCAN_BATCH_SIZE})"
    )
    scan_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=JanitorConfig.DRY_RUN_DEFAULT,
        help="Don't save to database (default: true)"
    )
    scan_parser.add_argument(
        "--save",
        action="store_false",
        dest="dry_run",
        help="Save results to database"
    )

    # STATS COMMAND
    stats_parser = subparsers.add_parser("stats", help="Show profitability statistics")

    # Parse arguments
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Route to command handler
    if args.command == "scan":
        cmd_scan(args)
    elif args.command == "stats":
        cmd_stats(args)


if __name__ == "__main__":
    main()
