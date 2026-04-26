"""
qn wrkr restart command.

Restarts a worker session by cleaning up any stale session and spawning
a new one.
"""

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.worker import Worker
from cli.core.sessions.binding_manager import get_binding_manager
from cli.core.sessions.persistence import get_session_for_worker, update_session_state, delete_session_record
from cli.core.session import SessionConfig
from cli.core.storage import StorageManager
from cli.core.onboarding import get_worker_env_vars, load_onboarding_context
from cli.core.constants import DEFAULT_ORG_ID
from datetime import datetime
from shared import WorkerNotFound


@click.command()
@click.argument("worker_id")
@click.option(
    "--provider",
    default="claude_code",
    help="Session provider (default: claude_code)",
)
@click.option(
    "--command",
    default="claude",
    help="CLI command for session (default: claude)",
)
@click.option(
    "--args",
    "session_args",
    default="--dangerously-skip-permissions",
    help="Additional args for session command",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Force restart even if session is active",
)
@pass_context
def restart_cmd(
    ctx: Context,
    worker_id: str,
    provider: str,
    command: str,
    session_args: str,
    force: bool,
):
    """Restart worker session.

    Cleans up any stale session references and spawns a new session.
    Use this to recover from session freeze or crash.

    \b
    Example:
        qn wrkr restart ceo
        qn wrkr restart worker-abc123 --force
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
        # Check org status - cannot restart workers if org is not running
        org_row = db.fetchone(
            "SELECT status FROM org_state WHERE id = ?", (DEFAULT_ORG_ID,)
        )
        if not org_row or org_row["status"] in ("stopped", "uninitialized"):
            raise click.ClickException(
                "Cannot restart worker: org is not running.\n"
                "Start it with: qn org start"
            )

        try:
            worker = Worker.get(db, worker_id)
        except WorkerNotFound:
            raise click.ClickException(
                f"Worker '{worker_id}' not found.\n"
                "Run 'qn org status' to see available workers."
            )

        click.echo(f"Restarting session for {worker.name}...")
        click.echo("")

        # Step 1: Cleanup existing session if any
        session_record = get_session_for_worker(db, worker_id)

        if session_record:
            session_id = session_record.get("id")
            tmux_session = session_record.get("tmux_session_name")
            current_state = session_record.get("state")

            # Block restart of active session unless --force is given
            if current_state in ("starting", "running", "idle") and not force:
                raise click.ClickException(
                    f"Worker session is currently {current_state}. "
                    f"Use --force to restart anyway."
                )

            click.echo("Cleaning up existing session...")

            # Update session state to stopped
            if session_id:
                update_session_state(
                    db=db,
                    session_id=session_id,
                    state="stopped",
                    stopped_at=datetime.now(),
                )

            # Kill and clear tmux session
            if tmux_session:
                import subprocess
                try:
                    subprocess.run(
                        ["tmux", "kill-session", "-t", tmux_session],
                        capture_output=True, timeout=5,
                    )
                except Exception:
                    pass
                db.execute(
                    """UPDATE sessions
                       SET tmux_session_name = NULL
                       WHERE worker_id = ?""",
                    (worker_id,)
                )
                db.connection.commit()

            # Update worker runtime status
            db.execute(
                """UPDATE worker_state
                   SET runtime_status = 'stopped',
                       updated_at = CURRENT_TIMESTAMP
                   WHERE worker_id = ?""",
                (worker_id,)
            )
            db.connection.commit()

            # Unbind worker-session
            try:
                manager = get_binding_manager(db)
                manager.unbind(worker_id)
            except Exception as e:
                click.echo(f"  Warning: Could not unbind: {e}")

            # Terminate existing session if still active
            if worker.is_session_active or force:
                try:
                    worker.terminate_session(force=True)
                except Exception as e:
                    click.echo(f"  Warning: Could not terminate: {e}")

            # Delete old session record so new spawn can create a fresh one
            if session_id:
                delete_session_record(db, session_id)

            click.echo("✓ Cleaned up existing session")
            click.echo("")

        # Step 2: Spawn new session
        click.echo("Spawning new session...")

        # Get worker directory and environment
        storage = StorageManager(org_path, db)
        worker_dir = storage.get_worker_path(worker_id)

        # Load onboarding context
        onboarding_ctx = load_onboarding_context(db, worker_id, org_path)
        env_vars = get_worker_env_vars(onboarding_ctx, org_path, db)

        # Parse args
        args = session_args.split() if session_args else []

        # Create session config
        config = SessionConfig(
            worker_id=worker_id,
            provider=provider,
            command=command,
            args=args,
            working_directory=worker_dir,
            env_vars=env_vars,
        )

        # Spawn session
        from cli.core.sessions.registry import get_default_registry
        registry = get_default_registry()
        worker.set_registry(registry)

        try:
            worker.spawn(config)
            click.echo(f"✓ New session spawned (provider: {provider})")
            click.echo("")
            click.echo(f"Session restarted for {worker.name}")

            # Show how to attach
            session_record = get_session_for_worker(db, worker_id)
            if session_record and session_record.get("tmux_session_name"):
                tmux_name = session_record["tmux_session_name"]
                click.echo("")
                click.echo("To attach to the session:")
                click.echo(f"  tmux attach-session -t {tmux_name}")

        except Exception as e:
            raise click.ClickException(f"Failed to spawn session: {e}")

    finally:
        db.close()
