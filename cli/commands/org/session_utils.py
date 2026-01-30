"""Shared helpers for org-level worker session control."""

from pathlib import Path
from typing import Optional

import click

from core.session import SessionConfig
from core.sessions.registry import get_default_registry
from core.worker import Worker


def spawn_worker_session(
    worker: Worker,
    provider: str,
    command: str,
    args_str: str,
    working_directory: Optional[Path | str] = None,
    env_vars: Optional[dict[str, str]] = None,
    welcome_message: Optional[str] = None,
    force_restart: bool = False,
) -> None:
    """Spawn a worker session with optional restart."""
    if force_restart and worker.is_session_active:
        worker.terminate_session(force=True)

    args = args_str.split() if args_str else []

    config = SessionConfig(
        worker_id=worker.id,
        provider=provider,
        command=command,
        args=args,
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
