"""
Database cleanup utilities.

Provides automatic cleanup of database connections at process exit.
"""

import atexit
import logging
import weakref
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .connection import Database

_logger = logging.getLogger(__name__)

# Track all Database instances for cleanup at exit
_all_databases: weakref.WeakSet["Database"] = weakref.WeakSet()


def register_database(db: "Database") -> None:
    """Register a database instance for cleanup at exit.

    Args:
        db: Database instance to register
    """
    _all_databases.add(db)


def _cleanup_databases() -> None:
    """Close all tracked database connections at process exit.

    Registered with atexit to ensure connections are properly closed.
    """
    for db in _all_databases:
        try:
            db.close_all()
        except Exception as e:
            # Intentionally swallowed: cleanup at exit must be best-effort.
            # A failing close should not prevent other databases from closing.
            # We catch Exception here because this runs at process exit and we
            # cannot predict what errors might occur during shutdown.
            _logger.debug(f"Database cleanup failed at exit (ignored): {e}")
            pass


# Register cleanup handler
atexit.register(_cleanup_databases)
