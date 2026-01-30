"""Context object for msgr commands."""

from pathlib import Path
from typing import Optional

import click

from core.db import Database


class MsgrContext:
    """Context object for msgr commands.

    Provides database connection and worker identity to commands.
    """

    def __init__(self, org_path: Path, worker_id: Optional[str] = None):
        self.org_path = org_path
        self.worker_id = worker_id
        self._db: Optional[Database] = None

    @property
    def db(self) -> Database:
        """Get database connection (lazy init)."""
        if self._db is None:
            db_path = self.org_path / "live" / "quinn.db"
            self._db = Database(str(db_path))
        return self._db

    def close(self):
        """Close database connection."""
        if self._db is not None:
            self._db.close()
            self._db = None


# Pass context decorator
pass_context = click.make_pass_decorator(MsgrContext)
