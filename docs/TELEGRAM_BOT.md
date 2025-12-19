# PhantomTrader Telegram Bot

Remote control and monitoring via Telegram.

---

## Setup

### 1. Create Bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow prompts
3. Copy the **API Token**

### 2. Get Chat ID

1. Message your bot
2. Visit: `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Find your `chat_id` in the response

### 3. Configure

Add to `.env`:

```ini
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=987654321
```

---

## Commands

### Status Commands

| Command | Description |
|---------|-------------|
| `/status` | Full portfolio status |
| `/balance` | Quick balance check |
| `/positions` | Active positions |
| `/trades` | Recent trade history |
| `/health` | System health check |

### Control Commands

| Command | Description |
|---------|-------------|
| `/start` | Start trading |
| `/stop` | Stop trading (pause) |
| `/live` | Enable live mode |
| `/monitor` | Switch to monitor mode |

### Configuration Commands

| Command | Description |
|---------|-------------|
| `/set size <USD>` | Set position size |
| `/set budget <USD>` | Set total budget |
| `/set mode <MODE>` | Set strategy mode |

### Asset Commands

| Command | Description |
|---------|-------------|
| `/add <SYMBOL> <MINT>` | Add token to watchlist |
| `/remove <SYMBOL>` | Remove token |
| `/enable <SYMBOL>` | Enable trading for token |
| `/disable <SYMBOL>` | Disable trading for token |

### Advanced Commands

| Command | Description |
|---------|-------------|
| `/force_sell <SYMBOL>` | Force sell position |
| `/train` | Trigger ML model training |
| `/reload` | Reload configuration |

---

## Example Usage

```
You: /status

PhantomTrader:
📊 PORTFOLIO STATUS
━━━━━━━━━━━━━━━━━━━━━
💰 Cash: $47.25
⛽ Gas: 0.0234 SOL
📈 Positions: 2

ACTIVE POSITIONS:
┌──────────┬──────────┬──────────┐
│ Symbol   │ PnL      │ Entry    │
├──────────┼──────────┼──────────┤
│ WIF      │ +2.3%    │ $2.45    │
│ BONK     │ -0.5%    │ $0.00002 │
└──────────┴──────────┴──────────┘

Mode: MONITOR | Strategy: SCALPER
```

---

## Alert Types

### Trade Alerts

```
✅ BUY WIF @ $2.45
   Size: $4.00
   RSI: 28.5
   Reason: RSI Oversold
```

```
🎯 SELL WIF @ $2.55 (+4.1%)
   PnL: +$0.16
   Reason: Take Profit
```

### Risk Alerts

```
⚠️ TSL Activated for WIF
   Max Price: $2.60
   Stop: $2.56
```

```
🚨 DAILY DRAWDOWN LIMIT
   Loss: -5.2%
   Action: Trading paused 24h
```

### System Alerts

```
⛽ GAS LOW
   SOL Balance: 0.003
   Action: Auto-refuel triggered
```

```
📡 RPC Failover
   Tier 1 blacklisted
   Fallback: DexScreener
```

---

## Architecture

**File:** `src/system/telegram_listener.py`

```python
class TelegramListener:
    """
    Async Telegram bot for remote control.
    Runs in separate thread from main bot.
    """
    
    def __init__(self, command_queue: Queue):
        self.queue = command_queue
        self.bot = Application.builder().token(TOKEN).build()
        self._register_handlers()
    
    def _register_handlers(self):
        self.bot.add_handler(CommandHandler("status", self.cmd_status))
        self.bot.add_handler(CommandHandler("start", self.cmd_start))
        # ... more handlers
    
    async def cmd_status(self, update, context):
        """Handle /status command."""
        status = self._get_portfolio_status()
        await update.message.reply_text(status)
    
    async def cmd_start(self, update, context):
        """Handle /start command."""
        self.queue.put({"type": "SET_MODE", "value": "LIVE"})
        await update.message.reply_text("🟢 Trading enabled")
```

---

## Command Processing

**File:** `src/system/command_processor.py`

Commands are processed asynchronously:

```python
class CommandProcessor:
    """Processes commands from Telegram queue."""
    
    def process(self, command: dict):
        cmd_type = command.get("type")
        
        if cmd_type == CMD_SET_MODE:
            self._handle_set_mode(command["value"])
        elif cmd_type == CMD_SET_SIZE:
            self._handle_set_size(command["value"])
        elif cmd_type == CMD_FORCE_SELL:
            self._handle_force_sell(command["symbol"])
```

---

## Notification Settings

Configure alert policies in `config/settings.py`:

```python
ALERT_POLICIES = {
    "ENGINE_DRAWDOWN_BREACH_PCT": 0.05,  # Alert at 5% drawdown
    "ALERT_COOLDOWN_SECONDS": 300,        # 5 min between alerts
}
```

---

## Security Notes

1. **Bot Token**: Keep secret, allows full bot control
2. **Chat ID**: Restricts who can send commands
3. **Rate Limits**: Telegram limits ~30 msg/sec
4. **Validation**: All commands validated before execution

```python
def _validate_sender(self, chat_id: int) -> bool:
    """Only allow commands from configured chat."""
    return str(chat_id) == os.getenv("TELEGRAM_CHAT_ID")
```
