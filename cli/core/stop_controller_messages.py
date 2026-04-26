"""Message templates / builders for the org-stop sequence.

Extracted from cli/core/stop_controller.py so the orchestrator file can
focus on flow logic. Currently a single builder; if more message types
get added (notifications, board messages, etc.) they belong here.
"""

from __future__ import annotations

from .stop_controller_models import WorkerStopState


def build_wrapup_message(state: WorkerStopState, timeout: int) -> str:
    """Build the wrap-up notification body sent to a worker at stop time.

    The message instructs the worker to save WIP, document blockers, and
    commit changes; it includes the per-worker timeout and asks for ACK.
    """
    return (
        f"**Workday Ending**\n\n"
        f"Worker: {state.worker_name} ({state.role})\n\n"
        f"Please wrap up your current work:\n"
        f"1. Save any work in progress to shared/\n"
        f"2. Document incomplete work in beads\n"
        f"3. Commit any changes\n\n"
        f"Timeout: {timeout} seconds\n\n"
        f"Reply with 'ACK' to acknowledge.\n"
        f"After timeout, your session will be terminated."
    )
