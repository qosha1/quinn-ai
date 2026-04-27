"""Shared helpers for the qn org okr subcommands.

run_bd is re-exported here so subcommand modules import it from one place.
Tests that previously patched 'cli.commands.org.okr.run_bd' should now
patch 'cli.commands.org.okr._helpers.run_bd'.
"""

import logging
import sqlite3
from typing import Optional

import click

from cli.commands.context import Context
from cli.core.bd_wrapper import run_bd  # noqa: F401 — re-exported
from cli.core.constants import BEAD_TYPE_EPIC
from cli.core.db import get_org_db_path, open_database

_logger = logging.getLogger(__name__)


def _create_okr(
    ctx: Context,
    title: str,
    description: Optional[str],
    owner: str,
    priority: str,
    label: tuple,
    due: Optional[str],
    parent: Optional[str],
):
    """Shared implementation for the set/add subcommands."""
    from cli.core.queries import create_okr, get_worker_by_name

    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    args = ["create", title, f"--type={BEAD_TYPE_EPIC}", f"--priority={priority}", "--label=okr"]
    if description:
        args.extend(["--description", description])
    if owner:
        args.extend(["--assignee", owner])
    for lbl in label:
        args.extend(["--label", lbl])
    if due:
        args.extend(["--due", due])
    if parent:
        args.extend(["--parent", parent])

    result = run_bd(
        args,
        org_path=org_path,
        capture_output=True,
        skip_permission_check=True,
    )

    if result.returncode != 0:
        raise click.ClickException(
            f"Failed to create OKR: {result.stderr}\n"
            "Check beads configuration and try again."
        )

    output = result.stdout.strip()
    click.echo(output)

    # Extract created ID from "Created issue: xxx" output
    okr_id = None
    for line in output.split("\n"):
        if "Created" in line and "-" in line:
            words = line.split()
            for word in reversed(words):
                if "-" in word and not word.startswith("-"):
                    okr_id = word.strip()
                    break
            break

    # Mirror the OKR into the SQLite okrs table for query/progress
    if okr_id:
        db = open_database(db_path)
        try:
            owner_id = _resolve_owner_id(db, owner)
            due_date = _parse_due_date(due)

            if not owner_id:
                _logger.warning(
                    "Could not resolve owner '%s' to a worker. "
                    "Bead was created; skipping SQLite OKR row.",
                    owner,
                )
            else:
                create_okr(
                    db=db,
                    title=title,
                    owner_id=owner_id,
                    parent_id=parent,
                    description=description,
                    status="active",
                    okr_id=okr_id,
                    due_date=due_date,
                )
        except sqlite3.Error as e:
            # SQLite mirror is secondary — don't fail if it errors
            _logger.warning(f"Failed to store OKR in database (ignored): {e}")
        finally:
            db.close()

        click.echo("")
        click.echo("Link work items to this OKR with:")
        click.echo(f"  bd dep add <work-id> {okr_id} --type serves")


def _resolve_owner_id(db, owner: str) -> Optional[str]:
    """Resolve owner name → worker_id.

    Order: by name, then by id, then (special-case) the literal 'ceo' →
    Org.ceo_worker_id. Without this, the SQLite okrs.owner_worker_id FK
    would fail on the literal string 'ceo'.
    """
    from cli.core.queries import get_worker_by_name

    if not owner:
        return None

    worker = get_worker_by_name(db, owner)
    if worker:
        return worker.id

    from cli.core.worker import Worker
    from shared.exceptions import WorkerNotFound

    try:
        return Worker.get(db, owner).id
    except (ValueError, KeyError, WorkerNotFound):
        if owner.lower() == "ceo":
            from cli.core.org import Org

            return Org(db).ceo_worker_id
        return None


def _parse_due_date(due: Optional[str]):
    """Parse a due date — supports +Nd / +Nw / +Nm / +Ny / ISO 8601."""
    if not due:
        return None

    import re
    from datetime import date, timedelta

    if due.startswith("+"):
        match = re.match(r"\+(\d+)([dwmy])", due)
        if match:
            num = int(match.group(1))
            unit = match.group(2)
            today = date.today()
            if unit == "d":
                return today + timedelta(days=num)
            if unit == "w":
                return today + timedelta(weeks=num)
            if unit == "m":
                return date(today.year, today.month + num, today.day)
            if unit == "y":
                return date(today.year + num, today.month, today.day)
        return None

    try:
        return date.fromisoformat(due)
    except ValueError:
        return None
