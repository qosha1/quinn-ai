"""
qn org tail — live activity feed with continuation engine supervision.

Streams org events to stdout (worker state changes, messages, bead updates)
while running the ContinuationEngine in the background so workers get nudged
even when the operator isn't watching. Stays alive until Ctrl+C.

This is the intended way to 'supervise' a running org without attaching to
individual sessions — run it in a background pane or tmux window.
"""

from __future__ import annotations

import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path


_SEVERITY_ICON = {
    "info": "·",
    "warning": "⚠",
    "error": "✗",
    "success": "✓",
}


def _fmt_ts(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%H:%M:%S")
    except Exception:
        return ts[:8] if ts else "??"


def _tail_loop(
    org_path: Path,
    poll_interval: float,
    last_n: int,
    no_color: bool,
    worker_filter: Optional[str],
) -> None:
    db = open_database(get_org_db_path(org_path))

    def clr(code: str, text: str) -> str:
        if no_color:
            return text
        return f"\033[{code}m{text}\033[0m"

    # Seed cursor — show last N events then follow
    rows = db.fetchall(
        """
        SELECT id, worker_id, activity_type, signal_strength, created_at
        FROM activity_signals
        ORDER BY id DESC LIMIT ?
        """,
        (last_n,),
    )
    cursor_id = rows[-1]["id"] if rows else 0

    # Show backfill
    for row in reversed(rows):
        wid = row["worker_id"]
        if worker_filter and not wid.endswith(worker_filter[-8:]):
            continue
        wrow = db.fetchone("SELECT name FROM workers WHERE id=?", (wid,))
        name = wrow["name"] if wrow else wid[:12]
        ts = _fmt_ts(row["created_at"])
        click.echo(f"  {clr('2', ts)}  {clr('36', name):12}  {row['activity_type']}")

    click.echo(clr("2", f"  ── following from id={cursor_id} (Ctrl+C to stop) ──"))

    while True:
        time.sleep(poll_interval)
        try:
            new_rows = db.fetchall(
                """
                SELECT id, worker_id, activity_type, signal_strength, created_at,
                       metadata
                FROM activity_signals WHERE id > ?
                ORDER BY id ASC
                """,
                (cursor_id,),
            )
        except Exception:
            continue

        for row in new_rows:
            cursor_id = row["id"]
            wid = row["worker_id"]
            if worker_filter and not wid.endswith(worker_filter[-8:]):
                continue
            wrow = db.fetchone("SELECT name FROM workers WHERE id=?", (wid,))
            name = wrow["name"] if wrow else wid[:12]
            ts = _fmt_ts(row["created_at"])
            atype = row["activity_type"]
            strength = row["signal_strength"]
            icon = "→" if strength >= 4 else "·"
            click.echo(f"  {clr('2', ts)}  {clr('36', name):12}  {icon} {atype}")

        # Also check for new messages
        try:
            new_msgs = db.fetchall(
                """
                SELECT m.id, m.content, m.from_worker_id, m.created_at,
                       c.name as channel_name
                FROM messages m
                JOIN channels c ON m.channel_id = c.id
                WHERE m.id > (SELECT COALESCE(MAX(id), 0) FROM messages WHERE id <= ?)
                  AND m.id > ?
                ORDER BY m.id ASC LIMIT 20
                """,
                (cursor_id, cursor_id),
            )
        except Exception:
            new_msgs = []

        for msg in new_msgs:
            wrow = db.fetchone(
                "SELECT name FROM workers WHERE id=?", (msg["from_worker_id"],)
            )
            name = wrow["name"] if wrow else (msg["from_worker_id"] or "?")[:12]
            chan = msg["channel_name"] or "?"
            ts = _fmt_ts(msg["created_at"])
            preview = (msg["content"] or "")[:72].replace("\n", " ")
            click.echo(
                f"  {clr('2', ts)}  {clr('35', name):12}  #{chan}: {preview}"
            )


@click.command()
@click.option(
    "--poll", "poll_interval", default=3.0, type=float,
    help="Seconds between polls (default: 3).",
)
@click.option(
    "--last", "last_n", default=20, type=int,
    help="Show last N events before following (default: 20).",
)
@click.option(
    "--worker", "worker_filter", default=None,
    help="Filter to a specific worker (name or partial ID).",
)
@click.option(
    "--no-color", is_flag=True, default=False,
    help="Disable ANSI color output.",
)
@click.option(
    "--no-engine", is_flag=True, default=False,
    help="Disable the background continuation engine (monitor-only mode).",
)
@pass_context
def tail_cmd(
    ctx: Context,
    poll_interval: float,
    last_n: int,
    worker_filter: Optional[str],
    no_color: bool,
    no_engine: bool,
):
    """Stream live org activity and supervise worker continuation.

    Follows activity_signals and messages in real time, printing each event
    as it arrives. Also runs the ContinuationEngine in the background so
    workers are nudged when idle — fixing the 'CEO goes silent after
    delegation' issue (quinn-ai-srwt).

    Run in a background pane while workers operate:

    \b
    Examples:
      qn org tail                        # follow all events
      qn org tail --worker cleo          # filter to CEO only
      qn org tail --no-engine            # monitor-only, no nudges
      qn org tail --last 50 --poll 5     # more history, slower poll
    """
    org_path = ctx.org_path
    if not org_path:
        raise click.ClickException("org_path required (use --org-path or $QUINN_ORG_PATH)")

    engine = None
    if not no_engine:
        try:
            from cli.core.continuation_engine import ContinuationEngine
            from cli.core.constants import CONTINUATION_ENGINE_POLL_INTERVAL
            engine = ContinuationEngine(
                org_path, poll_interval=CONTINUATION_ENGINE_POLL_INTERVAL
            )
            engine.start()
            click.echo(
                f"  ── continuation engine started (nudge interval: "
                f"{CONTINUATION_ENGINE_POLL_INTERVAL}s) ──",
                err=False,
            )
        except Exception as e:
            click.echo(f"Warning: could not start continuation engine: {e}", err=True)

    def _shutdown(sig, frame):
        if engine and engine.is_running():
            engine.stop()
        click.echo("\n  ── tail stopped ──")
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        _tail_loop(org_path, poll_interval, last_n, no_color, worker_filter)
    except Exception as e:
        click.echo(f"\nTail error: {e}", err=True)
    finally:
        if engine and engine.is_running():
            engine.stop()
