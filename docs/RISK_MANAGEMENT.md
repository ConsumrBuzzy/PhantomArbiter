# PhantomTrader Risk Management

Comprehensive documentation of all risk controls and safety mechanisms.

---

## Risk Management Overview

PhantomTrader implements multiple layers of risk management:

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: Position-Level Controls                          │
│  ├── Stop Loss (Fixed %)                                   │
│  ├── Trailing Stop Loss (Dynamic)                          │
│  └── Take Profit Targets                                   │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Portfolio-Level Controls                         │
│  ├── ATR-Based Position Sizing                             │
│  ├── Max Position Limits                                   │
│  └── Cash Reserve Requirements                             │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Strategy-Level Controls                          │
│  ├── Daily Drawdown Limits                                 │
│  ├── Strategy Drawdown Limits                              │
│  └── Global Lock (Distress Signal)                         │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: Token Safety                                     │
│  ├── Mint/Freeze Authority Checks                          │
│  ├── Honeypot Detection                                    │
│  └── Liquidity & Holder Concentration                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 1. Position-Level Controls

### Fixed Stop Loss

```python
STOP_LOSS_PCT = -0.03  # Exit at -3% loss
```

Triggered when:
```python
pnl_pct = (current_price - entry_price) / entry_price
if pnl_pct <= STOP_LOSS_PCT:
    return "SELL", "Stop-Loss", 0
```

### Trailing Stop Loss (V8.2)

**File:** `src/strategy/risk.py` → `TrailingStopManager`

Dynamic protection that locks in profits:

```python
TSL_ENABLED = True
TSL_ACTIVATION_PCT = 0.020   # +2.0% activates TSL
TSL_TRAIL_PCT = 0.015        # 1.5% trailing distance
```

**How it works:**

1. **Activation**: TSL activates when profit reaches +2%
2. **Max Tracking**: System tracks highest price achieved
3. **Stop Calculation**: `stop_price = max_price × (1 - TSL_TRAIL_PCT)`
4. **Trigger**: Sell when price drops below stop_price

```python
class TrailingStopManager:
    @staticmethod
    def update_tsl(current_price: float, state: dict) -> tuple:
        """
        Returns: (new_state, triggered, reason)
        """
        pnl_pct = (current_price - state['entry_price']) / state['entry_price']
        
        # Phase 1: Not yet activated
        if pnl_pct < TSL_ACTIVATION_PCT:
            return state, False, None
        
        # Phase 2: Activated - update max price
        if current_price > state['max_price_achieved']:
            state['max_price_achieved'] = current_price
            state['trailing_stop_price'] = current_price * (1 - TSL_TRAIL_PCT)
        
        # Phase 3: Check trigger
        if current_price <= state['trailing_stop_price']:
            return state, True, f"TSL@{state['trailing_stop_price']:.6f}"
        
        return state, False, None
```

### Take Profit

```python
TAKE_PROFIT_PCT = 0.04  # Exit at +4% profit
```

---

## 2. ATR-Based Position Sizing

**File:** `src/strategy/risk.py` → `PositionSizer`

Uses volatility to normalize risk across assets:

### Formula

```
Position Size = (Account Equity × Risk per Trade) / (ATR × ATR Multiplier)
```

### Configuration

```python
RISK_PER_TRADE_PCT = 0.02    # 2% of equity at risk
ATR_MULTIPLIER = 2.0          # Stop = ATR × 2
MIN_BUY_SIZE = 3.00          # Floor
MAX_BUY_SIZE = 5.00          # Ceiling
```

### Implementation

```python
class PositionSizer:
    @staticmethod
    def calculate_size(atr: float, win_rate: float = 0.0, symbol: str = None) -> float:
        """
        V8.3 Formula: Size = ATR_Size * (1 + WinRate)
        V9.1: Apply RS multiplier for market leaders
        """
        if atr <= 0:
            return Settings.MIN_BUY_SIZE
        
        # Base size from ATR
        dollar_risk = Settings.FIXED_DOLLAR_RISK
        stop_distance = atr * Settings.ATR_MULTIPLIER
        base_size = dollar_risk / stop_distance
        
        # Win rate scaling
        size = base_size * (1.0 + win_rate)
        
        # RS momentum multiplier
        rs_mult = PositionSizer.get_rs_multiplier(symbol)
        size *= rs_mult
        
        # Apply bounds
        return max(Settings.MIN_BUY_SIZE, min(size, Settings.MAX_BUY_SIZE))
```

### RS-Based Multiplier

Leaders (by Relative Strength) get larger allocations:

| RS Rank | Multiplier |
|---------|------------|
| 1 (Leader) | 1.5× |
| 2 | 1.25× |
| 3+ | 1.0× |

---

## 3. Portfolio-Level Controls

### Maximum Positions

```python
MAX_POSITIONS = 3            # Max concurrent positions
MAX_POSITIONS_PER_ENGINE = 5 # Per-engine limit
```

### Cash Reserve

```python
CASH_RESERVE = 3.0      # Minimum cash buffer (USD)
CASH_FLOOR_USD = 2.00   # Emergency reserve
```

### Capital Per Trade

```python
MAX_CAPITAL_PER_TRADE_PCT = 0.25  # Max 25% of cash per trade
```

---

## 4. Circuit Breakers (V28.0)

**File:** `src/core/capital_manager.py`

### Strategy Drawdown Limit

```python
MAX_DRAWDOWN_PER_STRATEGY_PCT = 0.15  # 15% max drawdown
```

When breached:
- Strategy is **auto-disabled**
- Alert sent via Telegram
- Manual reset required

### Daily Drawdown Limit

```python
DAILY_DRAWDOWN_LIMIT_PCT = 0.05  # 5% daily loss limit
```

When breached:
- Trading **paused for 24 hours**
- All pending orders cancelled
- Positions held (not force-closed)

### Global Kill Switch

```python
MAX_DAILY_DRAWDOWN = 0.10  # 10% portfolio drop
```

Complete trading halt across all strategies.

### Distress Signal

```python
DISTRESSED_THRESHOLD = -0.005  # -0.5%
```

Triggers **global lock** to prevent cascade selling.

---

## 5. Wallet Lock (Cross-Process Safety)

**File:** `src/strategy/risk.py` → `WalletLock`

Prevents simultaneous trading from multiple engines:

```python
class WalletLock:
    """File-based lock for cross-process wallet safety."""
    
    LOCK_FILE = ".wallet.lock"
    
    @classmethod
    def acquire(cls, timeout: float = 5.0) -> bool:
        """Acquire exclusive wallet access."""
        try:
            cls._lock = FileLock(LOCK_FILE)
            cls._lock.acquire(timeout=timeout)
            return True
        except Timeout:
            return False
    
    @classmethod
    def release(cls):
        """Release wallet lock."""
        if cls._lock:
            cls._lock.release()
```

---

## 6. Token Safety Validation (V5.7)

**File:** `src/core/validator.py` → `TokenValidator`

### Validation Layers

| Check | Purpose | Threshold |
|-------|---------|-----------|
| Mint Authority | Block infinite minting | Must be revoked |
| Freeze Authority | Block wallet freezing | Must be revoked |
| Honeypot | Block unsellable tokens | Must pass sell simulation |
| Liquidity | Ensure market depth | > $100,000 |
| Top 10 Holders | Prevent rug pulls | < 30% concentration |

### Validation Flow

```python
def validate(self, mint: str, symbol: str = "UNKNOWN") -> ValidationResult:
    # Layer 1: Authority checks (Solana RPC)
    mint_ok = self.check_mint_authority(mint)
    freeze_ok = self.check_freeze_authority(mint)
    
    # Layer 1: Honeypot simulation (Jupiter API)
    honeypot_ok = self.check_honeypot(mint)
    
    # Layer 2: Liquidity check (DexScreener API)
    liquidity_ok, liquidity_usd = self.check_liquidity(mint)
    
    # Layer 2: Holder concentration (Solana RPC)
    holders_ok, top10_pct = self.check_top_holders(mint)
    
    is_safe = all([mint_ok, freeze_ok, honeypot_ok, liquidity_ok, holders_ok])
    
    return ValidationResult(
        is_safe=is_safe,
        mint_authority_ok=mint_ok,
        freeze_authority_ok=freeze_ok,
        honeypot_ok=honeypot_ok,
        liquidity_ok=liquidity_ok,
        liquidity_usd=liquidity_usd,
        top_holders_ok=holders_ok,
        top10_pct=top10_pct
    )
```

---

## 7. Gas Management (V10.3)

**File:** `src/core/capital_manager.py`

### SOL Balance Monitoring

```python
GAS_FLOOR_SOL = 0.005      # Warn level (~$0.65)
GAS_CRITICAL_SOL = 0.002   # Auto-refuel trigger
GAS_REPLENISH_USD = 1.00   # Replenish amount
```

### Auto-Refuel Logic

```python
def _ensure_gas(self, engine_name: str, min_sol: float = 0.02):
    """Auto-buy SOL from USD when gas is low."""
    sol_balance = self.get_sol_balance(engine_name)
    
    if sol_balance < GAS_CRITICAL_SOL:
        # Calculate SOL to buy
        sol_price = self._get_sol_price()
        sol_to_buy = GAS_REPLENISH_USD / sol_price
        
        # Deduct from cash, add to SOL balance
        self._state["engines"][engine_name]["cash"] -= GAS_REPLENISH_USD
        self._state["engines"][engine_name]["sol_balance"] += sol_to_buy
        
        Logger.info(f"⛽ Auto-refueled {sol_to_buy:.4f} SOL")
```

---

## 8. Anti-Cascade Guard

Prevents rapid re-entries after stop-losses:

```python
HIBERNATION_SECONDS = 1800    # 30 min cooldown
EXTREME_OVERSOLD_RSI = 20     # RSI < 20 for re-entry
```

After a stop-loss:
1. Token enters **hibernation** for 30 minutes
2. Re-entry only allowed if RSI < 20 (extreme oversold)
3. Prevents emotional revenge trading

---

## 9. Max Hold Time (V47.6)

Force-sell stale positions:

```python
MAX_HOLD_TIME_MINUTES = 15  # Force-sell after 15 min
```

Prevents "zombie bags" from accumulating in scalping mode.

---

## 10. Capital Discipline (V48.0)

### Drawdown Reset

```python
MAX_CAPITAL_DRAWDOWN_PCT = 0.75  # 75% drawdown = reset
```

If equity drops 75% below starting capital:
- Paper wallet resets to starting capital
- Trade history preserved
- Clean slate for recovery

### Wallet Cloning

```python
CLONE_WALLET_ON_FIRST_RUN = True
```

Paper wallet starts with exact real wallet balance for accurate simulation.
