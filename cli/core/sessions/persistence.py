"""
Session persistence functions for database storage.

Provides CRUD operations for session records in quinn.db.
Sessions are 1:1 with workers and track the session state,
tmux session info, and other runtime details.
"""

import json
from datetime import datetime
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..db import Database


def create_session_record(
    db: "Database",
    session_id: str,
    worker_id: str,
    provider: str,
    command: str,
    args: Optional[list[str]] = None,
    working_directory: Optional[str] = None,
    tmux_session_name: Optional[str] = None,
    state: str = "starting",
) -> dict:
    """Create a new session record in the database.

    Args:
        db: Database instance
        session_id: Unique session ID (e.g., from SessionId)
        worker_id: Worker ID this session belongs to
        provider: Provider name (e.g., "claude_code")
        command: CLI command being run
        args: Optional command arguments as list
        working_directory: Optional working directory path
        tmux_session_name: Optional tmux session name for tracking
        state: Initial state (default: "starting")

    Returns:
        Dict with created session data

    Raises:
        sqlite3.IntegrityError: If worker_id already has a session
    """
    now = datetime.now()
    args_json = json.dumps(args) if args else None

    db.execute(
        """INSERT INTO sessions (
            id, worker_id, provider, command, args,
            working_directory, tmux_session_name, state, state_version,
            started_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id,
            worker_id,
            provider,
            command,
            args_json,
            working_directory,
            tmux_session_name,
            state,
            0,  # Initial state_version
            now,
            now,
            now,
        ),
    )
    db.connection.commit()

    return {
        "id": session_id,
        "worker_id": worker_id,
        "provider": provider,
        "command": command,
        "args": args,
        "working_directory": working_directory,
        "tmux_session_name": tmux_session_name,
        "state": state,
        "state_version": 0,
        "started_at": now,
        "created_at": now,
        "updated_at": now,
    }


class StateTransitionConflictError(Exception):
    """Raised when an optimistic locking conflict occurs during state transition."""

    def __init__(
        self,
        session_id: str,
        expected_state: Optional[str],
        expected_version: Optional[int],
        actual_state: Optional[str] = None,
        actual_version: Optional[int] = None,
    ):
        self.session_id = session_id
        self.expected_state = expected_state
        self.expected_version = expected_version
        self.actual_state = actual_state
        self.actual_version = actual_version
        super().__init__(
            f"State transition conflict for session {session_id}: "
            f"expected state={expected_state}, version={expected_version}, "
            f"actual state={actual_state}, version={actual_version}"
        )


def update_session_state(
    db: "Database",
    session_id: str,
    state: str,
    pid: Optional[int] = None,
    stopped_at: Optional[datetime] = None,
) -> bool:
    """Update session state and optionally PID.

    Note: This is the simple version without optimistic locking.
    For concurrent-safe updates, use atomic_transition_session_state().

    Args:
        db: Database instance
        session_id: Session ID to update
        state: New state
        pid: Optional PID to update
        stopped_at: Optional stopped timestamp (for stopped/crashed states)

    Returns:
        True if session was updated, False if not found
    """
    now = datetime.now()

    if pid is not None:
        db.execute(
            """UPDATE sessions
               SET state = ?, pid = ?, stopped_at = ?, updated_at = ?,
                   state_version = state_version + 1
               WHERE id = ?""",
            (state, pid, stopped_at, now, session_id),
        )
    else:
        db.execute(
            """UPDATE sessions
               SET state = ?, stopped_at = ?, updated_at = ?,
                   state_version = state_version + 1
               WHERE id = ?""",
            (state, stopped_at, now, session_id),
        )

    db.connection.commit()
    return db.connection.total_changes > 0


def atomic_transition_session_state(
    db: "Database",
    session_id: str,
    new_state: str,
    expected_state: Optional[str] = None,
    expected_version: Optional[int] = None,
    pid: Optional[int] = None,
    stopped_at: Optional[datetime] = None,
) -> tuple[bool, int]:
    """Atomically transition session state with optimistic locking.

    This function implements the SELECT ... FOR UPDATE pattern using
    SQLite's transaction isolation. It ensures that concurrent state
    changes don't corrupt the session state.

    Args:
        db: Database instance
        session_id: Session ID to update
        new_state: New state to transition to
        expected_state: Optional expected current state (for validation)
        expected_version: Optional expected version (for strict locking)
        pid: Optional PID to update
        stopped_at: Optional stopped timestamp

    Returns:
        Tuple of (success: bool, new_version: int)
        - success is True if transition happened, False if session not found
        - new_version is the new state_version after transition

    Raises:
        StateTransitionConflictError: If expected_state or expected_version
            don't match the current values (concurrent modification detected)
    """
    now = datetime.now()

    # Use a transaction to ensure atomicity
    with db.transaction() as cursor:
        # First, read the current state (acts as row lock in SQLite)
        cursor.execute(
            "SELECT state, state_version FROM sessions WHERE id = ?",
            (session_id,),
        )
        row = cursor.fetchone()

        if row is None:
            return (False, 0)

        current_state = row[0]
        current_version = row[1] if row[1] is not None else 0

        # Check expected state if provided
        if expected_state is not None and current_state != expected_state:
            raise StateTransitionConflictError(
                session_id=session_id,
                expected_state=expected_state,
                expected_version=expected_version,
                actual_state=current_state,
                actual_version=current_version,
            )

        # Check expected version if provided
        if expected_version is not None and current_version != expected_version:
            raise StateTransitionConflictError(
                session_id=session_id,
                expected_state=expected_state,
                expected_version=expected_version,
                actual_state=current_state,
                actual_version=current_version,
            )

        # Perform the update
        new_version = current_version + 1

        if pid is not None:
            cursor.execute(
                """UPDATE sessions
                   SET state = ?, state_version = ?, pid = ?,
                       stopped_at = ?, updated_at = ?
                   WHERE id = ?""",
                (new_state, new_version, pid, stopped_at, now, session_id),
            )
        else:
            cursor.execute(
                """UPDATE sessions
                   SET state = ?, state_version = ?, stopped_at = ?, updated_at = ?
                   WHERE id = ?""",
                (new_state, new_version, stopped_at, now, session_id),
            )

        return (True, new_version)


def get_session_state_and_version(
    db: "Database",
    session_id: str,
) -> Optional[tuple[str, int]]:
    """Get current state and version for a session.

    Args:
        db: Database instance
        session_id: Session ID

    Returns:
        Tuple of (state, version) or None if not found
    """
    row = db.fetchone(
        "SELECT state, state_version FROM sessions WHERE id = ?",
        (session_id,),
    )
    if row is None:
        return None
    return (row["state"], row["state_version"] if row["state_version"] is not None else 0)


def update_session_pid(
    db: "Database",
    session_id: str,
    pid: int,
) -> bool:
    """Update session PID.

    Args:
        db: Database instance
        session_id: Session ID to update
        pid: Process ID

    Returns:
        True if session was updated, False if not found
    """
    now = datetime.now()
    db.execute(
        """UPDATE sessions SET pid = ?, updated_at = ? WHERE id = ?""",
        (pid, now, session_id),
    )
    db.connection.commit()
    return db.connection.total_changes > 0


def update_session_tmux_name(
    db: "Database",
    session_id: str,
    tmux_session_name: str,
) -> bool:
    """Update session tmux session name.

    Args:
        db: Database instance
        session_id: Session ID to update
        tmux_session_name: Tmux session name

    Returns:
        True if session was updated, False if not found
    """
    now = datetime.now()
    db.execute(
        """UPDATE sessions SET tmux_session_name = ?, updated_at = ? WHERE id = ?""",
        (tmux_session_name, now, session_id),
    )
    db.connection.commit()
    return db.connection.total_changes > 0


def get_session_by_id(
    db: "Database",
    session_id: str,
) -> Optional[dict]:
    """Get session record by ID.

    Args:
        db: Database instance
        session_id: Session ID

    Returns:
        Dict with session data or None if not found
    """
    row = db.fetchone(
        "SELECT * FROM sessions WHERE id = ?",
        (session_id,),
    )
    if row is None:
        return None

    return _row_to_dict(row)


def get_session_for_worker(
    db: "Database",
    worker_id: str,
) -> Optional[dict]:
    """Get session record for a worker.

    Since sessions are 1:1 with workers, this returns the single
    session for the given worker if it exists.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        Dict with session data or None if not found
    """
    row = db.fetchone(
        "SELECT * FROM sessions WHERE worker_id = ?",
        (worker_id,),
    )
    if row is None:
        return None

    return _row_to_dict(row)


def get_active_sessions(db: "Database") -> list[dict]:
    """Get all active sessions.

    Active sessions are those in 'starting', 'running', or 'idle' state.

    Args:
        db: Database instance

    Returns:
        List of session dicts
    """
    rows = db.fetchall(
        """SELECT * FROM sessions
           WHERE state IN ('starting', 'running', 'idle')
           ORDER BY started_at DESC"""
    )
    return [_row_to_dict(row) for row in rows]


def get_all_sessions(db: "Database") -> list[dict]:
    """Get all session records.

    Args:
        db: Database instance

    Returns:
        List of session dicts
    """
    rows = db.fetchall(
        "SELECT * FROM sessions ORDER BY created_at DESC"
    )
    return [_row_to_dict(row) for row in rows]


def count_active_sessions(db: "Database") -> int:
    """Count active sessions.

    Active sessions are those in 'starting', 'running', or 'idle' state.

    Args:
        db: Database instance

    Returns:
        Count of active sessions
    """
    row = db.fetchone(
        """SELECT COUNT(*) as count FROM sessions
           WHERE state IN ('starting', 'running', 'idle')"""
    )
    return row["count"] if row else 0


def delete_session_record(
    db: "Database",
    session_id: str,
) -> bool:
    """Delete a session record.

    Args:
        db: Database instance
        session_id: Session ID to delete

    Returns:
        True if session was deleted, False if not found
    """
    db.execute(
        "DELETE FROM sessions WHERE id = ?",
        (session_id,),
    )
    db.connection.commit()
    return db.connection.total_changes > 0


def delete_session_for_worker(
    db: "Database",
    worker_id: str,
) -> bool:
    """Delete session record for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        True if session was deleted, False if not found
    """
    db.execute(
        "DELETE FROM sessions WHERE worker_id = ?",
        (worker_id,),
    )
    db.connection.commit()
    return db.connection.total_changes > 0


def _row_to_dict(row) -> dict:
    """Convert a database row to a dict with parsed JSON fields.

    Args:
        row: Database row (sqlite3.Row)

    Returns:
        Dict with session data
    """
    result = dict(row)

    # Parse args JSON if present
    if result.get("args"):
        try:
            result["args"] = json.loads(result["args"])
        except json.JSONDecodeError:
            result["args"] = []

    return result
