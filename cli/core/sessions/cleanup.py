"""
Session cleanup functions for handling orphaned resources.

Handles two types of orphaned resources:
1. Orphaned tmux sessions: tmux sessions that exist but aren't tracked in the database
2. Stale database records: session records where the tmux session no longer exists

These orphans can occur when:
- Worker process crashes unexpectedly
- System restart without proper shutdown
- Manual tmux session deletion
- Database corruption or rollback
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from .tmux_spawner import TmuxSpawner
from .persistence import (
    get_all_sessions,
    get_active_sessions,
    update_session_state,
    delete_session_record,
)

if TYPE_CHECKING:
    from ..db import Database

from ..constants import TMUX_SESSION_PREFIX


@dataclass
class OrphanedSession:
    """Represents an orphaned session resource."""

    session_name: str
    """Tmux session name."""

    source: str
    """Where the orphan was detected: 'tmux' (exists in tmux but not DB) or 'database' (in DB but no tmux)."""

    worker_id: Optional[str] = None
    """Worker ID if known from database record."""

    session_id: Optional[str] = None
    """Session ID if known from database record."""

    state: Optional[str] = None
    """Last known state from database."""


@dataclass
class CleanupResult:
    """Result of a cleanup operation."""

    orphaned_tmux_sessions: list[str]
    """Tmux sessions that were detected as orphaned."""

    stale_db_records: list[str]
    """Database session IDs that were stale."""

    tmux_sessions_killed: int
    """Number of tmux sessions that were killed."""

    db_records_updated: int
    """Number of database records that were marked as crashed."""

    db_records_deleted: int
    """Number of database records that were deleted."""

    errors: list[str]
    """Any errors encountered during cleanup."""


def find_orphaned_tmux_sessions(
    db: "Database",
    tmux_spawner: Optional[TmuxSpawner] = None,
) -> list[OrphanedSession]:
    """Find tmux sessions that exist but aren't tracked in the database.

    Scans for tmux sessions with the quinnai prefix (qn-*) and checks
    if they have a corresponding active database record.

    Args:
        db: Database instance
        tmux_spawner: Optional TmuxSpawner instance (creates default if None)

    Returns:
        List of OrphanedSession objects for tmux-only sessions
    """
    if tmux_spawner is None:
        tmux_spawner = TmuxSpawner()

    orphans = []

    # Get all tmux sessions
    all_tmux_sessions = tmux_spawner.list_sessions()

    # Filter to quinnai sessions only
    qn_tmux_sessions = [
        s for s in all_tmux_sessions
        if s.startswith(TMUX_SESSION_PREFIX)
    ]

    # Get all tracked sessions from database
    db_sessions = get_all_sessions(db)
    tracked_tmux_names = {
        s.get("tmux_session_name")
        for s in db_sessions
        if s.get("tmux_session_name")
    }

    # Find tmux sessions not in database
    for tmux_name in qn_tmux_sessions:
        if tmux_name not in tracked_tmux_names:
            orphans.append(OrphanedSession(
                session_name=tmux_name,
                source="tmux",
            ))

    return orphans


def find_stale_db_sessions(
    db: "Database",
    tmux_spawner: Optional[TmuxSpawner] = None,
) -> list[OrphanedSession]:
    """Find database session records where the tmux session no longer exists.

    Checks active database records (starting, running, idle) to see if
    their tmux sessions still exist.

    Args:
        db: Database instance
        tmux_spawner: Optional TmuxSpawner instance (creates default if None)

    Returns:
        List of OrphanedSession objects for database-only records
    """
    if tmux_spawner is None:
        tmux_spawner = TmuxSpawner()

    orphans = []

    # Get active sessions from database
    active_sessions = get_active_sessions(db)

    for session in active_sessions:
        tmux_name = session.get("tmux_session_name")

        # Skip sessions without tmux (e.g., subprocess spawner)
        if not tmux_name:
            continue

        # Check if tmux session exists
        if not tmux_spawner.is_alive(tmux_name):
            orphans.append(OrphanedSession(
                session_name=tmux_name,
                source="database",
                worker_id=session.get("worker_id"),
                session_id=session.get("id"),
                state=session.get("state"),
            ))

    return orphans


def find_all_orphans(
    db: "Database",
    tmux_spawner: Optional[TmuxSpawner] = None,
) -> list[OrphanedSession]:
    """Find all orphaned session resources.

    Combines results from both tmux and database checks.

    Args:
        db: Database instance
        tmux_spawner: Optional TmuxSpawner instance

    Returns:
        List of all OrphanedSession objects
    """
    if tmux_spawner is None:
        tmux_spawner = TmuxSpawner()

    orphans = []
    orphans.extend(find_orphaned_tmux_sessions(db, tmux_spawner))
    orphans.extend(find_stale_db_sessions(db, tmux_spawner))

    return orphans


def cleanup_orphaned_sessions(
    db: "Database",
    tmux_spawner: Optional[TmuxSpawner] = None,
    kill_tmux: bool = True,
    update_db: bool = True,
    delete_stale: bool = False,
) -> CleanupResult:
    """Clean up orphaned session resources.

    Handles both orphaned tmux sessions and stale database records.

    For orphaned tmux sessions (exist in tmux but not tracked):
    - If kill_tmux=True, kills the tmux session

    For stale database records (tracked but tmux gone):
    - If update_db=True, marks session state as 'crashed'
    - If delete_stale=True, deletes the record entirely

    Args:
        db: Database instance
        tmux_spawner: Optional TmuxSpawner instance
        kill_tmux: Whether to kill orphaned tmux sessions
        update_db: Whether to update stale database records
        delete_stale: Whether to delete stale records instead of marking crashed

    Returns:
        CleanupResult with details of actions taken
    """
    if tmux_spawner is None:
        tmux_spawner = TmuxSpawner()

    result = CleanupResult(
        orphaned_tmux_sessions=[],
        stale_db_records=[],
        tmux_sessions_killed=0,
        db_records_updated=0,
        db_records_deleted=0,
        errors=[],
    )

    # Find and handle orphaned tmux sessions
    tmux_orphans = find_orphaned_tmux_sessions(db, tmux_spawner)
    for orphan in tmux_orphans:
        result.orphaned_tmux_sessions.append(orphan.session_name)

        if kill_tmux:
            try:
                if tmux_spawner.stop(orphan.session_name, force=True):
                    result.tmux_sessions_killed += 1
                else:
                    result.errors.append(
                        f"Failed to kill tmux session: {orphan.session_name}"
                    )
            except Exception as e:
                result.errors.append(
                    f"Error killing tmux session {orphan.session_name}: {e}"
                )

    # Find and handle stale database records
    db_orphans = find_stale_db_sessions(db, tmux_spawner)
    for orphan in db_orphans:
        if orphan.session_id:
            result.stale_db_records.append(orphan.session_id)

        if not update_db:
            continue

        try:
            if delete_stale:
                # Delete the record
                if orphan.session_id and delete_session_record(db, orphan.session_id):
                    result.db_records_deleted += 1
            else:
                # Mark as crashed
                if orphan.session_id:
                    update_session_state(
                        db=db,
                        session_id=orphan.session_id,
                        state="crashed",
                        stopped_at=datetime.now(),
                    )
                    result.db_records_updated += 1
        except Exception as e:
            result.errors.append(
                f"Error updating session {orphan.session_id}: {e}"
            )

    return result


def run_startup_cleanup(
    db: "Database",
    tmux_spawner: Optional[TmuxSpawner] = None,
) -> CleanupResult:
    """Run cleanup suitable for application startup.

    This is a convenience function that:
    - Kills orphaned tmux sessions
    - Marks stale database records as crashed (but doesn't delete them)

    Call this when starting the application to reconcile any orphaned
    resources from previous crashes.

    Args:
        db: Database instance
        tmux_spawner: Optional TmuxSpawner instance

    Returns:
        CleanupResult with details of actions taken
    """
    return cleanup_orphaned_sessions(
        db=db,
        tmux_spawner=tmux_spawner,
        kill_tmux=True,
        update_db=True,
        delete_stale=False,
    )


@dataclass
class StopAllSessionsResult:
    """Result of stopping all sessions."""

    sessions_found: int
    """Number of active sessions found."""

    sessions_stopped: int
    """Number of sessions successfully stopped."""

    tmux_sessions_killed: int
    """Number of tmux sessions killed."""

    errors: list[str]
    """Errors encountered during stop."""


def stop_all_sessions(
    db: "Database",
    tmux_spawner: Optional[TmuxSpawner] = None,
    force: bool = False,
    timeout_seconds: int = 5,
) -> StopAllSessionsResult:
    """Stop all active sessions gracefully.

    Called during org stop to ensure all worker sessions are terminated
    before the org transitions to stopped state.

    For each active session:
    1. If has tmux_session_name, kills the tmux session
    2. Updates database state to 'stopped'
    3. Updates worker runtime state

    Args:
        db: Database instance
        tmux_spawner: Optional TmuxSpawner instance (creates default if None)
        force: If True, force kill without waiting for graceful shutdown
        timeout_seconds: Seconds to wait for graceful shutdown (unused for now)

    Returns:
        StopAllSessionsResult with summary of actions taken
    """
    if tmux_spawner is None:
        tmux_spawner = TmuxSpawner()

    result = StopAllSessionsResult(
        sessions_found=0,
        sessions_stopped=0,
        tmux_sessions_killed=0,
        errors=[],
    )

    # Get all active sessions
    active_sessions = get_active_sessions(db)
    result.sessions_found = len(active_sessions)

    for session in active_sessions:
        session_id = session.get("id")
        worker_id = session.get("worker_id")
        tmux_name = session.get("tmux_session_name")

        try:
            # Kill tmux session if it exists
            if tmux_name and tmux_spawner.is_alive(tmux_name):
                if tmux_spawner.stop(tmux_name, force=force):
                    result.tmux_sessions_killed += 1
                else:
                    result.errors.append(
                        f"Failed to kill tmux session: {tmux_name}"
                    )

            # Update session state to stopped
            if session_id:
                update_session_state(
                    db=db,
                    session_id=session_id,
                    state="stopped",
                    stopped_at=datetime.now(),
                )

            # Update worker runtime state
            if worker_id:
                from cli.core.queries import update_worker_runtime_status
                update_worker_runtime_status(db, worker_id, "stopped")

            result.sessions_stopped += 1

        except Exception as e:
            result.errors.append(
                f"Error stopping session {session_id}: {e}"
            )

    return result
