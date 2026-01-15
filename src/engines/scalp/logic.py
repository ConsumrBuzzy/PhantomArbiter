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

    def add_position(self, mint: str, symbol: str, entry_price: float, amount_token: float):
        self.positions[mint] = {
            "symbol": symbol,
            "entry_price": entry_price,
            "amount": amount_token,
            "timestamp": time.time(),
            "highest_price": entry_price # Trailing stop support
        }
        Logger.info(f"📝 Tracking new position: {symbol} ({mint[:8]}) @ ${entry_price:.4f}")

    def remove_position(self, mint: str):
        if mint in self.positions:
            del self.positions[mint]

    def get_position(self, mint: str) -> Optional[Dict]:
        return self.positions.get(mint)

from src.engines.base_engine import BaseEngine

class ScalpEngine(BaseEngine):
    """
    Executes the "Snipe" strategy:
    1. Scan Active Pods.
    2. Check Sentiment.
    3. Execute Swap via Jupiter.
    4. Managing Exits (TP/SL).
    """

    def __init__(self, live_mode: bool = False):
        super().__init__("scalp", live_mode)
        
        self.sentiment = SentimentEngine()
        self.tracker = ScalpTracker()
        
        # Risk Config
        self.trade_size_usd = 10.0 
        self.min_confidence = 70   
        self.tp_pct = 0.10         
        self.sl_pct = 0.05         
        
        # Drivers handled by BaseEngine

    async def tick(self):
        """Single execution step for Scalp Engine."""
        try:
            # 1. Manage Active Positions (Fast)
            await self.monitor_positions()
            
            # 2. Scan for New Entries
            await self.scan_pods()
            
            # Broadcast Status (Active Pod Count)
            if self._callback:
                await self._callback({
                    "active_pods": len(self.tracker.positions),
                    "pnl": 0.0 # Placeholder or calc PnL
                })
            
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
        pairs = pod_manager.get_pairs_for_pods(active_pods)
        
        for pair_name, mint, quote_mint in pairs:
            if self.tracker.get_position(mint):
                continue
                
            token_symbol = pair_name.split("/")[0]
            score = await self.sentiment.get_sentiment_score(token_symbol)
            
            from src.shared.state.app_state import state as app_state, ScalpSignal
            app_state.update_stat("pod_status", pod_manager.get_status()[:20])
            
            if score.should_enter:
                Logger.info(f"🚨 SIGNAL: {token_symbol} Sentiment={score.score:.0f} ({score.signal})")
                
                # Push to TUI
                app_state.add_signal(ScalpSignal(
                    token=token_symbol, signal_type=score.signal, confidence=score.confidence,
                    action="BUY", price=score.momentum_score or 0.0
                ))

                # Broadcast to Dashboard
                conf_val = {"HIGH": 0.9, "MEDIUM": 0.7, "LOW": 0.5}.get(score.confidence, 0.5)
                
                if self._callback:
                    await self._callback({
                        "type": "SIGNAL", 
                        "data": {
                            "token": token_symbol,
                            "sentiment": 0.8 if score.signal == "STRONG_BUY" else 0.6,
                            "confidence": conf_val,
                            "action": "BUY"
                        }
                    })

                # Execute
                await self.execute_entry(token_symbol, mint, score)

    async def execute_entry(self, symbol: str, mint: str, score: SentimentScore):
        """Execute Buy Order via Unified Base Interface."""
        Logger.info(f"🚀 EXECUTING SNIPE: {symbol} (Score: {score.score})")
        
        result = await self.execute_swap("BUY", self.trade_size_usd, mint, symbol)
        
        if result["success"]:
            amount_token = result["amount"]
            entry_price = result["price"]
            if entry_price == 0 and amount_token > 0:
                entry_price = self.trade_size_usd / amount_token
                
            self.tracker.add_position(mint, symbol, entry_price, amount_token)
            pod_manager.report_result(symbol, True, True, True)
            Logger.info(f"[{self.mode.upper()}] ✅ SNIPED {amount_token:.4f} {symbol}")
        else:
            Logger.warning(f"⚠️ Snipe failed: {result['error']}")

    async def monitor_positions(self):
        """Check PnL of held positions."""
        if not self.tracker.positions:
            return

        # BaseEngine has self.feed (JupiterFeed)
        for mint, pos in list(self.tracker.positions.items()):
            quote = self.feed.get_spot_price(mint)
            if not quote: continue
                
            current_price = quote.price
            entry_price = pos["entry_price"]
            pnl_pct = (current_price - entry_price) / entry_price
            
            should_exit = False
            reason = ""
            
            if pnl_pct >= self.tp_pct:
                should_exit = True
                reason = "Take Profit"
                Logger.success(f"💰 TAKE PROFIT: {pos['symbol']} (+{pnl_pct*100:.1f}%)")
            elif pnl_pct <= -self.sl_pct:
                should_exit = True
                reason = "Stop Loss"
                Logger.warning(f"🛑 STOP LOSS: {pos['symbol']} ({pnl_pct*100:.1f}%)")
                
            if should_exit:
                # Sell full position value
                usd_val = pos["amount"] * current_price
                await self.execute_swap("SELL", usd_val, mint, pos["symbol"])
                self.tracker.remove_position(mint)
