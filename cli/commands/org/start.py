"""
qn org start command.

Implements 6-phase org start sequence (quinnai-3gqq):

Phase 0 (Preflight): Validation before any state changes
    - Verify org exists (database, directory structure)
    - Validate provider configuration
    - Determine start mode (FIRST_START, RESUME, ALREADY_RUNNING)

Phase 1 (Cleanup): Orphaned session reconciliation
    - Kill orphaned tmux sessions from previous crashes
    - Update stale DB records
    - Best-effort (failure doesn't block startup)

Phase 2 (Transition): Atomic org + CEO state changes
    - Transition org INITIALIZED->RUNNING or STOPPED->RUNNING
    - Activate CEO worker (complete onboarding)
    - Update org-chart
    - Supports rollback on failure

Phase 3 (Onboarding): File system preparation
    - Create worker directory structure
    - Generate BRIEFING.md, STORAGE.md, WELCOME.md
    - Prepare environment variables

Phase 4 (Session Spawn): CEO session via registry
    - Create SessionConfig with working directory and env vars
    - Spawn session through provider adapter
    - Session spawn failure does NOT rollback org state

Phase 5 (Kickstart): Initial prompt delivery
    - Write INITIAL_TASK.md to worker directory
    - Send command to tmux session
    - Best-effort (failure doesn't fail start)

Phase 6 (Readiness): Optional wait for session ready
    - Poll session state until RUNNING or IDLE
    - Timeout if not ready within specified period
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
from cli.core.constants import (
    CONFIG_DIR,
    LIVE_DIR,
    SESSION_START_POLL_INTERVAL,
    SHARED_DIR,
    STORAGE_DIR,
    TMUX_SESSION_PREFIX,
    WORKERS_DIR,
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

    # =========================================================================
    # PHASE 0: PREFLIGHT - Validation before any state changes
    # =========================================================================
    click.echo("Phase 0: Validating organization...")
    db = _validate_preflight(org_path, skip_config_validation)

    try:
        org = Org.load(db)

        # Determine start mode
        start_mode = _determine_start_mode(org)

        if start_mode == StartMode.ALREADY_RUNNING:
            _handle_already_running(org, spawn_ceo, force, provider, session_command, session_args, wait, wait_timeout)
            return

        # =========================================================================
        # PHASE 1: CLEANUP - Orphaned session reconciliation (best-effort)
        # =========================================================================
        click.echo("Phase 1: Cleaning up orphaned sessions...")
        _cleanup_orphaned_sessions(db)

        # =========================================================================
        # PHASE 2: TRANSITION - Atomic org + CEO state changes (with rollback)
        # =========================================================================
        click.echo("Phase 2: Transitioning org state...")
        old_status, new_status = _transition_org_state(org, start_mode, org_path, db)

        # =========================================================================
        # PHASE 3-5: ONBOARDING + SESSION SPAWN + KICKSTART
        # =========================================================================
        # These phases are combined in _spawn_ceo_session_if_needed():
        # - Phase 3 (Onboarding): prepare_worker_onboarding() creates directory structure
        # - Phase 4 (Session Spawn): ceo.spawn() creates tmux session
        # - Phase 5 (Kickstart): _send_initial_prompt_to_ceo() sends initial task
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

        # =========================================================================
        # PHASE 6: READINESS - Optional wait for session ready state
        # =========================================================================
        if wait and spawn_ceo:
            click.echo("Phase 6: Waiting for session readiness...")
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


# =============================================================================
# PHASE 0: PREFLIGHT VALIDATION
# =============================================================================

def _cleanup_orphaned_sessions(db: Database) -> None:
    """Clean up orphaned tmux sessions from previous crashes.

    This prevents "session already exists" errors when spawning new sessions.
    Orphaned sessions occur when:
    - Worker processes crash unexpectedly
    - System restarts without proper shutdown
    - Session termination fails partway through

    Args:
        db: Database instance
    """
    from cli.core.sessions import run_startup_cleanup

    try:
        result = run_startup_cleanup(db)

        if result.tmux_sessions_killed > 0 or result.db_records_updated > 0:
            # Only show message if cleanup actually did something
            click.echo("Cleaned up orphaned sessions from previous run:")
            if result.tmux_sessions_killed > 0:
                click.echo(f"  Killed {result.tmux_sessions_killed} orphaned tmux session(s)")
            if result.db_records_updated > 0:
                click.echo(f"  Updated {result.db_records_updated} stale DB record(s)")

        if result.errors:
            # Log errors but don't fail - cleanup is best-effort
            for error in result.errors:
                click.echo(f"  Warning: {error}", err=True)

    except Exception as e:
        # Cleanup failure shouldn't prevent org start
        click.echo(f"Warning: Session cleanup failed: {e}", err=True)


def _validate_preflight(org_path: Path, skip_config_validation: bool) -> Database:
    """Phase 0 (Preflight): Validate everything before making state changes.

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
    required_dirs = [
        CONFIG_DIR,
        LIVE_DIR,
        f"{STORAGE_DIR}/{SHARED_DIR}",
        f"{STORAGE_DIR}/{WORKERS_DIR}",
    ]
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


# =============================================================================
# PHASE 2: ORG STATE TRANSITION
# =============================================================================

def _transition_org_state(
    org: Org,
    start_mode: StartMode,
    org_path: Path,
    db: Database,
) -> tuple[str, str]:
    """Phase 2 (Transition): Transition org state with rollback support.

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


# =============================================================================
# PHASES 3-5: ONBOARDING + SESSION SPAWN + KICKSTART
# =============================================================================

def _spawn_ceo_session_if_needed(
    ceo: Worker,
    org_path: Path,
    db: Database,
    provider: str,
    command: str,
    args_str: str,
    force: bool = False,
) -> None:
    """Phases 3-5: Onboarding, Session Spawn, and Kickstart.

    Phase 3 (Onboarding): Prepares worker directory and generates docs
    Phase 4 (Session Spawn): Creates tmux session via provider adapter
    Phase 5 (Kickstart): Sends initial prompt to start autonomous work

    Note: Session spawn failure does NOT rollback org state. The org remains
    RUNNING and can be recovered with `qn org start --spawn-ceo`.

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

    # Phase 3: Onboarding - prepare worker directory and docs
    click.echo("Phase 3: Preparing onboarding materials...")
    onboarding_ctx = prepare_worker_onboarding(db, ceo.id, org_path)

    # Get hierarchical worker directory from StorageManager
    storage = StorageManager(org_path, db)
    worker_dir = storage.get_worker_path(ceo.id)

    # Get environment variables
    env_vars = get_worker_env_vars(onboarding_ctx, org_path, db)

    # Phase 4: Session Spawn - create session config and spawn
    click.echo("Phase 4: Spawning CEO session...")
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
        click.echo(f"  CEO session spawned (provider: {provider})")

        # Phase 5: Kickstart - send initial prompt
        click.echo("Phase 5: Sending initial prompt to CEO...")
        _send_initial_prompt_to_ceo(ceo, worker_dir)

    except Exception as e:
        raise SessionSpawnError(ceo.id, str(e))


def _send_initial_prompt_to_ceo(ceo: Worker, worker_dir: Path) -> None:
    """Phase 5 (Kickstart): Send initial prompt to CEO to start autonomous work.

    This is best-effort - failure doesn't fail the org start. The CEO session
    is spawned and can receive manual input if kickstart fails.

    Args:
        ceo: CEO worker instance
        worker_dir: Path to CEO's worker directory
    """
    import time

    initial_prompt = """You are {ceo_name}, the CEO of this organization. You've just been onboarded.

Your working directory contains important onboarding materials:
- BRIEFING.md - Your role, responsibilities, OKRs, and first actions
- STORAGE.md - Storage architecture and where to save work
- WELCOME.md - Welcome message and context
- CLAUDE.md - Development guidelines
- AGENTS.md - Agent collaboration patterns

**CRITICAL INSTRUCTIONS:**

1. **FIRST: Introduce yourself to the team**
   ```bash
   # Check available channels
   msgr channels

   # Send your first message (required)
   msgr send #general "Hi team! I'm {ceo_name}, CEO. Starting work now. Reading briefing and reviewing OKRs."

   # Confirm message sent
   msgr inbox
   ```

2. Read your BRIEFING.md file: `cat BRIEFING.md`
3. Review your assigned OKRs: `qn org okr list`
4. Check for ready work: `bd ready`
5. Start working autonomously on your highest priority OKR

**AUTONOMOUS MODE:**
You were started with `qn org start`, which means you should operate autonomously:
- Work continuously based on OKRs without waiting for user input
- Make best-guess decisions aligned with objectives
- Document decisions in beads for later review
- Only stop for CRITICAL blockers that prevent ALL progress
- For non-critical questions: document in beads and proceed with reasonable default

**COMMUNICATION REQUIREMENT:**
Post status updates to #general as you work:
- When starting a task
- When completing a task
- Every 30-60 minutes with progress updates
- When blocked on anything

**YOUR FIRST TASK:**
Send your introduction message above, then read BRIEFING.md and follow the "First Actions" section.

Start by running: `msgr send #general "Hi team! I'm {ceo_name}, CEO. Starting work now. Reading briefing and reviewing OKRs."`"""

    import subprocess

    try:
        # Write initial prompt to a file in the worker's directory
        click.echo("Creating initial task instructions...")

        instructions_file = worker_dir / "INITIAL_TASK.md"
        formatted_prompt = initial_prompt.format(ceo_name=ceo.name)
        instructions_file.write_text(formatted_prompt)

        # Wait a moment for Claude Code to initialize
        time.sleep(2)

        # Send command via tmux to read the instructions
        tmux_session = f"{TMUX_SESSION_PREFIX}{ceo.id}"
        command = f"cat INITIAL_TASK.md"

        try:
            # Send the command
            subprocess.run(
                ["tmux", "send-keys", "-t", tmux_session, command],
                check=True,
                capture_output=True
            )
            # Wait a moment for it to appear in the buffer
            time.sleep(0.5)
            # Send Enter to execute it
            subprocess.run(
                ["tmux", "send-keys", "-t", tmux_session, "Enter"],
                check=True,
                capture_output=True
            )
            click.echo("✓ Initial task instructions sent and executed in CEO session")
            click.echo("  CEO should now be reading instructions and starting autonomous work")
        except subprocess.CalledProcessError as e:
            click.echo(f"Warning: Could not send command to tmux: {e}", err=True)
            click.echo(f"  CEO can manually run: cat INITIAL_TASK.md", err=True)

    except Exception as e:
        # Don't fail the org start if initial prompt fails
        click.echo(f"Warning: Failed to deliver initial instructions: {e}", err=True)
        click.echo(f"CEO session spawned but will need manual input to start work", err=True)


# =============================================================================
# PHASE 6: READINESS VERIFICATION
# =============================================================================

def _wait_for_ready(worker: Worker, timeout: int) -> None:
    """Phase 6 (Readiness): Wait for worker session to reach READY state.

    Args:
        worker: Worker instance
        timeout: Timeout in seconds

    Raises:
        SessionStartTimeout: If not ready within timeout
    """
    click.echo(f"Waiting for {worker.name} session to reach ready state (timeout: {timeout}s)...")

    start_time = time.time()
    while time.time() - start_time < timeout:
        # Check if session is in a ready state (RUNNING or IDLE)
        # Sessions transition: starting → running → idle
        # Both RUNNING and IDLE indicate the session is ready for work
        if worker.runtime_status in (RuntimeStatus.RUNNING.value, RuntimeStatus.IDLE.value):
            elapsed = int(time.time() - start_time)
            click.echo(f"✓ {worker.name} session ready (after {elapsed}s)")
            return
        time.sleep(SESSION_START_POLL_INTERVAL)

    # Timeout reached
    raise SessionStartTimeout(worker.id, timeout)


# =============================================================================
# WORKER-SPECIFIC START (Independent path, not part of org start sequence)
# =============================================================================

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
        provider: Session provider (from CLI, may be overridden by worker preference)
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

        # Use worker's preferred_provider if set and CLI didn't override with non-default
        effective_provider = provider
        if worker_obj.preferred_provider:
            # Worker has a preference - use it unless CLI explicitly specified something else
            # Default CLI provider is 'claude_code', so only override if worker prefers different
            effective_provider = worker_obj.preferred_provider
            if provider != "claude_code":
                # CLI explicitly specified a different provider - respect it
                effective_provider = provider
            else:
                click.echo(f"  Using worker's preferred provider: {effective_provider}")

        # Get hierarchical worker directory from StorageManager
        storage = StorageManager(org_path, db)
        worker_dir = storage.ensure_worker_storage(worker_obj.id)

        onboarding_ctx = load_onboarding_context(db, worker_obj.id, org_path)
        env_vars = get_worker_env_vars(onboarding_ctx, org_path, db)

        spawn_worker_session(
            worker=worker_obj,
            provider=effective_provider,
            command=session_command,
            args_str=session_args,
            working_directory=worker_dir,
            env_vars=env_vars,
            force_restart=True,
        )
        click.echo(f"Session started for {worker_obj.name}")

    finally:
        db.close()
