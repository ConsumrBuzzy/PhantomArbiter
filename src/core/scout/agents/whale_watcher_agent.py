import asyncio
import os
import json
from typing import Dict, Optional
from src.core.scout.agents.base_agent import BaseAgent, AgentSignal
from src.shared.infrastructure.rpc_balancer import get_rpc_balancer
from src.shared.system.logging import Logger
from src.shared.system.signal_bus import signal_bus, Signal, SignalType


class WhaleWatcherAgent(BaseAgent):
    """
    V66.0: The Whale Watcher Agent (Copy Trader)

    Roles:
    1. Shadow Tracking: Monitors 'Alpha Wallets' discovered by Scout.
    2. Copy Trading: Emits BUY signals when Top Wallets enter a position.
    """

    def __init__(self, config: Dict = None, metadata_registry: Dict = None):
        super().__init__(name="WHALE_WATCH", config=config or {})
        # V140: Strict Broker Protocol - No RPC in Agent
        # self.rpc = get_rpc_balancer() 

        # V67.0: Metadata Registry for Whale-Pulse Confidence Boost
        self.metadata_registry = metadata_registry or {}

        # Configuration
        self.poll_interval = 15.0  # Seconds (No longer used for polling)
        
        Logger.info(
            f"[{self.name}] Agent Initialized (Registry: {len(self.metadata_registry)} tokens)"
        )

    async def start(self):
        """Start listening for activity signals."""
        self.running = True
        # V140: Subscribe to Whale Sensor
        signal_bus.subscribe(SignalType.WHALE_ACTIVITY, self._handle_whale_activity)
        Logger.info(f"[{self.name}] Signal subscription active")

    def stop(self):
        self.running = False
        Logger.info(f"[{self.name}] Stopped")

    def on_tick(self, market_data: Dict) -> Optional[AgentSignal]:
        """
        Passive agent - doesn't react to price ticks directly.
        Reacts to on-chain events via signals.
        """
        return None

    # ═══════════════════════════════════════════════════════════════════════
    # WHALE WATCHING LOGIC
    # ═══════════════════════════════════════════════════════════════════════

    async def _handle_whale_activity(self, sig: Signal):
        """V140: Handle movement signal from WhaleSensor."""
        if not self.running:
            return
            
        wallet = sig.data.get("wallet")
        tx_data = sig.data.get("tx_data")
        
        if not wallet or not tx_data:
            return
            
        Logger.info(f"[{self.name}] 🐋 Analyzing activity for {wallet[:8]}...")
        await self._analyze_transaction(tx_data, wallet)

    async def _analyze_transaction(self, tx: dict, wallet: str):
        """Analyze TX to see if it's a BUY."""
        try:
            # Simple Heuristic: Did SOL balance DECREASE? (Spent SOL)
            # And Token Balance INCREASE? (Received Token)

            meta = tx.get("result", {}).get("meta", {})
            if not meta:
                return

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

            if wallet_idx == -1:
                return

            pre_sol = meta["preBalances"][wallet_idx]
            post_sol = meta["postBalances"][wallet_idx]

            sol_change = post_sol - pre_sol

            # If SOL went DOWN significantly (> 0.1 SOL, ignore slight gas)
            if sol_change < -50000000:  # -0.05 SOL
                # Likely a BUY (or transfer out)
                # To be sure, we should check token balances, but that requires parsing 'preTokenBalances'
                # which is verbose.

                # For V66.0, we assume SOL Spend = BUY intent if interaction is with DEX program.
                # Just emitting signal for now.

                Logger.info(
                    f"[{self.name}] 🚨 COPY TRADE SIGNAL: {wallet[:8]} spent {abs(sol_change) / 1e9:.2f} SOL"
                )

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

                # Emit to Global SignalBus (V33 Unification)
                usd_value = abs(sol_change) / 1e9 * 150  # Estimated USD value

                # V67.0: Update Whale-Pulse Confidence in Metadata Registry
                self._apply_whale_bonus(mint, usd_value)

                signal_bus.emit(
                    Signal(
                        type=SignalType.WHALE,
                        source=self.name,
                        data={
                            "symbol": mint,
                            "action": "BUY",
                            "confidence": 0.9,
                            "wallet": wallet,
                            "usd_value": usd_value,
                        },
                    )
                )

        except Exception as e:
            Logger.debug(f"[{self.name}] TX Analysis failed: {e}")

    def _find_token_received(self, meta, wallet_idx) -> Optional[str]:
        """Find if a token balance increased for this wallet."""
        # preTokenBalances / postTokenBalances
        # List of { accountIndex, mint, uiTokenAmount ... }

        pre_tokens = {
            x["mint"]: x
            for x in meta.get("preTokenBalances", [])
            if x.get("accountIndex") == wallet_idx
        }
        post_tokens = {
            x["mint"]: x
            for x in meta.get("postTokenBalances", [])
            if x.get("accountIndex") == wallet_idx
        }

        # Check for increase
        for mint, post_data in post_tokens.items():
            pre_amt = float(
                pre_tokens.get(mint, {}).get("uiTokenAmount", {}).get("amount", 0)
            )
            post_amt = float(post_data.get("uiTokenAmount", {}).get("amount", 0))

            if post_amt > pre_amt:
                return mint

        return None

    def _apply_whale_bonus(self, mint: str, usd_value: float) -> None:
        """
        V67.0: Apply Whale-Pulse confidence bonus to metadata registry.

        Bonus Scale:
        - $1k-$5k:   +0.05
        - $5k-$25k:  +0.15
        - $25k-$100k: +0.25
        - $100k+:    +0.35
        """
        if not self.metadata_registry:
            return

        # Get metadata for this mint
        metadata = self.metadata_registry.get(mint)
        if not metadata:
            return

        # Calculate bonus based on USD value (tiered)
        if usd_value >= 100_000:
            bonus = 0.35
        elif usd_value >= 25_000:
            bonus = 0.25
        elif usd_value >= 5_000:
            bonus = 0.15
        elif usd_value >= 1_000:
            bonus = 0.05
        else:
            return  # Below threshold, no bonus

        # Apply bonus (additive, capped at 0.5)
        try:
            current = getattr(metadata, "whale_confidence_bonus", 0.0)
            new_bonus = min(current + bonus, 0.5)
            metadata.whale_confidence_bonus = new_bonus
            Logger.info(
                f"🐋 [WHALE-PULSE] {mint[:8]}: +{bonus:.2f} confidence (Total: {new_bonus:.2f})"
            )
        except AttributeError:
            # Fallback for non-Rust metadata objects
            pass

