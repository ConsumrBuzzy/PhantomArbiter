"""
Skimmer CLI - Manual Testing Interface
=======================================
Command-line interface for testing zombie account scanning.

Usage:
    python -m src.modules.skimmer.cli --scan --dry-run --limit 50
    python -m src.modules.skimmer.cli --stats
    python -m src.modules.skimmer.cli --high-risk

Safety:
    All commands default to dry-run mode unless explicitly disabled.
"""

import argparse
import json
import sys
from typing import List
from src.modules.skimmer.core import SkimmerCore
from src.shared.system.database.core import DatabaseCore
from src.shared.system.database.repositories.wallet_repo import WalletRepository
from src.shared.system.logging import Logger


def scan_command(args):
    """Execute scan operation."""
    skimmer = SkimmerCore()
    
    # Get target addresses
    if args.source == 'whale_addresses':
        # Load from WalletRepository
        db = DatabaseCore()
        wallet_repo = WalletRepository(db)
        wallet_repo.init_table()
        addresses = wallet_repo.get_target_wallets()
        
        if not addresses:
            Logger.warning("⚠️ No whale addresses found in database")
            Logger.info("   Add addresses with: wallet_repo.add_target_wallet(address)")
            return
        
        Logger.info(f"📊 Loaded {len(addresses)} addresses from wallet database")
    
    elif args.source == 'json':
        # Load from existing JSON report
        try:
            with open('skimmer_report_batch_01_20260205.json', 'r') as f:
                data = json.load(f)
                addresses = [r['address'] for r in data.get('results', [])]
                Logger.info(f"📊 Loaded {len(addresses)} addresses from JSON report")
        except FileNotFoundError:
            Logger.error("❌ JSON report file not found")
            return
    
    else:
        # Manual address list
        if not args.addresses:
            Logger.error("❌ No addresses provided. Use --addresses or --source")
            return
        addresses = args.addresses.split(',')
    
    # Limit addresses
    if args.limit:
        addresses = addresses[:args.limit]
    
    # Execute scan
    results = skimmer.scan_targets(addresses, dry_run=args.dry_run)
    
    # Display results
    print("\n" + "="*60)
    print("SCAN RESULTS")
    print("="*60)
    print(f"Total Scanned:        {results['total_scanned']}")
    print(f"Zombies Found:        {results['zombies_found']}")
    print(f"Skipped:              {results['skipped']}")
    print(f"Estimated Yield:      {results['estimated_yield_sol']:.4f} SOL")
    print(f"Priority Fee:         {results['priority_fee_sol']:.6f} SOL")
    print(f"Min Yield Threshold:  {results['min_yield_threshold']:.6f} SOL")
    print(f"Dry Run:              {results['dry_run']}")
    print("="*60)
    
    # Show top candidates
    if results['results']:
        print("\nTop Zombie Candidates:")
        print("-"*60)
        sorted_results = sorted(
            results['results'], 
            key=lambda x: x['estimated_yield_sol'], 
            reverse=True
        )
        
        for i, zombie in enumerate(sorted_results[:10], 1):
            print(f"{i}. {zombie['address'][:12]}... | "
                  f"{zombie['estimated_yield_sol']:.6f} SOL | "
                  f"{zombie['risk_score']} | "
                  f"{zombie['reason']}")
        
        if len(sorted_results) > 10:
            print(f"... and {len(sorted_results) - 10} more")
    
    print("\n")


def stats_command(args):
    """Display scan statistics."""
    skimmer = SkimmerCore()
    stats = skimmer.get_statistics()
    
    print("\n" + "="*60)
    print("ZOMBIE TARGET STATISTICS")
    print("="*60)
    print(f"Total Targets:        {stats['total_targets']}")
    print(f"Pending:              {stats['pending']}")
    print(f"Verified:             {stats['verified']}")
    print(f"Closed:               {stats['closed']}")
    print(f"Skipped:              {stats['skipped']}")
    print(f"Failed (max retries): {stats['failed']}")
    print(f"Total Estimated Yield: {stats['total_estimated_yield_sol']:.4f} SOL")
    print("="*60)
    print("\n")


def high_risk_command(args):
    """Display high-risk targets for manual review."""
    skimmer = SkimmerCore()
    high_risk = skimmer.repo.get_high_risk_targets(limit=args.limit or 20)
    
    print("\n" + "="*60)
    print("HIGH RISK TARGETS (Manual Review Required)")
    print("="*60)
    
    if not high_risk:
        print("No high-risk targets found.")
    else:
        for i, target in enumerate(high_risk, 1):
            print(f"{i}. {target['address'][:12]}... | "
                  f"{target['estimated_yield_sol']:.6f} SOL | "
                  f"Status: {target['status']} | "
                  f"{target.get('error_message', 'Recent activity detected')}")
    
    print("="*60)
    print("\n")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Skimmer CLI - Zombie Account Scanner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan whale addresses (dry-run, safe)
  python -m src.modules.skimmer.cli --scan --dry-run
  
  # Scan first 50 addresses from JSON report
  python -m src.modules.skimmer.cli --scan --source json --limit 50 --dry-run
  
  # View statistics
  python -m src.modules.skimmer.cli --stats
  
  # Review high-risk targets
  python -m src.modules.skimmer.cli --high-risk --limit 10
        """
    )
    
    # Command selection
    parser.add_argument('--scan', action='store_true', help='Scan addresses for zombies')
    parser.add_argument('--stats', action='store_true', help='Display scan statistics')
    parser.add_argument('--high-risk', action='store_true', help='Show high-risk targets')
    
    # Scan options
    parser.add_argument('--source', choices=['whale_addresses', 'json', 'manual'], 
                        default='whale_addresses',
                        help='Address source (default: whale_addresses)')
    parser.add_argument('--addresses', type=str, help='Comma-separated addresses (if source=manual)')
    parser.add_argument('--limit', type=int, help='Limit number of addresses to scan')
    parser.add_argument('--dry-run', action='store_true', default=True, 
                        help='Preview only, no DB writes (default: True)')
    parser.add_argument('--execute', action='store_true', 
                        help='Actually write to DB (disables dry-run)')
    
    args = parser.parse_args()
    
    # Override dry-run if --execute specified
    if args.execute:
        args.dry_run = False
        Logger.warning("⚠️ Dry-run DISABLED - will write to database")
    
    # Execute commands
    try:
        if args.scan:
            scan_command(args)
        elif args.stats:
            stats_command(args)
        elif args.high_risk:
            high_risk_command(args)
        else:
            parser.print_help()
            sys.exit(1)
    
    except KeyboardInterrupt:
        Logger.warning("\n⚠️ Scan interrupted by user")
        sys.exit(130)
    except Exception as e:
        Logger.error(f"❌ CLI Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
