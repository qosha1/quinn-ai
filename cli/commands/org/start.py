"""
qn org start command.

Implements 4-phase org start sequence:
1. Pre-flight validation
2. Org state transition (with rollback)
3. CEO session spawning
4. Readiness verification
"""

import time
from enum import Enum
from pathlib import Path
from typing import Optional

import click

from cli.commands.context import pass_context, Context
from cli.core.config import (
    get_org_config_path,
    load_org_config,
    validate_and_raise,
)
from cli.core.db import open_database, get_org_db_path, Database
from cli.core.org import Org
from cli.core.org_chart import update_org_chart
from cli.core.onboarding import (
    get_worker_env_vars,
    load_onboarding_context,
    prepare_worker_onboarding,
)
from cli.core.session import SessionConfig
from cli.core.sessions.registry import get_default_registry
from cli.core.storage import StorageManager
from cli.core.worker import Worker
from shared import (
    InvalidOrgTransition,
    ConfigurationError,
    OrgStructureError,
    SessionSpawnError,
    SessionStartTimeout,
)
from shared.enums import OrgStatus, RuntimeStatus


class StartMode(Enum):
    """Org start modes based on current status."""
    FIRST_START = "first_start"  # INITIALIZED → RUNNING (activate CEO)
    RESUME = "resume"             # STOPPED → RUNNING (CEO already active)
    ALREADY_RUNNING = "already_running"  # RUNNING → RUNNING (idempotent)


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
@click.option(
    "--wait/--no-wait",
    default=False,
    help="Wait for CEO session to reach READY state before returning (default: False)",
)
@click.option(
    "--wait-timeout",
    type=int,
    default=60,
    help="Seconds to wait for session ready (requires --wait, default: 60)",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Force restart CEO session even if already active",
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
    wait: bool,
    wait_timeout: int,
    force: bool,
):
    """Start the organization.

    Transitions org to running state. If starting from initialized state,
    also activates the CEO worker and spawns their session by default.

    Use --no-spawn-ceo to start without spawning CEO session.
    Use --wait to block until CEO session reaches ready state.
    Use --force to restart CEO session even if already active.
    """
    org_path = ctx.org_path

    # Handle worker-specific start (independent path)
    if worker:
        _start_worker(
            org_path,
            worker,
            provider,
            session_command,
            session_args,
        )
        return

    # ===================
    # PHASE 1: PRE-FLIGHT VALIDATION
    # ===================

    db = _validate_preflight(org_path, skip_config_validation)

    try:
        org = Org.load(db)

        # Determine start mode
        start_mode = _determine_start_mode(org)

        if start_mode == StartMode.ALREADY_RUNNING:
            _handle_already_running(org, spawn_ceo, force, provider, session_command, session_args, wait, wait_timeout)
            return

        # ===================
        # PHASE 2: ORG STATE TRANSITION (with rollback)
        # ===================

        old_status, new_status = _transition_org_state(org, start_mode, org_path, db)

        # ===================
        # PHASE 3: CEO SESSION SPAWNING
        # ===================

        if spawn_ceo:
            try:
                _spawn_ceo_session_if_needed(
                    org.ceo,
                    org_path,
                    db,
                    provider,
                    session_command,
                    session_args,
                    force,
                )
            except Exception as e:
                # Don't rollback org state - just report error
                click.echo(f"\nError: Failed to spawn CEO session", err=True)
                click.echo(f"Reason: {e}", err=True)
                click.echo("\nOrganization is RUNNING but CEO session is not active.", err=True)
                click.echo("\nTo retry:", err=True)
                click.echo("  qn org start --spawn-ceo", err=True)
                click.echo("\nTo debug:", err=True)
                click.echo("  qn org status", err=True)
                click.echo("  qn wrkr logs ceo", err=True)
                raise click.ClickException(f"Session spawn failed: {e}")

        # ===================
        # PHASE 4: READINESS VERIFICATION
        # ===================

        if wait and spawn_ceo:
            _wait_for_ready(org.ceo, wait_timeout)

        # Report success
        click.echo(f"\nOrganization started at {org_path}")
        click.echo(f"  Status: {org.status}")
        if org.ceo:
            click.echo(f"  CEO: {org.ceo.name} ({org.ceo.lifecycle_status})")
            if org.ceo.is_session_active:
                click.echo(f"  CEO Session: {org.ceo.runtime_status}")

    finally:
        db.close()


# ===================
# PHASE 1: PRE-FLIGHT VALIDATION
# ===================

def _validate_preflight(org_path: Path, skip_config_validation: bool) -> Database:
    """Phase 1: Validate everything before making state changes.

    Returns:
        Database instance

    Raises:
        click.ClickException: On validation failure
    """
    # 1. Validate org exists
    db_path = get_org_db_path(org_path)
    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    # 2. Validate provider configuration (unless skipped)
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

    # 3. Validate org directory structure
    required_dirs = ["config", "live", "storage/shared", "storage/workers"]
    for dir_name in required_dirs:
        dir_path = org_path / dir_name
        if not dir_path.exists():
            raise click.ClickException(
                f"Missing required directory: {dir_name}\n"
                f"Organization structure at {org_path} is incomplete."
            )

    return open_database(db_path)


def _determine_start_mode(org: Org) -> StartMode:
    """Determine which start mode to use based on current org status.

    Args:
        org: Org instance

    Returns:
        StartMode enum value

    Raises:
        click.ClickException: If cannot start from current status
    """
    current_status = org.status

    if current_status == OrgStatus.RUNNING.value:
        return StartMode.ALREADY_RUNNING
    elif current_status == OrgStatus.INITIALIZED.value:
        return StartMode.FIRST_START
    elif current_status == OrgStatus.STOPPED.value:
        return StartMode.RESUME
    else:
        raise click.ClickException(
            f"Cannot start organization from status '{current_status}'.\n"
            "Check current status with 'qn org status'."
        )


def _handle_already_running(
    org: Org,
    spawn_ceo: bool,
    force: bool,
    provider: str,
    session_command: str,
    session_args: str,
    wait: bool,
    wait_timeout: int,
) -> None:
    """Handle the case where org is already running (idempotent).

    Args:
        org: Org instance
        spawn_ceo: Whether to spawn CEO session
        force: Whether to force restart session
        provider: Session provider
        session_command: Session command
        session_args: Session args
        wait: Whether to wait for ready
        wait_timeout: Timeout for waiting
    """
    click.echo("Organization is already running.")

    if not spawn_ceo:
        return

    ceo = org.ceo
    if ceo and ceo.is_session_active:
        if force:
            click.echo(f"Forcing CEO session restart (--force)...")
            ceo.terminate_session(force=True)
        else:
            click.echo(f"CEO session already active ({ceo.runtime_status})")
            return
    elif ceo:
        click.echo("Warning: Org is RUNNING but CEO session is not active")
        click.echo("Spawning CEO session...")

    # Spawn CEO session
    db = org.db
    org_path = Path(db.db_path).parent.parent  # live/quinn.db -> org_path
    _spawn_ceo_session_if_needed(ceo, org_path, db, provider, session_command, session_args, force=False)

    if wait:
        _wait_for_ready(ceo, wait_timeout)

    click.echo(f"CEO session spawned (provider: {provider})")


# ===================
# PHASE 2: ORG STATE TRANSITION
# ===================

def _transition_org_state(
    org: Org,
    start_mode: StartMode,
    org_path: Path,
    db: Database,
) -> tuple[str, str]:
    """Phase 2: Transition org state with rollback support.

    Args:
        org: Org instance
        start_mode: Start mode
        org_path: Org directory path
        db: Database instance

    Returns:
        Tuple of (old_status, new_status)

    Raises:
        click.ClickException: On transition failure (after rollback)
    """
    try:
        old_status, new_status = org.start()

        # Update org-chart to reflect lifecycle changes
        update_org_chart(db, org_path)

        return (old_status, new_status)

    except InvalidOrgTransition as e:
        raise click.ClickException(
            f"Cannot start organization: {e}\n"
            "Check current status with 'qn org status'."
        )
    except Exception as e:
        # Rollback org state on any error during transition
        click.echo(f"\nError during org state transition: {e}", err=True)
        click.echo("Rolling back org status...", err=True)

        # Get current status to rollback to the pre-start state
        # org.start() was called but may have partially succeeded
        old_status = org.status
        if old_status == OrgStatus.RUNNING.value:
            # Rollback to previous status
            if start_mode == StartMode.FIRST_START:
                org.rollback_to_status(OrgStatus.INITIALIZED.value)
                click.echo("Rolled back to INITIALIZED status")
            elif start_mode == StartMode.RESUME:
                org.rollback_to_status(OrgStatus.STOPPED.value)
                click.echo("Rolled back to STOPPED status")

        raise click.ClickException(f"Org start failed: {e}")


# ===================
# PHASE 3: CEO SESSION SPAWNING
# ===================

def _spawn_ceo_session_if_needed(
    ceo: Worker,
    org_path: Path,
    db: Database,
    provider: str,
    command: str,
    args_str: str,
    force: bool = False,
) -> None:
    """Spawn CEO session if not already active.

    Args:
        ceo: CEO Worker instance
        org_path: Path to org directory
        db: Database instance
        provider: Session provider name
        command: CLI command for the session
        args_str: Space-separated additional args
        force: Force restart even if active

    Raises:
        SessionSpawnError: If spawn fails
    """
    # Check if CEO session already active
    if ceo.is_session_active and not force:
        click.echo(f"CEO session already active ({ceo.runtime_status})")
        return

    if force and ceo.is_session_active:
        click.echo("Terminating existing CEO session (--force)...")
        ceo.terminate_session(force=True)

    # Parse args
    args = args_str.split() if args_str else []

    # Prepare onboarding (creates worker directory, briefing, docs)
    onboarding_ctx = prepare_worker_onboarding(db, ceo.id, org_path)

    # Get hierarchical worker directory from StorageManager
    storage = StorageManager(org_path, db)
    worker_dir = storage.get_worker_path(ceo.id)

    # Get environment variables
    env_vars = get_worker_env_vars(onboarding_ctx, org_path, db)

    # Create session config
    config = SessionConfig(
        worker_id=ceo.id,
        provider=provider,
        command=command,
        args=args,
        working_directory=worker_dir,
        env_vars=env_vars,
    )

    # Get registry and ensure provider is available
    registry = get_default_registry()
    if not registry.has(provider):
        available = registry.list_adapters()
        raise SessionSpawnError(
            ceo.id,
            f"Unknown session provider '{provider}'. "
            f"Available providers: {', '.join(available)}"
        )

    # Set registry on CEO worker and spawn
    ceo.set_registry(registry)
    try:
        ceo.spawn(config)
        click.echo(f"CEO session spawned (provider: {provider})")
    except Exception as e:
        raise SessionSpawnError(ceo.id, str(e))


# ===================
# PHASE 4: READINESS VERIFICATION
# ===================

def _wait_for_ready(worker: Worker, timeout: int) -> None:
    """Wait for worker session to reach READY state.

    Args:
        worker: Worker instance
        timeout: Timeout in seconds

    Raises:
        SessionStartTimeout: If not ready within timeout
    """
    click.echo(f"Waiting for {worker.name} session to reach ready state (timeout: {timeout}s)...")

    start_time = time.time()
    while time.time() - start_time < timeout:
        if worker.runtime_status == RuntimeStatus.RUNNING.value:
            elapsed = int(time.time() - start_time)
            click.echo(f"✓ {worker.name} session ready (after {elapsed}s)")
            return
        time.sleep(1)

    # Timeout reached
    raise SessionStartTimeout(worker.id, timeout)


# ===================
# WORKER-SPECIFIC START
# ===================

def _start_worker(
    org_path: Path,
    worker: str,
    provider: str,
    session_command: str,
    session_args: str,
) -> None:
    """Start a workday for a specific worker (independent path).

    Args:
        org_path: Org directory path
        worker: Worker name or ID
        provider: Session provider
        session_command: Session command
        session_args: Session args

    Raises:
        click.ClickException: On error
    """
    db_path = get_org_db_path(org_path)
    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    db = open_database(db_path)
    try:
        org = Org.load(db)

        if org.status != OrgStatus.RUNNING.value:
            raise click.ClickException(
                "Organization is not running.\n"
                "Run 'qn org start' first or start the org before starting a worker."
            )

        from cli.core.queries import get_worker_by_name
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
        storage = StorageManager(org_path, db)
        worker_dir = storage.ensure_worker_storage(worker_obj.id)

        onboarding_ctx = load_onboarding_context(db, worker_obj.id, org_path)
        env_vars = get_worker_env_vars(onboarding_ctx, org_path, db)

        spawn_worker_session(
            worker=worker_obj,
            provider=provider,
            command=session_command,
            args_str=session_args,
            working_directory=worker_dir,
            env_vars=env_vars,
            force_restart=True,
        )
        click.echo(f"Session started for {worker_obj.name}")

    finally:
        db.close()
