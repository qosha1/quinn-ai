"""
qn org start command.
"""

from typing import Optional

import click

from cli.commands.context import pass_context, Context
from cli.core.config import (
    get_org_config_path,
    load_org_config,
    validate_and_raise,
)
from cli.core.db import open_database, get_org_db_path
from cli.core.org import Org
from cli.core.org_chart import update_org_chart
from cli.core.session import SessionConfig
from cli.core.sessions.registry import get_default_registry
from shared import InvalidOrgTransition, ConfigurationError
from shared.enums import OrgStatus


@click.command()
@click.option(
    "--spawn-ceo/--no-spawn-ceo",
    default=True,
    help="Spawn CEO session after starting org (default: True)",
)
@click.option(
    "--provider",
    default="claude_code",
    help="Session provider for CEO (default: claude_code)",
)
@click.option(
    "--command",
    "session_command",
    default="claude",
    help="CLI command for session (default: claude)",
)
@click.option(
    "--args",
    "session_args",
    default="",
    help="Additional args for session command (space-separated)",
)
@click.option(
    "--skip-config-validation",
    is_flag=True,
    default=False,
    help="Skip provider configuration validation (for testing/development)",
)
@pass_context
def start_cmd(
    ctx: Context,
    spawn_ceo: bool,
    provider: str,
    session_command: str,
    session_args: str,
    skip_config_validation: bool,
):
    """Start the organization.

    Transitions org to running state. If starting from initialized state,
    also activates the CEO worker and spawns their session by default.

    Use --no-spawn-ceo to start without spawning CEO session.
    """
    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    # Validate provider configuration at startup (unless skipped)
    if not skip_config_validation:
        config_path = get_org_config_path(org_path)
        try:
            org_config = load_org_config(config_path)
            validate_and_raise(org_config)
        except FileNotFoundError as e:
            raise click.ClickException(
                f"Configuration file not found: {e}\n"
                "Ensure config/providers.yaml exists."
            )
        except ConfigurationError as e:
            raise click.ClickException(
                f"Configuration error: {e}\n"
                "Check config/providers.yaml for valid provider settings."
            )

    db = open_database(db_path)

    try:
        org = Org.load(db)

        if org.status == OrgStatus.RUNNING.value:
            click.echo("Organization is already running.")
            return

        try:
            org.start()
        except InvalidOrgTransition as e:
            raise click.ClickException(
                f"Cannot start organization: {e}\n"
                "Check current status with 'qn org status'."
            )

        # Update org-chart to reflect lifecycle changes (CEO is now active)
        update_org_chart(db, org_path)

        click.echo(f"Organization started at {org_path}")
        click.echo(f"Status: {org.status}")

        if org.ceo:
            click.echo(f"CEO: {org.ceo.name} ({org.ceo.lifecycle_status})")

            # Spawn CEO session if requested
            if spawn_ceo:
                _spawn_ceo_session(
                    org.ceo,
                    org_path,
                    provider,
                    session_command,
                    session_args,
                )
                click.echo(f"CEO session spawned (provider: {provider})")

    finally:
        db.close()


def _spawn_ceo_session(
    ceo,
    org_path,
    provider: str,
    command: str,
    args_str: str,
) -> None:
    """Spawn a session for the CEO worker.

    Args:
        ceo: CEO Worker instance
        org_path: Path to org directory
        provider: Session provider name
        command: CLI command for the session
        args_str: Space-separated additional args
    """
    # Parse args
    args = args_str.split() if args_str else []

    # Create session config
    config = SessionConfig(
        worker_id=ceo.id,
        provider=provider,
        command=command,
        args=args,
        working_directory=org_path,
    )

    # Get registry and ensure provider is available
    registry = get_default_registry()
    if not registry.has(provider):
        available = registry.list_adapters()
        raise click.ClickException(
            f"Unknown session provider '{provider}'.\n"
            f"Available providers: {', '.join(available)}\n"
            "Use --provider to specify a valid session provider."
        )

    # Set registry on CEO worker and spawn
    ceo.set_registry(registry)
    ceo.spawn(config)
