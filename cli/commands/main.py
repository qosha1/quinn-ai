"""
QuinnAI CLI entry point.

Provides the `qn` command with org and wrkr subcommand groups.
"""

import os
from pathlib import Path
from typing import Optional

import click

from core.db import open_database, init_database, get_org_db_path


# Context object passed to all commands
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


@click.group()
@click.option(
    "--org-path",
    type=click.Path(exists=False, path_type=Path),
    envvar="QUINN_ORG_PATH",
    help="Path to org folder. Defaults to QUINN_ORG_PATH env var.",
)
@click.pass_context
def qn(ctx, org_path: Optional[Path]):
    """QuinnAI organization management CLI.

    Two command groups for two actors:

    \b
    qn org   - Organization management (human operator)
    qn wrkr  - Worker operations (AI worker in session)
    """
    ctx.ensure_object(Context)
    if org_path:
        ctx.obj.org_path = org_path
    elif ctx.obj.org_path is None:
        # Default to current directory
        ctx.obj.org_path = Path.cwd()


@qn.group()
def org():
    """Manage organization lifecycle.

    Commands for human operators to manage the org.
    """
    pass


@qn.group()
def wrkr():
    """Worker operations.

    Commands for AI workers running in sessions.
    Requires QUINN_WORKER_ID environment variable.
    """
    pass


# Import and register subcommands
from commands.org import init_cmd, start_cmd, stop_cmd, status_cmd

org.add_command(init_cmd, name="init")
org.add_command(start_cmd, name="start")
org.add_command(stop_cmd, name="stop")
org.add_command(status_cmd, name="status")

from commands.wrkr import get_work_cmd, inbox_cmd, send_cmd, status_cmd as wrkr_status_cmd

wrkr.add_command(get_work_cmd, name="get-work")
wrkr.add_command(inbox_cmd, name="inbox")
wrkr.add_command(send_cmd, name="send")
wrkr.add_command(wrkr_status_cmd, name="status")


if __name__ == "__main__":
    qn()
