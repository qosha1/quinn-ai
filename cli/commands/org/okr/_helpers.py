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

# Tokens that indicate the OKR author is shipping a placeholder, not a
# concrete outcome. Refusing these at the CLI surface forces the CEO to
# resolve ambiguity (ask clarifying questions of the requester) BEFORE
# work spins up against an unclear target.
_PLACEHOLDER_TOKENS = ("TBD", "TODO", "FIXME", "PLACEHOLDER", "TBA", "<TODO>", "XXX")


def _parse_kr_flag(s: str) -> "KeyResult":
    """Parse a --kr 'metric:target:unit' value into a KeyResult.

    Lazy-import KeyResult so this module stays light at top-level.
    """
    from cli.core.queries.okr import KeyResult

    parts = s.split(":")
    if len(parts) != 3:
        raise click.ClickException(
            f"--kr must be 'metric:target:unit' (got {s!r}).\n"
            "Example: --kr 'test_coverage:80:percent'"
        )
    metric_raw, target_raw, unit_raw = parts
    metric = metric_raw.strip()
    unit = unit_raw.strip()
    if not metric or not unit:
        raise click.ClickException(
            f"--kr metric and unit must be non-empty (got {s!r})."
        )
    try:
        target = float(target_raw.strip())
    except ValueError:
        raise click.ClickException(
            f"--kr target must be numeric (got {target_raw.strip()!r}).\n"
            "Example: --kr 'test_coverage:80:percent'"
        )
    return KeyResult(metric=metric, target=target, unit=unit, current=0.0)


def _validate_okr_inputs(
    title: str,
    description: Optional[str],
    key_results: list,
    no_krs_needed: bool,
) -> None:
    """Refuse OKRs that are too vague to act on.

    Implements the schema-level guardrail (quinn-ai-XXX) so the CEO can't
    ship a goal without measurable success criteria, can't ship a title
    that is itself a placeholder, and can't bury 'TODO' / 'TBD' content
    in the description and call it specced.

    Workers downstream rely on the OKR being concrete; the system itself
    enforces that contract here rather than hoping the LLM will.
    """
    # Title placeholder check (case-insensitive token match — we want to
    # catch 'TBD title here' but not legitimate prose containing 'todo' as
    # a substring of e.g. 'todoist'; tokenize on word boundaries).
    title_tokens = {t.upper().strip(",.:;!?()[]{}\"'") for t in title.split()}
    bad_in_title = title_tokens & set(_PLACEHOLDER_TOKENS)
    if bad_in_title:
        raise click.ClickException(
            f"OKR title contains placeholder text: {sorted(bad_in_title)}.\n"
            "An OKR title must name a concrete outcome. Resolve the ambiguity\n"
            "(ask the requester what this is actually about) before filing."
        )

    if description:
        desc_tokens = {
            t.upper().strip(",.:;!?()[]{}\"'") for t in description.split()
        }
        bad_in_desc = desc_tokens & set(_PLACEHOLDER_TOKENS)
        if bad_in_desc:
            raise click.ClickException(
                f"OKR description contains placeholder text: {sorted(bad_in_desc)}.\n"
                "OKR descriptions must describe a concrete outcome, not a\n"
                "promise to fill in details later. Ask clarifying questions\n"
                "of the requester before filing."
            )

    if not no_krs_needed:
        if not key_results:
            raise click.ClickException(
                "OKR has no measurable key results.\n\n"
                "An OKR without quantifiable KRs is just a vibe. Pass at least one:\n"
                "    --kr 'metric:target:unit'    "
                "(e.g. --kr 'test_coverage:80:percent')\n\n"
                "If this OKR is genuinely exploratory and you cannot yet quantify\n"
                "success, pass --no-krs-needed and file a follow-up to revisit\n"
                "once you have enough information to set real KRs."
            )
        for kr in key_results:
            if not kr.metric or not kr.unit:
                raise click.ClickException(
                    f"KR has empty metric or unit (metric={kr.metric!r}, "
                    f"unit={kr.unit!r}). Both must be set."
                )


def _create_okr(
    ctx: Context,
    title: str,
    description: Optional[str],
    owner: str,
    priority: str,
    label: tuple,
    due: Optional[str],
    parent: Optional[str],
    key_results: Optional[list] = None,
    no_krs_needed: bool = False,
):
    """Shared implementation for the set/add subcommands."""
    from cli.core.queries import create_okr, get_worker_by_name

    key_results = key_results or []
    _validate_okr_inputs(title, description, key_results, no_krs_needed)

    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    # Resolve owner name → worker_id BEFORE bd create. Without this,
    # bd stores assignee as the literal name (e.g. "Cleo") while
    # downstream tooling (board health check, bd list --assignee, etc.)
    # queries by worker_id and finds nothing — surfaces as the
    # no_okrs false-positive (quinn-ai-uk9v). Fall through to the raw
    # owner string only if resolution fails (preserves existing
    # behaviour for unrecognised owners).
    bd_assignee: Optional[str] = owner
    if owner:
        try:
            _db_for_resolve = open_database(db_path)
            try:
                resolved = _resolve_owner_id(_db_for_resolve, owner)
                if resolved:
                    bd_assignee = resolved
            finally:
                _db_for_resolve.close()
        except sqlite3.Error:
            pass  # leave bd_assignee = owner; SQLite mirror step below logs.

    args = ["create", title, f"--type={BEAD_TYPE_EPIC}", f"--priority={priority}", "--label=okr"]
    if description:
        args.extend(["--description", description])
    if bd_assignee:
        args.extend(["--assignee", bd_assignee])
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

    # Extract created ID from "✓ Created issue: <id> — <title>" output.
    # Use the token immediately after "issue:" to avoid matching dates or
    # hyphenated words from the title (e.g. "2026-06-30", "AI/dev-tools").
    okr_id = None
    for line in output.split("\n"):
        if "issue:" in line.lower():
            parts = line.split("issue:", 1)
            if len(parts) == 2:
                # First whitespace-delimited token after "issue:"
                candidate = parts[1].strip().split()[0].rstrip("—").strip()
                if candidate:
                    okr_id = candidate
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
                    key_results=key_results or None,
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
