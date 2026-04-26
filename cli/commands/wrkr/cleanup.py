"""
qn wrkr cleanup command.

Cleans up stale worker sessions when tmux sessions are dead but database
still has session references.
"""

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.worker import Worker
from cli.core.sessions.binding_manager import get_binding_manager
from cli.core.sessions.persistence import get_session_for_worker, update_session_state
from datetime import datetime
from shared import WorkerNotFound


@click.command()
@click.argument("worker_id")
@pass_context
def cleanup_cmd(ctx: Context, worker_id: str):
    """Cleanup stale session for a worker.

    Removes stale tmux session references and unbinds worker-session
    when the tmux session no longer exists. Use this when a session
    has died or been killed outside of the normal workflow.

    \b
    Example:
        qn wrkr cleanup ceo
        qn wrkr cleanup worker-abc123
    """
    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    db = open_database(db_path)

    try:
        try:
            worker = Worker.get(db, worker_id)
        except WorkerNotFound:
            raise click.ClickException(
                f"Worker '{worker_id}' not found.\n"
                "Run 'qn org status' to see available workers."
            )

        # Get session info
        session_record = get_session_for_worker(db, worker_id)

        if not session_record:
            click.echo(f"Worker {worker.name} has no session record to cleanup.")
            return

        tmux_session = session_record.get("tmux_session_name")
        session_id = session_record.get("id")
        current_state = session_record.get("state")

        click.echo(f"Cleaning up session for {worker.name}...")
        if tmux_session:
            click.echo(f"  Tmux session: {tmux_session}")
        if session_id:
            click.echo(f"  Session ID: {session_id}")
        click.echo(f"  Current state: {current_state}")
        click.echo("")

        # Step 1: Update session state to stopped
        if session_id:
            update_session_state(
                db=db,
                session_id=session_id,
                state="stopped",
                stopped_at=datetime.now(),
            )
            click.echo("✓ Updated session state to 'stopped'")

        # Step 2: Clear tmux session name
        if tmux_session:
            db.execute(
                """UPDATE sessions
                   SET tmux_session_name = NULL
                   WHERE worker_id = ?""",
                (worker_id,)
            )
            db.connection.commit()
            click.echo("✓ Cleared tmux session reference")

        # Step 3: Update worker runtime status
        db.execute(
            """UPDATE worker_state
               SET runtime_status = 'stopped',
                   updated_at = CURRENT_TIMESTAMP
               WHERE worker_id = ?""",
            (worker_id,)
        )
        db.connection.commit()
        click.echo("✓ Updated worker runtime status to 'stopped'")

        # Step 4: Unbind worker-session
        try:
            manager = get_binding_manager(db)
            binding = manager.unbind(worker_id)
            if binding:
                click.echo(f"✓ Unbound worker-session binding")
            else:
                click.echo("  (No binding to unbind)")
        except Exception as e:
            click.echo(f"  Warning: Could not unbind session: {e}")

        click.echo("")
        click.echo(f"Session cleanup complete for {worker.name}")
        click.echo("")
        click.echo("To start a new session:")
        click.echo(f"  qn wrkr restart {worker_id}")

    finally:
        db.close()
