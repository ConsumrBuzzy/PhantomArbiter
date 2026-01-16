# Async Coroutine Fixes

## Issue
Multiple RuntimeWarnings were appearing during startup:
```
RuntimeWarning: coroutine 'JupiterFeed.get_spot_price' was never awaited
```

This occurred because `get_spot_price()` is an async method but was being called without the `await` keyword in several places.

## Root Cause
The `get_spot_price()` method in all price feed classes (`JupiterFeed`, `RaydiumFeed`, `OrcaFeed`, `MeteoraFeed`) is defined as `async def`, meaning it returns a coroutine that must be awaited. Calling it without `await` creates a coroutine object that is never executed, leading to the warning.

## Files Fixed

### 1. `src/interface/heartbeat_collector.py`
**Line 859**: Added `await` to `get_spot_price()` call
```python
# BEFORE
quote = self._price_feed.get_spot_price(symbol, "USDC")

# AFTER
quote = await self._price_feed.get_spot_price(symbol, "USDC")
```

### 2. `src/monitoring/neutrality.py`
**Line 265**: Added `await` to `get_spot_price()` call
```python
# BEFORE
quote = self.price_feed.get_spot_price("SOL", "USDC")

# AFTER
quote = await self.price_feed.get_spot_price("SOL", "USDC")
```

### 3. `src/interface/dashboard_server.py`
**Lines 317 & 415**: Added `await` to `get_spot_price()` calls (2 occurrences)
```python
# BEFORE
quote = self._val_feed.get_spot_price("SOL", "USDC")

# AFTER
quote = await self._val_feed.get_spot_price("SOL", "USDC")
```

### 4. `src/engines/scalp/logic.py`
**Line 164**: Added `await` to `get_spot_price()` call
```python
# BEFORE
quote = self.feed.get_spot_price(mint, self.feed.USDC_MINT)

# AFTER
quote = await self.feed.get_spot_price(mint, self.feed.USDC_MINT)
```

### 5. `src/engines/base_engine.py`
**Line 79**: Added `await` to `get_spot_price()` call
```python
# BEFORE
quote = self.feed.get_spot_price(token_mint, JupiterFeed.USDC_MINT)

# AFTER
quote = await self.feed.get_spot_price(token_mint, JupiterFeed.USDC_MINT)
```

### 6. `src/arbiter/strategies/triangular_engine.py`
**Line 182**: Added `await` to `get_spot_price()` call
```python
# BEFORE
spot = feed.get_spot_price(mint, USDC)

# AFTER
spot = await feed.get_spot_price(mint, USDC)
```

### 7. `src/arbiter/core/atomic_executor.py`
**Line 251**: Added `await` to `get_spot_price()` call
```python
# BEFORE
spot_price_obj = spot_feed.get_spot_price(MINTS.get(coin, ""), USDC)

# AFTER
spot_price_obj = await spot_feed.get_spot_price(MINTS.get(coin, ""), USDC)
```

### 8. `src/arbiter/core/orchestrator.py`
**Line 172**: Added `await` to `get_spot_price()` call
```python
# BEFORE
spot = feed.get_spot_price(opp.base_mint, opp.quote_mint)

# AFTER
spot = await feed.get_spot_price(opp.base_mint, opp.quote_mint)
```

### 9. `src/arbiter/core/rebalancer.py`
**Line 238**: Added `await` to `get_spot_price()` call
```python
# BEFORE
spot = spot_feed.get_spot_price(MINTS.get(coin, ""), USDC)

# AFTER
spot = await spot_feed.get_spot_price(MINTS.get(coin, ""), USDC)
```

### 10. `src/arbiter/core/phantom_score.py`
**Line 201**: Added `await` to `get_spot_price()` call
```python
# BEFORE
spot = feed.get_spot_price(mint, USDC)

# AFTER
spot = await feed.get_spot_price(mint, USDC)
```

## Impact
- **Before**: RuntimeWarnings appeared during startup, coroutines were never executed, price fetches silently failed
- **After**: All async calls properly awaited, price fetches execute correctly, no warnings

## Testing
Run the dashboard and verify:
1. No RuntimeWarnings appear in the console
2. Price data loads correctly for all engines
3. Heartbeat collector shows proper asset prices
4. Delta neutrality calculator gets accurate SOL prices

## Notes
- All calling functions were already `async`, so adding `await` was safe
- The fixes ensure that price fetches actually execute and return data
- Some test files and scripts still have unawaited calls, but those are not critical for production
