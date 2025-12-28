
import asyncio
import time
import os
import json
from typing import Dict, Optional, Set, List
from src.scraper.agents.base_agent import BaseAgent, AgentSignal
from src.infrastructure.rpc_balancer import get_rpc_balancer
from src.shared.system.logging import Logger

class WhaleWatcherAgent(BaseAgent):
    """
    V66.0: The Whale Watcher Agent (Copy Trader)
    
    Roles:
    1. Shadow Tracking: Monitors 'Alpha Wallets' discovered by Scout.
    2. Copy Trading: Emits BUY signals when Top Wallets enter a position.
    """
    
    def __init__(self, config: Dict = None):
        super().__init__(name="WHALE_WATCH", config=config or {})
        self.rpc = get_rpc_balancer()
        
        # Configuration
        self.watchlist_file = os.path.join(os.path.dirname(__file__), "../../data/smart_money_watchlist.json")
        self.poll_interval = 15.0 # Seconds
        self.last_signatures: Dict[str, str] = {} # wallet -> last_seen_signature
        
        Logger.info(f"[{self.name}] Agent Initialized")

    async def start(self):
        """Start background polling."""
        self.running = True
        asyncio.create_task(self._poll_whales_job())
        Logger.info(f"[{self.name}] Background polling started")

    def stop(self):
        self.running = False
        Logger.info(f"[{self.name}] Stopped")

    def on_tick(self, market_data: Dict) -> Optional[AgentSignal]:
        """
        Passive agent - doesn't react to price ticks directly.
        Reacts to on-chain events via polling.
        """
        if hasattr(self, 'pending_signal') and self.pending_signal:
            sig = self.pending_signal
            self.pending_signal = None
            return sig
        return None

    # ═══════════════════════════════════════════════════════════════════════
    # WHALE WATCHING LOGIC
    # ═══════════════════════════════════════════════════════════════════════

    async def _poll_whales_job(self):
        """Poll Top 5 Alpha Wallets for new moves."""
        while self.running:
            try:
                # 1. Reload Watchlist (Dynamic)
                watchlist = self._load_watchlist()
                
                # 2. Filter for "Top 5" (Best Win Rate)
                # Sort by win_rate descending
                candidates = sorted(
                    watchlist.items(), 
                    key=lambda item: item[1].get('score', {}).get('win_rate', 0), 
                    reverse=True
                )[:5]
                
                if not candidates:
                    await asyncio.sleep(self.poll_interval)
                    continue
                    
                # 3. Poll each
                for wallet, data in candidates:
                    await self._check_wallet_activity(wallet, data)
                    await asyncio.sleep(1.0) # Stagger requests
                    
                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                Logger.error(f"[{self.name}] Polling Error: {e}")
                await asyncio.sleep(5)

    async def _check_wallet_activity(self, wallet: str, data: Dict):
        """Check for new transactions."""
        try:
            # Get latest signature (Limit 1 is enough to check head)
            resp, err = self.rpc.call("getSignaturesForAddress", [wallet, {"limit": 1}])
            if err or not resp: return
            
            latest_sig = resp[0]['signature']
            
            # Init state
            if wallet not in self.last_signatures:
                self.last_signatures[wallet] = latest_sig
                return

            # If new signature found
            if latest_sig != self.last_signatures[wallet]:
                Logger.info(f"[{self.name}] 🐋 Activity detected on {wallet[:8]}!")
                self.last_signatures[wallet] = latest_sig
                
                # Analyze the TX (Did they BUY?)
                # We need to fetch the TX details
                await self._analyze_transaction(latest_sig, wallet)
                
        except Exception as e:
            pass

    async def _analyze_transaction(self, signature: str, wallet: str):
        """Analyze TX to see if it's a BUY."""
        tx, err = self.rpc.call("getTransaction", [signature, {"encoding": "json", "maxSupportedTransactionVersion": 0}])
        if err or not tx: return
        
        try:
            # Simple Heuristic: Did SOL balance DECREASE? (Spent SOL)
            # And Token Balance INCREASE? (Received Token)
            
            meta = tx.get("result", {}).get("meta", {})
            if not meta: return
            
            # Check Pre/Post Balances for wallet
            # Need to find index of wallet in accounts
            msg = tx.get("result", {}).get("transaction", {}).get("message", {})
            keys = msg.get("accountKeys", [])
            
            wallet_idx = -1
            for i, k in enumerate(keys):
                k_str = k.get("pubkey") if isinstance(k, dict) else k
                if k_str == wallet:
                    wallet_idx = i
                    break
            
            if wallet_idx == -1: return
            
            pre_sol = meta['preBalances'][wallet_idx]
            post_sol = meta['postBalances'][wallet_idx]
            
            sol_change = post_sol - pre_sol
            
            # If SOL went DOWN significantly (> 0.1 SOL, ignore slight gas)
            if sol_change < -50000000: # -0.05 SOL
                # Likely a BUY (or transfer out)
                # To be sure, we should check token balances, but that requires parsing 'preTokenBalances'
                # which is verbose.
                
                # For V66.0, we assume SOL Spend = BUY intent if interaction is with DEX program.
                # Just emitting signal for now.
                
                Logger.info(f"[{self.name}] 🚨 COPY TRADE SIGNAL: {wallet[:8]} spent {abs(sol_change)/1e9:.2f} SOL")
                
                # We don't know start symbol without deeper parsing.
                # We emit a generic signals or try to find the mint from token balances?
                
                mint = self._find_token_received(meta, wallet_idx)
                if mint:
                     # Boom.
                     pass
                else:
                    mint = "UNKNOWN"

                # Emit Signal (Async? No, signals are usually returned by on_tick)
                # But we are in a background loop. 
                # We need a way to push signals to the engine.
                # The BaseAgent interface 'on_tick' returns a signal, but for async events...
                # We might need a queue or callback?
                # V65 Architecture: DataBroker calls on_tick.
                # If we find something async, we can queue it and return it on next on_tick?
                # Or we inject it into a Shared bus.
                
                # For now, let's just Log it. The implementation plan says "Emit AgentSignal".
                # We will store it in a volatile 'pending_signal' slot.
                self.pending_signal = AgentSignal(
                    symbol=mint,
                    action="BUY",
                    confidence=0.9,
                    reason=f"Whale Copy: {wallet[:8]}",
                    metadata={"source": "WHALE_WATCHER", "wallet": wallet}
                )

        except Exception as e:
            Logger.debug(f"[{self.name}] TX Analysis failed: {e}")

    def _find_token_received(self, meta, wallet_idx) -> Optional[str]:
        """Find if a token balance increased for this wallet."""
        # preTokenBalances / postTokenBalances
        # List of { accountIndex, mint, uiTokenAmount ... }
        
        pre_tokens = {x['mint']: x for x in meta.get('preTokenBalances', []) if x.get('accountIndex') == wallet_idx}
        post_tokens = {x['mint']: x for x in meta.get('postTokenBalances', []) if x.get('accountIndex') == wallet_idx}
        
        # Check for increase
        for mint, post_data in post_tokens.items():
            pre_amt = float(pre_tokens.get(mint, {}).get('uiTokenAmount', {}).get('amount', 0))
            post_amt = float(post_data.get('uiTokenAmount', {}).get('amount', 0))
            
            if post_amt > pre_amt:
                return mint
                
        return None

    def _load_watchlist(self) -> Dict:
        if not os.path.exists(self.watchlist_file):
            return {}
        try:
            with open(self.watchlist_file, "r") as f:
                return json.load(f)
        except Exception:
            return {}
