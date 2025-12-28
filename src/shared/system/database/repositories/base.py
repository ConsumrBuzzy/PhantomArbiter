from typing import List, Dict, Any, Optional
from src.shared.system.database.core import DatabaseCore
from src.shared.system.logging import Logger

class BaseRepository:
    """
    Base class for Domain-Specific Repositories.
    Provides easy access to the DB Core cursor and common helpers.
    """
    def __init__(self, db: DatabaseCore):
        self.db = db

    def _execute(self, query: str, params: tuple = (), commit: bool = False) -> None:
        """Helper for fire-and-forget queries."""
        with self.db.cursor(commit=commit) as c:
            c.execute(query, params)

    def _fetchone(self, query: str, params: tuple = ()) -> Optional[dict]:
        """Helper to fetch a single row as a dict."""
        with self.db.cursor() as c:
            c.execute(query, params)
            row = c.fetchone()
            return dict(row) if row else None

    def _fetchall(self, query: str, params: tuple = ()) -> List[dict]:
        """Helper to fetch multiple rows."""
        with self.db.cursor() as c:
            c.execute(query, params)
            return [dict(row) for row in c.fetchall()]

    def init_table(self):
        """Override this to create tables."""
        raise NotImplementedError
