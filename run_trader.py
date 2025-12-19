"""
PhantomArbiter - Unified Price Exchange Trader
===============================================
V2.0 Stable Baseline (Consolidated from V1.x)

Core Features:
- Atomic Buy+Sell+Tip bundling with pre-flight simulation
- Spatial arbitrage across Jupiter, Raydium, Orca
- Automatic gas management and rent reclamation
"""

import asyncio
import os
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

# SOLANA / SOLDERS IMPORTS
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solders.pubkey import Pubkey
from solders.system_program import transfer, TransferParams

# Load .env and Settings
from dotenv import load_dotenv
load_dotenv()
from config.settings import Settings
from src.system.logging import Logger


# ═══════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
JITO_TIP_ADDRESS = "96g9sRestpBwaMbuEhc28Dcx2w57C8asLx1uWBYEAm8B"

# Core profitable pairs (reduced from 12 → 4 for stability)
CORE_PAIRS = [
    ("SOL/USDC", "So11111111111111111111111111111111111111112", USDC_MINT),
    ("BONK/USDC", "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", USDC_MINT),
    ("WIF/USDC", "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", USDC_MINT),
    ("JUP/USDC", "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", USDC_MINT),
]

# Whitelisted mints for rent reclamation (don't close these)
WHITELIST_MINTS = [
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",  # BONK
    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",  # WIF
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",  # JUP
    "So11111111111111111111111111111111111111112",   # SOL
]


class UnifiedTrader:
    """
    Atomic arbitrage trader with pre-flight simulation protection.
    
    Attributes:
        budget: Initial USDC allocation
        live_mode: If True, executes real transactions
        min_spread: Minimum spread % to consider profitable
        max_trade: Maximum trade size in USD
        full_wallet: If True, uses entire wallet balance
    """
    
    def __init__(
        self,
        budget: float = 50.0,
        live_mode: bool = False,
        min_spread: float = 0.20,
        max_trade: float = 10.0,
        full_wallet: bool = False
    ):
        self.budget = budget
        self.live_mode = live_mode
        self.min_spread = min_spread
        self.max_trade = max_trade
        self.full_wallet = full_wallet
        
        # Balance tracking
        self.current_balance = budget
        self.starting_balance = budget
        
        # Statistics
        self.total_trades = 0
        self.total_profit = 0.0
        self.trades: List[Dict] = []
        
        # Execution components (initialized in live mode)
        self.wallet_manager = None
        self.swapper = None
        self._connected = False
        
        if live_mode:
            self._setup_live_mode()

    # ═══════════════════════════════════════════════════════════════
    # LIVE MODE SETUP
    # ═══════════════════════════════════════════════════════════════
    
    def _setup_live_mode(self) -> None:
        """Initialize wallet and swapper for live trading."""
        private_key = os.getenv("PHANTOM_PRIVATE_KEY") or os.getenv("SOLANA_PRIVATE_KEY")
        
        if not private_key:
            print("\n❌ LIVE MODE FAILED: No private key found!")
            print("   Add SOLANA_PRIVATE_KEY to .env")
            self.live_mode = False
            return
        
        try:
            Settings.ENABLE_TRADING = True
            
            from src.execution.wallet import WalletManager
            from src.execution.swapper import JupiterSwapper
            
            self.wallet_manager = WalletManager()
            if not self.wallet_manager.keypair:
                raise ValueError("WalletManager failed to load keypair")
                 
            self.swapper = JupiterSwapper(self.wallet_manager)
            self._connected = True
            
            # Sync balance if Full Wallet Mode
            if self.full_wallet:
                usdc_bal = self.wallet_manager.get_balance(USDC_MINT)
                self.starting_balance = usdc_bal
                self.current_balance = usdc_bal
                print(f"   💰 Full Wallet Mode: Using real balance ${usdc_bal:.2f}")
            
            print(f"\n✅ LIVE MODE ENABLED")
            print(f"   Wallet: {self.wallet_manager.get_public_key()[:8]}...")
            max_trade_str = "UNLIMITED ♾️" if self.max_trade <= 0 else f"${self.max_trade}"
            print(f"   Max Trade: {max_trade_str}")
            print(f"   Gas Mgmt:  Enabled (Replenish < {Settings.GAS_CRITICAL_SOL} SOL)")
            
        except Exception as e:
            print(f"\n❌ LIVE MODE FAILED: {e}")
            self.live_mode = False
            self._connected = False

    def _ensure_connected(self) -> bool:
        """Verify RPC connection, attempt reconnect if needed."""
        if not self.live_mode:
            return True
            
        if not self._connected or not self.wallet_manager:
            try:
                self._setup_live_mode()
            except Exception as e:
                Logger.error(f"Reconnect failed: {e}")
                return False
        
        return self._connected

    # ═══════════════════════════════════════════════════════════════
    # ATOMIC TRANSACTION BUNDLING
    # ═══════════════════════════════════════════════════════════════

    async def prepare_atomic_bundle(
        self, 
        opportunity: Dict, 
        amount: float
    ) -> VersionedTransaction:
        """
        Bundle Buy + Sell + Jito Tip into one atomic transaction.
        
        This ensures all-or-nothing execution: if the arb fails,
        no funds are lost (except tip, which only pays on success).
        
        Args:
            opportunity: Dict with buy_mint, pair info
            amount: USD amount to trade
            
        Returns:
            Signed VersionedTransaction ready for submission
        """
        target_mint = opportunity["buy_mint"]
        amount_atomic = int(amount * 1_000_000)  # USDC has 6 decimals

        # 1. Get BUY Instructions (Slippage 0.5%)
        buy_quote = await self.swapper.get_quote(
            USDC_MINT, target_mint, amount_atomic, slippage=50
        )
        buy_ix = await self.swapper.get_swap_instructions(buy_quote)
        
        # 2. Get SELL Instructions (immediately sell back)
        sell_quote = await self.swapper.get_quote(
            target_mint, USDC_MINT, buy_quote['outAmount'], slippage=50
        )
        sell_ix = await self.swapper.get_swap_instructions(sell_quote)
        
        # 3. Add Jito Tip (100,000 Lamports = ~0.0001 SOL / $0.02)
        tip_ix = transfer(TransferParams(
            from_pubkey=self.wallet_manager.keypair.pubkey(),
            to_pubkey=Pubkey.from_string(JITO_TIP_ADDRESS),
            lamports=100_000 
        ))
        
        # 4. Combine all instructions
        all_ix = buy_ix + sell_ix + [tip_ix]
        
        recent_blockhash = await self.wallet_manager.client.get_latest_blockhash()
        msg = MessageV0.try_compile(
            self.wallet_manager.keypair.pubkey(), 
            all_ix, 
            [],  # Lookup tables can be added here
            recent_blockhash.value.blockhash
        )
        
        return VersionedTransaction(msg, [self.wallet_manager.keypair])

    # ═══════════════════════════════════════════════════════════════
    # TRADE EXECUTION
    # ═══════════════════════════════════════════════════════════════

    async def execute_trade(self, opportunity: Dict) -> Dict:
        """
        Execute a trade with atomic bundling and pre-flight simulation.
        
        For LIVE mode: Builds atomic Buy+Sell bundle, simulates, executes.
        For PAPER mode: Simulates P&L with realistic fee model.
        
        Args:
            opportunity: Dict with pair, buy_mint, spread_pct, etc.
            
        Returns:
            {"success": bool, "trade": {...}} or {"success": False, "error": str}
        """
        pair = opportunity["pair"]

        # 1. Determine trade amount
        if self.live_mode and self.full_wallet:
            real_balance = self.wallet_manager.get_balance(USDC_MINT)
        else:
            real_balance = self.current_balance
            
        amount = min(
            real_balance, 
            self.max_trade if self.max_trade > 0 else float('inf')
        )
        
        if amount < 1.0:
            return {"success": False, "error": "Insufficient balance"}

        # 2. Route to appropriate execution path
        if not self.live_mode:
            return self._execute_paper_trade(opportunity, amount)

        # ─── LIVE ATOMIC EXECUTION ───
        if not self._ensure_connected():
            return {"success": False, "error": "RPC connection failed"}

        try:
            Logger.info(f" 🛡️ Running Atomic Check for {pair}...")
            
            # Build atomic transaction
            atomic_tx = await self.prepare_atomic_bundle(opportunity, amount)
            
            # Pre-flight simulation (THE SAFETY SHIELD)
            simulation = await self.wallet_manager.client.simulate_transaction(atomic_tx)
            
            if simulation.value.err:
                err_msg = str(simulation.value.err)
                Logger.error(f" ❌ Simulation Failed: {err_msg}")
                return {"success": False, "error": f"Simulation: {err_msg}"}

            # Execute the bundle
            Logger.info(f" 🚀 Simulation Passed. Sending Atomic Transaction...")
            sig_result = await self.wallet_manager.client.send_transaction(atomic_tx)
            sig = sig_result.value
            
            if sig:
                Logger.success(f" ✅ Atomic Arb Landed! Sig: {str(sig)[:8]}...")
                
                # Wait for confirmation, sync balance
                await asyncio.sleep(2)
                new_bal = self.wallet_manager.get_balance(USDC_MINT)
                profit = new_bal - real_balance
                
                self.current_balance = new_bal
                self.total_profit += profit
                self.total_trades += 1
                self.trades.append({
                    "pair": pair,
                    "profit": profit,
                    "timestamp": time.time(),
                    "sig": str(sig)[:16]
                })
                
                return {
                    "success": True, 
                    "trade": {
                        "net_profit": profit, 
                        "pair": pair,
                        "mode": "LIVE"
                    }
                }
            
            return {"success": False, "error": "No signature returned"}
            
        except Exception as e:
            Logger.error(f" 💥 Execution Error: {str(e)}")
            self._connected = False  # Mark for reconnect
            return {"success": False, "error": str(e)}

    def _execute_paper_trade(self, opportunity: Dict, amount: float) -> Dict:
        """
        Simulate trade execution with realistic fee modeling.
        
        Fee model: 0.2% round-trip (DEX fees + slippage estimate)
        """
        spread_pct = opportunity["spread_pct"]
        gross_profit = amount * (spread_pct / 100)
        fees = amount * 0.002  # 0.2% round-trip
        net_profit = gross_profit - fees
        
        self.current_balance += net_profit
        self.total_profit += net_profit
        self.total_trades += 1
        self.trades.append({
            "pair": opportunity["pair"],
            "profit": net_profit,
            "timestamp": time.time(),
            "mode": "PAPER"
        })
        
        return {
            "success": True, 
            "trade": {
                "net_profit": net_profit, 
                "pair": opportunity["pair"], 
                "spread_pct": spread_pct,
                "mode": "PAPER"
            }
        }

    # ═══════════════════════════════════════════════════════════════
    # OPPORTUNITY SCANNING
    # ═══════════════════════════════════════════════════════════════
    
    async def scan_opportunities(self, verbose: bool = True) -> List[Dict]:
        """
        Scan DEXs for spatial arbitrage opportunities.
        
        Returns:
            List of profitable opportunities sorted by spread descending
        """
        opportunities = []
        
        try:
            from src.arbitrage.core.spread_detector import SpreadDetector
            from src.arbitrage.feeds.jupiter_feed import JupiterFeed
            from src.arbitrage.feeds.raydium_feed import RaydiumFeed
            from src.arbitrage.feeds.orca_feed import OrcaFeed
            
            detector = SpreadDetector(feeds=[
                JupiterFeed(),
                RaydiumFeed(),
                OrcaFeed(use_on_chain=False),
            ])
            
            spreads = detector.scan_all_pairs(CORE_PAIRS)
            
            if verbose:
                now = datetime.now().strftime("%H:%M:%S")
                print(f"\n   [{now}] MARKET SCAN:")
                print(f"   {'Pair':<12} {'Buy DEX':<10} {'Sell DEX':<10} {'Spread':<10} {'Status':<15}")
                print("   " + "-"*55)
            
            for opp in spreads:
                gross = opp.spread_pct
                fees = 0.20  # Estimated round-trip fees
                net = gross - fees
                
                # Determine status
                is_profitable = gross >= self.min_spread and net > 0
                
                if is_profitable:
                    status = "✅ PROFITABLE"
                elif gross >= self.min_spread:
                    status = "⚠️ High Fee Risk"
                elif net > 0:
                    status = "⚠️ < Min Spread"
                else:
                    status = "❌ Below min"
                
                if verbose:
                    print(f"   {opp.pair:<12} {opp.buy_dex:<10} {opp.sell_dex:<10} +{opp.spread_pct:.2f}%     {status}")
                
                # Build opportunity dict
                pair_index = next(
                    (i for i, p in enumerate(CORE_PAIRS) if p[0] == opp.pair), 
                    None
                )
                buy_mint = CORE_PAIRS[pair_index][1] if pair_index is not None else None
                
                dict_opp = {
                    "pair": opp.pair,
                    "buy_dex": opp.buy_dex,
                    "buy_price": opp.buy_price,
                    "sell_dex": opp.sell_dex,
                    "sell_price": opp.sell_price,
                    "buy_mint": buy_mint,
                    "spread_pct": opp.spread_pct,
                    "net_pct": net,
                    "status": status
                }
                
                if is_profitable and buy_mint:
                    opportunities.append(dict_opp)
            
            if verbose and opportunities:
                print(f"\n   🎯 {len(opportunities)} profitable opportunity found!")
                        
        except Exception as e:
            Logger.debug(f"Scan error: {e}")
            if verbose:
                print(f"   ⚠️ Scan error: {e}")
            
        return opportunities

    # ═══════════════════════════════════════════════════════════════
    # MAINTENANCE TASKS
    # ═══════════════════════════════════════════════════════════════
    
    async def _reclaim_rent(self) -> None:
        """Scan for empty token accounts and close them to reclaim rent."""
        if not self.wallet_manager or not self.live_mode:
            return
        
        try:
            from spl.token.constants import TOKEN_PROGRAM_ID
            from spl.token.instructions import close_account, CloseAccountParams
            from solana.rpc.types import TxOpts
            from solana.rpc.api import Client
            import requests
            
            pubkey = self.wallet_manager.keypair.pubkey()
            
            # Fetch token accounts
            payload = {
                "jsonrpc": "2.0", "id": 1, "method": "getTokenAccountsByOwner",
                "params": [
                    str(pubkey),
                    {"programId": str(TOKEN_PROGRAM_ID)},
                    {"encoding": "jsonParsed"}
                ]
            }
            res = requests.post("https://api.mainnet-beta.solana.com", json=payload).json()
            
            accounts_to_close = []
            if "result" in res and "value" in res["result"]:
                for acc in res["result"]["value"]:
                    info = acc["account"]["data"]["parsed"]["info"]
                    mint = info["mint"]
                    if float(info["tokenAmount"]["uiAmount"] or 0) == 0:
                        if mint not in WHITELIST_MINTS:
                            accounts_to_close.append(Pubkey.from_string(acc["pubkey"]))
            
            if not accounts_to_close:
                return

            print(f"   ♻️  Found {len(accounts_to_close)} empty accounts. Reclaiming gas...")
            
            # Close up to 5 accounts per batch
            instructions = []
            for acc in accounts_to_close[:5]:
                ix = close_account(CloseAccountParams(
                    account=acc, 
                    dest=pubkey, 
                    owner=pubkey, 
                    program_id=TOKEN_PROGRAM_ID, 
                    signers=[]
                ))
                instructions.append(ix)
                
            # Build and send transaction
            client = Client("https://api.mainnet-beta.solana.com")
            latest_blockhash = client.get_latest_blockhash().value.blockhash
            msg = MessageV0.try_compile(pubkey, instructions, [], latest_blockhash)
            tx = VersionedTransaction(msg, [self.wallet_manager.keypair])
            
            client.send_transaction(tx, opts=TxOpts(skip_preflight=True))
            print(f"   ✅ Reclaimed ~{len(instructions)*0.002:.4f} SOL")
            
        except Exception as e:
            print(f"   ⚠️ Reclaim failed: {e}")

    # ═══════════════════════════════════════════════════════════════
    # MAIN RUN LOOP
    # ═══════════════════════════════════════════════════════════════

    async def run(self, duration_minutes: int = 10, scan_interval: int = 5) -> None:
        """
        Main trading loop.
        
        Args:
            duration_minutes: How long to run (0 = infinite)
            scan_interval: Seconds between scans
        """
        mode_str = "🔴 LIVE" if self.live_mode else "📄 PAPER"
        
        print("\n" + "="*70)
        print(f"   PHANTOM ARBITER - {mode_str} TRADER")
        print("="*70)
        print(f"   Starting Balance: ${self.starting_balance:.2f}")
        print(f"   Min Spread:       {self.min_spread}%")
        
        max_trade_str = "UNLIMITED ♾️" if self.max_trade <= 0 else f"${self.max_trade:.2f}"
        print(f"   Max Trade:        {max_trade_str}")
        print(f"   Pairs:            {len(CORE_PAIRS)} core pairs")
        
        if self.full_wallet:
            print(f"   Full Wallet:      ENABLED (Dynamic Balance)")
        print(f"   Duration:         {duration_minutes} minutes")
        print("="*70)
        print("\n   Running... (Ctrl+C to stop)\n")
        
        # Initial rent reclaim
        if self.live_mode:
            await self._reclaim_rent()
        
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60) if duration_minutes > 0 else float('inf')
        
        last_trade_time: Dict[str, float] = {}  # Cooldown tracking
        cooldown = 5  # seconds
        loop_count = 0
        
        try:
            while time.time() < end_time:
                loop_count += 1
                now = datetime.now().strftime("%H:%M:%S")
                
                # Live Mode Maintenance
                if self.live_mode and self.wallet_manager:
                    await self.wallet_manager.check_and_replenish_gas(self.swapper)
                    
                    if loop_count % 10 == 0:
                        await self._reclaim_rent()
                    
                    if self.full_wallet:
                        self.current_balance = self.wallet_manager.get_balance(USDC_MINT)
                
                # Scan for opportunities
                try:
                    opportunities = await self.scan_opportunities()
                except asyncio.CancelledError:
                    break
                except Exception:
                    opportunities = []
                
                if opportunities:
                    # Sort by spread, take best not on cooldown
                    sorted_opps = sorted(
                        opportunities, 
                        key=lambda x: x["spread_pct"], 
                        reverse=True
                    )

                    for opp in sorted_opps:
                        pair = opp["pair"]
                        last_time = last_trade_time.get(pair, 0)
                        
                        if time.time() - last_time < cooldown:
                            continue
                        
                        # Execute trade
                        result = await self.execute_trade(opp)
                        
                        if result.get("success"):
                            trade = result["trade"]
                            last_trade_time[pair] = time.time()
                            
                            emoji = "💰" if trade["net_profit"] > 0 else "📉"
                            print(f"   [{now}] {emoji} {trade['mode']} #{self.total_trades}: {trade['pair']}")
                            print(f"            Spread: +{trade.get('spread_pct', 0):.2f}% → Net: ${trade['net_profit']:+.4f}")
                            print(f"            Balance: ${self.current_balance:.4f}")
                            print()
                            
                            if self.live_mode:
                                await self._reclaim_rent()
                            break
                        else:
                            print(f"   [{now}] ❌ TRADE FAILED: {result.get('error', 'Unknown')}")
                            break
                
                await asyncio.sleep(scan_interval)
                
        except KeyboardInterrupt:
            pass
        
        # Final summary
        self._print_summary(start_time, mode_str)
        self._save_session()

    def _print_summary(self, start_time: float, mode_str: str) -> None:
        """Print session summary."""
        runtime = (time.time() - start_time) / 60
        denom = self.starting_balance if self.starting_balance > 0 else 1
        roi = ((self.current_balance - self.starting_balance) / denom) * 100
        
        print("\n\n" + "="*70)
        print(f"   SESSION SUMMARY ({mode_str})")
        print("="*70)
        print(f"   Runtime:      {runtime:.1f} minutes")
        print(f"   Starting:     ${self.starting_balance:.2f}")
        print(f"   Ending:       ${self.current_balance:.4f}")
        print(f"   Profit:       ${self.total_profit:+.4f}")
        print(f"   ROI:          {roi:+.2f}%")
        print(f"   Trades:       {self.total_trades}")
        print("="*70)

    def _save_session(self) -> None:
        """Save session data to JSON."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        mode = "live" if self.live_mode else "paper"
        save_path = f"data/trading_sessions/{mode}_session_{timestamp}.json"
        
        denom = self.starting_balance if self.starting_balance > 0 else 1
        roi = ((self.current_balance - self.starting_balance) / denom) * 100
        
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, 'w') as f:
            json.dump({
                "mode": mode,
                "starting_balance": self.starting_balance,
                "ending_balance": self.current_balance,
                "total_profit": self.total_profit,
                "total_trades": self.total_trades,
                "roi_pct": roi,
                "pairs_monitored": [p[0] for p in CORE_PAIRS],
                "trades": self.trades
            }, f, indent=2)
        
        print(f"\n   Session saved: {save_path}")


# ═══════════════════════════════════════════════════════════════════
# MAIN ENTRYPOINT
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Phantom Arbiter Unified Trader")
    parser.add_argument("--live", action="store_true", help="Enable LIVE trading (REAL MONEY!)")
    parser.add_argument("--budget", type=float, default=50.0, help="Starting budget in USD")
    parser.add_argument("--duration", type=int, default=10, help="Duration in minutes")
    parser.add_argument("--interval", type=int, default=5, help="Scan interval in seconds")
    parser.add_argument("--min-spread", type=float, default=0.50, help="Minimum spread percent")
    parser.add_argument("--max-trade", type=float, default=10.0, help="Maximum trade size")
    parser.add_argument("--full-wallet", action="store_true", help="Use entire wallet balance")
    
    args = parser.parse_args()
    
    if args.live:
        print("\n" + "⚠️ "*20)
        print("   WARNING: LIVE MODE ENABLED!")
        print("   This will execute REAL transactions with REAL money!")
        print("⚠️ "*20)
        confirm = input("\n   Type 'I UNDERSTAND' to proceed: ")
        if confirm.strip() != "I UNDERSTAND":
            print("   Cancelled.")
            exit(0)
    
    trader = UnifiedTrader(
        budget=args.budget,
        live_mode=args.live,
        min_spread=args.min_spread,
        max_trade=args.max_trade,
        full_wallet=args.full_wallet
    )
    
    asyncio.run(trader.run(
        duration_minutes=args.duration,
        scan_interval=args.interval
    ))
