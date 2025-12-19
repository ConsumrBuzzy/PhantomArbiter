
import asyncio
import time
from typing import Dict, Optional, List
from src.agents.base_agent import BaseAgent, AgentSignal
from src.infrastructure.rpc_balancer import get_rpc_balancer
from src.system.logging import Logger
import os
import json
from config.settings import Settings
from src.core.shared_cache import SharedPriceCache

class ScoutAgent(BaseAgent):
    """
    V65.0: The Scout Agent (Navigator & Validator)
    
    Roles:
    1. Smart Money Tracker (Identify & Audit winners) -> TRUST_BOOST
    2. Microstructure Analyst (Order Flow Imbalance) -> BUY/SELL pressure
    3. Regime Detector (Trending/Choppy) -> Metadata
    """
    
    def __init__(self, config: Dict = None):
        super().__init__(name="SCOUT", config=config or {})
        self.rpc = get_rpc_balancer()
        
        # Smart Money Config
        self.watchlist_file = os.path.join(os.path.dirname(__file__), "../../data/smart_money_watchlist.json")
        self.watchlist = self._load_watchlist()
        self.audit_queue = asyncio.Queue()
        self.audited_wallets = set()
        
        self.MIN_WIN_RATE = 0.70
        self.MIN_ROI_AVG = 1.5 
        self.MIN_TRADES = 10
        
        # OFI Config (Classic order book - requires depth data)
        self.ofi_window_seconds = 1
        self.last_bid_size = 0.0
        self.last_ask_size = 0.0
        self.last_ofi_calc = 0
        
        # V77.0: Price Momentum Tracker (works without order book)
        self.price_history: Dict[str, List[tuple]] = {}  # {symbol: [(timestamp, price), ...]}
        self.momentum_window = 10  # Track last 10 ticks per symbol
        self.momentum_threshold = 0.02  # 2% move in window = signal
        self.pre_pump_signals: Dict[str, float] = {}  # {symbol: last_signal_time}
        self.signal_cooldown = 60  # Don't spam same token within 60s
        
        Logger.info(f"[{self.name}] Agent Initialized (Watchlist: {len(self.watchlist)})")

    def _load_watchlist(self) -> Dict:
        if not os.path.exists(self.watchlist_file):
            return {}
        try:
            with open(self.watchlist_file, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_watchlist(self):
        try:
            os.makedirs(os.path.dirname(self.watchlist_file), exist_ok=True)
            with open(self.watchlist_file, "w") as f:
                json.dump(self.watchlist, f, indent=2)
        except Exception as e:
            Logger.error(f"[{self.name}] Failed to save watchlist: {e}")

    async def start(self):
        """Start background auditing tasks."""
        self.running = True
        asyncio.create_task(self._process_audit_queue())
        asyncio.create_task(self._scan_active_tokens_job())
        Logger.info(f"[{self.name}] Background tasks started")

    def stop(self):
        self.running = False
        Logger.info(f"[{self.name}] Stopped")

    def on_tick(self, market_data: Dict) -> Optional[AgentSignal]:
        """
        V77.0: Enhanced tick analysis with Price Momentum + OFI.
        
        market_data expected: {'symbol': 'SOL', 'price': 100.0, 'bids': [], 'asks': []}
        """
        symbol = market_data.get('symbol', 'UNKNOWN')
        price = market_data.get('price', 0)
        
        if not price or price <= 0:
            return None
        
        # V77.0: Track price history for momentum
        self._track_price(symbol, price)
        
        # V77.0: Calculate momentum-based signal (no order book needed)
        momentum = self.calculate_price_momentum(symbol)
        
        if momentum and momentum > self.momentum_threshold:
            # Check cooldown
            last_signal = self.pre_pump_signals.get(symbol, 0)
            if time.time() - last_signal > self.signal_cooldown:
                self.pre_pump_signals[symbol] = time.time()
                
                # Log PRE_PUMP signal
                Logger.info(f"🚀 [SCOUT] PRE_PUMP: {symbol} +{momentum*100:.1f}% momentum detected!")
                
                return self._create_signal(
                    symbol=symbol,
                    action="BUY",
                    confidence=min(0.5 + momentum * 10, 0.9),  # Scale confidence with momentum
                    reason=f"PRE_PUMP: {momentum*100:.1f}% momentum",
                    metadata={"momentum": momentum, "strategy": "MOMENTUM"}
                )
        
        # Classic OFI (if we have order book data)
        ofi_score = self.calculate_ofi(market_data)
        
        if ofi_score > 5000:
             return self._create_signal(
                 symbol=symbol,
                 action="BUY",
                 confidence=0.8,
                 reason=f"High Order Flow Imbalance (OFI: {ofi_score:.0f})",
                 metadata={"ofi": ofi_score, "strategy": "MICROSTRUCTURE"}
             )
             
        return None
    
    def _track_price(self, symbol: str, price: float):
        """V77.0: Track price history for momentum calculation."""
        now = time.time()
        
        if symbol not in self.price_history:
            self.price_history[symbol] = []
        
        self.price_history[symbol].append((now, price))
        
        # Keep only last N ticks
        if len(self.price_history[symbol]) > self.momentum_window:
            self.price_history[symbol] = self.price_history[symbol][-self.momentum_window:]
    
    def calculate_price_momentum(self, symbol: str) -> Optional[float]:
        """
        V77.0: Calculate price momentum as % change over window.
        
        Returns:
            Float 0.0-1.0 representing price change, or None if insufficient data.
        """
        history = self.price_history.get(symbol, [])
        
        if len(history) < 3:  # Need at least 3 ticks
            return None
        
        # Get oldest and newest price
        oldest_price = history[0][1]
        newest_price = history[-1][1]
        
        if oldest_price <= 0:
            return None
        
        # Calculate % change
        momentum = (newest_price - oldest_price) / oldest_price
        
        return momentum

    def calculate_ofi(self, market_data: Dict) -> float:
        """
        Calculate Order Flow Imbalance ($e_n$).
        Formula: (CurrentBidSize - LastBidSize) - (CurrentAskSize - LastAskSize)
        *Simplified*: Focuses on size changes at best bid/ask.
        """
        try:
            # We need best bid/ask size
            # Assuming market_data has 'bids' list of [price, size] and 'asks'
            bids = market_data.get('bids', [])
            asks = market_data.get('asks', [])
            
            if not bids or not asks:
                return 0.0
                
            current_bid_size = float(bids[0][1])
            current_ask_size = float(asks[0][1])
            
            # Check delta
            delta_bid = current_bid_size - self.last_bid_size
            delta_ask = current_ask_size - self.last_ask_size
            
            # Update state
            self.last_bid_size = current_bid_size
            self.last_ask_size = current_ask_size
            
            # Make sure we don't spike on first run
            if self.last_ofi_calc == 0:
                self.last_ofi_calc = time.time()
                return 0.0
                
            # OFI = BidDelta - AskDelta
            # If Bid Size INCREASES (people lining up to buy) -> Positive
            # If Ask Size INCREASES (people lining up to sell) -> Negative impact
            ofi = delta_bid - delta_ask
            
            return ofi
            
        except Exception:
            return 0.0

    # ═══════════════════════════════════════════════════════════════════════
    # V69.0: FLASH AUDIT (Fast First-Buyer Check for Sniper)
    # ═══════════════════════════════════════════════════════════════════════
    
    def flash_audit(self, mint: str) -> Optional[Dict]:
        """
        V69.0 / V72.0: Quick audit of a token's first buyers for Smart Money presence.
        
        V72.0: Now uses Bitquery First 100 Buyers API as primary source.
        Fallback to RPC if Bitquery unavailable.
        
        Returns:
            {'smart_money_count': int, 'rug_risk': bool, 'wallets': [], 'source': str}
            or None if audit fails
        """
        # V72.0: Try Bitquery First 100 Buyers (faster, more complete)
        try:
            from src.infrastructure.bitquery_adapter import BitqueryAdapter
            bitquery = BitqueryAdapter()
            buyers = bitquery.get_first_100_buyers(mint)
            
            if buyers:
                smart_money_count = 0
                found_wallets = []
                
                for wallet in buyers[:20]:  # Check first 20 for speed
                    if wallet in self.watchlist:
                        smart_money_count += 1
                        found_wallets.append(wallet[:8])
                
                # Rug risk: if first buyer bought >10% of first 20 transactions
                first_buyer = buyers[0] if buyers else None
                first_buyer_count = buyers[:20].count(first_buyer) if first_buyer else 0
                rug_risk = first_buyer_count >= 3
                
                return {
                    "smart_money_count": smart_money_count,
                    "rug_risk": rug_risk,
                    "wallets": found_wallets,
                    "source": "BITQUERY",
                    "total_buyers_checked": len(buyers[:20])
                }
        except Exception as e:
            Logger.debug(f"[{self.name}] Bitquery Flash Audit skipped: {e}")
        
        # Fallback: RPC-based audit (original V69.0 logic)
        try:
            resp, err = self.rpc.call("getSignaturesForAddress", [mint, {"limit": 10}])
            if err or not resp:
                return None
            
            signatures = resp.result if hasattr(resp, 'result') else resp
            if not signatures:
                return None
            
            smart_money_count = 0
            found_wallets = []
            rug_indicators = 0
            
            for sig_info in signatures[:10]:
                sig = sig_info.get("signature") if isinstance(sig_info, dict) else sig_info
                tx_resp, tx_err = self.rpc.call("getTransaction", [sig, {"encoding": "jsonParsed"}])
                
                if tx_err or not tx_resp:
                    continue
                
                tx = tx_resp.result if hasattr(tx_resp, 'result') else tx_resp
                if not tx:
                    continue
                    
                accounts = tx.get("transaction", {}).get("message", {}).get("accountKeys", [])
                
                for acc in accounts[:5]:
                    pubkey = acc.get("pubkey") if isinstance(acc, dict) else acc
                    if pubkey and pubkey in self.watchlist:
                        smart_money_count += 1
                        found_wallets.append(pubkey[:8])
                        break
                
                if len(accounts) >= 2:
                    acc0 = accounts[0].get("pubkey") if isinstance(accounts[0], dict) else accounts[0]
                    acc1 = accounts[1].get("pubkey") if isinstance(accounts[1], dict) else accounts[1]
                    if acc0 == acc1:
                        rug_indicators += 1
            
            return {
                "smart_money_count": smart_money_count,
                "rug_risk": rug_indicators >= 2,
                "wallets": found_wallets,
                "source": "RPC"
            }
            
        except Exception as e:
            Logger.debug(f"[{self.name}] Flash Audit Error: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════════════
    # SMART MONEY LOGIC (Migrated)
    # ═══════════════════════════════════════════════════════════════════════

    async def _process_audit_queue(self):
        """Background worker to process wallet audits with rate limiting."""
        Logger.info(f"[{self.name}] Audit worker started")
        while self.running:
            try:
                wallet_address = await self.audit_queue.get()
                
                if wallet_address in self.audited_wallets:
                    self.audit_queue.task_done()
                    continue
                
                self.audited_wallets.add(wallet_address)
                
                # Perform Audit (Silent - only log discoveries)
                # Logger.debug(f"[{self.name}] Auditing wallet: {wallet_address[:8]}...")
                score = await self.calculate_wallet_performance(wallet_address)
                
                if score and score['is_smart_money']:
                    Logger.info(f"[{self.name}] 🧠 SMART MONEY FOUND! {wallet_address[:8]} (WR: {score['win_rate']:.2f}, ROI: {score['avg_roi']:.2f}x)")
                    self.watchlist[wallet_address] = {
                        "score": score,
                        "timestamp": time.time(),
                        "label": "Auto-Discovered"
                    }
                    self._save_watchlist()
                
                # Rate Limit (1 audit per minute to save RPC credits)
                self.audit_queue.task_done()
                await asyncio.sleep(60) 
                
            except Exception as e:
                Logger.error(f"[{self.name}] Worker error: {e}")
                await asyncio.sleep(5)
                
    async def _scan_active_tokens_job(self):
        """V61.0 Integration: Periodically scan active candidates for Smart Money."""
        while self.running:
            try:
                # 1. Get active candidates (from Settings.ASSETS or Watch list)
                candidates = list(Settings.ACTIVE_ASSETS.values()) + list(Settings.WATCH_ASSETS.values())
                
                for mint in candidates:
                    # Resolve symbol
                    symbol = next((k for k, v in Settings.ASSETS.items() if v == mint), "UNKNOWN")
                    
                    # Scan
                    score = await self.scan_token_for_smart_money(mint)
                    if score > 0:
                        SharedPriceCache.write_trust_score(symbol, score)
                        # Only log high-confidence signals (score > 0.5)
                        if score > 0.5:
                            Logger.info(f"[{self.name}] 🧠 Smart Money on {symbol}: {score:.1f}")
                    
                    await asyncio.sleep(10) # 10s delay between tokens
                
                await asyncio.sleep(300) 
            except Exception as e:
                Logger.error(f"[{self.name}] Scan job error: {e}")
                await asyncio.sleep(60)

    async def trigger_audit(self, token_mint: str):
        """Public trigger: Find buyers of this successful token."""
        # V67.8: Resolve symbol using TokenScraper
        from src.infrastructure.token_scraper import get_token_scraper
        scraper = get_token_scraper()
        info = scraper.lookup(token_mint)
        symbol = info.get("symbol", token_mint[:8])
        name = info.get("name", "Unknown")
        
        Logger.info(f"[{self.name}] 🚀 Mooner Audit: {symbol} ({name})")
        
        resp, err = self.rpc.call("getSignaturesForAddress", [token_mint, {"limit": 100}])
        if err or not resp:
            return

        signatures = [s['signature'] for s in resp]
        candidates = set()
        
        # Check first 20 signatures
        for sig_info in signatures[:20]:
            sig = sig_info['signature'] if isinstance(sig_info, dict) else sig_info
            tx, tx_err = self.rpc.call("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0}])
            if tx_err or not tx: continue
            
            buyer = self._extract_signer(tx)
            if buyer and buyer not in self.watchlist:
                candidates.add(buyer)
                
        # Enqueue candidates
        for c in candidates:
            await self.audit_queue.put(c)

    def _extract_signer(self, tx_data: dict) -> Optional[str]:
        try:
            msg = tx_data.get("result", {}).get("transaction", {}).get("message", {})
            keys = msg.get("accountKeys", [])
            if keys:
                if isinstance(keys[0], dict):
                    return keys[0].get("pubkey")
                return keys[0]
        except: pass
        return None

    async def calculate_wallet_performance(self, wallet_address: str) -> Optional[Dict]:
        """Audit the wallet's last 50 trades."""
        resp, err = self.rpc.call("getSignaturesForAddress", [wallet_address, {"limit": 50}])
        if err or not resp: return None
        
        trades = []
        wins = 0
        total_roi = 0.0
        
        # Analyze last 20 txs
        sigs = [s['signature'] for s in resp[:20]] 
        
        for sig in sigs:
            tx, err = self.rpc.call("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0}])
            if err or not tx: continue
            
            pnl = self._analyze_tx_pnl(tx, wallet_address)
            if pnl:
                trades.append(pnl)
                if pnl > 0: wins += 1
                total_roi += pnl
                
        if not trades: return None
        
        win_rate = wins / len(trades)
        avg_roi = 1.5 if win_rate > 0.6 else 0.5 
        
        is_smart = (win_rate >= self.MIN_WIN_RATE)
        
        return {
            "win_rate": win_rate,
            "avg_roi": avg_roi,
            "trades": len(trades),
            "is_smart_money": is_smart
        }

    def _analyze_tx_pnl(self, tx: dict, wallet: str) -> Optional[float]:
        """Estimate PnL impact."""
        try:
            meta = tx.get("result", {}).get("meta", {})
            if not meta: return None
            
            # Simple heuristic matching DiscoveryEngine
            return self._check_picking_ability(tx, wallet, meta)
                
        except: pass
        return None

    def _check_picking_ability(self, tx, wallet, meta) -> Optional[float]:
        return 1.0 # Placeholder match

    async def scan_token_for_smart_money(self, token_mint: str) -> float:
        """Check if Smart Money is interacting."""
        if not self.watchlist: 
            return 0.0
            
        resp, err = self.rpc.call("getSignaturesForAddress", [token_mint, {"limit": 50}])
        if err or not resp:
            return 0.0
            
        smart_hits = 0
        sigs_to_check = [s['signature'] for s in resp[:15]]
        
        for sig in sigs_to_check:
             tx, err_tx = self.rpc.call("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0}])
             if not tx: continue
             
             signer = self._extract_signer(tx)
             if signer and signer in self.watchlist:
                 smart_hits += 1
                 
        if smart_hits >= 3: return 1.0
        if smart_hits == 2: return 0.8
        if smart_hits == 1: return 0.5
        return 0.0

