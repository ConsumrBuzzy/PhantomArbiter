
import os
import json
import glob
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from src.shared.system.db_manager import db_manager
from src.shared.system.logging import Logger

def migrate_trade_history():
    """Import data/trade_history.json into DB."""
    json_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/trade_history.json"))
    
    if not os.path.exists(json_path):
        Logger.info("   ℹ️ No trade_history.json found. Skipping trade migration.")
        return

    try:
        with open(json_path, 'r') as f:
            trades = json.load(f)
            
        count = 0
        for t in trades:
            # Map JSON keys to DB keys if necessary
            # JSON: symbol, entry_price, exit_price, size_usd, pnl_usd, net_pnl_pct, reason, timestamp, is_win
            # DB:   symbol, entry_price, exit_price, size_usd, pnl_usd, net_pnl_pct, exit_reason, timestamp, is_win
            
            trade_data = {
                'symbol': t.get('symbol'),
                'entry_price': t.get('entry_price'),
                'exit_price': t.get('exit_price'),
                'size_usd': t.get('size_usd'),
                'pnl_usd': t.get('pnl_usd'),
                'net_pnl_pct': t.get('net_pnl_pct'),
                'exit_reason': t.get('reason'), # Key change
                'timestamp': t.get('timestamp'), # String ISO format? DB expects REAL (timestamp)?
                'is_win': t.get('is_win')
            }
            
            # Timestamp conversion: DB uses REAL (time.time()), JSON has ISO string
            try:
                import dateutil.parser
                if isinstance(trade_data['timestamp'], str):
                    dt = dateutil.parser.parse(trade_data['timestamp'])
                    trade_data['timestamp'] = dt.timestamp()
            except ImportError:
                 # Fallback if dateutil not installed, try basic
                 pass
            except Exception:
                pass

            # SQLite stores check
            db_manager.log_trade(trade_data)
            count += 1
            
        Logger.success(f"   ✅ Migrated {count} trades to SQLite.")
        
        # Renaissance: Rename old file to .bak
        os.rename(json_path, json_path + ".bak")
        Logger.info("   📦 Archived trade_history.json -> .bak")
        
    except Exception as e:
        Logger.error(f"   ❌ Trade Migration Failed: {e}")

def migrate_positions():
    """Import src/strategy/position_*.json into DB."""
    strategy_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/strategy"))
    files = glob.glob(os.path.join(strategy_dir, "position_*.json"))
    
    if not files:
        Logger.info("   ℹ️ No legacy position files found.")
        return

    count = 0
    for filepath in files:
        try:
            filename = os.path.basename(filepath)
            symbol = filename.replace("position_", "").replace(".json", "")
            
            with open(filepath, 'r') as f:
                data = json.load(f)
                
            # DB expects specific keys. Map if needed.
            # JSON: entry_price, cost_basis, in_position, max_price_achieved, trailing_stop_price
            # DB: same keys
            
            db_manager.save_position(symbol, data)
            count += 1
            
            # Archive
            os.rename(filepath, filepath + ".bak")
            
        except Exception as e:
            Logger.error(f"   ❌ Position Migration Failed ({filename}): {e}")
            
    if count > 0:
        Logger.success(f"   ✅ Migrated {count} active positions.")

if __name__ == "__main__":
    Logger.info("🚀 Starting V10.5 Database Migration...")
    migrate_trade_history()
    migrate_positions()
    Logger.info("✨ Migration Complete.")
