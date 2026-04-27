"""
Concrete OrgConnection implementation for QuinnAI orgs.

Connects to a QuinnAI org's SQLite database to provide read access
to org state, workers, messages, OKRs, and budget information.

The board TUI is independent of org lifecycle - orgs can run without board,
board can connect/disconnect at will.
"""

import threading
from pathlib import Path
from typing import Any, Callable, Optional

from cli.core.db import Database

from ..logging_config import get_board_logger

logger = get_board_logger(__name__)

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


class QuinnAIOrgConnection(OrgConnection):
    """Connection to a QuinnAI org via SQLite database.

    Facade that owns the database connection and delegates all operations
    to OrgReader (reads) and OrgCommander (mutations/interventions).

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

        # Delegates (created after connecting)
        self._reader = None
        self._commander = None

        # Real-time update tracking
        self._subscribers: list[Callable[[str, Any], None]] = []
        self._last_wal_pages: Optional[int] = None
        self._polling_enabled = False
        self._subscriber_lock = threading.Lock()

        if not self._org_path.exists():
            raise OrgNotFound(self._org_path)

        self._connect()

    def _get_db_path(self) -> Path:
        """Get the database path for this org."""
        return self._org_path / self.DB_RELATIVE_PATH

    def _connect(self) -> None:
        """Connect to the org database and initialize delegates.

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

        try:
            if self._database_factory:
                self._db = self._database_factory(db_path)
            else:
                self._db = Database(db_path)
        except (DatabaseCorrupt, DatabaseLocked, OrgConnectionError):
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
            if isinstance(e, OrgConnectionError):
                raise
            raise OrgConnectionError(f"Failed to connect to database at {db_path}: {e}")

        self._connected = True
        self._init_delegates()

    def _init_delegates(self) -> None:
        """Create OrgReader and OrgCommander delegates after db is connected."""
        from .org_reader import OrgReader
        from .org_commander import OrgCommander

        self._reader = OrgReader(
            db=self._db,
            org_path=self._org_path,
            board_channel=self.BOARD_CHANNEL,
            escalations_channel=self.ESCALATIONS_CHANNEL,
        )
        self._commander = OrgCommander(
            db=self._db,
            org_path=self._org_path,
            board_channel=self.BOARD_CHANNEL,
            escalations_channel=self.ESCALATIONS_CHANNEL,
            get_ceo_fn=self.get_ceo,
            get_board_channel_id_fn=self._reader._get_board_channel_id,
            get_org_info_fn=self.get_org_info,
            mark_message_read_fn=self.mark_message_read,
        )

    def _disconnect(self) -> None:
        """Disconnect from the org database."""
        with self._subscriber_lock:
            self._subscribers.clear()
            self._polling_enabled = False
            self._last_wal_pages = None

        if self._db is not None:
            self._db.close()
            self._db = None
        self._connected = False
        self._reader = None
        self._commander = None

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
    # ORG STATE — delegates to OrgReader
    # ==================

    def get_org_info(self) -> OrgInfo:
        """Get current org information."""
        self._ensure_connected()
        return self._reader.get_org_info()

    def get_budget_summary(self) -> BudgetSummary:
        """Get budget summary for the org."""
        self._ensure_connected()
        return self._reader.get_budget_summary()

    def get_health_status(self):
        """Get organization health status."""
        self._ensure_connected()
        return self._reader.get_health_status()

    # ==================
    # WORKERS — delegates to OrgReader
    # ==================

    def get_workers(self) -> list[WorkerInfo]:
        """Get all workers in the org."""
        self._ensure_connected()
        return self._reader.get_workers()

    def get_worker(self, worker_id: str) -> Optional[WorkerInfo]:
        """Get a specific worker by ID."""
        self._ensure_connected()
        return self._reader.get_worker(worker_id)

    def get_ceo(self) -> Optional[WorkerInfo]:
        """Get the CEO worker."""
        self._ensure_connected()
        return self._reader.get_ceo()

    def get_recent_activity(
        self,
        minutes: int = 30,
        limit: int = 50,
    ) -> list[dict]:
        """Get recent activity from all workers."""
        self._ensure_connected()
        return self._reader.get_recent_activity(minutes=minutes, limit=limit)

    # ==================
    # MESSAGES — delegates to OrgReader / OrgCommander
    # ==================

    def get_all_channels(self) -> list[dict[str, Any]]:
        """Get all channels in the org."""
        self._ensure_connected()
        return self._reader.get_all_channels()

    def get_channel_messages(
        self,
        channel_id: str,
        unread_only: bool = False,
        limit: int = 100,
    ) -> list[Message]:
        """Get messages from a specific channel."""
        self._ensure_connected()
        return self._reader.get_channel_messages(
            channel_id=channel_id, unread_only=unread_only, limit=limit
        )

    def get_board_messages(self, unread_only: bool = False) -> list[Message]:
        """Get messages escalated to the board."""
        self._ensure_connected()
        return self._reader.get_board_messages(unread_only=unread_only)

    def get_unread_count(self) -> int:
        """Get count of unread board messages."""
        self._ensure_connected()
        return self._reader.get_unread_count()

    def mark_message_read(self, message_id: str) -> bool:
        """Mark a message as read."""
        self._ensure_connected()
        return self._reader.mark_message_read(message_id)

    def send_board_response(
        self,
        message_id: str,
        response: str,
    ) -> bool:
        """Send a board response to a message."""
        self._ensure_connected()
        return self._commander.send_board_response(
            message_id=message_id, response=response
        )

    # ==================
    # OKRS — delegates to OrgReader
    # ==================

    def get_okrs(self, owner_id: Optional[str] = None) -> list[OKRInfo]:
        """Get OKRs, optionally filtered by owner."""
        self._ensure_connected()
        return self._reader.get_okrs(owner_id=owner_id)

    def get_current_briefing(self) -> Optional[str]:
        """Get current CEO briefing from config."""
        self._ensure_connected()
        return self._reader.get_current_briefing()

    # ==================
    # ORG ACTIONS — delegates to OrgCommander
    # ==================

    def start_org(self) -> bool:
        """Start the org (if stopped or initialized)."""
        self._ensure_connected()
        return self._commander.start_org()

    def stop_org(self) -> bool:
        """Stop the org gracefully."""
        self._ensure_connected()
        return self._commander.stop_org()

    def restart_org(self) -> tuple[bool, str]:
        """Restart the org (stop then start)."""
        self._ensure_connected()
        return self._commander.restart_org()

    def restart_worker_session(self, worker_id: str, force: bool = True) -> tuple[bool, Optional[str]]:
        """Restart a worker's session."""
        self._ensure_connected()
        return self._commander.restart_worker_session(worker_id=worker_id, force=force)

    # ==================
    # BOARD INTERVENTIONS — delegates to OrgCommander
    # ==================

    def pause_worker(self, worker_id: str, reason: Optional[str] = None) -> bool:
        """Pause a worker via CLI command."""
        self._ensure_connected()
        return self._commander.pause_worker(worker_id=worker_id, reason=reason)

    def resume_worker(self, worker_id: str) -> bool:
        """Resume a worker via CLI command."""
        self._ensure_connected()
        return self._commander.resume_worker(worker_id=worker_id)

    def fire_worker(self, worker_id: str, reason: Optional[str] = None) -> bool:
        """Terminate a worker via CLI command."""
        self._ensure_connected()
        return self._commander.fire_worker(worker_id=worker_id, reason=reason)

    # ==================
    # CEO BRIEFING — delegates to OrgCommander
    # ==================

    def send_ceo_briefing(self, briefing_content: str) -> bool:
        """Send briefing to CEO as high-priority message."""
        self._ensure_connected()
        return self._commander.send_ceo_briefing(briefing_content)

    def update_briefing(self, briefing_content: str) -> bool:
        """Update CEO briefing and notify CEO."""
        self._ensure_connected()
        return self._commander.update_briefing(briefing_content)

    # ==================
    # SESSION CLEANUP — delegates to OrgCommander
    # ==================

    def cleanup_stale_session(self, worker_id: str, tmux_session_name: Optional[str]) -> bool:
        """Cleanup a stale session for a worker."""
        self._ensure_connected()
        return self._commander.cleanup_stale_session(
            worker_id=worker_id, tmux_session_name=tmux_session_name
        )

    def validate_all_sessions(self) -> dict[str, list[str]]:
        """Validate all tmux sessions and identify stale ones."""
        import subprocess

        self._ensure_connected()

        result = {
            'valid': [],
            'stale': [],
            'no_session': [],
        }

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

            if not tmux_name:
                result['no_session'].append(worker_id)
                continue

            if self._validate_tmux_session(tmux_name):
                result['valid'].append(worker_id)
            else:
                result['stale'].append(worker_id)
                logger.warning(f"Stale session detected for worker {worker_id}: {tmux_name}")

        return result

    def _validate_tmux_session(self, session_name: str) -> bool:
        """Check if a tmux session exists."""
        import subprocess

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
    # PROVIDER CONFIGURATION — delegates to OrgReader / OrgCommander
    # ==================

    def get_provider_config(self) -> dict:
        """Get provider configuration for the org."""
        self._ensure_connected()
        return self._reader.get_provider_config()

    def set_default_provider(self, provider_name: str) -> tuple[bool, str]:
        """Set the default provider for the org."""
        self._ensure_connected()
        return self._commander.set_default_provider(provider_name)

    def validate_provider_config(self) -> tuple[bool, list[str]]:
        """Validate provider configuration."""
        self._ensure_connected()
        return self._commander.validate_provider_config()

    # ==================
    # CURSOR-BASED STATUS POLLING — delegates to OrgReader / OrgCommander
    # ==================

    def get_status_changes_since_cursor(self, cursor_id: int) -> list[dict]:
        """Get status changes since a given cursor position."""
        self._ensure_connected()
        return self._reader.get_status_changes_since_cursor(cursor_id)

    def update_poll_cursor(self, client_id: str, last_change_id: int) -> None:
        """Update the poll cursor position for a client."""
        self._ensure_connected()
        self._commander.update_poll_cursor(client_id, last_change_id)

    def get_last_status_change_id(self) -> int:
        """Get the latest status change ID."""
        self._ensure_connected()
        return self._reader.get_last_status_change_id()

    def has_pending_changes(self, cursor_id: int) -> bool:
        """Check if there are pending status changes since cursor."""
        self._ensure_connected()
        return self._reader.has_pending_changes(cursor_id)

    # ==================
    # SUBSCRIPTIONS (stays in main class — owns polling lifecycle)
    # ==================

    def subscribe_to_updates(
        self,
        callback: Callable[[str, Any], None],
    ) -> Callable[[], None]:
        """Subscribe to real-time org updates via SQLite WAL polling.

        Polls the database for changes and notifies subscribers when detected.

        Args:
            callback: Function called with (event_type, event_data) when changes detected.
                     event_type will be "database_changed"

        Returns:
            Function to call to unsubscribe
        """
        if not self._connected:
            logger.warning("Cannot subscribe: not connected to database")
            return lambda: None

        with self._subscriber_lock:
            self._subscribers.append(callback)

            if self._last_wal_pages is None:
                self._last_wal_pages = self._get_wal_page_count()

            if len(self._subscribers) == 1:
                self._polling_enabled = True
                logger.info(f"Real-time updates enabled for {self._org_path}")

        def unsubscribe():
            with self._subscriber_lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)
                if len(self._subscribers) == 0:
                    self._polling_enabled = False
                    self._last_wal_pages = None
                    logger.info(f"Real-time updates disabled for {self._org_path}")

        return unsubscribe

    def check_for_updates(self) -> bool:
        """Check if database has changed since last check.

        Returns:
            True if changes were detected and subscribers notified
        """
        if not self._polling_enabled or not self._connected:
            return False

        with self._subscriber_lock:
            if len(self._subscribers) == 0:
                return False
            subscribers_copy = list(self._subscribers)

        try:
            current_version = self._get_wal_page_count()

            if self._last_wal_pages is not None and current_version != self._last_wal_pages:
                self._last_wal_pages = current_version
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
        """Get the current WAL page count to detect database changes."""
        if not self._db:
            return 0

        try:
            row = self._db.fetchone("PRAGMA wal_checkpoint(PASSIVE)")
            if row and len(row) >= 2:
                return int(row[1])
            return 0
        except Exception as e:
            logger.error(f"Error fetching WAL page count: {e}")
            return 0

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
