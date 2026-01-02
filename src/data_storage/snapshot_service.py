"""
Snapshot Service - Full State Checkpoints.

Captures and saves complete market state for rehydration.
Implements the "Hard Check" in the Bellows architecture.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime


@dataclass
class TokenSnapshot:
    """Snapshot of a single token's state."""
    mint: str
    symbol: str
    price: float
    volume_24h: float = 0.0
    liquidity: float = 0.0
    price_change_24h: float = 0.0
    last_update: float = 0.0
    source: str = "SNAPSHOT"


@dataclass
class MarketSnapshot:
    """
    Complete market state at a point in time.
    
    The "Keyframe" in video codec terms.
    """
    timestamp: float
    sequence: int  # TrendEngine sequence at capture
    tokens: Dict[str, TokenSnapshot] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_json(self, pretty: bool = False) -> str:
        """Serialize to JSON."""
        data = {
            "timestamp": self.timestamp,
            "sequence": self.sequence,
            "captured_at": datetime.fromtimestamp(self.timestamp).isoformat(),
            "token_count": len(self.tokens),
            "tokens": {
                mint: asdict(token)
                for mint, token in self.tokens.items()
            },
            "metadata": self.metadata,
        }
        if pretty:
            return json.dumps(data, indent=2)
        return json.dumps(data, separators=(",", ":"))
    
    @classmethod
    def from_json(cls, json_str: str) -> "MarketSnapshot":
        """Deserialize from JSON."""
        data = json.loads(json_str)
        tokens = {
            mint: TokenSnapshot(**token_data)
            for mint, token_data in data.get("tokens", {}).items()
        }
        return cls(
            timestamp=data["timestamp"],
            sequence=data.get("sequence", 0),
            tokens=tokens,
            metadata=data.get("metadata", {}),
        )
    
    def save(self, path: str) -> None:
        """Save snapshot to file."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(self.to_json(pretty=True))
    
    @classmethod
    def load(cls, path: str) -> "MarketSnapshot":
        """Load snapshot from file."""
        with open(path, "r") as f:
            return cls.from_json(f.read())


class SnapshotService:
    """
    Manages market state checkpoints.
    
    Features:
    - Periodic checkpoint scheduling
    - On-demand capture
    - Exit-hook for graceful save
    - Checkpoint discovery for rehydration
    """
    
    # Default checkpoint directory
    DEFAULT_DIR = "archives/checkpoints"
    
    # Checkpoint interval (blocks or time)
    CHECKPOINT_INTERVAL_BLOCKS = 1000
    CHECKPOINT_INTERVAL_SECONDS = 3600  # 1 hour
    
    def __init__(
        self,
        checkpoint_dir: Optional[str] = None,
        price_source: Optional[Any] = None,
    ) -> None:
        self.checkpoint_dir = checkpoint_dir or self.DEFAULT_DIR
        self._price_source = price_source  # SharedPriceCache or similar
        
        self._last_checkpoint_time = time.time()
        self._last_checkpoint_seq = 0
        self._checkpoint_count = 0
        
        # Ensure directory exists
        os.makedirs(self.checkpoint_dir, exist_ok=True)
    
    def set_price_source(self, source: Any) -> None:
        """Set the price data source."""
        self._price_source = source
    
    def capture(self, sequence: int = 0) -> MarketSnapshot:
        """
        Capture current market state.
        
        Args:
            sequence: Current TrendEngine sequence number
            
        Returns:
            MarketSnapshot with all current prices
        """
        tokens = {}
        
        # Get prices from source
        if self._price_source:
            try:
                # Try SharedPriceCache interface
                if hasattr(self._price_source, "get_all_prices"):
                    prices = self._price_source.get_all_prices()
                    for symbol, data in prices.items():
                        if isinstance(data, dict):
                            mint = data.get("mint", symbol)
                            tokens[mint] = TokenSnapshot(
                                mint=mint,
                                symbol=symbol,
                                price=data.get("price", 0),
                                volume_24h=data.get("volume_24h", 0),
                                liquidity=data.get("liquidity", 0),
                                last_update=data.get("timestamp", time.time()),
                            )
            except Exception:
                pass
        
        snapshot = MarketSnapshot(
            timestamp=time.time(),
            sequence=sequence,
            tokens=tokens,
            metadata={
                "source": "SnapshotService",
                "version": "1.0",
                "checkpoint_count": self._checkpoint_count + 1,
            },
        )
        
        return snapshot
    
    def save_checkpoint(self, snapshot: MarketSnapshot) -> str:
        """
        Save snapshot as checkpoint file.
        
        Returns path to saved file.
        """
        # Generate filename: cp_YYYYMMDD_HHMMSS.json
        dt = datetime.fromtimestamp(snapshot.timestamp)
        filename = f"cp_{dt.strftime('%Y%m%d_%H%M%S')}.json"
        path = os.path.join(self.checkpoint_dir, filename)
        
        snapshot.save(path)
        
        self._last_checkpoint_time = time.time()
        self._last_checkpoint_seq = snapshot.sequence
        self._checkpoint_count += 1
        
        return path
    
    def should_checkpoint(self, current_seq: int) -> bool:
        """
        Check if we should create a checkpoint.
        
        Triggers:
        - Sequence delta >= CHECKPOINT_INTERVAL_BLOCKS
        - Time delta >= CHECKPOINT_INTERVAL_SECONDS
        """
        seq_delta = current_seq - self._last_checkpoint_seq
        time_delta = time.time() - self._last_checkpoint_time
        
        return (
            seq_delta >= self.CHECKPOINT_INTERVAL_BLOCKS or
            time_delta >= self.CHECKPOINT_INTERVAL_SECONDS
        )
    
    def get_latest_checkpoint(self) -> Optional[MarketSnapshot]:
        """
        Find and load the most recent checkpoint.
        
        Returns None if no checkpoints exist.
        """
        try:
            files = [
                f for f in os.listdir(self.checkpoint_dir)
                if f.startswith("cp_") and f.endswith(".json")
            ]
            
            if not files:
                return None
            
            # Sort by name (which includes timestamp)
            files.sort(reverse=True)
            latest = files[0]
            
            path = os.path.join(self.checkpoint_dir, latest)
            return MarketSnapshot.load(path)
            
        except Exception:
            return None
    
    def list_checkpoints(self) -> List[str]:
        """List all checkpoint files."""
        try:
            files = [
                f for f in os.listdir(self.checkpoint_dir)
                if f.startswith("cp_") and f.endswith(".json")
            ]
            return sorted(files)
        except Exception:
            return []
    
    def get_stats(self) -> Dict:
        """Get service statistics."""
        checkpoints = self.list_checkpoints()
        return {
            "checkpoint_dir": self.checkpoint_dir,
            "checkpoint_count": len(checkpoints),
            "last_checkpoint_time": self._last_checkpoint_time,
            "last_checkpoint_seq": self._last_checkpoint_seq,
            "total_saved": self._checkpoint_count,
        }


# Global instance
_service: Optional[SnapshotService] = None


def get_snapshot_service() -> SnapshotService:
    """Get or create the global SnapshotService instance."""
    global _service
    if _service is None:
        _service = SnapshotService()
    return _service
