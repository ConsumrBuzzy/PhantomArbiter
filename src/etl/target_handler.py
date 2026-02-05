import sqlite3
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class Target:
    id: int
    url: str
    status: str
    priority: int
    last_scraped: Optional[datetime]
    retry_count: int

class TargetHandler:
    def __init__(self, db_path: str = "targets.db"):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        """Initialize the SQLite database with the targets schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                status TEXT DEFAULT 'pending', -- pending, processing, completed, failed
                priority INTEGER DEFAULT 1,
                last_scraped TIMESTAMP,
                retry_count INTEGER DEFAULT 0,
                meta_data JSON
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_status_priority 
            ON targets(status, priority DESC)
        ''')
        conn.commit()
        conn.close()
        logger.info(f"Initialized Target DB at {self.db_path}")

    def add_target(self, url: str, priority: int = 1) -> bool:
        """Add a new target URL to the queue."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO targets (url, priority, status)
                VALUES (?, ?, 'pending')
            ''', (url, priority))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Failed to add target {url}: {e}")
            return False

    def get_next_target(self) -> Optional[Target]:
        """Fetch the next pending target with highest priority."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            # Select next target
            cursor.execute('''
                SELECT id, url, status, priority, last_scraped, retry_count
                FROM targets
                WHERE status = 'pending'
                ORDER BY priority DESC, id ASC
                LIMIT 1
            ''')
            row = cursor.fetchone()
            
            if row:
                # Mark as processing
                target_id = row[0]
                cursor.execute("UPDATE targets SET status = 'processing' WHERE id = ?", (target_id,))
                conn.commit()
                conn.close()
                return Target(
                    id=row[0],
                    url=row[1],
                    status=row[2],
                    priority=row[3],
                    last_scraped=row[4],
                    retry_count=row[5]
                )
            conn.close()
            return None
        except Exception as e:
            logger.error(f"Failed to get next target: {e}")
            return None

    def update_status(self, target_id: int, status: str, retry_increment: bool = False):
        """Update the status of a target (e.g., completed, failed)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        timestamp = datetime.now() if status == 'completed' else None
        retry_sql = "retry_count = retry_count + 1," if retry_increment else ""
        
        cursor.execute(f'''
            UPDATE targets 
            SET status = ?, 
                {retry_sql}
                last_scraped = COALESCE(?, last_scraped)
            WHERE id = ?
        ''', (status, timestamp, target_id))
        conn.commit()
        conn.close()

if __name__ == "__main__":
    # Test harness
    handler = TargetHandler()
    handler.add_target("https://example.com/profile/123", priority=10)
    target = handler.get_next_target()
    if target:
        print(f"Processing: {target.url}")
        handler.update_status(target.id, "completed")
