"""
Database module for QuinnAI CLI.

Provides the central quinn.db SQLite database for all org state, workers,
teams, communication, and runtime state.
"""

import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Optional

# Current schema version - increment when schema changes
SCHEMA_VERSION = 1


class Database:
    """Central database for QuinnAI org state."""

    def __init__(self, db_path: Path):
        """Initialize database connection.

        Args:
            db_path: Path to quinn.db file
        """
        self.db_path = db_path
        self._connection: Optional[sqlite3.Connection] = None

    @property
    def connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._connection is None:
            self._connection = sqlite3.connect(
                str(self.db_path),
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
            )
            self._connection.row_factory = sqlite3.Row
            # Enable foreign key support
            self._connection.execute("PRAGMA foreign_keys = ON")
        return self._connection

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
        except Exception:
            self.connection.rollback()
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
        """Close database connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> "Database":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()


# Schema definition
SCHEMA_SQL = """
-- ===================
-- CORE TABLES
-- ===================

-- Organization state (one per org folder)
CREATE TABLE IF NOT EXISTS org_state (
    id TEXT PRIMARY KEY DEFAULT 'default',
    status TEXT NOT NULL CHECK(status IN ('uninitialized', 'initialized', 'running', 'stopped')),
    ceo_worker_id TEXT,
    started_at DATETIME,
    stopped_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Teams (hierarchical, mirrors org-chart)
CREATE TABLE IF NOT EXISTS teams (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    parent_team_id TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_team_id) REFERENCES teams(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_teams_parent ON teams(parent_team_id);

-- Workers (everyone is a worker - CEO, manager, junior)
CREATE TABLE IF NOT EXISTS workers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    team_id TEXT NOT NULL,
    manager_id TEXT,
    status TEXT NOT NULL CHECK(status IN ('pending', 'onboarding', 'active', 'offboarding', 'terminated')),
    skills TEXT NOT NULL DEFAULT '{}',
    cost INTEGER NOT NULL CHECK(cost >= 0 AND cost <= 100),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE RESTRICT,
    FOREIGN KEY (manager_id) REFERENCES workers(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_workers_team ON workers(team_id);
CREATE INDEX IF NOT EXISTS idx_workers_status ON workers(status);
CREATE INDEX IF NOT EXISTS idx_workers_manager ON workers(manager_id);

-- Worker runtime state (for crash recovery, monitoring)
CREATE TABLE IF NOT EXISTS worker_state (
    worker_id TEXT PRIMARY KEY,
    runtime_status TEXT NOT NULL CHECK(runtime_status IN ('starting', 'running', 'idle', 'stopped', 'crashed')),
    current_task_id TEXT,
    pid INTEGER,
    started_at DATETIME,
    last_activity DATETIME,
    tasks_completed INTEGER NOT NULL DEFAULT 0,
    tasks_failed INTEGER NOT NULL DEFAULT 0,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_worker_state_status ON worker_state(runtime_status);

-- ===================
-- COMMUNICATION
-- ===================

-- Channels (persistent spaces - team, topic, direct)
CREATE TABLE IF NOT EXISTS channels (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('team', 'topic', 'direct')),
    team_id TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_channels_type ON channels(type);
CREATE INDEX IF NOT EXISTS idx_channels_team ON channels(team_id);

-- Channel subscriptions (who's in which channel)
CREATE TABLE IF NOT EXISTS channel_subscriptions (
    channel_id TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    subscribed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (channel_id, worker_id),
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE,
    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
);

-- Messages (permanent knowledge - never deleted)
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    thread_id TEXT,
    parent_id TEXT,
    from_worker_id TEXT NOT NULL,
    content TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 2 CHECK(priority >= 0 AND priority <= 4),
    time_sensitivity TEXT NOT NULL DEFAULT 'whenever'
        CHECK(time_sensitivity IN ('immediate', 'hours', 'days', 'weeks', 'whenever')),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE,
    FOREIGN KEY (from_worker_id) REFERENCES workers(id) ON DELETE RESTRICT,
    FOREIGN KEY (parent_id) REFERENCES messages(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messages_channel ON messages(channel_id);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_messages_from_worker ON messages(from_worker_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_messages_priority ON messages(priority);

-- Message references (links to beads, asks, etc.)
CREATE TABLE IF NOT EXISTS message_refs (
    message_id TEXT NOT NULL,
    ref_type TEXT NOT NULL,
    ref_id TEXT NOT NULL,
    PRIMARY KEY (message_id, ref_type, ref_id),
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
);

-- ===================
-- CONFIG
-- ===================

-- Key-value config store
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


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
        ("schema_version", str(SCHEMA_VERSION))
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
        if stored_version < SCHEMA_VERSION:
            migrate_database(db, stored_version, SCHEMA_VERSION)

    return db


def migrate_database(db: Database, from_version: int, to_version: int) -> None:
    """Run database migrations.

    Args:
        db: Database instance
        from_version: Current schema version
        to_version: Target schema version
    """
    # Migration registry - add new migrations here
    migrations: dict[int, list[str]] = {
        # Version 2 migrations would go here:
        # 2: ["ALTER TABLE workers ADD COLUMN new_field TEXT;"],
    }

    for version in range(from_version + 1, to_version + 1):
        if version in migrations:
            for sql in migrations[version]:
                db.execute(sql)

    # Update schema version
    db.execute(
        "UPDATE config SET value = ? WHERE key = 'schema_version'",
        (str(to_version),)
    )
    db.connection.commit()


def get_org_db_path(org_path: Path) -> Path:
    """Get the database path for an org folder.

    Args:
        org_path: Path to org folder

    Returns:
        Path to quinn.db
    """
    return org_path / "live" / "quinn.db"
