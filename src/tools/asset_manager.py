"""
Asset Manager Module
====================
Programmatic control of watchlist.json for adding, promoting, and demoting tokens.
V9.7: Unified to use data/watchlist.json (same as settings.py)
"""

import json
import os
import time
from config.settings import Settings


class AssetManager:
    """Manages watchlist.json for automated token lifecycle management."""
    
    CATEGORY_ORDER = ["WATCH", "SCOUT", "VOLATILE", "ACTIVE"]
    
    def __init__(self):
        # V9.7: Use data/watchlist.json (unified with settings.py)
        self.assets_file = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../data/watchlist.json")
        )
        self.assets = self._load_assets()
    
    def _load_assets(self) -> dict:
        """Load current assets.json."""
        try:
            with open(self.assets_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"   ⚠️ Failed to load assets.json: {e}")
            return {"assets": {}}

    def reload(self):
        """Reload assets from disk usage."""
        self.assets = self._load_assets()

    
    def _save_assets(self):
        """Persist assets.json to disk."""
        try:
            with open(self.assets_file, 'w') as f:
                json.dump(self.assets, f, indent=4)
            # Reload Settings to pick up changes
            Settings._reload_assets()
        except Exception as e:
            print(f"   ⚠️ Failed to save assets.json: {e}")
    
    def add_token(self, symbol: str, mint: str, category: str = "WATCH") -> bool:
        """
        Add a new token to assets.json.
        
        Args:
            symbol: Token symbol
            mint: Mint address
            category: Initial category (default WATCH)
            
        Returns:
            True if added, False if already exists
        """
        if symbol in self.assets.get("assets", {}):
            return False  # Already exists
        
        self.assets["assets"][symbol] = {
            "mint": mint,
            "category": category,
            "trading_enabled": False,  # Never auto-enable trading
            "added_at": time.time(),
            "source": "auto_discovery"
        }
        
        self._save_assets()
        print(f"   ✅ Added {symbol} to {category}")
        return True
    
    def promote_token(self, symbol: str, to_category: str) -> bool:
        """
        Promote/demote a token to a new category.
        
        Args:
            symbol: Token symbol
            to_category: Target category
            
        Returns:
            True if changed, False otherwise
        """
        if symbol not in self.assets.get("assets", {}):
            return False
        
        old_category = self.assets["assets"][symbol].get("category", "WATCH")
        
        if old_category == to_category:
            return False
        
        self.assets["assets"][symbol]["category"] = to_category
        self.assets["assets"][symbol]["promoted_at"] = time.time()
        
        # Enable trading only if promoted to ACTIVE
        if to_category == "ACTIVE":
            self.assets["assets"][symbol]["trading_enabled"] = True
        elif to_category in ["WATCH", "SCOUT"]:
            self.assets["assets"][symbol]["trading_enabled"] = False
        
        self._save_assets()
        print(f"   📈 {symbol}: {old_category} → {to_category}")
        return True
    
    def remove_token(self, symbol: str) -> bool:
        """
        Remove a token from assets.json.
        
        Args:
            symbol: Token symbol
            
        Returns:
            True if removed, False if not found
        """
        if symbol not in self.assets.get("assets", {}):
            return False
        
        del self.assets["assets"][symbol]
        self._save_assets()
        print(f"   🗑️ Removed {symbol}")
        return True
    
    def get_tokens_by_category(self, category: str) -> list:
        """Get all tokens in a specific category."""
        tokens = []
        for symbol, data in self.assets.get("assets", {}).items():
            if data.get("category") == category:
                tokens.append({
                    "symbol": symbol,
                    "mint": data.get("mint"),
                    "trading_enabled": data.get("trading_enabled", False)
                })
        return tokens
    
    def get_all_mints(self) -> set:
        """Get set of all known mint addresses."""
        return {
            data.get("mint") 
            for data in self.assets.get("assets", {}).values()
            if data.get("mint")
        }

    def get_all_tokens(self) -> dict:
        """Get all tokens as {symbol: mint}."""
        return {
            symbol: data.get("mint")
            for symbol, data in self.assets.get("assets", {}).items()
            if data.get("mint")
        }
    
    def get_category(self, symbol: str) -> str | None:
        """Get current category for a token."""
        if symbol in self.assets.get("assets", {}):
            return self.assets["assets"][symbol].get("category")
        return None


# Add reload method to Settings if not exists
if not hasattr(Settings, '_reload_assets'):
    @classmethod
    def _reload_assets(cls):
        """Reload assets from disk."""
        try:
            # V9.7: Reload from unified watchlist location
            a, v, w, s, all_a, meta = cls.load_assets()
            cls.ACTIVE_ASSETS = a
            cls.VOLATILE_ASSETS = v
            cls.WATCH_ASSETS = w
            cls.SCOUT_ASSETS = s
            cls.ASSETS = all_a
            cls.ASSET_METADATA = meta
        except Exception as e:
            print(f"⚠️ Failed to reload assets: {e}")
    
    Settings._reload_assets = _reload_assets


# CLI for testing
if __name__ == "__main__":
    manager = AssetManager()
    
    print("📦 ASSET MANAGER - Status")
    print("=" * 40)
    
    for cat in ["ACTIVE", "VOLATILE", "SCOUT", "WATCH"]:
        tokens = manager.get_tokens_by_category(cat)
        print(f"\n{cat}: {len(tokens)} tokens")
        for t in tokens[:5]:
            print(f"   {t['symbol']}: trading={t['trading_enabled']}")
