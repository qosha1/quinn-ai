"""Session queries."""

from typing import Optional

from ..db import Database


def get_active_session_tmux_name(db: Database, worker_id: str) -> Optional[str]:
    """Get tmux session name for worker's active session.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        Tmux session name or None if no active session found
    """
    row = db.fetchone(
        """SELECT tmux_session_name
           FROM sessions
           WHERE worker_id = ? AND state IN ('starting', 'idle', 'running')
           ORDER BY created_at DESC
           LIMIT 1""",
        (worker_id,)
    )
    return row["tmux_session_name"] if row else None


def get_session_by_worker(db: Database, worker_id: str) -> Optional[dict]:
    """Get active session for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        Session dict or None if no active session found
    """
    row = db.fetchone(
        """SELECT *
           FROM sessions
           WHERE worker_id = ? AND state IN ('starting', 'idle', 'running')
           ORDER BY created_at DESC
           LIMIT 1""",
        (worker_id,)
    )
    return dict(row) if row else None


__all__ = [
    "get_active_session_tmux_name",
    "get_session_by_worker",
]
