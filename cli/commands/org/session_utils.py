"""Shared helpers for org-level worker session control."""

from pathlib import Path
from typing import Optional

import click

from cli.core.session import SessionConfig
from cli.core.sessions.registry import get_default_registry
from cli.core.worker import Worker


# Default worker kickstart prompt — quinn-ai-lja7. Sent to non-CEO workers'
# tmux pane via send-keys after spawn so they don't idle waiting for input.
# The CEO gets its own INITIAL_TASK.md via qn org start Phase 5; this is the
# equivalent for hired workers.
_WORKER_INITIAL_TASK_TEMPLATE = """You are {name}, a {role} on this team.

CRITICAL: act autonomously now, do not wait for further instructions.

1. Read your briefing: cat BRIEFING.md
2. Check your inbox: msgr inbox --full
3. Check assigned work: bd ready
4. For any P0/P1 bead assigned to you, claim it (bd update <id> --status=in_progress) and complete the deliverable described in its description.
5. Post status updates to #general as you make progress (msgr send #general 'status: ...').
6. When finished with assigned beads, mark them closed (bd close <id> --reason '...') and post completion to #general.

Do not stop early. Do not ask for confirmation. The org needs you to ship today.
"""


def spawn_worker_session(
    worker: Worker,
    provider: str,
    command: str,
    args_str: str,
    working_directory: Optional[Path | str] = None,
    env_vars: Optional[dict[str, str]] = None,
    welcome_message: Optional[str] = None,
    force_restart: bool = False,
    model: Optional[str] = "claude-sonnet-4-6",
) -> None:
    """Spawn a worker session with optional restart.

    After the spawn returns, deliver an INITIAL_TASK.md kickstart prompt to
    the worker via tmux send-keys (quinn-ai-lja7). Without this, hired
    workers idle in their TUI until the session times out and the
    delegated work is permanently lost.
    """
    if force_restart and worker.is_session_active:
        worker.terminate_session(force=True)

    args = args_str.split() if args_str else []

    config = SessionConfig(
        worker_id=worker.id,
        provider=provider,
        command=command,
        args=args,
        model=model,
        working_directory=Path(working_directory) if working_directory else None,
        env_vars=env_vars or {},
        welcome_message=welcome_message,
    )

    registry = get_default_registry()
    if not registry.has(provider):
        available = registry.list_adapters()
        raise click.ClickException(
            f"Unknown session provider '{provider}'.\n"
            f"Available providers: {', '.join(available)}\n"
            "Use --provider to specify a valid session provider."
        )

    worker.set_registry(registry)
    worker.spawn(config)

    # Skip kickstart for the CEO — they receive INITIAL_TASK.md via qn org
    # start's Phase 5 and shouldn't get a duplicate from here.
    if worker.role and worker.role.upper() != "CEO" and working_directory is not None:
        _send_worker_kickstart(worker, Path(working_directory))


def _send_worker_kickstart(worker: Worker, worker_dir: Path) -> None:
    """Write INITIAL_TASK.md and inject 'cat INITIAL_TASK.md' into the worker's pane.

    Mirrors the CEO kickstart in cli/core/org_start_controller.py
    _send_initial_prompt_to_ceo, scoped down for hired workers.

    Best-effort: failure here doesn't fail the spawn.
    """
    import time

    try:
        from cli.core.constants import (
            INITIAL_PROMPT_FILESYSTEM_FLUSH,
            TMUX_SEND_KEYS_INTERSTITIAL,
            TMUX_SESSION_PREFIX,
        )
        from cli.core.org_start_controller import (
            _tmux_send_keys_with_retry,
            _wait_for_pane_ready,
        )
    except ImportError:
        return  # constants/helpers not importable in this context; silently skip

    instructions = worker_dir / "INITIAL_TASK.md"
    try:
        instructions.write_text(
            _WORKER_INITIAL_TASK_TEMPLATE.format(name=worker.name, role=worker.role)
        )
    except OSError:
        return  # can't write the file; skip kickstart

    time.sleep(INITIAL_PROMPT_FILESYSTEM_FLUSH)

    tmux_session = f"{TMUX_SESSION_PREFIX}{worker.id}"

    if not _wait_for_pane_ready(tmux_session, timeout=15.0):
        # Pane never reported ready; still attempt delivery best-effort
        # (matches CEO behavior — sometimes the pane is ready but the
        # heuristic missed it).
        pass

    _tmux_send_keys_with_retry(tmux_session, "cat INITIAL_TASK.md")
    time.sleep(TMUX_SEND_KEYS_INTERSTITIAL)
    _tmux_send_keys_with_retry(tmux_session, "Enter")
