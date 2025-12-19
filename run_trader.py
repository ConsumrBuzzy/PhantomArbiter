"""
Phantom Arbiter - Unified Trader (Paper + Live)
=================================================
Switch between paper and live mode with one flag.

Usage:
    # Paper mode (default, safe)
    python run_trader.py --budget 50 --duration 10
    
    # Live mode (REAL MONEY!)
    python run_trader.py --live --budget 5 --duration 10
    
⚠️ LIVE MODE WILL EXECUTE REAL TRADES ⚠️
"""

import asyncio
import os
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

# Load .env file
from dotenv import load_dotenv
load_dotenv()

from config.settings import Settings
from src.system.logging import Logger


class UnifiedTrader:
    """
    Unified trader that works in both paper and live mode.
    
    Paper Mode: Uses real prices, simulates execution
    Live Mode:  Uses real prices, executes real swaps
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
        
        # Wallet tracking
        self.current_balance = budget
        self.starting_balance = budget
        self.total_trades = 0
        self.total_profit = 0.0
        
        # Trade history
        self.trades: List[Dict] = []
        
        # Live mode components
        self.wallet_manager = None
        self.swapper = None
        
        if live_mode:
            self._setup_live_mode()
    
    def _setup_live_mode(self):
        """Setup live trading components."""
        private_key = os.getenv("PHANTOM_PRIVATE_KEY") or os.getenv("SOLANA_PRIVATE_KEY")
        
        if not private_key:
            print("\n❌ LIVE MODE FAILED: No private key found!")
            print("   Add SOLANA_PRIVATE_KEY to .env")
            self.live_mode = False
            return
        
        try:
            # Force enable trading
            Settings.ENABLE_TRADING = True
            
            from src.execution.wallet import WalletManager
            from src.execution.swapper import JupiterSwapper
            
            self.wallet_manager = WalletManager()
            if not self.wallet_manager.keypair:
                 raise ValueError("WalletManager failed to load keypair")
                 
            self.swapper = JupiterSwapper(self.wallet_manager)
            
            # Sync Initial Balance if Full Wallet Mode
            if self.full_wallet:
                usdc_bal = self.wallet_manager.get_balance("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
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
    
    async def scan_opportunities(self, verbose: bool = True) -> List[Dict]:
        """Scan for spatial arbitrage opportunities."""
        opportunities = []
        all_spreads = []
        
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
            
            USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            pairs = [
                ("SOL/USDC", "So11111111111111111111111111111111111111112", USDC),
                ("BONK/USDC", "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", USDC),
                ("WIF/USDC", "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", USDC),
                ("JUP/USDC", "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", USDC),
                # New Additions
                ("JTO/USDC", "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL", USDC),
                ("RAY/USDC", "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R", USDC),
                ("PYTH/USDC", "HZ1JovNiVvGrGNiiYvEozEVGZ58xaU3RKwX8eACQBCt3", USDC),
                ("POPCAT/USDC", "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr", USDC),
                # DeFi / Infra Additions
                ("DRIFT/USDC", "DriFtupJYLTosbwoN8koMbEYSx54aFAVLddWsbksjwg7", USDC),
                ("KMNO/USDC", "KMNo3nJsBXfcpJTVhZcXLW7RmTwTt4GVFE7suUBo9sS", USDC),
                ("TNSR/USDC", "TNSRxcUxoT9xBG3de7PiJyTDYu7kskLqcpddxnEJAS6", USDC),
                ("RENDER/USDC", "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof", USDC),
            ]
            
            spreads = detector.scan_all_pairs(pairs)
            
            # Show all spreads
            if verbose:
                now = datetime.now().strftime("%H:%M:%S")
                print(f"\n   [{now}] MARKET SCAN:")
                print(f"   {'Pair':<12} {'Buy DEX':<10} {'Sell DEX':<10} {'Spread':<10} {'Status':<15}")
                print("   " + "-"*55)
            
            for opp in spreads:
                gross = opp.spread_pct
                fees = 0.20
                net = gross - fees
                
                # Determine status
                is_profitable = False
                status = "❌ Below min"
                
                # Logic: Must meet user's min spread AND be theoretically positive after 0.2% fees
                if gross >= self.min_spread:
                    if net > 0:
                        status = "✅ PROFITABLE"
                        is_profitable = True
                    else:
                        status = "⚠️ High Fee Risk"
                elif net > 0:
                    status = "⚠️ < Min Spread"
                
                if verbose:
                    print(f"   {opp.pair:<12} {opp.buy_dex:<10} {opp.sell_dex:<10} +{opp.spread_pct:.2f}%     {status}")
                
                dict_opp = {
                    "pair": opp.pair,
                    "buy_dex": opp.buy_dex,
                    "buy_price": opp.buy_price,
                    "sell_dex": opp.sell_dex,
                    "sell_price": opp.sell_price,
                    "buy_mint": pairs[[p[0] for p in pairs].index(opp.pair)][1] if opp.pair in [p[0] for p in pairs] else None,
                    "spread_pct": opp.spread_pct,
                    "net_pct": net,
                    "status": status # Add status for all_spreads
                }
                
                if is_profitable:
                    opportunities.append(dict_opp)
                
                all_spreads.append(dict_opp)
            
            if verbose and opportunities:
                print(f"\n   🎯 {len(opportunities)} profitable opportunity found!")
                        
        except Exception as e:
            Logger.debug(f"Scan error: {e}")
            if verbose:
                print(f"   ⚠️ Scan error: {e}")
            
        return opportunities
    
    async def execute_trade(self, opportunity: Dict) -> Dict:
        """Execute a trade (paper or live)."""
        
        # Determine Trade Amount
        amount = 0.0
        
        if self.live_mode and self.full_wallet and self.wallet_manager:
            # Full Wallet Mode: internal balance IS the wallet balance
            real_balance = self.wallet_manager.get_balance("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
            self.current_balance = real_balance
            
            # Use entire balance if max_trade is 0 (Unlimited), otherwise cap
            limit = self.max_trade if self.max_trade > 0 else float('inf')
            amount = min(real_balance, limit)
            
            # Leave dust buffer? (e.g. 0.1 USDC) for fees/rent if holding USDC? 
            # Usually strict amount is fine if gas is SOL.
        else:
            # Paper or Fixed Budget Mode
            limit = self.max_trade if self.max_trade > 0 else float('inf')
            amount = min(self.current_balance, limit)
        
        if self.live_mode and self.swapper:
            # LIVE EXECUTION
            try:
                # Get the mint for the target token
                pair = opportunity["pair"]
                mint_map = {
                    "SOL/USDC": "So11111111111111111111111111111111111111112",
                    "BONK/USDC": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
                    "WIF/USDC": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
                    "JUP/USDC": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
                    # New Additions
                    "JTO/USDC": "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",
                    "RAY/USDC": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
                    "PYTH/USDC": "HZ1JovNiVvGrGNiiYvEozEVGZ58xaU3RKwX8eACQBCt3",
                    "POPCAT/USDC": "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",
                    "DRIFT/USDC": "DriFtupJYLTosbwoN8koMbEYSx54aFAVLddWsbksjwg7",
                    "KMNO/USDC": "KMNo3nJsBXfcpJTVhZcXLW7RmTwTt4GVFE7suUBo9sS",
                    "TNSR/USDC": "TNSRxcUxoT9xBG3de7PiJyTDYu7kskLqcpddxnEJAS6",
                    "RENDER/USDC": "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof",
                }
                target_mint = mint_map.get(pair)
                
                if not target_mint:
                    return {"success": False, "error": f"Unknown pair: {pair}"}
                
                if not target_mint:
                    return {"success": False, "error": f"Unknown pair: {pair}"}
                
                # Dynamic Gas & Safety Check (V4.0: Rigorous Precision)
                # -----------------------------------------------------
                # 1. Determine Priority Fee based on size
                priority_fee = 1000 # Default Micro
                if amount >= 500: priority_fee = 1000000
                elif amount >= 100: priority_fee = 100000
                elif amount >= 10: priority_fee = 10000
                
                # 2. Calculate Exact Tx Fee
                # Formula: 5000 Sig + (ComputeUnits * MicroLamports)
                COMPUTE_UNITS = 300_000 # Conservative upper bound for Jupiter swap
                priority_cost_lamports = COMPUTE_UNITS * priority_fee / 1_000_000
                total_lamports = 5000 + priority_cost_lamports
                tx_fee_sol = total_lamports / 1_000_000_000
                
                # 3. Calculate Rent (ATA Creation)
                # If we don't hold the token, we pay 0.002 SOL to open account
                has_token_account = False
                buy_mint = opportunity.get("buy_mint")
                if buy_mint:
                    # Check if balance > 0 (implies account exists)
                    # OR check explicit account existence? get_balance returns 0 if no account or empty.
                    # We assume 0 means "might need to open". 
                    # Actually wallet.get_token_info returns None if no account.
                    # But get_balance returns 0.0.
                    # Let's assume Worst Case: If balance == 0, we pay rent.
                    if self.wallet_manager.get_balance(buy_mint) > 0:
                        has_token_account = True
                
                rent_cost_sol = 0.0 if has_token_account else 0.002039
                
                # 4. Total Cost in USD
                SOL_PRICE_SAFETY = 250.0 
                tx_cost_usd = tx_fee_sol * SOL_PRICE_SAFETY
                rent_cost_usd = rent_cost_sol * SOL_PRICE_SAFETY
                
                gross_profit_usd = amount * (opportunity["spread_pct"] / 100)
                
                # STRICT RULE: Profit must cover the "Burned" Gas (Priority + Sig)
                if gross_profit_usd < tx_cost_usd:
                     return {
                         "success": False, 
                         "error": f"Unprofitable: Profit ${gross_profit_usd:.4f} < Gas ${tx_cost_usd:.4f}"
                     }
                     
                # SOFT RULE: Rent is a "Deposit", not a loss.
                # If profit doesn't cover rent, we still proceed but log it.
                # This allows entering new markets (like WIF) without needing 3% spreads.
                if gross_profit_usd < (tx_cost_usd + rent_cost_usd):
                    # We are "investing" in the account creation
                    pass 
                
                # Execute BUY
                reason = f"Arb: {opportunity['buy_dex']}->{opportunity['sell_dex']} (Fee: {priority_fee}uL)"
                
                # Snapshot Balance BEFORE (Protection)
                pre_token_info = self.wallet_manager.get_token_info(target_mint)
                pre_balance = int(pre_token_info["amount"]) if pre_token_info else 0
                
                buy_sig = self.swapper.execute_swap("BUY", amount, reason, target_mint=target_mint, priority_fee=priority_fee)
                
                if buy_sig:
                    Logger.info(f" ⏳ Buy Sent: {buy_sig[-8:]}... Waiting for confirmation...")
    
                    acquired_amount = 0
                    # Increase retries and add a small delay
                    for i in range(15): 
                        await asyncio.sleep(2) # Give the RPC more time to breathe
                        post_token_info = self.wallet_manager.get_token_info(target_mint)
                        post_balance = int(post_token_info["amount"]) if post_token_info else 0
        
                        if post_balance > pre_balance:
                            acquired_amount = post_balance - pre_balance
                            Logger.info(f" ✅ Balance confirmed! (+{acquired_amount} units)")
                            break
                        Logger.info(f" ⏳ Syncing... Retry {i+1}/15")

                    if acquired_amount <= 0:
                        # EMERGENCY: We have the tokens but the RPC won't show them.
                        # Don't just return. Log a CRITICAL error.
                        Logger.error(" !!! CRITICAL: SPLIT-LEG DETECTED !!!")
                        Logger.error(f" Money is stuck in {target_mint}. Manual sell required.")
                        return {"success": False, "error": "Split-Leg: RPC Sync Failure"}

                    # Execute SELL (Only acquired amount)
                    Logger.info(f"   🔄 Executing SELL Leg (Selling {acquired_amount} units)...")
                    sell_sig = self.swapper.execute_swap("SELL", 0, reason, target_mint=target_mint, priority_fee=priority_fee, override_atomic_amount=acquired_amount)
                    
                    realized_profit = 0.0
                    if sell_sig:
                        Logger.success(f"   ✅ Cycle Complete (Buy+Sell): {sell_sig[-8:]}")
                        Logger.info("   ⏳ Verifying PnL...")
                        
                        # Wait for Sell to settle to see true profit
                        for _ in range(15): # 15s max
                            await asyncio.sleep(1)
                            current_usdc = self.wallet_manager.get_balance("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
                            if current_usdc != real_balance: # Balance changed
                                realized_profit = current_usdc - real_balance
                                self.current_balance = current_usdc # Update internal state
                                break
                    else:
                        Logger.error("   ❌ SELL FAILED! You are now Long this token.")

                    # Use REALIZED profit if available, otherwise 0 (or estimate failure)
                    net_profit = realized_profit if sell_sig else -amount # If sell failed, we assume loss of principal (temporarily)
                        
                    self.total_profit += net_profit
                    self.total_trades += 1
                    
                    trade = {
                        "timestamp": time.time(),
                        "mode": "LIVE",
                        "pair": pair,
                        "amount": amount,
                        "spread_pct": opportunity["spread_pct"],
                        "net_profit": net_profit,
                        "signature": f"B:{buy_sig[-4:]} S:{sell_sig[-4:] if sell_sig else 'FAIL'}",
                        "balance_after": self.current_balance
                    }
                    self.trades.append(trade)
                    return {"success": True, "trade": trade}
                else:
                    return {"success": False, "error": f"Swap returned None (check logs)"}
            
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        else:
            # PAPER EXECUTION
            gross_profit = amount * (opportunity["spread_pct"] / 100)
            fees = amount * 0.002
            net_profit = gross_profit - fees
            
            self.current_balance += net_profit
            self.total_profit += net_profit
            self.total_trades += 1
            
            trade = {
                "timestamp": time.time(),
                "mode": "PAPER",
                "pair": opportunity["pair"],
                "amount": amount,
                "spread_pct": opportunity["spread_pct"],
                "net_profit": net_profit,
                "signature": f"PAPER_{int(time.time())}",
                "balance_after": self.current_balance
            }
            self.trades.append(trade)
            
            return {"success": True, "trade": trade}
    
    async def _reclaim_rent(self):
        """Scan for empty token accounts and close them to reclaim rent."""
        if not self.wallet_manager or not self.live_mode: return
        
        try:
            # 1. Scan
            from spl.token.constants import TOKEN_PROGRAM_ID
            from spl.token.instructions import close_account, CloseAccountParams
            from solders.pubkey import Pubkey
            from solders.transaction import VersionedTransaction
            from solders.message import MessageV0
            from solana.rpc.types import TxOpts
            from solana.rpc.api import Client
            
            pubkey = self.wallet_manager.keypair.pubkey()
            
            # Whitelist: DO NOT close these accounts even if empty
            # This saves the 0.002 SOL re-opening fee for common arb tokens.
            WHITELIST_MINTS = [
                "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", # BONK
                "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", # WIF
                "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", # JUP
                "So11111111111111111111111111111111111111112",  # SOL
                "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",  # JTO
                "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R", # RAY
                "HZ1JovNiVvGrGNiiYvEozEVGZ58xaU3RKwX8eACQBCt3", # PYTH
                "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr", # POPCAT
            ]
            
            # Simple RPC call using requests
            import requests
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
                    if float(info["tokenAmount"]["uiAmount"]) == 0:
                        if mint not in WHITELIST_MINTS:
                            accounts_to_close.append(Pubkey.from_string(acc["pubkey"]))
            
            if not accounts_to_close:
                return

            print(f"   ♻️  Found {len(accounts_to_close)} empty accounts. Reclaiming gas...")
            
            # 2. Close Accounts (Batch of 5)
            instructions = []
            for acc in accounts_to_close[:5]:
                ix = close_account(CloseAccountParams(
                    account=acc, dest=pubkey, owner=pubkey, program_id=TOKEN_PROGRAM_ID, signers=[]
                ))
                instructions.append(ix)
                
            # 3. Send
            client = Client("https://api.mainnet-beta.solana.com")
            latest_blockhash = client.get_latest_blockhash().value.blockhash
            msg = MessageV0.try_compile(pubkey, instructions, [], latest_blockhash)
            tx = VersionedTransaction(msg, [self.wallet_manager.keypair])
            
            client.send_transaction(tx, opts=TxOpts(skip_preflight=True))
            print(f"   ✅ Reclaimed ~{len(instructions)*0.002:.4f} SOL")
            
        except Exception as e:
            print(f"   ⚠️ Reclaim failed: {e}")

    async def run(self, duration_minutes: int = 10, scan_interval: int = 5):
        """Run the trader."""
        
        mode_str = "🔴 LIVE" if self.live_mode else "📄 PAPER"
        
        print("\n" + "="*70)
        print(f"   PHANTOM ARBITER - {mode_str} TRADER")
        print("="*70)
        print(f"   Starting Balance: ${self.starting_balance:.2f}")
        print(f"   Min Spread:       {self.min_spread}%")
        
        max_trade_str = "UNLIMITED ♾️" if self.max_trade <= 0 else f"${self.max_trade:.2f}"
        print(f"   Max Trade:        {max_trade_str}")
        
        if self.full_wallet:
             print(f"   Full Wallet:      ENABLED (Dynamic Balance)")
        print(f"   Duration:         {duration_minutes} minutes")
        print("="*70)
        print("\n   Running... (Ctrl+C to stop)\n")
        
        # Initial Vacuum
        if self.live_mode:
            await self._reclaim_rent()
        
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60) if duration_minutes > 0 else float('inf')
        
        last_trade_time = {}  # Cooldown tracking
        cooldown = 5  # seconds
        loop_count = 0
        
        try:
            while time.time() < end_time:
                loop_count += 1
                now = datetime.now().strftime("%H:%M:%S")
                
                # Live Mode Maintenance
                if self.live_mode and self.wallet_manager:
                    # 1. Check Gas
                    await self.wallet_manager.check_and_replenish_gas(self.swapper)
                    
                    # 2. Reclaim Rent (Every 10 loops)
                    if loop_count % 10 == 0:
                        await self._reclaim_rent()
                    
                    # 3. Sync Balance (if full wallet)
                    if self.full_wallet:
                         bal = self.wallet_manager.get_balance("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
                         self.current_balance = bal
                
                try:
                    opportunities = await self.scan_opportunities()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    opportunities = []
                
                if opportunities:
                    # Find best opportunity not on cooldown
                    sorted_opportunities = sorted(opportunities, key=lambda x: x["spread_pct"], reverse=True)
        
                    # Display top 20 opportunities (if any)
                    for res in sorted_opportunities[:20]:
                        star = "✅" if res["spread_pct"] >= self.min_spread else "⚠️" if res["spread_pct"] > 0.2 else "❌"
                        status = "PROFITABLE" if res["spread_pct"] >= self.min_spread else "< Min Spread" if res["spread_pct"] > 0.2 else "Below min"
                        Logger.info(f"   [{now}] {star} {res['pair']} | Spread: {res['spread_pct']:.2f}% ({status})")

                    for opp in sorted_opportunities:
                        pair = opp["pair"]
                        last_time = last_trade_time.get(pair, 0)
                        
                        if time.time() - last_time < cooldown:
                            continue
                        
                        # Execute
                        result = await self.execute_trade(opp)
                        
                        if result.get("success"):
                            trade = result["trade"]
                            last_trade_time[pair] = time.time()
                            
                            emoji = "💰" if trade["net_profit"] > 0 else "📉"
                            print(f"   [{now}] {emoji} {trade['mode']} #{self.total_trades}: {trade['pair']}")
                            print(f"            Spread: +{trade['spread_pct']:.2f}% → Net: ${trade['net_profit']:+.4f}")
                            print(f"            Balance: ${self.current_balance:.4f}")
                            print()
                            
                            # Post-trade cleanup
                            if self.live_mode:
                                await self._reclaim_rent()
                                
                            break
                        else:
                            # Print error
                            error = result.get("error", "Unknown error")
                            print(f"   [{now}] ❌ TRADE FAILED: {error}")
                            break
                else:
                    # Scan already printed all spreads, no action needed
                    pass
                
                await asyncio.sleep(scan_interval)
                
        except KeyboardInterrupt:
            pass
        
        # Final summary
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
        
        # Save session
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        mode = "live" if self.live_mode else "paper"
        save_path = f"data/trading_sessions/{mode}_session_{timestamp}.json"
        
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, 'w') as f:
            json.dump({
                "mode": mode,
                "starting_balance": self.starting_balance,
                "ending_balance": self.current_balance,
                "total_profit": self.total_profit,
                "total_trades": self.total_trades,
                "roi_pct": roi,
                "runtime_minutes": runtime,
                "trades": self.trades
            }, f, indent=2)
        
        print(f"\n   Session saved: {save_path}")


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Phantom Arbiter Unified Trader")
    parser.add_argument("--live", action="store_true", help="Enable LIVE trading (REAL MONEY!)")
    parser.add_argument("--budget", type=float, default=50.0, help="Starting budget in USD (ignored if --full-wallet)")
    parser.add_argument("--duration", type=int, default=10, help="Duration in minutes")
    parser.add_argument("--interval", type=int, default=5, help="Scan interval in seconds")
    parser.add_argument("--min-spread", type=float, default=0.50, help="Minimum spread percent (Default: 0.50)")
    parser.add_argument("--max-trade", type=float, default=10.0, help="Maximum trade size")
    parser.add_argument("--full-wallet", action="store_true", help="Use ENTIRE wallet balance (up to max-trade)")
    
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
