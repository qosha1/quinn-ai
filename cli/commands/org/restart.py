"""
qn org restart command.

Restarts an organization by stopping then starting it.
Equivalent to 'qn org stop && qn org start' but atomic.
"""

import click

from commands.context import pass_context, Context
from core.db import get_org_db_path, open_database
from core.org import Org
from shared.enums import OrgStatus


@click.command()
@click.option(
    "--spawn-ceo/--no-spawn-ceo",
    default=True,
    help="Spawn CEO session after restart (default: True)",
)
@click.option(
    "--provider",
    default="claude_code",
    help="Session provider for CEO (default: claude_code)",
)
@click.option(
    "--skip-config-validation",
    is_flag=True,
    default=False,
    help="Skip provider configuration validation (for testing/development)",
)
@click.option(
    "--graceful-timeout",
    type=int,
    default=10,
    help="Seconds to wait for graceful shutdown before restart (default: 10)",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Force restart even if sessions don't stop gracefully",
)
@pass_context
def restart_cmd(
    ctx: Context,
    spawn_ceo: bool,
    provider: str,
    skip_config_validation: bool,
    graceful_timeout: int,
    force: bool,
):
    """Restart the organization.

    Stops the organization gracefully, then starts it again.
    This is equivalent to running 'qn org stop && qn org start' but
    ensures atomic execution.

    Use --no-spawn-ceo to restart without spawning CEO session.
    Use --force to skip graceful shutdown and kill sessions immediately.
    Use --skip-config-validation to skip provider validation (for testing).
    """
    org_path = ctx.org_path

    # Validate org exists
    db_path = get_org_db_path(org_path)
    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    # Check current status
    db = open_database(db_path)
    try:
        org = Org.load(db)
        current_status = org.status

        if current_status not in [OrgStatus.RUNNING.value, OrgStatus.STOPPED.value]:
            raise click.ClickException(
                f"Cannot restart organization in '{current_status}' state.\n"
                "Organization must be 'running' or 'stopped'.\n"
                "Check current status with 'qn org status'."
            )

        click.echo(f"Restarting organization at {org_path}...")
        click.echo(f"  Current status: {current_status}")

    finally:
        db.close()

    # ====================
    # PHASE 1: STOP ORG
    # ====================

    from .stop import stop_cmd

    # Create new context with same org_path for stop command
    stop_ctx = click.Context(stop_cmd, obj=Context(org_path=org_path))
    stop_ctx.params = {
        "cleanup": True,
        "worker": None,
        "force": force,
        "graceful_timeout": graceful_timeout,
        "yes": True,  # Skip confirmation for restart
        "save_state": True,
    }

    try:
        stop_ctx.invoke(stop_cmd, **stop_ctx.params)
    except click.ClickException as e:
        raise click.ClickException(
            f"Failed to stop organization during restart:\n{e.message}\n\n"
            f"Org may be in inconsistent state. Check: qn org status"
        )

    click.echo("\n" + "=" * 60)
    click.echo("Stop phase complete. Starting org...")
    click.echo("=" * 60 + "\n")

    # ====================
    # PHASE 2: START ORG
    # ====================

    from .start import start_cmd

    # Create new context with same org_path for start command
    start_ctx = click.Context(start_cmd, obj=Context(org_path=org_path))
    start_ctx.params = {
        "spawn_ceo": spawn_ceo,
        "worker": None,
        "provider": provider,
        "session_command": "claude",
        "session_args": "--dangerously-skip-permissions",
        "skip_config_validation": skip_config_validation,
        "wait": False,
        "wait_timeout": 60,
        "force": False,
    }

    try:
        start_ctx.invoke(start_cmd, **start_ctx.params)
    except click.ClickException as e:
        raise click.ClickException(
            f"Org stopped but failed to start:\n{e.message}\n\n"
            f"Org is in STOPPED state. To start manually:\n"
            f"  qn org start --provider={provider}"
        )

    click.echo("\n✓ Organization restarted successfully")
