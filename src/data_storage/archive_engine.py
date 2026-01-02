"""
Archive Engine - JSONL Delta Storage.

Git-friendly append-only storage for delta blocks.
"""

from __future__ import annotations

import gzip
import json
import os
import time
from datetime import datetime
from typing import List, Optional, Iterator

from src.data_storage.trend_engine import DeltaBlock


class ArchiveEngine:
    """
    JSONL archive for delta blocks.
    
    Features:
    - Append-only JSONL format (Git-diff friendly)
    - Session rotation
    - Optional compression for old files
    """
    
    DEFAULT_DIR = "archives/deltas"
    
    def __init__(self, archive_dir: Optional[str] = None) -> None:
        self.archive_dir = archive_dir or self.DEFAULT_DIR
        self._current_file: Optional[str] = None
        self._handle = None
        self._deltas_written = 0
        self._session_start = time.time()
        
        os.makedirs(self.archive_dir, exist_ok=True)
    
    def get_current_session_path(self) -> str:
        """Get or create current session file path."""
        if self._current_file is None:
            dt = datetime.now()
            filename = f"deltas_{dt.strftime('%Y%m%d_%H%M%S')}.jsonl"
            self._current_file = os.path.join(self.archive_dir, filename)
        return self._current_file
    
    def append_delta(self, delta: DeltaBlock) -> None:
        """Append a single delta block to current session."""
        path = self.get_current_session_path()
        
        with open(path, "a") as f:
            f.write(delta.to_jsonl() + "\n")
        
        self._deltas_written += 1
    
    def append_deltas(self, deltas: List[DeltaBlock]) -> int:
        """Append multiple delta blocks. Returns count written."""
        if not deltas:
            return 0
        
        path = self.get_current_session_path()
        
        with open(path, "a") as f:
            for delta in deltas:
                f.write(delta.to_jsonl() + "\n")
        
        self._deltas_written += len(deltas)
        return len(deltas)
    
    def rotate_session(self) -> str:
        """
        Close current session and start a new one.
        
        Returns path to closed session file.
        """
        old_file = self._current_file
        self._current_file = None
        self._session_start = time.time()
        return old_file or ""
    
    def read_deltas(self, path: str) -> Iterator[DeltaBlock]:
        """Read delta blocks from a JSONL file."""
        if path.endswith(".gz"):
            opener = gzip.open
            mode = "rt"
        else:
            opener = open
            mode = "r"
        
        with opener(path, mode) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        yield DeltaBlock.from_jsonl(line)
                    except Exception:
                        continue
    
    def read_deltas_since(
        self, 
        since_timestamp: float,
        since_sequence: int = 0,
    ) -> Iterator[DeltaBlock]:
        """
        Read all deltas since a given timestamp/sequence.
        
        Scans all delta files and yields matching blocks.
        """
        files = self.list_delta_files()
        
        for filename in files:
            path = os.path.join(self.archive_dir, filename)
            for delta in self.read_deltas(path):
                if delta.timestamp >= since_timestamp and delta.sequence > since_sequence:
                    yield delta
    
    def list_delta_files(self) -> List[str]:
        """List all delta files in chronological order."""
        try:
            files = [
                f for f in os.listdir(self.archive_dir)
                if f.startswith("deltas_") and (f.endswith(".jsonl") or f.endswith(".jsonl.gz"))
            ]
            return sorted(files)
        except Exception:
            return []
    
    def compress_old_files(self, max_age_hours: float = 24.0) -> int:
        """
        Compress old delta files with gzip.
        
        Returns count of files compressed.
        """
        cutoff = time.time() - (max_age_hours * 3600)
        compressed = 0
        
        for filename in self.list_delta_files():
            if filename.endswith(".gz"):
                continue  # Already compressed
            
            path = os.path.join(self.archive_dir, filename)
            
            try:
                mtime = os.path.getmtime(path)
                if mtime < cutoff:
                    # Compress
                    with open(path, "rb") as f_in:
                        with gzip.open(path + ".gz", "wb") as f_out:
                            f_out.write(f_in.read())
                    
                    os.remove(path)
                    compressed += 1
            except Exception:
                continue
        
        return compressed
    
    def get_stats(self) -> dict:
        """Get archive statistics."""
        files = self.list_delta_files()
        
        total_size = 0
        for f in files:
            try:
                path = os.path.join(self.archive_dir, f)
                total_size += os.path.getsize(path)
            except Exception:
                pass
        
        return {
            "archive_dir": self.archive_dir,
            "file_count": len(files),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "deltas_this_session": self._deltas_written,
            "current_file": self._current_file,
        }


# Global instance
_engine: Optional[ArchiveEngine] = None


def get_archive_engine() -> ArchiveEngine:
    """Get or create the global ArchiveEngine instance."""
    global _engine
    if _engine is None:
        _engine = ArchiveEngine()
    return _engine
