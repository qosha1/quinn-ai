"""Shared helpers for org-level worker session control."""

from pathlib import Path
from typing import Optional

import click

from cli.core.session import SessionConfig
from cli.core.sessions.registry import get_default_registry
from cli.core.worker import Worker


# Default worker kickstart prompt — quinn-ai-lja7. Sent to non-CEO workers'
# tmux pane via send-keys after spawn so they don't idle waiting for input.
# The CEO gets its own INITIAL_TASK.md via qn org start Phase 5; the hired
# worker's equivalent lives as a file under cli/config/templates/ and is
# rendered via cli.core.prompts.render_initial_task (quinn-ai-58rw) — no
# magic-string prompts in code.


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

    # Inject tool guard hook before spawn so the session starts with it active.
    if working_directory is not None:
        try:
            from cli.core.session.tool_guard import write_tool_guard_hook_config
            org_path = env_vars.get("QUINN_ORG_PATH") or env_vars.get("ORG_PATH") if env_vars else None
            if org_path:
                write_tool_guard_hook_config(
                    working_dir=Path(working_directory),
                    org_path=Path(org_path),
                    worker_id=worker.id,
                )
        except Exception:
            pass  # Hook injection is best-effort — don't block spawn

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
            TMUX_SESSION_PREFIX,
        )
        from cli.core.org_start_controller import deliver_initial_prompt
    except ImportError:
        return  # constants/helpers not importable in this context; silently skip

    from cli.core.prompts import render_initial_task
    from cli.core.constants.prompts import INITIAL_TASK_KIND_WORKER

    instructions = worker_dir / "INITIAL_TASK.md"
    try:
        instructions.write_text(
            render_initial_task(
                INITIAL_TASK_KIND_WORKER, name=worker.name, role=worker.role
            )
        )
    except OSError:
        return  # can't write the file; skip kickstart

    time.sleep(INITIAL_PROMPT_FILESYSTEM_FLUSH)

    tmux_session = f"{TMUX_SESSION_PREFIX}{worker.id}"

    # Verify-and-retry delivery, shared with the CEO kickstart (quinn-ai-ns6t):
    # re-send until the pane confirms the prompt landed, so a hired worker
    # never boots idle from a send that vanished into a still-booting TUI. Uses
    # the ABSOLUTE path so it works whether the worker's cwd is its storage dir
    # (greenfield) or the project root (host-mode) — quinn-ai-ltvl.
    deliver_initial_prompt(tmux_session, instructions)
