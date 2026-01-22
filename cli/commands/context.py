"""
CLI context shared across all commands.
"""

from pathlib import Path
from typing import Optional

import click

from cli.core.db import open_database, get_org_db_path


class Context:
    """CLI context holding shared state."""

    def __init__(self, org_path: Optional[Path] = None):
        self.org_path = org_path
        self._db = None

    @property
    def db(self):
        """Get database connection (lazy load)."""
        if self._db is None:
            if self.org_path is None:
                raise click.ClickException("No org path specified")
            db_path = get_org_db_path(self.org_path)
            if not db_path.exists():
                raise click.ClickException(
                    f"Org not initialized: {self.org_path}"
                )
            self._db = open_database(db_path)
        return self._db

    def close(self):
        """Close database connection."""
        if self._db is not None:
            self._db.close()
            self._db = None


pass_context = click.make_pass_decorator(Context, ensure=True)
