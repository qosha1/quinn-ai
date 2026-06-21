"""
Org start controller — orchestration for `qn org start`.

This module owns the 6-phase startup sequence; the cli/commands/org/start.py
file is a thin Click adapter that builds args and calls into here. Mirrors
the cli/core/stop_controller.py ↔ cli/commands/org/stop.py split.

Phases (see cli/commands/org/start.py docstring for prose):
0. Preflight — validate db, config, dirs (raises ClickException on issues)
1. Cleanup  — orphaned tmux sessions (best-effort)
2. Transition — atomic org+CEO state change with rollback
3-5. Onboarding + Session spawn + Kickstart (combined)
6. Readiness — optional wait for session ready

The functions kept their original signatures and module-level identity so
existing tests in cli/tests/test_org_start_phases.py that import them
directly (e.g. `from cli.core.org_start_controller import
_validate_preflight`) keep working with one path change.

NOTE: this layer still uses click.echo / click.ClickException for
output and error reporting. A follow-up could thread a reporter
callback through to fully de-couple core from click (matching
cli/core/stop_controller.py's purer separation).
"""

from __future__ import annotations

import logging
import subprocess
import time

_logger = logging.getLogger(__name__)
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import click

from cli.core.config import (
    get_org_config_path,
    load_org_config,
    validate_and_raise,
)
from cli.core.constants import (
    CONFIG_DIR,
    INITIAL_PROMPT_DELIVERY_ATTEMPTS,
    INITIAL_PROMPT_FILESYSTEM_FLUSH,
    INITIAL_PROMPT_READY_TIMEOUT,
    INITIAL_PROMPT_VERIFICATION_POLL,
    INITIAL_PROMPT_VERIFICATION_WINDOW,
    LIVE_DIR,
    SESSION_START_POLL_INTERVAL,
    SHARED_DIR,
    STORAGE_DIR,
    TMUX_SEND_KEYS_INTERSTITIAL,
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
    resolve_session_cwd,
)
from cli.core.session import SessionConfig
from cli.core.sessions.registry import get_default_registry
from cli.core.storage import StorageManager
from cli.core.worker import Worker
from shared.core.tools import OrgToolsConfig, check_tool_presence
from shared import (
    InvalidOrgTransition,
    ConfigurationError,
    OrgStructureError,  # noqa: F401 — re-exported for back-compat
    SessionSpawnError,
    SessionStartTimeout,
)
from shared.enums import OrgStatus, RuntimeStatus


class StartMode(Enum):
    """Org start modes based on current status."""

    FIRST_START = "first_start"  # INITIALIZED → RUNNING (activate CEO)
    RESUME = "resume"             # STOPPED → RUNNING (CEO already active)
    ALREADY_RUNNING = "already_running"  # RUNNING → RUNNING (idempotent)


# =============================================================================
# PHASE 0: PREFLIGHT VALIDATION
# =============================================================================


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

    # 2b. Validate the declared toolchain contract (fail fast on missing
    #     REQUIRED CLIs; warn on missing optional). Gated by the same flag
    #     as provider validation so tests/advanced users can bypass.
    if not skip_config_validation:
        _verify_required_toolchain(org_path)

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

    # 4. Verify CLI tool dependencies (warn on missing, don't fail)
    _verify_cli_tools(org_path)

    return open_database(db_path)


def _verify_required_toolchain(org_path: Path) -> None:
    """Fail fast if any REQUIRED toolchain CLI is missing; warn on optional.

    The contract is the org.yml `toolchain` block persisted by the loader to
    <org config>/toolchain.yaml (quinn-ai-a3pg.1.2). No contract -> no-op.

    Raises:
        click.ClickException: If a required tool is not on PATH.
    """
    from cli.core.toolchain import check_toolchain, load_toolchain

    require, optional = load_toolchain(org_path)
    if not require and not optional:
        return
    report = check_toolchain(require, optional)
    if report.missing_optional:
        click.echo(
            f"Warning: missing optional tools: {', '.join(report.missing_optional)}",
            err=True,
        )
    if not report.ok:
        raise click.ClickException(
            f"Missing required tools: {', '.join(report.missing_required)}\n"
            "Install them, or re-run with --skip-config-validation to bypass."
        )


def _verify_cli_tools(org_path: Path) -> None:
    """Warn if any declared org CLI tools are missing from PATH."""
    tools_config = OrgToolsConfig.load_from_yaml(org_path / "config" / "tools.yaml")
    if not tools_config.tools:
        return
    missing = [t for t in tools_config.tools if not check_tool_presence(t)]
    if missing:
        names = ", ".join(t.name for t in missing)
        click.echo(f"Warning: missing CLI tools: {names}", err=True)
        for t in missing:
            if t.install_cmd:
                click.echo(f"  Install {t.name}: {t.install_cmd}", err=True)


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
            click.echo("Forcing CEO session restart (--force)...")
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
# PHASE 1: ORPHANED SESSION CLEANUP
# =============================================================================


def _cleanup_orphaned_sessions(db: Database) -> None:
    """Clean up orphaned tmux sessions from previous crashes.

    Best-effort: failure here doesn't block startup.
    """
    from cli.core.sessions import run_startup_cleanup

    try:
        result = run_startup_cleanup(db)

        if result.tmux_sessions_killed > 0 or result.db_records_updated > 0:
            click.echo("Cleaned up orphaned sessions from previous run:")
            if result.tmux_sessions_killed > 0:
                click.echo(f"  Killed {result.tmux_sessions_killed} orphaned tmux session(s)")
            if result.db_records_updated > 0:
                click.echo(f"  Updated {result.db_records_updated} stale DB record(s)")

        if result.errors:
            for error in result.errors:
                click.echo(f"  Warning: {error}", err=True)

    except Exception as e:
        click.echo(f"Warning: Session cleanup failed: {e}", err=True)


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

    Returns:
        Tuple of (old_status, new_status)

    Raises:
        click.ClickException: On transition failure (after rollback)
    """
    try:
        old_status, new_status = org.start()
        update_org_chart(db, org_path)
        return (old_status, new_status)

    except InvalidOrgTransition as e:
        raise click.ClickException(
            f"Cannot start organization: {e}\n"
            "Check current status with 'qn org status'."
        )
    except Exception as e:
        click.echo(f"\nError during org state transition: {e}", err=True)
        click.echo("Rolling back org status...", err=True)

        old_status = org.status
        if old_status == OrgStatus.RUNNING.value:
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
    model: "str | None" = None,
) -> None:
    """Phases 3-5: Onboarding, Session Spawn, Kickstart.

    Session spawn failure does NOT rollback org state — the org remains
    RUNNING and can be recovered with `qn org start --spawn-ceo`.

    Raises:
        SessionSpawnError: If spawn fails
    """
    if ceo.is_session_active and not force:
        click.echo(f"CEO session already active ({ceo.runtime_status})")
        return

    if force and ceo.is_session_active:
        click.echo("Terminating existing CEO session (--force)...")
        ceo.terminate_session(force=True)

    args = args_str.split() if args_str else []

    click.echo("Phase 3: Preparing onboarding materials...")
    onboarding_ctx = prepare_worker_onboarding(db, ceo.id, org_path)

    storage = StorageManager(org_path, db)
    worker_dir = storage.get_worker_path(ceo.id)

    env_vars = get_worker_env_vars(onboarding_ctx, org_path, db)

    # Inject tool guard hook into CEO working directory before spawn.
    session_cwd = resolve_session_cwd(org_path, worker_dir)
    try:
        from cli.core.session.tool_guard import write_tool_guard_hook_config
        write_tool_guard_hook_config(
            working_dir=session_cwd,
            org_path=org_path,
            worker_id=ceo.id,
        )
    except Exception as _tg_err:
        _logger.debug(f"Tool guard hook injection failed (non-fatal): {_tg_err}")

    click.echo("Phase 4: Spawning CEO session...")
    config = SessionConfig(
        worker_id=ceo.id,
        provider=provider,
        command=command,
        args=args,
        model=model,
        working_directory=session_cwd,
        env_vars=env_vars,
    )

    registry = get_default_registry()
    if not registry.has(provider):
        available = registry.list_adapters()
        raise SessionSpawnError(
            ceo.id,
            f"Unknown session provider '{provider}'. "
            f"Available providers: {', '.join(available)}",
        )

    ceo.set_registry(registry)
    try:
        ceo.spawn(config)
        click.echo(f"  CEO session spawned (provider: {provider})")

        click.echo("Phase 5: Sending initial prompt to CEO...")
        _send_initial_prompt_to_ceo(ceo, worker_dir)

    except Exception as e:
        raise SessionSpawnError(ceo.id, str(e))


# Initial-task (kickstart) prompts live as files under cli/config/templates/
# and are rendered via cli.core.prompts.render_initial_task (quinn-ai-58rw) —
# no magic-string prompts in code. Host-mode CEOs get the survey-first variant
# so they never auto-claim a human-owned bead (quinn-ai-jd0g, quinn-ai-llvh).


def _capture_pane(tmux_session: str) -> str:
    """Capture current pane content from a tmux session, or return ''."""
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", tmux_session, "-p"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return result.stdout if result.returncode == 0 else ""
    except (subprocess.SubprocessError, OSError):
        return ""


def _wait_for_pane_ready(
    tmux_session: str,
    timeout: float = 15.0,
    poll_interval: float = 0.5,
) -> bool:
    """Poll capture-pane until the spawned TUI is ready to receive input.

    Originally added for quinn-ai-k2cy: prior code fired tmux send-keys
    within ~100ms of new-session, before claude had finished booting.
    Result: 'cat INITIAL_TASK.md' keystrokes vanished into a not-yet-ready
    TUI and the CEO sat idle forever.

    Tightened for quinn-ai-qim4: the original heuristic was
    'has ❯ OR len(pane.strip()) > 200'. The 200-char fallback matched
    bash echoing the long 'claude --dangerously-skip-permissions'
    invocation + a few dozen blank lines BEFORE the Claude Code TUI
    rendered its ❯ prompt. Phase 5's keystrokes still landed in a
    not-yet-receptive TUI and silently disappeared — surfaced live by
    canary 09 instrumentation (cmd_ok=True, enter_ok=True,
    pane_before_len==pane_after_len, no message in pane).

    Now require the actual prompt-cursor character. The known cursors:
      - '❯'   Claude Code (and other Starship-style TUIs)
      - '>'   simpler line editors used by some CLIs (e.g. cursor)
    The '>' check is loose, so we also require it to appear at the
    START of a line (after a newline) so it doesn't match '<a>' style
    junk in pre-TUI banners. The '❯' is unique enough on its own.

    Returns True if ready before timeout, False otherwise. Caller can
    still proceed if False — best-effort delivery keeps Phase 5 from
    failing the whole org start over a slow TUI boot.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pane = _capture_pane(tmux_session)
        if pane and _looks_like_tui_prompt(pane):
            return True
        time.sleep(poll_interval)
    return False


def _pane_shows_prompt_landed(pane: str, sent_cmd: str) -> bool:
    """True iff pane content shows specific evidence the prompt was delivered.

    Two acceptable proofs (quinn-ai-moho):
    1. The literal cat command (or a recognizable substring of it) appears
       in the pane — keystrokes reached the TUI's input area.
    2. A claude-code processing indicator appears — the message was
       submitted and claude is actively responding. Indicators include
       its tool-use bullets (⏺, ⎿), thinking spinner (✻), and common
       English markers ('Crunching', 'Reading', 'Thinking').

    The previous "any pane content changed" check was too loose — TUI
    redraws between captures (cursor blink, status bar) registered as
    'changed' even when keystrokes never landed.
    """
    if not pane:
        return False

    # Proof 1: the cat command (or its filename tail) is visible.
    # Tail of sent_cmd is enough — long absolute paths get wrapped in
    # the TUI input box, but the filename or "INITIAL_TASK.md" stays.
    cmd_tail = sent_cmd.split("/")[-1] if "/" in sent_cmd else sent_cmd
    if cmd_tail and cmd_tail in pane:
        return True
    # Also check for the leading "cat " token to catch shorter paths.
    if sent_cmd in pane:
        return True

    # Proof 2: claude is actively processing.
    processing_markers = ("⏺", "✻", "⎿", "Crunching", "Reading", "Thinking")
    return any(m in pane for m in processing_markers)


def _looks_like_tui_prompt(pane: str) -> bool:
    """True iff pane content shows an interactive TUI prompt cursor.

    Strict — matches the actual cursor character, not a content-length
    heuristic that bash output can trip (qim4).
    """
    if "❯" in pane:
        return True
    # '>' must be at start of a line (after newline or at very start),
    # followed by space — a typical line-editor prompt shape. Avoids
    # matching XML-ish or arrow-shaped junk in pre-TUI output.
    for line in pane.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("> ") or stripped == ">":
            return True
    return False


def _tmux_send_keys_with_retry(
    tmux_session: str,
    keys: str,
    *,
    attempts: int = 3,
    backoff: float = 0.3,
) -> bool:
    """Send keystrokes to tmux with retry-on-failure.

    Returns True on success, False if all attempts fail. Doesn't raise —
    the caller handles failure (best-effort delivery).
    """
    for i in range(attempts):
        try:
            subprocess.run(
                ["tmux", "send-keys", "-t", tmux_session, keys],
                check=True,
                capture_output=True,
                timeout=2,
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            if i < attempts - 1:
                time.sleep(backoff * (i + 1))
    return False


def deliver_initial_prompt(tmux_session: str, instructions_file) -> bool:
    """Deliver 'cat <instructions_file>' to a freshly-spawned session, verifying
    it landed and re-sending until it does. Returns True if confirmed.

    A single send can race claude's still-booting TUI and vanish, leaving the
    worker (CEO or hired) idle forever (quinn-ai-ns6t). This gates on the REAL
    outcome — the pane showing the command — not on readiness detection, so it
    works even when the TUI wasn't ready for an earlier send. Re-cat'ing an
    already-delivered file is harmless (idempotent read). Shared by the CEO
    kickstart and the hired-worker kickstart so both are equally robust.
    """
    cmd = f"cat {instructions_file}"
    # Best-effort initial readiness; kept short because the retry loop below is
    # the real guarantee.
    _wait_for_pane_ready(tmux_session, timeout=INITIAL_PROMPT_READY_TIMEOUT)

    for attempt in range(1, INITIAL_PROMPT_DELIVERY_ATTEMPTS + 1):
        cmd_sent = _tmux_send_keys_with_retry(tmux_session, cmd)
        time.sleep(TMUX_SEND_KEYS_INTERSTITIAL)
        enter_sent = _tmux_send_keys_with_retry(tmux_session, "Enter")
        # Second Enter (quinn-ai-moho): claude's TUI sometimes treats the first
        # Enter after a long pasted line as newline-in-input, not submit.
        time.sleep(TMUX_SEND_KEYS_INTERSTITIAL)
        _tmux_send_keys_with_retry(tmux_session, "Enter")
        if not (cmd_sent and enter_sent):
            continue  # send-keys retries exhausted this round; try again

        elapsed = 0.0
        while elapsed < INITIAL_PROMPT_VERIFICATION_WINDOW:
            time.sleep(INITIAL_PROMPT_VERIFICATION_POLL)
            elapsed += INITIAL_PROMPT_VERIFICATION_POLL
            pane = _capture_pane(tmux_session)
            if pane and _pane_shows_prompt_landed(pane, cmd):
                return True
    return False


def _send_initial_prompt_to_ceo(ceo: Worker, worker_dir: Path) -> None:
    """Phase 5 (Kickstart): Send initial prompt to CEO.

    Best-effort: failure here doesn't fail the org start. After delivering
    the prompt, poll the pane briefly to verify the CEO actually received
    and started processing it (quinn-ai-kx03). Without this verification
    we used to print 'sent and executed' even when the prompt vanished
    into a TUI that wasn't ready yet.
    """
    try:
        click.echo("Creating initial task instructions...")

        instructions_file = worker_dir / "INITIAL_TASK.md"
        # Elide the redundant "{name}, the CEO" / "I'm {name}, CEO" phrasing
        # when the worker's name matches their role (placeholder-default
        # case — see quinn-ai-exem). Reads as "You are the CEO" / "I'm the CEO".
        if ceo.name.strip().casefold() == ceo.role.strip().casefold():
            self_intro = f"the {ceo.role} of this organization"
            chat_intro = f"I'm the {ceo.role}."
        else:
            self_intro = f"{ceo.name}, the {ceo.role} of this organization"
            chat_intro = f"I'm {ceo.name}, {ceo.role}."
        # Select template: host-mode CEOs get the survey-first variant
        # (quinn-ai-jd0g) so they never auto-claim human-owned beads.
        try:
            from cli.core.host_mode import is_host_mode as _is_host_mode
            _use_host_template = _is_host_mode(ceo._org_path)
        except Exception:
            _use_host_template = False
        from cli.core.prompts import render_initial_task
        from cli.core.constants.prompts import (
            INITIAL_TASK_KIND_CEO,
            INITIAL_TASK_KIND_CEO_HOST,
        )
        kind = (
            INITIAL_TASK_KIND_CEO_HOST if _use_host_template
            else INITIAL_TASK_KIND_CEO
        )
        formatted_prompt = render_initial_task(
            kind, self_intro=self_intro, chat_intro=chat_intro
        )
        instructions_file.write_text(formatted_prompt)

        time.sleep(INITIAL_PROMPT_FILESYSTEM_FLUSH)

        tmux_session = f"{TMUX_SESSION_PREFIX}{ceo.id}"
        # Use the absolute path. In host-mode, the worker's cwd is the
        # project_root (so they can edit project files directly), not the
        # worker's storage dir — so a bare 'cat INITIAL_TASK.md' fails.
        # The absolute path works in both greenfield and host-mode.
        # (quinn-ai-ltvl)

        try:
            # Verify-and-retry delivery (quinn-ai-ns6t) — shared with hired
            # workers so both kickstart paths are equally robust against a send
            # vanishing into a still-booting TUI.
            received = deliver_initial_prompt(tmux_session, instructions_file)

            if received:
                click.echo("✓ Initial task instructions delivered; CEO session is processing")
                click.echo("  Use 'qn org observe ceo' to watch progress, or 'qn org logs ceo' for transcripts")
            else:
                click.echo(
                    f"⚠ Initial task instructions could not be confirmed after "
                    f"{INITIAL_PROMPT_DELIVERY_ATTEMPTS} attempts",
                    err=True,
                )
                click.echo(
                    "  The CEO may not have received the prompt. Check with 'qn org observe ceo' "
                    "and re-send manually if needed: tmux send-keys -t "
                    f"{tmux_session} 'cat {instructions_file}' Enter",
                    err=True,
                )
        except subprocess.CalledProcessError as e:
            click.echo(f"Warning: Could not send command to tmux: {e}", err=True)
            click.echo(f"  CEO can manually run: cat {instructions_file}", err=True)

    except Exception as e:
        click.echo(f"Warning: Failed to deliver initial instructions: {e}", err=True)
        click.echo("CEO session spawned but will need manual input to start work", err=True)


# =============================================================================
# PHASE 6: READINESS VERIFICATION
# =============================================================================


def _wait_for_ready(worker: Worker, timeout: int) -> None:
    """Phase 6 (Readiness): Wait for worker session to reach READY state.

    Raises:
        SessionStartTimeout: If not ready within timeout
    """
    click.echo(f"Waiting for {worker.name} session to reach ready state (timeout: {timeout}s)...")

    start_time = time.time()
    while time.time() - start_time < timeout:
        if worker.runtime_status in (RuntimeStatus.RUNNING.value, RuntimeStatus.IDLE.value):
            elapsed = int(time.time() - start_time)
            click.echo(f"✓ {worker.name} session ready (after {elapsed}s)")
            return
        time.sleep(SESSION_START_POLL_INTERVAL)

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

        effective_provider = provider
        if worker_obj.preferred_provider:
            effective_provider = worker_obj.preferred_provider
            if provider != "claude_code":
                # CLI explicitly specified a different provider — respect it
                effective_provider = provider
            else:
                click.echo(f"  Using worker's preferred provider: {effective_provider}")

        storage = StorageManager(org_path, db)
        worker_dir = storage.ensure_worker_storage(worker_obj.id)

        onboarding_ctx = load_onboarding_context(db, worker_obj.id, org_path)
        env_vars = get_worker_env_vars(onboarding_ctx, org_path, db)

        spawn_worker_session(
            worker=worker_obj,
            provider=effective_provider,
            command=session_command,
            args_str=session_args,
            working_directory=resolve_session_cwd(org_path, worker_dir),
            env_vars=env_vars,
            force_restart=True,
        )
        click.echo(f"Session started for {worker_obj.name}")

    finally:
        db.close()


# =============================================================================
# PUBLIC ENTRY POINT
# =============================================================================


def _spawn_other_active_workers(
    db: "Database",
    org_path: Path,
    provider: str,
    session_command: str,
    session_args: str,
) -> None:
    """Spawn sessions for all active non-CEO workers that have budget and no running session."""
    from cli.core.queries import get_workers_by_status
    from cli.core.budget.enforcer import check_budget
    from cli.commands.org.session_utils import spawn_worker_session
    from cli.core.onboarding import get_worker_env_vars, prepare_worker_onboarding
    from cli.core.storage import StorageManager
    from shared.exceptions import NoBudgetAllocationError

    workers = get_workers_by_status(db, "active")
    non_ceo = [w for w in workers if w.role.upper() != "CEO"]
    if not non_ceo:
        return

    click.echo(f"Spawning sessions for {len(non_ceo)} active worker(s)...")
    for worker_data in non_ceo:
        worker_obj = Worker(db, worker_data.id, org_path=org_path)
        if worker_obj.is_session_active:
            continue
        try:
            check_budget(db, worker_obj.id, required_amount=0)
        except NoBudgetAllocationError:
            click.echo(f"  Skipping {worker_data.name} — no budget allocated")
            continue
        try:
            storage = StorageManager(org_path, db)
            worker_dir = storage.ensure_worker_storage(worker_obj.id)
            onboarding_ctx = prepare_worker_onboarding(db, worker_obj.id, org_path)
            env_vars = get_worker_env_vars(onboarding_ctx, org_path, db)
            eff_provider = worker_obj.preferred_provider or provider
            spawn_worker_session(
                worker=worker_obj,
                provider=eff_provider,
                command=session_command,
                args_str=session_args,
                working_directory=resolve_session_cwd(org_path, worker_dir),
                env_vars=env_vars,
                force_restart=False,
            )
            click.echo(f"  Session started for {worker_data.name}")
        except Exception as e:
            click.echo(f"  Warning: could not start {worker_data.name}: {e}", err=True)


def execute_start(
    ctx_org_path: Path,
    *,
    spawn_ceo: bool,
    worker: "str | None",
    provider: str,
    session_command: str,
    session_args: str,
    skip_config_validation: bool,
    wait: bool,
    wait_timeout: int,
    force: bool,
    model: "str | None" = None,
) -> None:
    """Run the full org start sequence (or worker-specific start).

    Equivalent to what cli.commands.org.start.start_cmd does, but
    callable from anywhere — tests, scripts, programmatic flows.

    Raises:
        click.ClickException: on validation / transition failure
        SessionSpawnError: on session-spawn failure (after org reached RUNNING)
        SessionStartTimeout: if --wait and timeout elapses before ready
    """
    org_path = ctx_org_path

    # Worker-specific start: independent path
    if worker:
        _start_worker(org_path, worker, provider, session_command, session_args)
        return

    click.echo("Phase 0: Validating organization...")
    db = _validate_preflight(org_path, skip_config_validation)

    try:
        org = Org.load(db)
        start_mode = _determine_start_mode(org)

        if start_mode == StartMode.ALREADY_RUNNING:
            _handle_already_running(
                org, spawn_ceo, force, provider, session_command, session_args, wait, wait_timeout
            )
            return

        click.echo("Phase 1: Cleaning up orphaned sessions...")
        _cleanup_orphaned_sessions(db)

        click.echo("Phase 2: Transitioning org state...")
        _transition_org_state(org, start_mode, org_path, db)

        if spawn_ceo:
            try:
                _spawn_ceo_session_if_needed(
                    org.ceo, org_path, db, provider, session_command, session_args, force,
                    model=model,
                )
            except Exception as e:
                click.echo("\nError: Failed to spawn CEO session", err=True)
                click.echo(f"Reason: {e}", err=True)
                click.echo("\nOrganization is RUNNING but CEO session is not active.", err=True)
                click.echo("\nTo retry:", err=True)
                click.echo("  qn org start --spawn-ceo", err=True)
                click.echo("\nTo debug:", err=True)
                click.echo("  qn org status", err=True)
                click.echo("  qn wrkr logs ceo", err=True)
                raise click.ClickException(f"Session spawn failed: {e}")

        if wait and spawn_ceo:
            click.echo("Phase 6: Waiting for session readiness...")
            _wait_for_ready(org.ceo, wait_timeout)

        _spawn_other_active_workers(db, org_path, provider, session_command, session_args)

        click.echo(f"\nOrganization started at {org_path}")
        click.echo(f"  Status: {org.status}")
        if org.ceo:
            click.echo(f"  CEO: {org.ceo.name} ({org.ceo.lifecycle_status})")
            if org.ceo.is_session_active:
                click.echo(f"  CEO Session: {org.ceo.runtime_status}")

        # Spawn the continuation engine as a detached background daemon so
        # workers get nudged when idle even after this process exits.
        # Without this, the engine is never started and CEOs stop polling
        # their inbox after the first delegation cycle (quinn-ai-srwt).
        _spawn_continuation_daemon(org_path)

    finally:
        db.close()


def _spawn_continuation_daemon(org_path: Path) -> None:
    """Start a detached continuation engine daemon for this org.

    Spawns `qn org tail --no-color` in a new session so it outlives this
    process. Idempotent: does nothing if a daemon for this org is already
    running (detected via pid-file).
    """
    import subprocess
    import sys

    pid_file = org_path / "live" / "continuation-engine.pid"

    # Check if already running
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            # Signal 0 checks existence without killing
            import os
            os.kill(pid, 0)
            return  # daemon already alive
        except (ValueError, ProcessLookupError, PermissionError, OSError):
            pid_file.unlink(missing_ok=True)

    try:
        log_path = org_path / "live" / "continuation-engine.log"
        with open(log_path, "a") as log_fh:
            proc = subprocess.Popen(
                [sys.executable, "-m", "cli.commands.continuation_daemon",
                 "--org-path", str(org_path)],
                stdout=log_fh,
                stderr=log_fh,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        pid_file.write_text(str(proc.pid))
        click.echo(f"  Continuation engine: running (pid {proc.pid})")
    except Exception as e:
        click.echo(
            f"  Warning: could not start continuation engine daemon: {e}",
            err=True,
        )
        click.echo(
            "  Run 'qn org tail' in a background pane to supervise workers.",
            err=True,
        )
