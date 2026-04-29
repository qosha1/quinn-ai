"""
qn org start command — thin Click wrapper around cli.core.org_start_controller.

The 6-phase startup orchestration lives in
cli/core/org_start_controller.py (mirrors how cli/core/stop_controller.py
mirrors cli/commands/org/stop.py). This file is just the Click decoration
+ argument plumbing.

Phase reference (full text in cli/core/org_start_controller.py):
- 0 Preflight: validate db, config, dirs
- 1 Cleanup:   orphaned tmux session reconciliation (best-effort)
- 2 Transition: atomic org+CEO state change with rollback
- 3-5 Onboarding + Session Spawn + Kickstart (combined)
- 6 Readiness: optional wait for session ready
"""

from typing import Optional

import click

from cli.commands.context import pass_context, Context

# Re-export the controller's helpers and StartMode so existing tests that
# do `from cli.commands.org.start import _validate_preflight` continue to
# work after the move (cli/tests/test_org_start_phases.py uses this).
from cli.core.org_start_controller import (  # noqa: F401
    StartMode,
    _cleanup_orphaned_sessions,
    _determine_start_mode,
    _handle_already_running,
    _send_initial_prompt_to_ceo,
    _spawn_ceo_session_if_needed,
    _start_worker,
    _transition_org_state,
    _validate_preflight,
    _wait_for_ready,
    execute_start,
)
# Lazy-imported in _cleanup_orphaned_sessions; named here for tests that
# want to patch 'cli.commands.org.start.run_startup_cleanup'.
from cli.core.sessions import run_startup_cleanup  # noqa: F401
# Same back-compat hook for prepare_worker_onboarding etc. that tests
# patch on this module.
from cli.core.onboarding import (  # noqa: F401
    get_worker_env_vars,
    prepare_worker_onboarding,
)
from cli.core.sessions.registry import get_default_registry  # noqa: F401


@click.command()
@click.option(
    "--spawn-ceo/--no-spawn-ceo",
    default=True,
    help="Spawn CEO session (default: True). Use --no-spawn-ceo to start without spawning CEO.",
)
@click.option(
    "--worker",
    default=None,
    help="Start a workday for a specific worker (name or ID) instead of the org.",
)
@click.option(
    "--provider",
    default="claude_code",
    help="Session provider (default: claude_code).",
)
@click.option(
    "--command",
    "session_command",
    default="claude",
    help="CLI command for session (default: claude).",
)
@click.option(
    "--args",
    "session_args",
    default="--dangerously-skip-permissions",
    help="Additional args to pass to the CLI command.",
)
@click.option(
    "--model",
    "model",
    default=None,
    envvar="QUINNAI_CANARY_MODEL",
    help=(
        "Pin the LLM model for the spawned CEO session (e.g., "
        "'claude-sonnet-4-6', 'claude-opus-4-7', or aliases like "
        "'sonnet'/'opus'). For claude_code, this becomes '--model <id>' "
        "on the claude CLI. Defaults to \\$QUINNAI_CANARY_MODEL or, if "
        "unset, whatever model the user is logged into. (quinn-ai-875q)"
    ),
)
@click.option(
    "--skip-config-validation",
    is_flag=True,
    default=False,
    help="Skip provider config validation (advanced).",
)
@click.option(
    "--wait/--no-wait",
    default=False,
    help="Wait for CEO session to reach ready state before returning.",
)
@click.option(
    "--wait-timeout",
    default=60,
    type=int,
    help="Seconds to wait for ready state (default: 60).",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Force restart CEO session even if already active.",
)
@pass_context
def start_cmd(
    ctx: Context,
    spawn_ceo: bool,
    worker: Optional[str],
    provider: str,
    session_command: str,
    session_args: str,
    model: Optional[str],
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
    execute_start(
        ctx.org_path,
        spawn_ceo=spawn_ceo,
        worker=worker,
        provider=provider,
        session_command=session_command,
        session_args=session_args,
        model=model,
        skip_config_validation=skip_config_validation,
        wait=wait,
        wait_timeout=wait_timeout,
        force=force,
    )
