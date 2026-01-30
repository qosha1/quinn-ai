"""
QuinnAI database module.

Provides database connection management, schema initialization, migrations,
and transaction support for the QuinnAI org database.

Public API:
    Database - Main database connection class
    TransactionalFileContext - File tracking for transactional rollback
    init_database - Initialize a new database with schema
    open_database - Open an existing database (with migrations)
    get_org_db_path - Get database path for an org folder
    SCHEMA_VERSION - Current schema version (for backward compatibility)
    DEFAULT_BUSY_TIMEOUT_MS - Default busy timeout (for backward compatibility)
"""

from core.constants import DB_SCHEMA_VERSION, DEFAULT_DB_BUSY_TIMEOUT_MS

from .connection import Database
from .context import TransactionalFileContext
from .init import get_org_db_path, init_database, open_database

# Legacy aliases for backward compatibility
SCHEMA_VERSION = DB_SCHEMA_VERSION
DEFAULT_BUSY_TIMEOUT_MS = DEFAULT_DB_BUSY_TIMEOUT_MS

__all__ = [
    # Main classes
    "Database",
    "TransactionalFileContext",
    # Initialization functions
    "init_database",
    "open_database",
    "get_org_db_path",
    # Constants (for backward compatibility)
    "SCHEMA_VERSION",
    "DEFAULT_BUSY_TIMEOUT_MS",
]
