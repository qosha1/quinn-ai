"""
CLI context shared across all commands.

Follows "No Config Discovery" principle - all values are passed explicitly
through CLI options, which may use envvar as a convenience but the flow
is still explicit (CLI option -> Context -> command).
"""

from pathlib import Path
from typing import Optional

import click

from cli.core.db import open_database, get_org_db_path


class Context:
    """CLI context holding shared state.

    Values are set from CLI options (which may use envvar), not from
    direct environment variable reads in command implementations.
    """

    def __init__(
        self,
        org_path: Optional[Path] = None,
        worker_id: Optional[str] = None,
    ):
        self.org_path = org_path
        self.worker_id = worker_id
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
