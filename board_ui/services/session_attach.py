"""Attach to a worker's tmux session, suspending the Textual app while inside."""

import subprocess


def attach_to_worker_session(tmux_session_name: str) -> bool:
    """Attach to a worker's tmux session.

    In a Textual context, call app.suspend() before this function so the TUI
    yields the terminal. On detach (prefix+d), the caller resumes Textual.

    Args:
        tmux_session_name: The tmux session name (e.g. "qn-worker-abc123")

    Returns:
        True if attach succeeded (returncode 0), False if session not found
    """
    result = subprocess.run(
        ["tmux", "attach-session", "-t", tmux_session_name],
        check=False,
    )
    return result.returncode == 0
