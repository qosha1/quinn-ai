"""
Database connection management.

Provides the Database class with thread-local connections, WAL mode,
and transaction support.
"""

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional

from core.constants import DEFAULT_DB_BUSY_TIMEOUT_MS

from .cleanup import register_database
from .context import TransactionalFileContext

_logger = logging.getLogger(__name__)

# Connection configuration
WAL_MODE_ENABLED = True


class Database:
    """Central database for QuinnAI org state.

    Connection Management:
    - Uses thread-local storage for connections (safe for multi-threaded access)
    - Enables WAL mode for concurrent reads with single writer
    - Configures busy timeout for handling lock contention
    - Tracks instances for cleanup at process exit

    SQLite Concurrency Notes:
    - SQLite allows multiple readers but only one writer at a time
    - WAL mode allows readers to proceed while a writer is active
    - Each thread gets its own connection to avoid threading issues
    - The main connection (from the thread that created Database) is the
      primary connection; other threads get their own via thread-local storage
    """

    def __init__(
        self,
        db_path: Path,
        busy_timeout_ms: int = DEFAULT_DB_BUSY_TIMEOUT_MS,
        enable_wal: bool = WAL_MODE_ENABLED,
    ):
        """Initialize database connection manager.

        Args:
            db_path: Path to quinn.db file
            busy_timeout_ms: How long to wait for locks (default 5000ms)
            enable_wal: Enable WAL journal mode for concurrent reads (default True)
        """
        self.db_path = db_path
        self._busy_timeout_ms = busy_timeout_ms
        self._enable_wal = enable_wal
        self._local = threading.local()
        self._main_thread_id = threading.get_ident()
        self._closed = False

        # Register for cleanup at exit
        register_database(self)

    def _create_connection(self) -> sqlite3.Connection:
        """Create a new SQLite connection with proper configuration.

        Returns:
            Configured sqlite3.Connection
        """
        conn = sqlite3.connect(
            str(self.db_path),
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            timeout=self._busy_timeout_ms / 1000.0,  # sqlite3 timeout is in seconds
            check_same_thread=False,  # We manage threading ourselves
        )
        conn.row_factory = sqlite3.Row

        # Configure pragmas
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")

        if self._enable_wal:
            conn.execute("PRAGMA journal_mode = WAL")
            # WAL checkpoint settings for better performance
            conn.execute("PRAGMA wal_autocheckpoint = 1000")  # Checkpoint every 1000 pages

        return conn

    @property
    def connection(self) -> sqlite3.Connection:
        """Get or create thread-local database connection.

        Each thread gets its own connection. This is necessary because
        SQLite connections are not fully thread-safe (cursor state, etc.).

        Returns:
            sqlite3.Connection for the current thread
        """
        if self._closed:
            raise RuntimeError("Database has been closed")

        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = self._create_connection()

        return self._local.connection

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        """Context manager for database transactions.

        Yields:
            Database cursor for executing queries

        Example:
            with db.transaction() as cursor:
                cursor.execute("INSERT INTO ...")
        """
        cursor = self.connection.cursor()
        try:
            yield cursor
            self.connection.commit()
        except Exception as e:
            # Catch all exceptions to ensure rollback happens
            # This needs to be broad because user code can raise anything
            self.connection.rollback()
            _logger.error(f"Transaction failed, rolling back: {e}")
            raise
        finally:
            cursor.close()

    @contextmanager
    def transaction_with_files(
        self,
    ) -> Generator[tuple[sqlite3.Cursor, TransactionalFileContext], None, None]:
        """Context manager for transactions that create files.

        Provides both a database cursor and a file tracking context.
        If the transaction is rolled back (due to an exception), any files
        tracked through the context are automatically deleted.

        Yields:
            Tuple of (cursor, file_context) for executing queries and tracking files

        Example:
            with db.transaction_with_files() as (cursor, file_ctx):
                cursor.execute("INSERT INTO workers...")
                storage_path = storage.ensure_worker_storage(worker_id)
                file_ctx.track_created(storage_path)
                # If exception occurs here, both DB and storage are rolled back

        Note:
            This prevents orphaned files from accumulating when database
            transactions fail (fixes quinnai-12oj).
        """
        cursor = self.connection.cursor()
        file_ctx = TransactionalFileContext()
        try:
            yield cursor, file_ctx
            self.connection.commit()
            file_ctx.clear()  # Success - don't track files anymore
        except Exception as e:
            # Catch all exceptions to ensure rollback happens
            # This needs to be broad because user code can raise anything
            self.connection.rollback()
            file_ctx.rollback()  # Clean up created files
            _logger.error(f"Transaction with files failed, rolling back: {e}")
            raise
        finally:
            cursor.close()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a SQL statement.

        Args:
            sql: SQL statement to execute
            params: Parameters for the statement

        Returns:
            Cursor with results
        """
        return self.connection.execute(sql, params)

    def executemany(self, sql: str, params_seq: list[tuple]) -> sqlite3.Cursor:
        """Execute a SQL statement for multiple parameter sets.

        Args:
            sql: SQL statement to execute
            params_seq: Sequence of parameter tuples

        Returns:
            Cursor with results
        """
        return self.connection.executemany(sql, params_seq)

    def fetchone(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """Execute query and fetch one result.

        Args:
            sql: SQL query to execute
            params: Parameters for the query

        Returns:
            Single row or None
        """
        cursor = self.execute(sql, params)
        return cursor.fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        """Execute query and fetch all results.

        Args:
            sql: SQL query to execute
            params: Parameters for the query

        Returns:
            List of rows
        """
        cursor = self.execute(sql, params)
        return cursor.fetchall()

    def close(self) -> None:
        """Close database connection for the current thread.

        For multi-threaded usage, call close_all() to close connections
        from all threads.
        """
        if hasattr(self._local, 'connection') and self._local.connection is not None:
            self._local.connection.close()
            self._local.connection = None

    def close_all(self) -> None:
        """Close the database and mark it as closed.

        After calling this, the Database instance cannot be used.
        This is primarily for cleanup at process exit.
        """
        self._closed = True
        # Close the current thread's connection if it exists
        self.close()

    def __enter__(self) -> "Database":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()

    def get_connection_info(self) -> dict[str, Any]:
        """Get information about the current connection for debugging.

        Returns:
            Dict with connection configuration details
        """
        info = {
            "db_path": str(self.db_path),
            "busy_timeout_ms": self._busy_timeout_ms,
            "wal_enabled": self._enable_wal,
            "thread_id": threading.get_ident(),
            "is_main_thread": threading.get_ident() == self._main_thread_id,
            "has_connection": hasattr(self._local, 'connection') and self._local.connection is not None,
            "closed": self._closed,
        }

        # Add pragma info if connected
        if info["has_connection"]:
            try:
                cursor = self._local.connection.execute("PRAGMA journal_mode")
                info["journal_mode"] = cursor.fetchone()[0]
            except sqlite3.Error as e:
                # Ignore pragma query failures - this is diagnostic info only
                _logger.debug(f"Failed to query journal_mode: {e}")
                pass

        return info
