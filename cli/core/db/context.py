"""
Transactional file context for database operations.

Provides context managers that track file operations during database
transactions, allowing automatic cleanup on rollback.
"""

import logging
import shutil
from pathlib import Path
from typing import Callable

_logger = logging.getLogger(__name__)


class TransactionalFileContext:
    """Tracks files/directories created during a transaction for rollback cleanup.

    When used within a database transaction, any files or directories created
    through this context will be automatically deleted if the transaction is
    rolled back.

    Usage:
        with db.transaction_with_files() as (cursor, file_ctx):
            cursor.execute("INSERT INTO workers...")
            file_ctx.track_created(storage_path)  # Track created file/dir
            # If exception occurs, both DB and files are rolled back

    Note:
        This solves the orphaned file problem (quinnai-12oj) where database
        rollbacks left storage files on disk.
    """

    def __init__(self) -> None:
        """Initialize the file tracking context."""
        self._created_paths: list[Path] = []
        self._cleanup_callbacks: list[Callable[[], None]] = []

    def track_created(self, path: Path) -> Path:
        """Track a file or directory created during the transaction.

        Args:
            path: Path to the created file or directory

        Returns:
            The same path (for chaining convenience)
        """
        self._created_paths.append(path)
        return path

    def register_cleanup(self, callback: Callable[[], None]) -> None:
        """Register a custom cleanup callback for rollback.

        Args:
            callback: Function to call on rollback (no arguments)
        """
        self._cleanup_callbacks.append(callback)

    def rollback(self) -> None:
        """Delete all tracked files/directories and run cleanup callbacks.

        Called automatically when the transaction context manager catches
        an exception (before re-raising).
        """
        # Run custom cleanup callbacks first (in reverse order)
        for callback in reversed(self._cleanup_callbacks):
            try:
                callback()
            except Exception as e:
                # Intentionally swallowed: cleanup must be best-effort.
                # A failing callback should not prevent other cleanup from running.
                # We catch Exception here (not specific types) because cleanup callbacks
                # can raise any error and we need to ensure all callbacks run.
                _logger.debug(f"Cleanup callback failed (ignored): {e}")
                pass

        # Delete tracked paths in reverse order (newest first)
        for path in reversed(self._created_paths):
            try:
                if path.exists():
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
            except OSError:
                # Intentionally swallowed: cleanup is best-effort.
                # File may be locked, permissions changed, or already deleted.
                pass

    def clear(self) -> None:
        """Clear all tracked files (called on successful commit)."""
        self._created_paths.clear()
        self._cleanup_callbacks.clear()
