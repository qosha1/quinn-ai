"""
Database module for QuinnAI CLI.

DEPRECATED: This module is a backward-compatibility facade.
All code has been refactored into cli.core.db package.

Import from core.db instead:
    from cli.core.db import Database, init_database, open_database

This file will be removed in a future version.
"""

# Re-export everything from the new package structure
# This maintains backward compatibility for existing imports
from cli.core.db import (
    # Main classes
    Database,
    TransactionalFileContext,
    # Functions
    init_database,
    open_database,
    get_org_db_path,
    # Constants
    SCHEMA_VERSION,
    DEFAULT_BUSY_TIMEOUT_MS,
)

__all__ = [
    "Database",
    "TransactionalFileContext",
    "init_database",
    "open_database",
    "get_org_db_path",
    "SCHEMA_VERSION",
    "DEFAULT_BUSY_TIMEOUT_MS",
]
