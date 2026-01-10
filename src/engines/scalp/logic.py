"""
Scalp Engine Logic
==================
The "Brain" of the Meme Hunter.
Orchestrates Pods (Targets) + Sentiment (Signals) -> Jupiter (Execution).
"""

import asyncio
import time
from typing import Dict, Optional, List
from datetime import datetime

from config.settings import Settings
from src.shared.system.logging import Logger
from src.drivers.jupiter_driver import JupiterSwapper
from src.drivers.wallet_manager import WalletManager
from src.engines.scalp.pods import pod_manager
from src.engines.scalp.sentiment import SentimentEngine, SentimentScore

class ScalpTracker:
    """Tracks active scalp positions for TP/SL."""
    def __init__(self):
        self.positions: Dict[str, Dict] = {}  # {mint: {entry_price: float, amount: float, time: float}}

    def add_position(self, mint: str, entry_price: float, amount_token: float):
        self.positions[mint] = {
            "entry_price": entry_price,
            "amount": amount_token,
            "timestamp": time.time(),
            "highest_price": entry_price # Trailing stop support
        }
        Logger.info(f"📝 Tracking new position: {mint[:8]} @ ${entry_price:.4f}")

    def remove_position(self, mint: str):
        if mint in self.positions:
            del self.positions[mint]

    def get_position(self, mint: str) -> Optional[Dict]:
        return self.positions.get(mint)

class ScalpEngine:
    """
    Executes the "Snipe" strategy:
    1. Scan Active Pods.
    2. Check Sentiment.
    3. Execute Swap via Jupiter.
    4. Managing Exits (TP/SL).
    """

    def __init__(self, live_mode: bool = False):
        self.live_mode = live_mode
        self.wallet = WalletManager()
        self.swapper = JupiterSwapper(self.wallet)
        self.sentiment = SentimentEngine()
        self.tracker = ScalpTracker()
        
        # Risk Config
        self.trade_size_usd = 10.0 # Small snippets
        self.min_confidence = 70   # Sentiment score
        self.tp_pct = 0.10         # +10% Take Profit
        self.sl_pct = 0.05         # -5% Stop Loss
        
        Logger.info(f"Scalp Engine Initialized (Live={self.live_mode})")

    async def tick(self):
        """Single execution step for Scalp Engine."""
        try:
            # 1. Manage Active Positions (Fast)
            await self.monitor_positions()
            
            # 2. Scan for New Entries
            await self.scan_pods()
            
            return {"state": "ACTIVE"}
        except Exception as e:
            Logger.error(f"Scalp Tick Error: {e}")
            return {"state": "ERROR"}

    async def run_loop(self):
        """Legacy entry point - now delegates to TUIRunner if possible."""
        from src.shared.ui.tui_manager import TUIRunner
        runner = TUIRunner(self, "SCALP", tick_interval=5.0)
        await runner.run()

    async def scan_pods(self):
        """Scan active pods for opportunities."""
        active_pods = pod_manager.get_active_pods()
        # Logger.info(f"🔍 Scanning Pods: {active_pods}")
        
        pairs = pod_manager.get_pairs_for_pods(active_pods)
        # Filter for SOL pairs usually, or just check tokens directly?
        # Pods return (PairName, Mint, QuoteMint)
        
        for pair_name, mint, quote_mint in pairs:
            # Skip if we already hold it
            if self.tracker.get_position(mint):
                continue
                
            # Check Sentiment
            token_symbol = pair_name.split("/")[0]
            score = await self.sentiment.get_sentiment_score(token_symbol)
            
            # V2: Update AppState for TUI
            from src.shared.state.app_state import state as app_state, ScalpSignal
            app_state.update_stat("pod_status", pod_manager.get_status()[:20])
            
            if score.should_enter:
                Logger.info(f"🚨 SIGNAL: {token_symbol} Sentiment={score.score:.0f} ({score.signal})")
                
                # Push to TUI
                app_state.add_signal(ScalpSignal(
                    token=token_symbol,
                    signal_type=score.signal,
                    confidence=score.confidence,
                    action="BUY",
                    price=score.momentum_score or 0.0 # Placeholder
                ))

                if self.live_mode:
                    await self.execute_entry(token_symbol, mint, score)
                else:
                    Logger.info(f"   [SIM] Would BUY ${self.trade_size_usd} of {token_symbol}")

    async def execute_entry(self, symbol: str, mint: str, score: SentimentScore):
        """Execute Buy Order via Jupiter."""
        Logger.info(f"🚀 EXECUTING SNIPE: {symbol} (Score: {score.score})")
        
        # 1. Buy
        result = self.swapper.execute_swap(
            direction="BUY",
            amount_usd=self.trade_size_usd,
            reason=f"Sentiment Snipe {score.score}",
            target_mint=mint
        )
        
        if result["success"]:
            # Need to fetch execution price/amount to track
            # Result gives 'outAmount'.
            # Assume price = trade_size / out_amount roughly
            # For exact tracking we'd need a price feed, but let's approximate
            out_amount_atomic = int(result.get("outAmount", 0))
            # Decimals? We need token info.
            info = self.wallet.get_token_info(mint)
            if info:
                decimals = int(info["decimals"])
                amount_token = out_amount_atomic / (10 ** decimals)
                entry_price = self.trade_size_usd / amount_token if amount_token > 0 else 0
                
                self.tracker.add_position(mint, entry_price, amount_token)
                pod_manager.report_result(symbol, True, True, True) # Reward pod
            else:
                Logger.warning("⚠️ Bought token but failed to get info for tracking.")

    async def monitor_positions(self):
        """Check PnL of held positions."""
        # Need price feed for held tokens
        # We can use Jupiter Price API via standard feed or simple quote
        if not self.tracker.positions:
            return

        from src.shared.feeds.jupiter_feed import JupiterFeed
        feed = JupiterFeed()
        
        for mint, pos in list(self.tracker.positions.items()):
            # Get Current Price
            quote = feed.get_spot_price(mint, Settings.USDC_MINT)
            if not quote:
                continue
                
            current_price = quote.price
            entry_price = pos["entry_price"]
            pnl_pct = (current_price - entry_price) / entry_price
            
            # Log periodic status
            # Logger.debug(f"   📊 {mint[:4]}: {pnl_pct*100:.2f}% PnL (${current_price:.4f})")
            
            # TP/SL Logic
            if pnl_pct >= self.tp_pct:
                Logger.success(f"💰 TAKE PROFIT: {mint[:8]} (+{pnl_pct*100:.1f}%)")
                if self.live_mode:
                    self.swapper.execute_swap("SELL", 0, "Take Profit", target_mint=mint)
                self.tracker.remove_position(mint)
                
            elif pnl_pct <= -self.sl_pct:
                Logger.warning(f"🛑 STOP LOSS: {mint[:8]} ({pnl_pct*100:.1f}%)")
                if self.live_mode:
                    self.swapper.execute_swap("SELL", 0, "Stop Loss", target_mint=mint)
                self.tracker.remove_position(mint)
