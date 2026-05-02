"""qn wrkr pause / resume — temporarily suspend or re-activate worker autonomy."""

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.org import Org
from cli.core.queries import resolve_worker, get_or_create_direct_channel, create_message

_PAUSE_MSG = (
    "PAUSE DIRECTIVE from board operator.\n\n"
    "Hold your current work. Do NOT start new tasks or send outbound messages until you receive a RESUME directive. "
    "Save your current state to a bead with --notes describing where you paused. "
    "Then wait for instructions."
)

_RESUME_MSG = (
    "RESUME DIRECTIVE from board operator.\n\n"
    "You may continue your work. Check your inbox for any new context, then pick up where you left off."
)


def _send_directive(ctx: Context, worker_name: str, content: str, label: str) -> None:
    org_path = ctx.org_path
    db = open_database(get_org_db_path(org_path))
    try:
        org = Org.load(db)
        if org.ceo is None:
            raise click.ClickException("No CEO found.")
        sender_id = org.ceo.id

        target = resolve_worker(db, worker_name)
        if target is None:
            raise click.ClickException(f"Worker '{worker_name}' not found.")

        channel = get_or_create_direct_channel(db, sender_id, target.id)
        create_message(
            db,
            channel_id=channel.id,
            from_worker_id=sender_id,
            content=content,
            priority=2,
            time_sensitivity="immediate",
        )
        click.echo(f"{label} directive sent to {target.name}.")
    finally:
        db.close()


@click.command("pause")
@click.argument("worker_name")
@pass_context
def pause_cmd(ctx: Context, worker_name: str) -> None:
    """Send a pause directive to a worker — they hold until resumed.

    WORKER_NAME: Worker name or ID
    """
    _send_directive(ctx, worker_name, _PAUSE_MSG, "Pause")


@click.command("resume")
@click.argument("worker_name")
@pass_context
def resume_cmd(ctx: Context, worker_name: str) -> None:
    """Send a resume directive to a paused worker.

    WORKER_NAME: Worker name or ID
    """
    _send_directive(ctx, worker_name, _RESUME_MSG, "Resume")
