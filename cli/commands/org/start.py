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
from cli.core.onboarding import (
    generate_returning_message,
    generate_welcome_message,
    get_worker_env_vars,
    load_onboarding_context,
    prepare_worker_onboarding,
)
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
    "--worker",
    help="Start a workday for a specific worker (name or ID).",
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
    default="--dangerously-skip-permissions",
    help="Additional args for session command (default: --dangerously-skip-permissions)",
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
    worker: Optional[str],
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

        if worker:
            if org.status != OrgStatus.RUNNING.value:
                raise click.ClickException(
                    "Organization is not running.\n"
                    "Run 'qn org start' first or start the org before starting a worker."
                )

            from cli.core.queries import get_worker_by_name
            from cli.core.worker import Worker
            from cli.commands.org.session_utils import spawn_worker_session

            worker_data = get_worker_by_name(db, worker)
            if not worker_data:
                try:
                    worker_obj = Worker.get(db, worker)
                except (ValueError, KeyError):
                    raise click.ClickException(
                        f"Worker '{worker}' not found.\n"
                        "Use 'qn org status' to see available workers."
                    )
            else:
                worker_obj = Worker(db, worker_data.id, org_path=org_path)

            click.echo(f"Starting workday for {worker_obj.name}...")
            # Get hierarchical worker directory from StorageManager
            from cli.core.storage import StorageManager
            storage = StorageManager(org_path, db)
            worker_dir = storage.ensure_worker_storage(worker_obj.id)

            onboarding_ctx = load_onboarding_context(db, worker_obj.id, org_path)
            env_vars = get_worker_env_vars(onboarding_ctx, org_path, db)
            welcome = generate_returning_message(onboarding_ctx)

            spawn_worker_session(
                worker=worker_obj,
                provider=provider,
                command=session_command,
                args_str=session_args,
                working_directory=worker_dir,
                env_vars=env_vars,
                welcome_message=welcome,
                force_restart=True,
            )
            click.echo(f"Session started for {worker_obj.name}")
            return

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
    from cli.core.onboarding import (
        prepare_worker_onboarding,
        get_worker_env_vars,
        generate_welcome_message,
    )

    # Parse args
    args = args_str.split() if args_str else []

    # Prepare onboarding (creates worker directory, briefing, docs)
    db = open_database(get_org_db_path(org_path))
    try:
        onboarding_ctx = prepare_worker_onboarding(db, ceo.id, org_path)

        # Get hierarchical worker directory from StorageManager
        from cli.core.storage import StorageManager
        storage = StorageManager(org_path, db)
        worker_dir = storage.get_worker_path(ceo.id)

        # Get environment variables
        env_vars = get_worker_env_vars(onboarding_ctx, org_path, db)

        # Generate welcome message
        welcome = generate_welcome_message(onboarding_ctx, worker_dir)
    finally:
        db.close()

    # Create session config
    config = SessionConfig(
        worker_id=ceo.id,
        provider=provider,
        command=command,
        args=args,
        working_directory=worker_dir,  # Worker dir, not org root
        env_vars=env_vars,
        welcome_message=welcome,
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
