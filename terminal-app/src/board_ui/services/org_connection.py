"""
Concrete OrgConnection implementation for QuinnAI orgs.

Connects to a QuinnAI org's SQLite database to provide read access
to org state, workers, messages, OKRs, and budget information.

The board TUI is independent of org lifecycle - orgs can run without board,
board can connect/disconnect at will.
"""

import json
import logging
import subprocess
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

from ..interfaces.org_connection import (
    OrgConnection,
    OrgInfo,
    OrgStatus,
    WorkerInfo,
    WorkerStatus,
    SessionState,
    BudgetSummary,
    Message,
    OKRInfo,
)


class OrgConnectionError(Exception):
    """Base exception for org connection errors."""

    pass


class OrgNotFound(OrgConnectionError):
    """Raised when org path doesn't exist or is invalid."""

    def __init__(self, path: Path):
        self.path = path
        super().__init__(f"Org not found at: {path}")


class DatabaseNotFound(OrgConnectionError):
    """Raised when org database doesn't exist."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        super().__init__(f"Database not found: {db_path}")


class DatabaseCorrupt(OrgConnectionError):
    """Raised when database file is corrupt or malformed."""

    def __init__(self, db_path: Path, original_error: Exception):
        self.db_path = db_path
        self.original_error = original_error
        super().__init__(
            f"Database is corrupt or malformed at {db_path}: {original_error}"
        )


class DatabaseLocked(OrgConnectionError):
    """Raised when database is locked by another process."""

    def __init__(self, db_path: Path, original_error: Exception):
        self.db_path = db_path
        self.original_error = original_error
        super().__init__(
            f"Database is locked at {db_path}. Another process may be using it: {original_error}"
        )


class _Sqlite3Wrapper:
    """Minimal wrapper around sqlite3 to match CLI Database interface.

    Used as a fallback when cli.core.db.Database is not available.
    Provides the same interface for fetchone, fetchall, execute, and close.

    Raises:
        DatabaseCorrupt: If database file is corrupt or malformed
        DatabaseLocked: If database is locked by another process
        OrgConnectionError: For other database connection errors
    """

    def __init__(self, db_path: Path):
        import sqlite3

        self._db_path = db_path
        try:
            self._conn = sqlite3.connect(str(db_path), timeout=10.0)
            self._conn.row_factory = sqlite3.Row
            # Verify database is readable by executing a simple query
            self._conn.execute("SELECT 1")
        except sqlite3.DatabaseError as e:
            error_msg = str(e).lower()
            if "corrupt" in error_msg or "malformed" in error_msg:
                raise DatabaseCorrupt(db_path, e)
            raise OrgConnectionError(f"Database error at {db_path}: {e}")
        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "locked" in error_msg:
                raise DatabaseLocked(db_path, e)
            raise OrgConnectionError(f"Cannot open database at {db_path}: {e}")
        except PermissionError as e:
            raise OrgConnectionError(
                f"Permission denied accessing database at {db_path}: {e}"
            )
        except Exception as e:
            raise OrgConnectionError(f"Failed to connect to database at {db_path}: {e}")

    @property
    def connection(self):
        """Return the underlying sqlite3 connection."""
        return self._conn

    def fetchone(self, sql: str, params: tuple = ()) -> Optional[Any]:
        """Execute SQL and fetch one row."""
        cursor = self._conn.execute(sql, params)
        return cursor.fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> list:
        """Execute SQL and fetch all rows."""
        cursor = self._conn.execute(sql, params)
        return cursor.fetchall()

    def execute(self, sql: str, params: tuple = ()) -> None:
        """Execute SQL statement."""
        self._conn.execute(sql, params)

    def close(self) -> None:
        """Close the connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


class QuinnAIOrgConnection(OrgConnection):
    """Connection to a QuinnAI org via SQLite database.

    Provides read-only access to org state for the board TUI.
    Connects to the org's quinn.db at {org_path}/live/quinn.db.

    Example:
        conn = QuinnAIOrgConnection(Path("/path/to/my-org"))
        if conn.is_connected:
            info = conn.get_org_info()
            workers = conn.get_workers()
    """

    # Database path pattern relative to org root
    DB_RELATIVE_PATH = Path("live") / "quinn.db"

    # Board channel names (preferred first, then fallback)
    BOARD_CHANNEL = "board-channel"
    ESCALATIONS_CHANNEL = "escalations"  # Backward compatibility

    def __init__(self, org_path: Path, database_factory: Optional[Callable] = None):
        """Initialize connection to an org.

        Args:
            org_path: Path to the org folder (contains live/quinn.db)
            database_factory: Optional factory function for creating database connections.
                              If not provided, uses the CLI's Database class.

        Raises:
            OrgNotFound: If org_path doesn't exist
        """
        self._org_path = org_path.resolve()
        self._db = None
        self._connected = False
        self._database_factory = database_factory

        # Real-time update tracking
        self._subscribers: list[Callable[[str, Any], None]] = []
        self._last_wal_pages: Optional[int] = None
        self._polling_enabled = False
        self._subscriber_lock = threading.Lock()  # Protects subscriber list modifications

        # Validate org path exists
        if not self._org_path.exists():
            raise OrgNotFound(self._org_path)

        # Attempt to connect
        self._connect()

    def _get_db_path(self) -> Path:
        """Get the database path for this org."""
        return self._org_path / self.DB_RELATIVE_PATH

    def _connect(self) -> None:
        """Connect to the org database.

        Raises:
            DatabaseNotFound: If database doesn't exist
            DatabaseCorrupt: If database file is corrupt or malformed
            DatabaseLocked: If database is locked by another process
            OrgConnectionError: For other database connection errors
        """
        import sqlite3

        db_path = self._get_db_path()
        if not db_path.exists():
            raise DatabaseNotFound(db_path)

        # Use provided factory or import Database from CLI core
        try:
            if self._database_factory:
                self._db = self._database_factory(db_path)
            else:
                # Try to import Database from CLI core (thread-safe with WAL mode)
                # Fall back to raw sqlite3 if CLI module not available
                try:
                    from cli.core.db import Database

                    self._db = Database(db_path)
                except ImportError:
                    # CLI module not available - use sqlite3 directly
                    # _Sqlite3Wrapper handles its own error conversion
                    self._db = _Sqlite3Wrapper(db_path)
        except (DatabaseCorrupt, DatabaseLocked, OrgConnectionError):
            # Re-raise our custom exceptions as-is
            raise
        except sqlite3.DatabaseError as e:
            error_msg = str(e).lower()
            if "corrupt" in error_msg or "malformed" in error_msg:
                raise DatabaseCorrupt(db_path, e)
            raise OrgConnectionError(f"Database error at {db_path}: {e}")
        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "locked" in error_msg:
                raise DatabaseLocked(db_path, e)
            raise OrgConnectionError(f"Cannot open database at {db_path}: {e}")
        except PermissionError as e:
            raise OrgConnectionError(
                f"Permission denied accessing database at {db_path}: {e}"
            )
        except Exception as e:
            # Catch any other unexpected errors
            if isinstance(e, OrgConnectionError):
                raise
            raise OrgConnectionError(f"Failed to connect to database at {db_path}: {e}")

        self._connected = True

    def _disconnect(self) -> None:
        """Disconnect from the org database."""
        # Clear subscribers and disable polling (thread-safe)
        with self._subscriber_lock:
            self._subscribers.clear()
            self._polling_enabled = False
            self._last_wal_pages = None

        if self._db is not None:
            self._db.close()
            self._db = None
        self._connected = False

    def _ensure_connected(self) -> None:
        """Ensure we have an active database connection.

        Raises:
            OrgConnectionError: If not connected
        """
        if not self._connected or self._db is None:
            raise OrgConnectionError("Not connected to org")

    # ==================
    # PROPERTIES
    # ==================

    @property
    def org_path(self) -> Path:
        """Path to the connected org."""
        return self._org_path

    @property
    def is_connected(self) -> bool:
        """Check if currently connected to an org."""
        return self._connected and self._db is not None

    # ==================
    # ORG STATE
    # ==================

    def get_org_info(self) -> OrgInfo:
        """Get current org information.

        Returns:
            OrgInfo with current org state
        """
        self._ensure_connected()

        # Get org state from database
        row = self._db.fetchone("SELECT * FROM org_state WHERE id = 'default'")

        if not row:
            # Uninitialized org
            return OrgInfo(
                path=self._org_path,
                name=self._org_path.name,
                status=OrgStatus.UNINITIALIZED,
                ceo_worker_id=None,
                worker_count=0,
                active_session_count=0,
                started_at=None,
                stopped_at=None,
            )

        # Get counts
        worker_count = self._get_worker_count()
        active_session_count = self._get_active_session_count()

        # Parse status
        status_str = row["status"]
        try:
            status = OrgStatus(status_str)
        except ValueError:
            status = OrgStatus.UNINITIALIZED

        # Parse timestamps
        started_at = self._parse_datetime(row["started_at"])
        stopped_at = self._parse_datetime(row["stopped_at"])

        return OrgInfo(
            path=self._org_path,
            name=self._org_path.name,
            status=status,
            ceo_worker_id=row["ceo_worker_id"],
            worker_count=worker_count,
            active_session_count=active_session_count,
            started_at=started_at,
            stopped_at=stopped_at,
        )

    def _get_worker_count(self) -> int:
        """Get total worker count."""
        row = self._db.fetchone("SELECT COUNT(*) as count FROM workers")
        return row["count"] if row else 0

    def _get_active_session_count(self) -> int:
        """Get count of active sessions."""
        # Try sessions table first (new)
        try:
            row = self._db.fetchone(
                """SELECT COUNT(*) as count FROM sessions
                   WHERE state IN ('starting', 'running', 'idle')"""
            )
            if row and row["count"] > 0:
                return row["count"]
        except Exception:
            # sessions table doesn't exist, try fallback
            pass

        # Fall back to worker_state for backwards compatibility
        try:
            row = self._db.fetchone(
                """SELECT COUNT(*) as count FROM worker_state
                   WHERE runtime_status IN ('starting', 'running', 'idle')"""
            )
            return row["count"] if row else 0
        except Exception as e:
            # Both tables failed - unexpected schema
            logger.warning(
                "Failed to query session tables, org database may have unexpected schema: %s",
                e,
            )
            return 0

    def get_budget_summary(self) -> BudgetSummary:
        """Get budget summary for the org.

        Returns:
            BudgetSummary with current budget state
        """
        self._ensure_connected()

        # Get current budget pool
        now = datetime.now()
        pool_row = self._db.fetchone(
            """SELECT * FROM budget_pools
               WHERE period_start <= ? AND period_end >= ?
               ORDER BY created_at DESC LIMIT 1""",
            (now, now),
        )

        if not pool_row:
            # No active budget pool
            return BudgetSummary(
                total_allocated=0.0,
                total_spent=0.0,
                total_available=0.0,
                period_start=now,
                period_end=now + timedelta(days=30),
                spend_today=0.0,
                spend_this_week=0.0,
            )

        pool_id = pool_row["id"]
        period_start = self._parse_datetime(pool_row["period_start"]) or now
        period_end = self._parse_datetime(pool_row["period_end"]) or (
            now + timedelta(days=30)
        )

        # Get totals from budget_balances
        totals_row = self._db.fetchone(
            """SELECT
                   SUM(allocated) as total_allocated,
                   SUM(spent) as total_spent,
                   SUM(available) as total_available
               FROM budget_balances bb
               JOIN budget_allocations ba ON bb.allocation_id = ba.id
               WHERE ba.pool_id = ?""",
            (pool_id,),
        )

        # Fallback to zeros if budget_balances is empty
        # This handles orgs initialized before budget_balances was properly created
        if totals_row["total_allocated"] is None:
            total_allocated = 0.0
            total_spent = 0.0
            total_available = 0.0
        else:
            total_allocated = float(totals_row["total_allocated"] or 0)
            total_spent = float(totals_row["total_spent"] or 0)
            total_available = float(totals_row["total_available"] or 0)

        # Calculate spend today
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        spend_today_row = self._db.fetchone(
            """SELECT SUM(ABS(amount)) as total
               FROM budget_transactions
               WHERE type = 'spend' AND created_at >= ?""",
            (today_start,),
        )
        spend_today = float(spend_today_row["total"] or 0)

        # Calculate spend this week
        week_start = today_start - timedelta(days=today_start.weekday())
        spend_week_row = self._db.fetchone(
            """SELECT SUM(ABS(amount)) as total
               FROM budget_transactions
               WHERE type = 'spend' AND created_at >= ?""",
            (week_start,),
        )
        spend_this_week = float(spend_week_row["total"] or 0)

        return BudgetSummary(
            total_allocated=total_allocated,
            total_spent=total_spent,
            total_available=total_available,
            period_start=period_start,
            period_end=period_end,
            spend_today=spend_today,
            spend_this_week=spend_this_week,
        )

    # ==================
    # WORKERS
    # ==================

    def get_workers(self) -> list[WorkerInfo]:
        """Get all workers in the org.

        Returns:
            List of WorkerInfo sorted by hierarchy (CEO first)
        """
        self._ensure_connected()

        # Get all workers with team info
        rows = self._db.fetchall(
            """SELECT w.*, t.name as team_name
               FROM workers w
               JOIN teams t ON w.team_id = t.id
               ORDER BY w.manager_id NULLS FIRST, w.created_at"""
        )

        # Get session states for all workers
        session_states = self._get_worker_session_states()

        # Get CEO worker ID
        org_row = self._db.fetchone(
            "SELECT ceo_worker_id FROM org_state WHERE id = 'default'"
        )
        ceo_id = org_row["ceo_worker_id"] if org_row else None

        workers = []
        for row in rows:
            worker_id = row["id"]
            session_info = session_states.get(worker_id, {})
            is_ceo = (worker_id == ceo_id)
            role = row["role"]
            manager_id = row["manager_id"]

            # Determine session mode: CEOs and managers default to autonomous
            # is_manager = no manager_id AND not CEO
            is_manager = (manager_id is None) and not is_ceo
            session_mode = "autonomous" if (is_ceo or is_manager) else "interactive"

            workers.append(
                WorkerInfo(
                    id=worker_id,
                    name=row["name"],
                    role=role,
                    team_name=row["team_name"],
                    status=self._parse_worker_status(row["status"]),
                    session_state=self._parse_session_state(
                        session_info.get("state")
                    ),
                    tmux_session_name=session_info.get("tmux_session_name"),
                    manager_id=manager_id,
                    current_task=session_info.get("current_task_id"),
                    is_ceo=is_ceo,
                    session_mode=session_mode,
                )
            )

        return workers

    def get_worker(self, worker_id: str) -> Optional[WorkerInfo]:
        """Get a specific worker by ID.

        Args:
            worker_id: Worker ID to look up

        Returns:
            WorkerInfo or None if not found
        """
        self._ensure_connected()

        row = self._db.fetchone(
            """SELECT w.*, t.name as team_name
               FROM workers w
               JOIN teams t ON w.team_id = t.id
               WHERE w.id = ?""",
            (worker_id,),
        )

        if not row:
            return None

        # Get session state
        session_info = self._get_worker_session_state(worker_id)

        # Check if CEO
        org_row = self._db.fetchone(
            "SELECT ceo_worker_id FROM org_state WHERE id = 'default'"
        )
        ceo_id = org_row["ceo_worker_id"] if org_row else None
        is_ceo = (worker_id == ceo_id)
        manager_id = row["manager_id"]

        # Determine session mode
        is_manager = (manager_id is None) and not is_ceo
        session_mode = "autonomous" if (is_ceo or is_manager) else "interactive"

        return WorkerInfo(
            id=worker_id,
            name=row["name"],
            role=row["role"],
            team_name=row["team_name"],
            status=self._parse_worker_status(row["status"]),
            session_state=self._parse_session_state(session_info.get("state")),
            tmux_session_name=session_info.get("tmux_session_name"),
            manager_id=manager_id,
            current_task=session_info.get("current_task_id"),
            is_ceo=is_ceo,
            session_mode=session_mode,
        )

    def get_ceo(self) -> Optional[WorkerInfo]:
        """Get the CEO worker.

        Returns:
            WorkerInfo for CEO or None if org not initialized
        """
        self._ensure_connected()

        # Get CEO worker ID
        org_row = self._db.fetchone(
            "SELECT ceo_worker_id FROM org_state WHERE id = 'default'"
        )

        if not org_row or not org_row["ceo_worker_id"]:
            return None

        return self.get_worker(org_row["ceo_worker_id"])

    def _get_worker_session_states(self) -> dict[str, dict]:
        """Get session states for all workers.

        Returns:
            Dict mapping worker_id to session info dict
        """
        # Try sessions table first
        rows = self._db.fetchall(
            """SELECT worker_id, state, tmux_session_name
               FROM sessions"""
        )

        result = {}
        for row in rows:
            result[row["worker_id"]] = {
                "state": row["state"],
                "tmux_session_name": row["tmux_session_name"],
            }

        # Add current task from worker_state
        state_rows = self._db.fetchall(
            """SELECT worker_id, current_task_id, runtime_status
               FROM worker_state"""
        )

        for row in state_rows:
            worker_id = row["worker_id"]
            if worker_id not in result:
                result[worker_id] = {"state": row["runtime_status"]}
            result[worker_id]["current_task_id"] = row["current_task_id"]

        return result

    def _get_worker_session_state(self, worker_id: str) -> dict:
        """Get session state for a specific worker.

        Returns:
            Dict with session info or empty dict
        """
        # Try sessions table first
        row = self._db.fetchone(
            """SELECT state, tmux_session_name
               FROM sessions WHERE worker_id = ?""",
            (worker_id,),
        )

        if row:
            result = {
                "state": row["state"],
                "tmux_session_name": row["tmux_session_name"],
            }
        else:
            result = {}

        # Add current task from worker_state
        state_row = self._db.fetchone(
            """SELECT current_task_id, runtime_status
               FROM worker_state WHERE worker_id = ?""",
            (worker_id,),
        )

        if state_row:
            if "state" not in result:
                result["state"] = state_row["runtime_status"]
            result["current_task_id"] = state_row["current_task_id"]

        return result

    # ==================
    # MESSAGES (BOARD INBOX)
    # ==================

    def _get_board_channel_id(self) -> Optional[str]:
        """Get board channel ID, trying board-channel first, then escalations."""
        # Try board-channel first (preferred)
        channel = self._db.fetchone(
            "SELECT id FROM channels WHERE name = ?",
            (self.BOARD_CHANNEL,),
        )
        if channel:
            return channel["id"]

        # Fallback to escalations (backward compat)
        channel = self._db.fetchone(
            "SELECT id FROM channels WHERE name = ?",
            (self.ESCALATIONS_CHANNEL,),
        )
        return channel["id"] if channel else None

    def get_board_messages(self, unread_only: bool = False) -> list[Message]:
        """Get messages escalated to the board.

        Messages from the board channel are treated as board messages.
        Tries board-channel first, then falls back to escalations for backward compatibility.

        Args:
            unread_only: If True, only return unread messages

        Returns:
            List of messages sorted by priority then recency
        """
        self._ensure_connected()

        # Get board channel (tries board-channel first, then escalations)
        channel_id = self._get_board_channel_id()

        if not channel_id:
            return []

        # Build query for messages
        if unread_only:
            # Join with notification_beads to check read status
            # Board messages are "unread" if they have pending notification beads
            rows = self._db.fetchall(
                """SELECT DISTINCT m.*,
                          COALESCE(w.name, m.from_worker_id) as from_worker_name,
                          c.name as channel_name
                   FROM messages m
                   LEFT JOIN workers w ON m.from_worker_id = w.id
                   JOIN channels c ON m.channel_id = c.id
                   JOIN notification_beads nb ON nb.message_id = m.id
                   WHERE m.channel_id = ? AND nb.status = 'pending'
                   ORDER BY m.priority DESC, m.created_at DESC""",
                (channel_id,),
            )
        else:
            rows = self._db.fetchall(
                """SELECT m.*,
                          COALESCE(w.name, m.from_worker_id) as from_worker_name,
                          c.name as channel_name
                   FROM messages m
                   LEFT JOIN workers w ON m.from_worker_id = w.id
                   JOIN channels c ON m.channel_id = c.id
                   WHERE m.channel_id = ?
                   ORDER BY m.priority DESC, m.created_at DESC""",
                (channel_id,),
            )

        messages = []
        for row in rows:
            # Check if message has been read (no pending notification beads)
            is_read = self._is_message_read(row["id"])

            messages.append(
                Message(
                    id=row["id"],
                    from_worker_id=row["from_worker_id"],
                    from_worker_name=row["from_worker_name"],
                    channel_name=row["channel_name"],
                    content=row["content"],
                    priority=row["priority"],
                    created_at=self._parse_datetime(row["created_at"]) or datetime.now(),
                    is_read=is_read,
                    requires_response=row["priority"] >= 3,  # High priority
                )
            )

        return messages

    def get_unread_count(self) -> int:
        """Get count of unread board messages.

        Returns:
            Number of unread messages
        """
        self._ensure_connected()

        # Get board channel (tries board-channel first, then escalations)
        channel_id = self._get_board_channel_id()

        if not channel_id:
            return 0

        # Count messages with pending notification beads
        count_row = self._db.fetchone(
            """SELECT COUNT(DISTINCT m.id) as count
               FROM messages m
               JOIN notification_beads nb ON nb.message_id = m.id
               WHERE m.channel_id = ? AND nb.status = 'pending'""",
            (channel_id,),
        )

        return count_row["count"] if count_row else 0

    def send_board_response(
        self,
        message_id: str,
        response: str,
    ) -> bool:
        """Send a board response to a message.

        Creates a reply message in the same channel as the original message.
        The response is async - workers will see it when they check.

        Args:
            message_id: ID of message being responded to
            response: Response content

        Returns:
            True if response was queued successfully
        """
        self._ensure_connected()

        # Get original message
        msg_row = self._db.fetchone(
            "SELECT channel_id, thread_id FROM messages WHERE id = ?",
            (message_id,),
        )

        if not msg_row:
            return False

        channel_id = msg_row["channel_id"]
        thread_id = msg_row["thread_id"] or message_id

        # Create response message
        # Use a special "board" worker ID for board responses
        import uuid

        response_id = f"msg-{str(uuid.uuid4())[:8]}"
        now = datetime.now()

        try:
            self._db.execute(
                """INSERT INTO messages
                   (id, channel_id, thread_id, parent_id, from_worker_id, content,
                    priority, time_sensitivity, created_at)
                   VALUES (?, ?, ?, ?, 'board', ?, 3, 'immediate', ?)""",
                (response_id, channel_id, thread_id, message_id, response, now),
            )
            self._db.connection.commit()

            # Mark original as read
            self.mark_message_read(message_id)

            return True
        except Exception:
            return False

    def mark_message_read(self, message_id: str) -> bool:
        """Mark a message as read.

        Closes all notification beads for this message.

        Args:
            message_id: ID of message to mark

        Returns:
            True if marked successfully
        """
        self._ensure_connected()

        try:
            now = datetime.now()
            self._db.execute(
                """UPDATE notification_beads
                   SET status = 'read', read_at = ?
                   WHERE message_id = ? AND status = 'pending'""",
                (now, message_id),
            )
            self._db.connection.commit()
            return True
        except Exception:
            return False

    def _is_message_read(self, message_id: str) -> bool:
        """Check if a message has been read (no pending notification beads)."""
        row = self._db.fetchone(
            """SELECT COUNT(*) as count FROM notification_beads
               WHERE message_id = ? AND status = 'pending'""",
            (message_id,),
        )
        return row["count"] == 0 if row else True

    # ==================
    # OKRS
    # ==================

    def get_okrs(self, owner_id: Optional[str] = None) -> list[OKRInfo]:
        """Get OKRs, optionally filtered by owner.

        Args:
            owner_id: If provided, only return OKRs owned by this worker

        Returns:
            List of OKRs in hierarchy order
        """
        self._ensure_connected()

        if owner_id:
            rows = self._db.fetchall(
                """SELECT o.*, w.name as owner_name
                   FROM okrs o
                   JOIN workers w ON o.owner_worker_id = w.id
                   WHERE o.owner_worker_id = ?
                   ORDER BY o.parent_okr_id NULLS FIRST, o.created_at""",
                (owner_id,),
            )
        else:
            rows = self._db.fetchall(
                """SELECT o.*, w.name as owner_name
                   FROM okrs o
                   JOIN workers w ON o.owner_worker_id = w.id
                   ORDER BY o.parent_okr_id NULLS FIRST, o.created_at"""
            )

        okrs = []
        for row in rows:
            # Parse key results from JSON (sqlite3.Row doesn't have .get())
            key_results = self._parse_key_results(row["key_results"])

            # Count children
            children_count = self._count_child_okrs(row["id"])

            okrs.append(
                OKRInfo(
                    id=row["id"],
                    title=row["title"],
                    description=row["description"],
                    owner_name=row["owner_name"],
                    owner_id=row["owner_worker_id"],
                    status=row["status"],
                    parent_id=row["parent_okr_id"],
                    key_results=key_results,
                    due_date=self._parse_datetime(row["due_date"]),
                    children_count=children_count,
                )
            )

        return okrs

    def _parse_key_results(self, kr_json: Optional[str]) -> list[dict[str, Any]]:
        """Parse key results from JSON string."""
        if not kr_json:
            return []
        try:
            return json.loads(kr_json)
        except (json.JSONDecodeError, TypeError):
            return []

    def _count_child_okrs(self, okr_id: str) -> int:
        """Count OKRs that have this OKR as parent."""
        row = self._db.fetchone(
            "SELECT COUNT(*) as count FROM okrs WHERE parent_okr_id = ?",
            (okr_id,),
        )
        return row["count"] if row else 0

    # ==================
    # ORG ACTIONS
    # ==================

    def start_org(self) -> bool:
        """Start the org (if stopped or initialized).

        Uses subprocess call to qn CLI to properly transition the org.
        This avoids direct dependency on cli.core.org which may not be available.

        Returns:
            True if org was started successfully
        """
        self._ensure_connected()

        # Check current status first
        org_info = self.get_org_info()
        if org_info.status not in (OrgStatus.INITIALIZED, OrgStatus.STOPPED):
            return False

        # Use subprocess-based start from org_discovery
        from .org_discovery import start_org as subprocess_start_org

        result = subprocess_start_org(self._org_path)
        return result.success

    def stop_org(self) -> bool:
        """Stop the org gracefully.

        Uses subprocess call to qn CLI to properly transition the org.
        This avoids direct dependency on cli.core.org which may not be available.

        Returns:
            True if org was stopped successfully
        """
        self._ensure_connected()

        # Check current status first
        org_info = self.get_org_info()
        if org_info.status != OrgStatus.RUNNING:
            return False

        # Use subprocess-based stop from org_discovery
        from .org_discovery import stop_org as subprocess_stop_org

        result = subprocess_stop_org(self._org_path)
        return result.success

    def restart_org(self) -> tuple[bool, str]:
        """Restart the org (stop then start).

        Uses subprocess calls to qn CLI for proper state transitions.

        Returns:
            Tuple of (success: bool, message: str)
        """
        self._ensure_connected()

        # Check current status
        org_info = self.get_org_info()
        if org_info.status not in (OrgStatus.RUNNING, OrgStatus.STOPPED):
            return False, f"Cannot restart org in status: {org_info.status.value}"

        # Use subprocess-based restart from org_discovery
        from .org_discovery import restart_org as subprocess_restart_org

        result = subprocess_restart_org(
            org_path=self._org_path,
            spawn_ceo=True,
            provider="claude_code",
            skip_config_validation=True,
        )
        return result.success, result.message

    # ==================
    # BOARD INTERVENTIONS
    # ==================

    def pause_worker(self, worker_id: str, reason: Optional[str] = None) -> bool:
        """Pause a worker via CLI command."""
        self._ensure_connected()

        try:
            cmd = ["qn", "board", "pause", worker_id, "--org-path", str(self._org_path)]
            if reason:
                cmd.extend(["--reason", reason])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                # Update session state to stopped
                self._db.execute(
                    "UPDATE sessions SET state = 'stopped' WHERE worker_id = ?",
                    (worker_id,)
                )
                self._db.connection.commit()

                self._log_intervention("pause", worker_id, reason or "Board paused worker")
                return True
            else:
                logger.error(f"Failed to pause worker {worker_id}: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Error pausing worker {worker_id}: {e}")
            return False

    def resume_worker(self, worker_id: str) -> bool:
        """Resume a worker via CLI command."""
        self._ensure_connected()

        try:
            result = subprocess.run(
                ["qn", "board", "resume", worker_id, "--org-path", str(self._org_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                # Update session state to running
                self._db.execute(
                    "UPDATE sessions SET state = 'running' WHERE worker_id = ?",
                    (worker_id,)
                )
                self._db.connection.commit()

                self._log_intervention("resume", worker_id, "Board resumed worker")
                return True
            else:
                logger.error(f"Failed to resume worker {worker_id}: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Error resuming worker {worker_id}: {e}")
            return False

    def fire_worker(self, worker_id: str, reason: Optional[str] = None) -> bool:
        """Terminate a worker via CLI command."""
        self._ensure_connected()

        try:
            cmd = ["qn", "board", "fire", worker_id, "--force", "--org-path", str(self._org_path)]
            if reason:
                cmd.extend(["--reason", reason])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                # Update worker status to terminated and session to stopped
                self._db.execute(
                    "UPDATE workers SET status = 'terminated' WHERE id = ?",
                    (worker_id,)
                )
                self._db.execute(
                    "UPDATE sessions SET state = 'stopped' WHERE worker_id = ?",
                    (worker_id,)
                )
                self._db.connection.commit()

                self._log_intervention("fire", worker_id, reason or "Board fired worker")
                self._notify_ceo_of_intervention("fire", worker_id, reason or "No reason provided")
                return True
            else:
                logger.error(f"Failed to fire worker {worker_id}: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Error firing worker {worker_id}: {e}")
            return False

    def _log_intervention(self, action: str, worker_id: str, reason: str) -> None:
        """Log intervention to board-channel."""
        try:
            now = datetime.now()
            import uuid

            channel_id = self._get_board_channel_id()
            if not channel_id:
                return

            message_id = f"msg-{str(uuid.uuid4())[:8]}"

            content = (
                f"**INTERVENTION: {action.upper()}**\n\n"
                f"Worker: {worker_id}\n"
                f"Reason: {reason}\n"
                f"Time: {now.isoformat()}"
            )

            self._db.execute(
                """INSERT INTO messages
                   (id, channel_id, from_worker_id, content, priority, time_sensitivity, created_at)
                   VALUES (?, ?, 'board', ?, 3, 'immediate', ?)""",
                (message_id, channel_id, content, now),
            )
            self._db.connection.commit()
        except Exception as e:
            logger.warning(f"Failed to log intervention: {e}")

    def _notify_ceo_of_intervention(self, action: str, worker_id: str, reason: str) -> None:
        """Notify CEO of board intervention by creating notification bead."""
        try:
            import uuid

            channel_id = self._get_board_channel_id()
            if not channel_id:
                return

            message_id = f"msg-{str(uuid.uuid4())[:8]}"
            now = datetime.now()

            content = (
                f"**BOARD INTERVENTION NOTIFICATION**\n\n"
                f"Action: {action.upper()}\n"
                f"Worker: {worker_id}\n"
                f"Reason: {reason}\n"
                f"Time: {now.isoformat()}"
            )

            # Create message
            self._db.execute(
                """INSERT INTO messages
                   (id, channel_id, from_worker_id, content, priority, time_sensitivity, created_at)
                   VALUES (?, ?, 'board', ?, 4, 'immediate', ?)""",
                (message_id, channel_id, content, now),
            )

            # Create notification bead for CEO
            ceo = self.get_ceo()
            if ceo:
                notification_id = f"nb-{str(uuid.uuid4())[:8]}"
                self._db.execute(
                    """INSERT INTO notification_beads
                       (id, worker_id, message_id, channel_id, status, priority, created_at, read_at, expires_at)
                       VALUES (?, ?, ?, ?, 'pending', 4, ?, NULL, NULL)""",
                    (notification_id, ceo.id, message_id, channel_id, now),
                )

            self._db.connection.commit()
        except Exception as e:
            logger.warning(f"Failed to notify CEO: {e}")

    # ==================
    # CEO BRIEFING
    # ==================

    def send_ceo_briefing(self, briefing_content: str) -> bool:
        """Send briefing to CEO as high-priority message."""
        self._ensure_connected()

        try:
            from cli.core.queries import create_message, generate_id
            from cli.core.notifications import create_notification_bead
        except ImportError:
            logger.warning(
                "CLI module not available; falling back to direct SQL for CEO briefing."
            )
            return self._send_ceo_briefing_fallback(briefing_content)

        try:
            ceo = self.get_ceo()
            if not ceo:
                return False

            channel_id = self._get_board_channel_id()
            if not channel_id:
                return False

            # Ensure content has CEO Briefing header if it doesn't already
            if "CEO Briefing" not in briefing_content:
                content = f"# CEO Briefing\n\n{briefing_content}"
            else:
                content = briefing_content

            # Create message from CEO
            message = create_message(
                db=self._db,
                channel_id=channel_id,
                from_worker_id=ceo.id,
                content=content,
                priority=0,
                time_sensitivity="immediate",
                message_id=generate_id("msg"),
            )

            # Create notification for CEO (normally sender doesn't get notified)
            # But for briefing, we want the CEO to see it as a notification
            create_notification_bead(
                db=self._db,
                worker_id=ceo.id,
                message_id=message.id,
                channel_id=channel_id,
                priority=0,
            )

            return True
        except Exception as e:
            logger.error(f"Failed to send CEO briefing: {e}")
            return False

    def _send_ceo_briefing_fallback(self, briefing_content: str) -> bool:
        """Fallback to direct SQL when CLI helpers are unavailable."""
        try:
            import uuid

            ceo = self.get_ceo()
            if not ceo:
                return False

            channel_id = self._get_board_channel_id()
            if not channel_id:
                return False

            if "CEO Briefing" not in briefing_content:
                content = f"# CEO Briefing\n\n{briefing_content}"
            else:
                content = briefing_content

            now = datetime.now()
            message_id = f"msg-{str(uuid.uuid4())[:8]}"
            self._db.execute(
                """INSERT INTO messages
                   (id, channel_id, from_worker_id, content, priority, time_sensitivity, created_at)
                   VALUES (?, ?, ?, ?, 0, 'immediate', ?)""",
                (message_id, channel_id, ceo.id, content, now),
            )

            notification_id = f"nb-{str(uuid.uuid4())[:8]}"
            self._db.execute(
                """INSERT INTO notification_beads
                   (id, worker_id, message_id, channel_id, status, priority, created_at, read_at, expires_at)
                   VALUES (?, ?, ?, ?, 'pending', 0, ?, NULL, NULL)""",
                (notification_id, ceo.id, message_id, channel_id, now),
            )
            self._db.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to send CEO briefing (fallback): {e}")
            return False

    def get_current_briefing(self) -> Optional[str]:
        """Get current CEO briefing from config."""
        self._ensure_connected()

        briefing_path = self._org_path / "config" / "ceo_briefing.md"
        if briefing_path.exists():
            return briefing_path.read_text()
        return None

    def update_briefing(self, briefing_content: str) -> bool:
        """Update CEO briefing and notify CEO."""
        self._ensure_connected()

        try:
            # Save to config
            config_path = self._org_path / "config" / "ceo_briefing.md"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(briefing_content)

            # Send to CEO
            return self.send_ceo_briefing(briefing_content)
        except Exception as e:
            logger.error(f"Failed to update briefing: {e}")
            return False

    # ==================
    # SUBSCRIPTIONS
    # ==================

    def subscribe_to_updates(
        self,
        callback: Callable[[str, Any], None],
    ) -> Callable[[], None]:
        """Subscribe to real-time org updates via SQLite WAL polling.

        Polls the database for changes and notifies subscribers when detected.
        Uses PRAGMA wal_checkpoint(PASSIVE) to track WAL page count, which
        increments on any database write (even from the same connection).

        Args:
            callback: Function called with (event_type, event_data) when changes detected.
                     event_type will be "database_changed"

        Returns:
            Function to call to unsubscribe
        """
        if not self._connected:
            logger.warning("Cannot subscribe: not connected to database")
            return lambda: None

        # Add subscriber to list (thread-safe)
        with self._subscriber_lock:
            self._subscribers.append(callback)

            # Initialize last_change_count on first subscriber
            if self._last_wal_pages is None:
                self._last_wal_pages = self._get_wal_page_count()

            # Enable polling if this is the first subscriber
            if len(self._subscribers) == 1:
                self._polling_enabled = True
                logger.info(f"Real-time updates enabled for {self._org_path}")

        # Return unsubscribe function
        def unsubscribe():
            with self._subscriber_lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)
                # Disable polling if no more subscribers
                if len(self._subscribers) == 0:
                    self._polling_enabled = False
                    self._last_wal_pages = None
                    logger.info(f"Real-time updates disabled for {self._org_path}")

        return unsubscribe

    def check_for_updates(self) -> bool:
        """Check if database has changed since last check.

        Uses SQLite's PRAGMA wal_checkpoint(PASSIVE) to track WAL page count.
        The page count increments on any write, even from the same connection.
        Should be called periodically (e.g., every 100-500ms) to poll for updates.

        Returns:
            True if changes were detected and subscribers notified
        """
        if not self._polling_enabled or not self._connected:
            return False

        # Get subscriber list snapshot (thread-safe)
        with self._subscriber_lock:
            if len(self._subscribers) == 0:
                return False
            subscribers_copy = list(self._subscribers)

        try:
            current_version = self._get_wal_page_count()

            # Check if WAL page count changed
            if self._last_wal_pages is not None and current_version != self._last_wal_pages:
                self._last_wal_pages = current_version
                # Notify all subscribers
                for subscriber in subscribers_copy:
                    try:
                        subscriber("database_changed", {"wal_pages": current_version})
                    except Exception as e:
                        logger.error(f"Error notifying subscriber: {e}")
                return True

            self._last_wal_pages = current_version
            return False

        except Exception as e:
            logger.error(f"Error checking for database updates: {e}")
            return False

    def _get_wal_page_count(self) -> int:
        """Get the current WAL page count to detect database changes.

        Uses PRAGMA wal_checkpoint(PASSIVE) which returns the number of pages
        in the WAL file. This increments whenever writes occur to the database,
        even from the same connection.

        Returns:
            Current WAL page count, or 0 if WAL not enabled or on error
        """
        if not self._db:
            return 0

        try:
            # PRAGMA wal_checkpoint(PASSIVE) returns (busy, log, checkpointed)
            # log = number of pages in WAL file (increments on writes)
            row = self._db.fetchone("PRAGMA wal_checkpoint(PASSIVE)")
            if row and len(row) >= 2:
                return int(row[1])  # WAL page count
            return 0
        except Exception as e:
            logger.error(f"Error fetching WAL page count: {e}")
            return 0

    # ==================
    # HELPER METHODS
    # ==================

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        """Parse datetime from various formats."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    def _parse_worker_status(self, status_str: str) -> WorkerStatus:
        """Parse worker status string to enum."""
        try:
            return WorkerStatus(status_str)
        except ValueError:
            return WorkerStatus.PENDING

    def _parse_session_state(self, state_str: Optional[str]) -> Optional[SessionState]:
        """Parse session state string to enum."""
        if not state_str:
            return None
        try:
            return SessionState(state_str)
        except ValueError:
            return None

    # ==================
    # SESSION CLEANUP
    # ==================

    def cleanup_stale_session(self, worker_id: str, tmux_session_name: Optional[str]) -> bool:
        """Cleanup a stale session for a worker.

        Called when session validation fails (tmux session doesn't exist but
        database still has references). Performs cleanup:
        1. Clear tmux_session_name from sessions table
        2. Update worker runtime status to 'stopped'
        3. Unbind worker-session binding (best-effort)

        Args:
            worker_id: Worker ID with stale session
            tmux_session_name: The stale tmux session name (for verification)

        Returns:
            True if cleanup succeeded, False otherwise
        """
        self._ensure_connected()

        try:
            # Step 1: Clear tmux_session_name from sessions table
            self._db.execute(
                """UPDATE sessions
                   SET tmux_session_name = NULL,
                       state = 'stopped',
                       stopped_at = CURRENT_TIMESTAMP
                   WHERE worker_id = ?""",
                (worker_id,)
            )
            self._db.connection.commit()

            # Step 2: Update worker runtime status
            self._db.execute(
                """UPDATE worker_state
                   SET runtime_status = 'stopped',
                       updated_at = CURRENT_TIMESTAMP
                   WHERE worker_id = ?""",
                (worker_id,)
            )
            self._db.connection.commit()

            # Step 3: Unbind worker-session (best-effort, may not exist)
            # Try to import and use the binding manager
            try:
                from cli.core.sessions.binding_manager import get_binding_manager
                manager = get_binding_manager(self._db)
                manager.unbind(worker_id)
            except (ImportError, Exception) as e:
                # Best-effort - log but don't fail cleanup
                logger.debug(f"Could not unbind session for {worker_id}: {e}")

            logger.info(f"Cleaned up stale session for worker {worker_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to cleanup stale session for {worker_id}: {e}")
            return False

    def validate_all_sessions(self) -> dict[str, list[str]]:
        """Validate all tmux sessions and identify stale ones.

        Checks all workers with tmux_session_name and verifies the session
        still exists using `tmux has-session`. Useful for health checks.

        Returns:
            Dict with:
            - 'valid': List of worker IDs with valid sessions
            - 'stale': List of worker IDs with stale sessions (need cleanup)
            - 'no_session': List of worker IDs with no tmux session
        """
        self._ensure_connected()

        result = {
            'valid': [],
            'stale': [],
            'no_session': [],
        }

        # Get all workers with potential sessions
        rows = self._db.fetchall(
            """SELECT w.id, s.tmux_session_name, ws.runtime_status
               FROM workers w
               LEFT JOIN sessions s ON w.id = s.worker_id
               LEFT JOIN worker_state ws ON w.id = ws.worker_id
               WHERE w.status = 'active'"""
        )

        for row in rows:
            worker_id = row['id']
            tmux_name = row['tmux_session_name']
            runtime_status = row['runtime_status']

            if not tmux_name:
                result['no_session'].append(worker_id)
                continue

            # Validate tmux session exists
            if self._validate_tmux_session(tmux_name):
                result['valid'].append(worker_id)
            else:
                # Session is stale - should be cleaned up
                result['stale'].append(worker_id)
                logger.warning(f"Stale session detected for worker {worker_id}: {tmux_name}")

        return result

    def _validate_tmux_session(self, session_name: str) -> bool:
        """Check if a tmux session exists.

        Args:
            session_name: Name of the tmux session to validate

        Returns:
            True if session exists, False otherwise
        """
        try:
            result = subprocess.run(
                ["tmux", "has-session", "-t", session_name],
                capture_output=True,
                timeout=2,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    # ==================
    # CONTEXT MANAGER
    # ==================

    def __enter__(self) -> "QuinnAIOrgConnection":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - close connection."""
        self._disconnect()

    def close(self) -> None:
        """Close the connection."""
        self._disconnect()
