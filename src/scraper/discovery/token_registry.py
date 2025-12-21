"""
V54.0: Token Registry
=====================
Persistent registry for known tokens.
Maps Mint Address -> Metadata (Name, Symbol, URI).

Persists to: data/token_registry.json
"""

import os
import json
import time
from typing import Dict, Optional, Any
from dataclasses import dataclass, asdict

from src.shared.system.logging import Logger
from config.settings import Settings

@dataclass
class TokenMetadata:
    mint: str
    name: str
    symbol: str
    uri: str = ""
    timestamp: float = 0.0
    platform: str = "unknown"

class TokenRegistry:
    """
    Persistent registry for token metadata.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TokenRegistry, cls).__new__(cls)
            cls._instance._init()
        return cls._instance
    
    def _init(self):
        self.registry: Dict[str, TokenMetadata] = {}
        self.file_path = os.path.join(os.getcwd(), "data", "token_registry.json")
        self._ensure_data_dir()
        self._load_registry()
        
    def _ensure_data_dir(self):
        """Ensure data directory exists."""
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        
    def _load_registry(self):
        """Load registry from disk."""
        if not os.path.exists(self.file_path):
            return
            
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for mint, meta in data.items():
                    self.registry[mint] = TokenMetadata(**meta)
            Logger.info(f"   🏷️ [REGISTRY] Loaded {len(self.registry)} tokens")
        except Exception as e:
            Logger.error(f"   ❌ [REGISTRY] Load failed: {e}")
            
    def save_registry(self):
        """Save registry to disk."""
        try:
            data = {mint: asdict(meta) for mint, meta in self.registry.items()}
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            Logger.error(f"   ❌ [REGISTRY] Save failed: {e}")

    def register_token(self, mint: str, name: str, symbol: str, uri: str = "", platform: str = "unknown") -> TokenMetadata:
        """
        Register a new token. Updates if exists.
        
        Args:
            mint: Token CA
            name: Token Name
            symbol: Token Symbol
            uri: Metadata URI
            platform: Launch platform
        """
        if not mint:
            return None
            
        # Normalize
        symbol = symbol.upper().strip()
        name = name.strip()
        
        meta = TokenMetadata(
            mint=mint,
            name=name,
            symbol=symbol,
            uri=uri,
            timestamp=time.time(),
            platform=platform
        )
        
        self.registry[mint] = meta
        self.save_registry()
        return meta
        
    def get_token(self, mint: str) -> Optional[TokenMetadata]:
        """Get token metadata by mint."""
        return self.registry.get(mint)
        
    def is_known(self, mint: str) -> bool:
        """Check if token is already registered."""
        return mint in self.registry

# Singleton Accessor
def get_token_registry() -> TokenRegistry:
    return TokenRegistry()
