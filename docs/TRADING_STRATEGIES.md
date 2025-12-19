# PhantomTrader Trading Strategies

Detailed explanation of all trading strategies and their logic.

---

## Strategy Architecture

PhantomTrader supports multiple trading strategies through **BaseStrategy** inheritance:

```
BaseStrategy (src/strategy/base_strategy.py)
├── DecisionEngine (src/engine/decision_engine.py)     ← RSI Scalping
├── KeltnerLogic (src/strategy/keltner_logic.py)       ← Channel Breakouts
├── VwapLogic (src/strategy/vwap_logic.py)             ← VWAP Entries
└── LongtailLogic (src/strategy/longtail_logic.py)     ← Scout Discovery
```

---

## 1. RSI Scalping Strategy (DecisionEngine)

**File:** `src/engine/decision_engine.py`  
**Mode:** `SCALPER`

The primary strategy using RSI (Relative Strength Index) for entry/exit signals.

### Entry Conditions

| Condition | Threshold | Description |
|-----------|-----------|-------------|
| RSI Oversold | RSI < 30 | Market is oversold, potential bounce |
| Uptrend Confirmation | Price > SMA50 | Trend alignment |
| Validation Pass | Token safety OK | No honeypots/rugs |
| Cash Available | > MIN_BUY_SIZE | Sufficient capital |

### Exit Conditions

| Condition | Trigger | Priority |
|-----------|---------|----------|
| Take Profit | PnL ≥ +4% | High |
| Trailing Stop | TSL triggered | High |
| Stop Loss | PnL ≤ -3% | High |
| RSI Overbought | RSI > 70 | Medium |
| Max Hold Time | > 15 min | Low |

### Dynamic Strategy Adjustment (DSA)

The engine adapts based on win rate:

```python
# V11.0: Update market mode from win rate
def update_market_mode(self):
    win_rate = db_manager.get_win_rate(limit=20)
    
    if win_rate >= 0.55:
        self.mode = "AGGRESSIVE"   # Tighter stops, higher targets
    elif win_rate < 0.40:
        self.mode = "DEFENSIVE"    # Wider stops, conservative
    else:
        self.mode = "NEUTRAL"      # Default settings
```

---

## 2. Keltner Channel Strategy

**File:** `src/strategy/keltner_logic.py`  
**Mode:** `KELTNER`

Uses Keltner Channels (EMA + ATR bands) for breakout detection.

### Channel Calculation

```
Middle Band = EMA(20)
Upper Band  = EMA(20) + ATR(14) × 2
Lower Band  = EMA(20) - ATR(14) × 2
```

### Entry Conditions

| Signal | Condition | Description |
|--------|-----------|-------------|
| **Long Entry** | Price closes above Upper Band | Bullish breakout |
| + RSI Check | RSI < 70 | Not overbought |
| + Volume | Volume > SMA(20) | Confirmation |

### Exit Conditions

| Signal | Condition |
|--------|-----------|
| Mean Reversion | Price returns to Middle Band |
| Stop Loss | Price < Entry - ATR × 2 |
| Trailing Stop | Standard TSL logic |

---

## 3. VWAP Strategy

**File:** `src/strategy/vwap_logic.py`  
**Mode:** `VWAP`

Trades based on Volume-Weighted Average Price for "fair value" entries.

### VWAP Calculation

```
VWAP = Σ(Price × Volume) / Σ(Volume)
```

### Entry Conditions

| Signal | Condition | Description |
|--------|-----------|-------------|
| **Buy Dip** | Price < VWAP × 0.98 | 2% below VWAP |
| + RSI Check | RSI < 40 | Oversold confirmation |
| + Trend | Price > SMA(50) | Uptrend |

### Exit Conditions

| Signal | Condition |
|--------|-----------|
| Fair Value | Price returns to VWAP |
| Take Profit | Price > VWAP × 1.03 |
| Stop Loss | Standard -3% |

---

## 4. Longtail Strategy

**File:** `src/strategy/longtail_logic.py`  
**Mode:** `LONGTAIL`

Focuses on newly discovered tokens from the Scout pipeline.

### Characteristics

- Lower frequency than Scalper
- Higher risk tolerance
- Targets early-stage tokens
- Uses grading system for qualification

### Entry Conditions

| Condition | Threshold |
|-----------|-----------|
| Token Grade | ≥ 70/100 |
| RSI | < 35 (deeper oversold) |
| Liquidity | > $50,000 |
| Days Active | > 7 days |

### Exit Strategy

More aggressive profit-taking:
- Take Profit: +6% (vs 4% for Scalper)
- Stop Loss: -5% (wider buffer)

---

## Technical Indicators

### RSI Calculation

**File:** `src/strategy/signals.py`

```python
class TechnicalAnalysis:
    @staticmethod
    def calculate_rsi(prices: list, period: int = 14) -> float:
        """
        RSI = 100 - (100 / (1 + RS))
        RS = Average Gain / Average Loss
        """
        if len(prices) < period + 1:
            return TechnicalAnalysis._simple_rsi(prices)
        
        gains, losses = 0.0, 0.0
        for i in range(1, period + 1):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains += change
            else:
                losses -= change
        
        avg_gain = gains / period
        avg_loss = losses / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))
```

### Moving Averages

```python
# Simple Moving Average
@staticmethod
def calculate_sma(prices, period: int = 50) -> float:
    if len(prices) < period:
        return 0.0
    return sum(prices[-period:]) / period

# Exponential Moving Average
@staticmethod
def calculate_ema(prices, period: int = 20) -> float:
    alpha = 2.0 / (period + 1.0)
    ema = sum(prices[:period]) / period
    
    for price in prices[period:]:
        ema = (price * alpha) + (ema * (1 - alpha))
    
    return ema
```

### Average True Range (ATR)

```python
@staticmethod
def calculate_atr(highs, lows, closes, period: int = 14) -> float:
    """
    TR = Max(H-L, |H-PC|, |L-PC|)
    ATR = Wilder's Smoothing of TR
    """
    tr_list = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        tr_list.append(tr)
    
    atr = sum(tr_list[:period]) / period
    for tr in tr_list[period:]:
        atr = ((atr * (period - 1)) + tr) / period
    
    return atr
```

---

## Watcher State Machine

**File:** `src/strategy/watcher.py`

Each asset has a Watcher that tracks:

```python
@dataclass
class WatcherState:
    symbol: str
    mint: str
    in_position: bool = False
    entry_price: float = 0.0
    entry_time: float = 0.0
    max_price_achieved: float = 0.0
    trailing_stop_price: float = 0.0
    
    # Calculated
    def pnl_pct(self, current_price: float) -> float:
        if not self.in_position or self.entry_price <= 0:
            return 0.0
        return (current_price - self.entry_price) / self.entry_price
```

### State Transitions

```
┌──────────────┐  RSI < 30   ┌─────────────┐
│   WATCHING   │ ─────────▶  │ IN_POSITION │
└──────────────┘             └─────────────┘
       ▲                           │
       │                           │ TP/SL/TSL
       └───────────────────────────┘
```

---

## Ensemble Mode (V45.0)

**File:** `src/strategy/ensemble.py`

Combines signals from multiple strategies:

```python
class EnsembleStrategy:
    """
    Aggregates signals from multiple strategies and uses
    consensus logic for final decision.
    """
    
    def __init__(self, strategies: list):
        self.strategies = strategies
    
    def analyze(self, watcher, price) -> tuple:
        votes = []
        for strategy in self.strategies:
            action, reason, size = strategy.analyze_tick(watcher, price)
            votes.append((action, reason, size))
        
        # Majority voting
        return self._resolve_consensus(votes)
```

---

## Strategy Selection

Strategies are selected at engine initialization:

```python
# main.py / data_broker.py

if mode == "SCALPER":
    engine = TradingCore(strategy_class=DecisionEngine)
elif mode == "KELTNER":
    engine = TradingCore(strategy_class=KeltnerLogic)
elif mode == "VWAP":
    engine = TradingCore(strategy_class=VwapLogic)
elif mode == "LONGTAIL":
    engine = TradingCore(strategy_class=LongtailLogic)
```

---

## Metrics Tracking

**File:** `src/strategy/metrics.py`

```python
class Metrics:
    """
    Tracks performance metrics for strategy tuning.
    """
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    
    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.wins / self.total_trades
    
    @property
    def avg_pnl(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.total_pnl / self.total_trades
```
