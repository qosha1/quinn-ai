"""
Database initialization and opening logic.

Provides functions for creating new databases and opening existing ones
with migration support.
"""

from pathlib import Path

from core.constants import DB_SCHEMA_VERSION

from .connection import Database
from .migrations import migrate_database
from .schema import SCHEMA_SQL


def init_database(db_path: Path) -> Database:
    """Initialize a new database with schema.

    Args:
        db_path: Path where quinn.db should be created

    Returns:
        Initialized Database instance
    """
    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db = Database(db_path)

    # Create schema
    db.connection.executescript(SCHEMA_SQL)

    # Set schema version
    db.execute(
        "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
        ("schema_version", str(DB_SCHEMA_VERSION))
    )

    # Initialize default org state if not exists
    existing = db.fetchone("SELECT id FROM org_state WHERE id = 'default'")
    if not existing:
        db.execute(
            "INSERT INTO org_state (id, status) VALUES ('default', 'uninitialized')"
        )

    db.connection.commit()
    return db


def open_database(db_path: Path) -> Database:
    """Open an existing database.

    Args:
        db_path: Path to existing quinn.db

    Returns:
        Database instance

    Raises:
        FileNotFoundError: If database doesn't exist
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    db = Database(db_path)

    # Check schema version
    version_row = db.fetchone("SELECT value FROM config WHERE key = 'schema_version'")
    if version_row:
        stored_version = int(version_row["value"])
        if stored_version < DB_SCHEMA_VERSION:
            migrate_database(db, stored_version, DB_SCHEMA_VERSION)

    return db


def get_org_db_path(org_path: Path) -> Path:
    """Get the database path for an org folder.

    Args:
        org_path: Path to org folder

    Returns:
        Path to quinn.db
    """
    return org_path / "live" / "quinn.db"
