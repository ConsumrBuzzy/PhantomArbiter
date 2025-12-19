# PhantomTrader Troubleshooting

Common issues and their solutions.

---

## Quick Diagnostics

```bash
# Test wallet connection
python test_connection.py

# Test Jupiter API
python test_jupiter.py

# Check portfolio status
python main.py --status
```

---

## Connection Issues

### "No private key - Monitor mode only"

**Cause:** `SOLANA_PRIVATE_KEY` not set in `.env`

**Solution:**
```ini
# .env
SOLANA_PRIVATE_KEY=your_base58_private_key
```

Make sure the key is the **base58** encoded private key (not the public key).

---

### "RPC connection failed"

**Cause:** Rate limiting or RPC endpoint down

**Solutions:**

1. **Add more RPC endpoints** to `config/rpc_pool.json`:
```json
{
  "endpoints": [
    {"url": "https://your-quicknode.com", "weight": 10},
    {"url": "https://your-helius.com", "weight": 5}
  ]
}
```

2. **Check endpoint status** at:
   - [Solana Status](https://status.solana.com/)
   - [Helius Status](https://status.helius.xyz/)

3. **Increase timeout** in `src/system/rpc_pool.py`

---

### "Tier 1 blacklisted for 2 hours"

**Cause:** Multiple RPC failures triggered auto-blacklist

**Solution:** Wait for cooldown or add more endpoints. The system will automatically fall back to Tier 2 (DexScreener).

---

## Trading Issues

### "TRADING DISABLED"

**Cause:** Bot is in Monitor mode

**Solution:**
```bash
python main.py --live --scalper
```

Or via Telegram: `/live`

---

### "All slippage tiers exhausted"

**Cause:** Market too volatile or low liquidity

**Solutions:**

1. **Increase slippage tolerance** in `config/settings.py`:
```python
ADAPTIVE_SLIPPAGE_TIERS = [100, 300, 500, 1000, 1500]  # Added 15%
```

2. **Check token liquidity** - may be too low
3. **Wait for market stability**

---

### "Stop-Loss triggered immediately"

**Cause:** Slippage caused entry price to be worse than expected

**Solutions:**

1. **Increase minimum position size** to reduce relative slippage impact
2. **Trade more liquid tokens** (check `MIN_LIQUIDITY_USD`)
3. **Adjust stop-loss** to account for slippage:
```python
STOP_LOSS_PCT = -0.05  # Wider stop
```

---

### "TSL not activating"

**Cause:** Price never reached activation threshold

**Check:**
```python
TSL_ACTIVATION_PCT = 0.020  # +2% required
```

The position must reach +2% profit before TSL activates.

---

### "Position stuck / Zombie bag"

**Cause:** Position recorded but trade failed

**Solutions:**

1. **Check actual wallet** for token balance
2. **Force reconciliation:**
```bash
python main.py --status  # Triggers reconciliation
```

3. **Manual cleanup** in `config/capital_state.json`

---

## Data Issues

### "RSI shows 50.0 for all tokens"

**Cause:** Insufficient price history

**Solutions:**

1. **Wait for backfill** - takes ~5 min at startup
2. **Check CoinGecko API key** for rate limits
3. **Verify `coingecko_id`** in `data/watchlist.json`

---

### "Prices not updating"

**Cause:** Data broker not running or cache stale

**Check:**
```bash
# View cache status
python -c "from src.core.shared_cache import SharedPriceCache; print(SharedPriceCache.get_broker_status())"
```

**Solutions:**

1. **Restart data broker** in separate terminal:
```bash
python data_broker.py
```

2. **Check for lock file issues** - delete `data/.price_cache.lock`

---

### "WinError 5: Access Denied" (Windows)

**Cause:** File lock contention on Windows

**Solution:** Already handled in `SharedPriceCache._write_raw()` with retry logic. If persistent:

1. Close other instances of the bot
2. Delete lock files:
```bash
del data\.price_cache.lock
del .wallet.lock
```

---

## Configuration Issues

### "Failed to load assets.json"

**Cause:** Invalid JSON syntax

**Solution:**
1. Validate JSON at [jsonlint.com](https://jsonlint.com/)
2. Check `data/watchlist.json` for:
   - Missing commas
   - Trailing commas
   - Unclosed brackets

---

### "Token not found in watchlist"

**Cause:** Token not added to `data/watchlist.json`

**Solution:**
```json
{
  "assets": {
    "NEW_TOKEN": {
      "mint": "TOKEN_MINT_ADDRESS",
      "category": "SCOUT",
      "trading_enabled": false
    }
  }
}
```

---

## Database Issues

### "Database locked"

**Cause:** Multiple processes accessing SQLite

**Solutions:**

1. **Stop all bot instances** then restart one
2. **Increase timeout** in `src/system/db_manager.py`:
```python
conn.execute("PRAGMA busy_timeout = 30000")  # 30 seconds
```

---

### "No trades in history"

**Cause:** Monitor mode doesn't log to main DB

**Note:** Paper trades are tracked in `config/capital_state.json`, not `data/trading_journal.db`.

---

## Token Validation Issues

### "Token failed validation"

**Cause:** Safety checks failed

**Check validation result:**
```python
from src.core.validator import TokenValidator
validator = TokenValidator()
result = validator.validate("MINT_ADDRESS", "SYMBOL")
print(result)
```

**Common failures:**
| Reason | Meaning |
|--------|---------|
| Mint authority active | Developer can print tokens |
| Freeze authority active | Developer can freeze wallets |
| Honeypot detected | Token unsellable |
| Low liquidity | < $100K TVL |
| High concentration | Top 10 wallets hold > 30% |

---

## Performance Issues

### "Tick loop falling behind"

**Cause:** Too many assets or slow RPC

**Solutions:**

1. **Reduce active assets** to ≤10
2. **Increase tick interval** with lower frequency
3. **Use faster RPC endpoints**
4. **Enable `SILENT_MODE`** for less logging

---

### "Memory usage growing"

**Cause:** Price history not being pruned

**Solution:** History is limited to 100 points. If still growing:
```python
# Check history length
from src.core.shared_cache import SharedPriceCache
cache = SharedPriceCache._read_raw()
for sym, data in cache.get("prices", {}).items():
    print(f"{sym}: {len(data.get('history', []))} points")
```

---

## Telegram Issues

### "Bot not responding"

**Causes:**
1. Bot token invalid
2. Chat ID mismatch
3. Bot not started

**Solutions:**

1. **Verify token** with BotFather
2. **Check chat ID** matches `.env`
3. **Send `/start`** to your bot first

---

### "Commands ignored"

**Cause:** Security validation rejecting commands

**Check:** Ensure `TELEGRAM_CHAT_ID` in `.env` matches your actual chat ID.

---

## Logs & Debugging

### Enable Debug Mode

```python
# config/settings.py
SILENT_MODE = False  # Enable verbose logging
```

### View Logs

Logs are printed to stdout. For file logging:
```bash
python main.py --monitor 2>&1 | tee bot.log
```

### Diagnostic Output

Check `diagnostic_output.txt` for startup diagnostics.

---

## Getting Help

1. **Check logs** for error messages
2. **Review this document** for known issues
3. **Check GitHub Issues** for similar problems
4. **Create detailed issue** with:
   - Python version
   - Error message
   - Steps to reproduce
   - Relevant config (sans secrets)
