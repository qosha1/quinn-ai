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

import subprocess
import time
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
    INITIAL_PROMPT_FILESYSTEM_FLUSH,
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

    click.echo("Phase 4: Spawning CEO session...")
    config = SessionConfig(
        worker_id=ceo.id,
        provider=provider,
        command=command,
        args=args,
        model=model,
        working_directory=resolve_session_cwd(org_path, worker_dir),
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


_INITIAL_PROMPT_TEMPLATE = """=== EXECUTE THIS NOW — these are YOUR active instructions ===

This file is being cat'd into your active claude session by the org's
spawn flow. You ARE the worker described below — NOT an outside reader
analyzing the document. Do not summarize this. Do not describe what it
would do. Read it and BEGIN EXECUTING immediately, starting with the
'CRITICAL INSTRUCTIONS' steps in order. Your first action after reading
this file MUST be `msgr inbox` (per Inbox discipline in BRIEFING.md).

If you find yourself thinking "this is a script for another worker,
not for me" — that's wrong. You are that worker. Execute now.

=== END FRAMING — instructions follow ===

You are {self_intro}. You've just been onboarded.

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

   # Send your first message (required). NOTE: quote the channel name —
   # bash treats unquoted '#' as a comment and the message will be lost.
   msgr send '#general' "Hi team! {chat_intro} Starting work now. Reading briefing and reviewing OKRs."

   # Confirm message sent
   msgr inbox
   ```

2. Read your BRIEFING.md file: `cat "$WORKER_STORAGE/BRIEFING.md"` (use the full path — your cwd may be the project root in host-mode, not your storage dir)
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

**WORK LOOP (run this after every task or turn ends):**
```
msgr inbox   # check for new messages and directives first
bd ready     # see available work
```
Pick the highest priority item, work it to completion, then repeat. Never sit idle — if `bd ready` is empty, check `bd list --status=open` or ask your manager for direction.
You can also use `/loop` to automate this cycle.

**COMMUNICATION REQUIREMENT — INBOX DISCIPLINE (MANDATORY):**

`msgr inbox` is a continuous polling queue, not a passive notification.
After every action that ends a turn — finishing a task, replying to a
DM, hitting a wait state — your NEXT action MUST be `msgr inbox`.
Also re-check `msgr inbox` every ~5 minutes during long work.

When inbox shows messages:
- **Questions** → answer EVERY one. "No reply" is not a valid response.
- **Directives** ("please pick up X", "next up — Y", "switch to Z") →
  EXECUTE IMMEDIATELY. Do NOT reply with "Want me to proceed?". The
  right reply is "On it, starting now" + immediate action.
- **Status updates** → acknowledge with a one-line confirmation so the
  sender knows the loop closed.

Post status updates to '#general' as you work (note the quotes —
bash strips unquoted '#general' as a comment):
- When starting a task: msgr send '#general' "Starting: <title>"
- When completing a task: msgr send '#general' "Completed: <title>"
- Every 30-60 minutes with progress updates
- When blocked on anything

**YOUR FIRST TASK:**
Send your introduction message above, then read BRIEFING.md and follow the "First Actions" section.

Start by running: msgr send '#general' "Hi team! {chat_intro} Starting work now. Reading briefing and reviewing OKRs."
"""


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
        formatted_prompt = _INITIAL_PROMPT_TEMPLATE.format(
            self_intro=self_intro,
            chat_intro=chat_intro,
        )
        instructions_file.write_text(formatted_prompt)

        time.sleep(INITIAL_PROMPT_FILESYSTEM_FLUSH)

        tmux_session = f"{TMUX_SESSION_PREFIX}{ceo.id}"
        # Use the absolute path. In host-mode, the worker's cwd is the
        # project_root (so they can edit project files directly), not the
        # worker's storage dir — so a bare 'cat INITIAL_TASK.md' fails.
        # The absolute path works in both greenfield and host-mode.
        # (quinn-ai-ltvl)
        cmd = f"cat {instructions_file}"

        try:
            # quinn-ai-k2cy: wait for the CEO TUI to be ready before sending
            # keystrokes. Without this, claude is still booting and the
            # 'cat INITIAL_TASK.md' input vanishes into a not-yet-rendered
            # interactive prompt. The CEO then sits idle forever with no
            # directive.
            ready = _wait_for_pane_ready(tmux_session)
            if not ready:
                click.echo(
                    "  ⚠ CEO TUI did not appear ready within the wait window; "
                    "delivering prompt anyway (best-effort).",
                    err=True,
                )
            pane_before = _capture_pane(tmux_session)

            cmd_sent = _tmux_send_keys_with_retry(tmux_session, cmd)
            time.sleep(TMUX_SEND_KEYS_INTERSTITIAL)
            enter_sent = _tmux_send_keys_with_retry(tmux_session, "Enter")
            # Second Enter (quinn-ai-moho): claude-code's TUI sometimes
            # treats the first Enter after a long pasted line as a
            # newline-in-input rather than submit. A second Enter
            # reliably submits whatever's in the input. Empirically
            # verified by manual repro against Cleo's session — first
            # Enter left text in the input box, second Enter submitted.
            time.sleep(TMUX_SEND_KEYS_INTERSTITIAL)
            _tmux_send_keys_with_retry(tmux_session, "Enter")
            if not (cmd_sent and enter_sent):
                raise subprocess.CalledProcessError(
                    1, ["tmux", "send-keys"],
                    output=b"send-keys retries exhausted",
                )

            # Poll briefly for SPECIFIC evidence the prompt landed:
            # either the cat command text in the pane (proves keystrokes
            # reached the TUI) or a claude processing indicator (proves
            # the message was submitted and claude is responding).
            # The previous "any pane diff = success" check was a
            # false-positive when the TUI itself redrew (cursor blinks,
            # status bar updates) between captures while keystrokes never
            # actually landed (quinn-ai-moho).
            verification_window = INITIAL_PROMPT_VERIFICATION_WINDOW
            poll_interval = INITIAL_PROMPT_VERIFICATION_POLL
            elapsed = 0.0
            received = False
            while elapsed < verification_window:
                time.sleep(poll_interval)
                elapsed += poll_interval
                pane_after = _capture_pane(tmux_session)
                if pane_after and _pane_shows_prompt_landed(pane_after, cmd):
                    received = True
                    break

            if received:
                click.echo("✓ Initial task instructions delivered; CEO session is processing")
                click.echo("  Use 'qn org observe ceo' to watch progress, or 'qn org logs ceo' for transcripts")
            else:
                click.echo(
                    f"⚠ Initial task instructions sent but no pane activity observed within "
                    f"{verification_window:.0f}s",
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

    finally:
        db.close()
