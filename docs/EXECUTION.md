# PhantomTrader Execution

Trade execution, Jupiter integration, and simulation realism.

---

## Execution Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  TradingCore                                                │
│  └── DecisionEngine returns (BUY/SELL, reason, size)        │
├─────────────────────────────────────────────────────────────┤
│  Execution Path                                             │
│  ┌─────────────────┐  ┌─────────────────┐                  │
│  │ LIVE MODE       │  │ MONITOR MODE    │                  │
│  │ JupiterSwapper  │  │ CapitalManager  │                  │
│  │ (Real trades)   │  │ (Simulation)    │                  │
│  └────────┬────────┘  └────────┬────────┘                  │
│           │                    │                           │
│           ▼                    ▼                           │
│  ┌─────────────────┐  ┌─────────────────┐                  │
│  │ Jupiter API     │  │ Paper Wallet    │                  │
│  │ SmartRouter     │  │ Slippage Model  │                  │
│  │ JITO Private TX │  │ Fee Simulation  │                  │
│  └────────┬────────┘  └─────────────────┘                  │
│           │                                                 │
│           ▼                                                 │
│  ┌─────────────────┐                                       │
│  │ Solana RPC      │                                       │
│  │ (Blockchain)    │                                       │
│  └─────────────────┘                                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 1. JupiterSwapper (Live Execution)

**File:** `src/execution/swapper.py`

### Swap Flow

```python
class JupiterSwapper:
    def execute_swap(self, direction, amount_usd, reason, target_mint=None):
        """Execute swap with adaptive slippage."""
        
        if not Settings.ENABLE_TRADING:
            Logger.info(f"🔒 TRADING DISABLED: Would {direction} ${amount_usd}")
            return None
        
        SLIPPAGE_TIERS = [100, 300, 500, 1000]  # 1% → 10%
        
        for tier_idx, slippage_bps in enumerate(SLIPPAGE_TIERS):
            try:
                # 1. Get Quote
                quote = self.router.get_jupiter_quote(
                    input_mint, output_mint, amount_atomic, slippage_bps
                )
                if not quote:
                    continue
                
                # 2. Build Transaction
                payload = {
                    "quoteResponse": quote,
                    "userPublicKey": self.wallet.get_public_key(),
                    "wrapAndUnwrapSol": True,
                    "computeUnitPriceMicroLamports": PRIORITY_FEE
                }
                swap_data = self.router.get_swap_transaction(payload)
                
                # 3. Sign Transaction
                raw_tx = base64.b64decode(swap_data["swapTransaction"])
                tx = VersionedTransaction.from_bytes(raw_tx)
                signed_tx = VersionedTransaction(tx.message, [self.wallet.keypair])
                
                # 4. Send via JITO (if available)
                if self.jito_available:
                    tx_sig = self.jito_client.send_transaction(signed_tx)
                else:
                    tx_sig = self.client.send_transaction(signed_tx)
                
                Logger.success(f"✅ Tx Sent: solscan.io/tx/{tx_sig}")
                return str(tx_sig.value)
                
            except Exception as e:
                if "SlippageExceeded" in str(e):
                    Logger.warning(f"⚠️ Tier {tier_idx+1} failed, escalating...")
                    continue
                raise
        
        Logger.error("❌ All slippage tiers exhausted")
        return None
```

### Adaptive Slippage

```python
ADAPTIVE_SLIPPAGE_TIERS = [100, 300, 500, 1000]  # BPS
# 1% → 3% → 5% → 10%
```

If a swap fails due to slippage, automatically retry with higher tolerance.

---

## 2. JITO Protection (V12.3)

**File:** `src/execution/swapper.py`

Prevents MEV/front-running attacks:

### How It Works

1. **Private Transaction Pool**: Transactions sent to JITO block builders
2. **Bundle Protection**: Your transaction isn't visible in public mempool
3. **Priority Tip**: Small tip to validators for inclusion

```python
def __init__(self, wallet_manager):
    # Initialize JITO client
    jito_url = self.router.get_jito_execution_url()
    if jito_url:
        self.jito_client = Client(jito_url)
        self.jito_available = True
        Logger.info("🛡️ JITO Block Engine configured")
```

### JITO Configuration

```python
JITO_TIP_LAMPORTS = 1000  # ~0.000001 SOL per block
```

---

## 3. WalletManager

**File:** `src/execution/wallet.py`

### Keypair Management

```python
class WalletManager:
    def __init__(self):
        self.keypair = self._load_keypair()
    
    def _load_keypair(self):
        """Load keypair from environment."""
        key = os.getenv("SOLANA_PRIVATE_KEY")
        if not key:
            Logger.warning("⚠️ No private key - Monitor mode only")
            return None
        return Keypair.from_base58_string(key)
```

### Balance Fetching

```python
def get_balance(self, mint_str) -> float:
    """Fetch SPL token balance via RPC."""
    rpc = get_rpc_pool().get_client()
    pubkey = self.keypair.pubkey()
    
    # Get token accounts
    response = rpc.get_token_accounts_by_owner(
        pubkey, 
        {"mint": mint_str}
    )
    
    if response.value:
        account = response.value[0]
        return float(account.account.data.parsed["info"]["tokenAmount"]["uiAmount"])
    return 0.0

def get_sol_balance(self) -> float:
    """Fetch native SOL balance for gas."""
    rpc = get_rpc_pool().get_client()
    balance = rpc.get_balance(self.keypair.pubkey())
    return balance.value / 1e9  # Lamports → SOL
```

### Autonomous Gas Management

```python
def check_and_replenish_gas(self, swapper):
    """Swap USDC → SOL if gas is critical."""
    sol_balance = self.get_sol_balance()
    
    if sol_balance < Settings.GAS_CRITICAL_SOL:
        Logger.warning(f"⛽ SOL critical ({sol_balance:.4f}), auto-refueling...")
        swapper.execute_swap(
            direction="BUY",
            amount_usd=Settings.GAS_REPLENISH_USD,
            reason="Gas Refuel",
            target_mint="So11111111111111111111111111111111111111112"  # Wrapped SOL
        )
```

---

## 4. Paper Wallet (Simulation)

**File:** `src/execution/paper_wallet.py`

For Monitor mode, simulates all trading mechanics:

```python
class PaperWallet:
    """Simulated wallet for paper trading."""
    
    def __init__(self, initial_usdc: float = 100.0, initial_sol: float = 0.1):
        self.usdc = initial_usdc
        self.sol = initial_sol
        self.positions = {}  # {symbol: {balance, avg_price, entry_time}}
    
    def execute_buy(self, symbol: str, mint: str, price: float, size_usd: float):
        """Simulate buy with realistic slippage and fees."""
        # Apply slippage
        slippage = self._calculate_slippage(size_usd)
        effective_price = price * (1 + slippage)
        
        # Deduct gas fee
        self.sol -= Settings.SIMULATION_SWAP_FEE_SOL
        
        # Calculate tokens received
        tokens = size_usd / effective_price
        
        # Update position
        self.usdc -= size_usd
        self.positions[symbol] = {
            "balance": tokens,
            "avg_price": effective_price,
            "entry_time": time.time()
        }
        
        return True
```

---

## 5. CapitalManager (V40.0)

**File:** `src/core/capital_manager.py`

Centralized capital management for all simulation:

### Singleton Pattern

```python
class CapitalManager:
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance
```

### State Persistence

```python
STATE_FILE = "config/capital_state.json"

def _save_state(self):
    """Atomic write with os.replace."""
    temp_file = STATE_FILE + ".tmp"
    with open(temp_file, 'w') as f:
        json.dump(self._state, f, indent=2)
    os.replace(temp_file, STATE_FILE)
```

### Execute with Slippage

```python
def execute_buy(self, engine_name, symbol, mint, price, size_usd, 
                liquidity_usd=100000.0, is_volatile=False):
    """Execute buy with V46.0 Dynamic Slippage."""
    
    # Calculate slippage
    slippage_pct, slippage_cost = self._calculate_slippage(
        size_usd, liquidity_usd, is_volatile
    )
    
    # Apply MEV penalty (if unlucky)
    if random.random() < Settings.MEV_RISK_RATE_PCT:
        mev_penalty = random.uniform(0, Settings.MEV_PENALTY_MAX_PCT)
        slippage_pct += mev_penalty
        Logger.warning(f"🥪 Sandwiched! Extra {mev_penalty:.2%} slippage")
    
    effective_price = price * (1 + slippage_pct)
    tokens = size_usd / effective_price
    
    # Deduct gas
    self._ensure_gas(engine_name)
    engine = self._state["engines"][engine_name]
    engine["sol_balance"] -= Settings.SIMULATION_SWAP_FEE_SOL
    engine["cash"] -= size_usd
    
    # Record position
    engine["positions"][symbol] = Position(
        symbol=symbol,
        mint=mint,
        balance=tokens,
        avg_price=effective_price,
        entry_time=time.time()
    )
    
    self._save_state()
    return True
```

---

## 6. Dynamic Slippage Model (V46.0)

```python
def _calculate_slippage(self, trade_size_usd, liquidity_usd, is_volatile=False):
    """
    Realistic slippage based on:
    1. Base spread (0.3%)
    2. Size impact (larger trades = more slippage)
    3. Volatility multiplier (3x in volatile markets)
    """
    # Base slippage
    base = Settings.SLIPPAGE_BASE_PCT  # 0.3%
    
    # Size impact: 0.05 * (size / liquidity)
    size_impact = Settings.SLIPPAGE_IMPACT_MULTIPLIER * (trade_size_usd / liquidity_usd)
    
    # Volatility adjustment
    vol_mult = Settings.SLIPPAGE_VOLATILITY_MULTIPLIER if is_volatile else 1.0
    
    # Total slippage
    slippage_pct = (base + size_impact) * vol_mult
    slippage_cost = trade_size_usd * slippage_pct
    
    return slippage_pct, slippage_cost
```

---

## 7. Transaction Failure Simulation

```python
TRANSACTION_FAILURE_RATE_PCT = 0.05  # 5% failure rate

def _simulate_transaction(self):
    """Simulate network failures."""
    if random.random() < Settings.TRANSACTION_FAILURE_RATE_PCT:
        raise TransactionFailure("Network timeout")
    
    # Execution delay
    delay_ms = random.randint(
        Settings.EXECUTION_DELAY_MIN_MS,
        Settings.EXECUTION_DELAY_MAX_MS
    )
    time.sleep(delay_ms / 1000)
```

---

## 8. Partial Fills

```python
PARTIAL_FILL_RATE_PCT = 0.10  # 10% chance
MIN_FILL_PCT = 0.80           # 80% minimum

def _apply_partial_fill(self, size_usd):
    """Simulate partial order fills."""
    if random.random() < Settings.PARTIAL_FILL_RATE_PCT:
        fill_pct = random.uniform(Settings.MIN_FILL_PCT, 1.0)
        Logger.info(f"📊 Partial fill: {fill_pct:.1%}")
        return size_usd * fill_pct
    return size_usd
```

---

## 9. SmartRouter

**File:** `src/system/smart_router.py`

Manages RPC endpoint selection:

```python
class SmartRouter:
    def __init__(self):
        self.endpoints = self._load_endpoints()
        self.current_idx = 0
    
    def get_best_endpoint(self):
        """Get highest-weighted available endpoint."""
        available = [e for e in self.endpoints if not e["blacklisted"]]
        return max(available, key=lambda x: x["weight"])
    
    def get_jupiter_quote(self, input_mint, output_mint, amount, slippage_bps):
        """Route quote through best endpoint."""
        endpoint = self.get_best_endpoint()
        # ... make request ...
    
    def get_jito_execution_url(self):
        """Get JITO block engine URL for private transactions."""
        return self.jito_endpoints[0] if self.jito_endpoints else None
```

---

## 10. Execution Modes

| Mode | Real Trades | Simulation | Use Case |
|------|-------------|------------|----------|
| `--live` | ✅ | ❌ | Production trading |
| `--monitor` | ❌ | ✅ | Paper trading |
| `--data` | ❌ | ❌ | Data broker only |

```python
# main.py
if args.live:
    Settings.ENABLE_TRADING = True
    Logger.info("🔴 LIVE MODE - Real trades enabled")
else:
    Settings.ENABLE_TRADING = False
    Logger.info("🟢 MONITOR MODE - Paper trading")
```
