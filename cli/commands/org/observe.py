"""
qn org observe command.

Attach to or stream a worker's tmux session in real-time.
"""

import time
from typing import Optional

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.worker import Worker
from cli.core.queries import get_worker_by_name, get_worker
from shared import WorkerNotFound
from shared.pyterm.tmux_session import TmuxSession


def get_tmux_session_name(worker_id: str) -> str:
    """Get the tmux session name for a worker.

    Uses consistent naming with AgentSession.

    Args:
        worker_id: Worker ID

    Returns:
        tmux session name in format qn-{worker_id}
    """
    return f"qn-{worker_id}"


def stream_session_output(session_name: str, poll_interval: float = 0.5) -> None:
    """Stream tmux session output by polling.

    Uses TmuxSession for consistent tmux handling.

    Args:
        session_name: tmux session name
        poll_interval: Seconds between polls
    """
    last_output = ""

    click.echo(f"Streaming session '{session_name}'... (Ctrl+C to stop)")
    click.echo("-" * 60)

    try:
        while True:
            if not TmuxSession.exists(session_name):
                click.echo("\nSession ended.")
                break

            current_output = TmuxSession.capture(session_name)

            if current_output != last_output:
                # Clear screen and show new output
                click.clear()
                click.echo(f"[Streaming: {session_name}] (Ctrl+C to stop)")
                click.echo("-" * 60)
                click.echo(current_output, nl=False)
                last_output = current_output

            time.sleep(poll_interval)

    except KeyboardInterrupt:
        click.echo("\n\nStopped streaming.")


@click.command()
@click.argument("worker")
@click.option(
    "--stream",
    is_flag=True,
    help="Stream output by polling instead of attaching to session.",
)
@click.option(
    "--poll-interval",
    type=float,
    default=0.5,
    help="Poll interval in seconds when using --stream (default: 0.5).",
)
@pass_context
def observe_cmd(ctx: Context, worker: str, stream: bool, poll_interval: float):
    """Observe a worker's tmux session in real-time.

    Attaches to the worker's tmux session to see what they're doing.
    The worker must have an active session (starting, running, or idle).

    WORKER can be the worker name or worker ID.

    \b
    Examples:
      qn org observe alice           # Attach to alice's session
      qn org observe alice --stream  # Poll and print output without attaching
      qn org observe wrkr-abc123     # Use worker ID

    \b
    When attached (default mode):
      - You will take over your terminal to view the worker's session
      - Use tmux's detach key sequence to exit (Ctrl+B, then D)
      - The worker's session continues running after you detach

    \b
    When streaming (--stream):
      - Output is polled and printed to your terminal
      - Use Ctrl+C to stop streaming
      - Does not affect the worker's session
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
        # Try to find worker by name first, then by ID
        worker_data = get_worker_by_name(db, worker)
        if worker_data is None:
            worker_data = get_worker(db, worker)

        if worker_data is None:
            raise click.ClickException(
                f"Worker '{worker}' not found.\n"
                "Use 'qn org status' to see available workers."
            )

        # Load Worker instance to check session status
        try:
            worker_obj = Worker.get(db, worker_data.id)
        except WorkerNotFound:
            raise click.ClickException(
                f"Worker '{worker}' not found.\n"
                "Use 'qn org status' to see available workers."
            )

        # Check if worker has an active session
        if not worker_obj.is_session_active:
            runtime_status = worker_obj.runtime_status or "none"
            raise click.ClickException(
                f"Worker '{worker_data.name}' does not have an active session.\n"
                f"Current runtime status: {runtime_status}\n"
                "Worker must be in 'starting', 'running', or 'idle' state to observe."
            )

        # Get tmux session name (consistent with AgentSession naming)
        session_name = get_tmux_session_name(worker_data.id)

        # Verify tmux session actually exists using TmuxSession
        if not TmuxSession.exists(session_name):
            raise click.ClickException(
                f"Worker '{worker_data.name}' shows active but tmux session '{session_name}' not found.\n"
                "The session may have crashed. Try 'qn org cleanup' to sync state."
            )

        click.echo(f"Observing worker '{worker_data.name}' ({worker_data.id})")
        click.echo(f"Role: {worker_data.role}")
        click.echo(f"Session: {session_name}")
        click.echo("")

        if stream:
            # Stream mode - poll and print output
            stream_session_output(session_name, poll_interval)
        else:
            # Attach mode - take over terminal
            click.echo("Attaching to session... (Ctrl+B, then D to detach)")
            db.close()  # Close DB before exec replaces process
            TmuxSession.attach(session_name)

    finally:
        db.close()
