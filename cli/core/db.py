"""
Database module for QuinnAI CLI.

Provides the central quinn.db SQLite database for all org state, workers,
teams, communication, and runtime state.

Connection Management:
- Single-writer, multi-reader via WAL mode
- Thread-local connections for multi-threaded access
- Busy timeout for handling lock contention
- Proper cleanup via atexit handler
"""

import atexit
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Generator, Optional
import weakref

# Current schema version - increment when schema changes
SCHEMA_VERSION = 16

# Connection configuration
DEFAULT_BUSY_TIMEOUT_MS = 5000  # 5 seconds
WAL_MODE_ENABLED = True

# Track all Database instances for cleanup at exit
_all_databases: weakref.WeakSet["Database"] = weakref.WeakSet()


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
            except Exception:
                # Intentionally swallowed: cleanup must be best-effort.
                # A failing callback should not prevent other cleanup from running.
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
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
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
        _all_databases.add(self)

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
        except Exception:
            self.connection.rollback()
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
        except Exception:
            self.connection.rollback()
            file_ctx.rollback()  # Clean up created files
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
            except Exception:
                pass

        return info


def _cleanup_databases() -> None:
    """Close all tracked database connections at process exit.

    Registered with atexit to ensure connections are properly closed.
    """
    for db in _all_databases:
        try:
            db.close_all()
        except Exception:
            # Intentionally swallowed: cleanup at exit must be best-effort.
            # A failing close should not prevent other databases from closing.
            pass


# Register cleanup handler
atexit.register(_cleanup_databases)


# Schema definition
SCHEMA_SQL = """
-- ===================
-- CORE TABLES
-- ===================

-- Organization state (one per org folder)
CREATE TABLE IF NOT EXISTS org_state (
    id TEXT PRIMARY KEY CHECK(id = 'default'),  -- Singleton: only 'default' allowed
    name TEXT NOT NULL DEFAULT 'My Organization',
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
    lead_id TEXT,
    channel_id TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_team_id) REFERENCES teams(id) ON DELETE SET NULL,
    FOREIGN KEY (lead_id) REFERENCES workers(id) ON DELETE SET NULL,
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_teams_parent ON teams(parent_team_id);
CREATE INDEX IF NOT EXISTS idx_teams_lead ON teams(lead_id);

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
    -- Hiring authority cascade fields
    hiring_authority_scope TEXT,
    delegated_budget INTEGER NOT NULL DEFAULT 0,
    max_reports INTEGER NOT NULL DEFAULT 10,
    -- Offboarding workflow tracking
    offboarding_ask_bead_id TEXT,
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

-- Sessions (1:1 with worker - worker's brain)
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL UNIQUE,
    provider TEXT NOT NULL,
    model TEXT,
    command TEXT NOT NULL,
    args TEXT,
    working_directory TEXT,
    tmux_session_name TEXT,
    pid INTEGER,
    state TEXT NOT NULL CHECK(state IN ('starting', 'idle', 'running', 'stopped', 'crashed')),
    state_version INTEGER NOT NULL DEFAULT 0,
    started_at DATETIME,
    stopped_at DATETIME,
    last_activity DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_sessions_worker ON sessions(worker_id);
CREATE INDEX IF NOT EXISTS idx_sessions_state ON sessions(state);
CREATE INDEX IF NOT EXISTS idx_sessions_last_activity ON sessions(last_activity);

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
CREATE INDEX IF NOT EXISTS idx_channel_subs_worker ON channel_subscriptions(worker_id);

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
CREATE INDEX IF NOT EXISTS idx_messages_parent ON messages(parent_id);

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

-- ===================
-- FULL TEXT SEARCH
-- ===================

-- FTS5 table for message content search
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    content='messages',
    content_rowid='rowid'
);

-- Triggers to keep FTS in sync with messages table
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (NEW.rowid, NEW.content);
END;

CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', OLD.rowid, OLD.content);
END;

CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', OLD.rowid, OLD.content);
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES (NEW.rowid, NEW.content);
END;

-- ===================
-- TEAM MEMBERSHIP
-- ===================

-- Team membership with roles (member, lead, admin)
CREATE TABLE IF NOT EXISTS team_members (
    team_id TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('member', 'lead', 'admin')),
    joined_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (team_id, worker_id),
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_team_members_worker ON team_members(worker_id);

-- ===================
-- PERMISSIONS
-- ===================

-- Direct permission grants
CREATE TABLE IF NOT EXISTS permissions (
    id TEXT PRIMARY KEY,
    bead_id TEXT,
    grantee_type TEXT NOT NULL CHECK(grantee_type IN ('worker', 'team')),
    grantee_id TEXT NOT NULL,
    level INTEGER NOT NULL CHECK(level >= 0 AND level <= 5),
    granted_by TEXT,
    granted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bead_id, grantee_type, grantee_id)
);
CREATE INDEX IF NOT EXISTS idx_permissions_bead ON permissions(bead_id);
CREATE INDEX IF NOT EXISTS idx_permissions_grantee ON permissions(grantee_type, grantee_id);

-- Precomputed effective permissions (cache table)
CREATE TABLE IF NOT EXISTS effective_permissions (
    worker_id TEXT NOT NULL,
    bead_id TEXT NOT NULL,
    level INTEGER NOT NULL CHECK(level >= 0 AND level <= 5),
    computed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (worker_id, bead_id),
    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_effective_perm_level ON effective_permissions(level);

-- Permission audit log
CREATE TABLE IF NOT EXISTS permission_audit (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL CHECK(action IN ('grant', 'revoke', 'check', 'deny')),
    bead_id TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    level INTEGER,
    details TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_perm_audit_bead ON permission_audit(bead_id);
CREATE INDEX IF NOT EXISTS idx_perm_audit_worker ON permission_audit(worker_id);
CREATE INDEX IF NOT EXISTS idx_perm_audit_action ON permission_audit(action);
CREATE INDEX IF NOT EXISTS idx_perm_audit_time ON permission_audit(created_at);

-- ===================
-- NOTIFICATIONS (EPHEMERAL BEADS)
-- ===================

-- Notification beads - ephemeral work units pointing to messages
-- Created when message sent to channel, one per subscriber
-- Closed when worker reads/actions the notification
-- Purged after configurable days when closed or when expires_at is reached
CREATE TABLE IF NOT EXISTS notification_beads (
    id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'read', 'actioned', 'closed')),
    priority INTEGER NOT NULL DEFAULT 2 CHECK(priority >= 0 AND priority <= 4),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read_at DATETIME,
    actioned_at DATETIME,
    closed_at DATETIME,
    expires_at DATETIME,
    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE,
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE,
    UNIQUE(worker_id, message_id)
);
CREATE INDEX IF NOT EXISTS idx_notif_beads_worker ON notification_beads(worker_id);
CREATE INDEX IF NOT EXISTS idx_notif_beads_status ON notification_beads(status);
CREATE INDEX IF NOT EXISTS idx_notif_beads_worker_status ON notification_beads(worker_id, status);
CREATE INDEX IF NOT EXISTS idx_notif_beads_priority ON notification_beads(priority);
CREATE INDEX IF NOT EXISTS idx_notif_beads_closed_at ON notification_beads(closed_at);
CREATE INDEX IF NOT EXISTS idx_notif_beads_expires_at ON notification_beads(expires_at);
CREATE INDEX IF NOT EXISTS idx_notif_beads_message ON notification_beads(message_id);
CREATE INDEX IF NOT EXISTS idx_notif_beads_channel ON notification_beads(channel_id);

-- ===================
-- BUDGET TABLES
-- ===================

-- Organization budget pool (funded by billing/subscription)
CREATE TABLE IF NOT EXISTS budget_pools (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    total_credits DECIMAL(15,2) NOT NULL DEFAULT 0,
    period_start DATETIME NOT NULL,
    period_end DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Budget allocations (who has how much budget)
-- Implements the cascade: Board -> CEO -> Directors -> Managers -> Workers
CREATE TABLE IF NOT EXISTS budget_allocations (
    id TEXT PRIMARY KEY,

    -- Who owns this allocation
    worker_id TEXT NOT NULL,

    -- Where budget came from (NULL = from org pool, otherwise from manager)
    source_worker_id TEXT,
    pool_id TEXT,

    -- Budget amounts
    allocated_credits DECIMAL(15,2) NOT NULL,
    spent_credits DECIMAL(15,2) NOT NULL DEFAULT 0,
    reserved_credits DECIMAL(15,2) NOT NULL DEFAULT 0,

    -- Period tracking
    period_start DATETIME NOT NULL,
    period_end DATETIME NOT NULL,

    -- Allocation rules
    can_delegate BOOLEAN NOT NULL DEFAULT FALSE,
    delegation_limit DECIMAL(15,2),

    -- Timestamps
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE,
    FOREIGN KEY (source_worker_id) REFERENCES workers(id) ON DELETE SET NULL,
    FOREIGN KEY (pool_id) REFERENCES budget_pools(id) ON DELETE CASCADE,

    -- Either from pool or from source_worker, not both
    CHECK (
        (source_worker_id IS NULL AND pool_id IS NOT NULL) OR
        (source_worker_id IS NOT NULL AND pool_id IS NULL)
    ),

    -- Can't spend more than allocated
    CHECK (spent_credits + reserved_credits <= allocated_credits)
);

CREATE INDEX IF NOT EXISTS idx_budget_allocations_worker ON budget_allocations(worker_id);
CREATE INDEX IF NOT EXISTS idx_budget_allocations_source ON budget_allocations(source_worker_id);
CREATE INDEX IF NOT EXISTS idx_budget_allocations_period ON budget_allocations(period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_budget_allocations_pool ON budget_allocations(pool_id);

-- Budget transactions (immutable ledger of all budget movements)
CREATE TABLE IF NOT EXISTS budget_transactions (
    id TEXT PRIMARY KEY,
    allocation_id TEXT NOT NULL,
    worker_id TEXT NOT NULL,

    -- Transaction type
    type TEXT NOT NULL CHECK(type IN (
        'allocation',
        'spend',
        'reserve',
        'release',
        'transfer_out',
        'transfer_in',
        'adjustment',
        'refund'
    )),

    -- Amount (positive for credits in, negative for credits out)
    amount DECIMAL(15,2) NOT NULL,

    -- Provider details (for spend transactions)
    provider TEXT,
    model TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,

    -- Reference to what caused this transaction
    reference_type TEXT,
    reference_id TEXT,

    -- Audit trail
    description TEXT,
    metadata TEXT,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (allocation_id) REFERENCES budget_allocations(id) ON DELETE CASCADE,
    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_budget_transactions_allocation ON budget_transactions(allocation_id);
CREATE INDEX IF NOT EXISTS idx_budget_transactions_worker ON budget_transactions(worker_id);
CREATE INDEX IF NOT EXISTS idx_budget_transactions_type ON budget_transactions(type);
CREATE INDEX IF NOT EXISTS idx_budget_transactions_created ON budget_transactions(created_at);
CREATE INDEX IF NOT EXISTS idx_budget_transactions_provider ON budget_transactions(provider, model);

-- Materialized balance view (updated via triggers for performance)
CREATE TABLE IF NOT EXISTS budget_balances (
    allocation_id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL,

    -- Current balances (derived from transactions)
    allocated DECIMAL(15,2) NOT NULL,
    spent DECIMAL(15,2) NOT NULL,
    reserved DECIMAL(15,2) NOT NULL,
    available DECIMAL(15,2) NOT NULL,
    delegated DECIMAL(15,2) NOT NULL,

    -- Period info
    period_start DATETIME NOT NULL,
    period_end DATETIME NOT NULL,

    -- Last update
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (allocation_id) REFERENCES budget_allocations(id) ON DELETE CASCADE,
    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_budget_balances_worker ON budget_balances(worker_id);
CREATE INDEX IF NOT EXISTS idx_budget_balances_available ON budget_balances(available);

-- ===================
-- BUDGET TRIGGERS
-- ===================

-- Update budget_balances on transaction insert
CREATE TRIGGER IF NOT EXISTS update_budget_balance_on_transaction
AFTER INSERT ON budget_transactions
BEGIN
    UPDATE budget_balances
    SET
        spent = spent + CASE
            WHEN NEW.type = 'spend' THEN ABS(NEW.amount)
            WHEN NEW.type = 'refund' THEN -ABS(NEW.amount)
            ELSE 0
        END,
        reserved = reserved + CASE
            WHEN NEW.type = 'reserve' THEN ABS(NEW.amount)
            WHEN NEW.type = 'release' THEN -ABS(NEW.amount)
            ELSE 0
        END,
        delegated = delegated + CASE
            WHEN NEW.type = 'transfer_out' THEN ABS(NEW.amount)
            ELSE 0
        END,
        allocated = allocated + CASE
            WHEN NEW.type = 'allocation' THEN NEW.amount
            WHEN NEW.type = 'transfer_in' THEN NEW.amount
            WHEN NEW.type = 'adjustment' THEN NEW.amount
            ELSE 0
        END,
        available = (
            allocated + CASE
                WHEN NEW.type = 'allocation' THEN NEW.amount
                WHEN NEW.type = 'transfer_in' THEN NEW.amount
                WHEN NEW.type = 'adjustment' THEN NEW.amount
                ELSE 0
            END
        ) - (
            spent + CASE
                WHEN NEW.type = 'spend' THEN ABS(NEW.amount)
                WHEN NEW.type = 'refund' THEN -ABS(NEW.amount)
                ELSE 0
            END
        ) - (
            reserved + CASE
                WHEN NEW.type = 'reserve' THEN ABS(NEW.amount)
                WHEN NEW.type = 'release' THEN -ABS(NEW.amount)
                ELSE 0
            END
        ) - (
            delegated + CASE
                WHEN NEW.type = 'transfer_out' THEN ABS(NEW.amount)
                ELSE 0
            END
        ),
        updated_at = CURRENT_TIMESTAMP
    WHERE allocation_id = NEW.allocation_id;
END;

-- ===================
-- EVENTS (AUDIT TRAIL)
-- ===================

-- Events table for system-wide audit trail and recovery
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,    -- worker.hired|worker.fired|okr.created|...
    entity_type TEXT NOT NULL,   -- worker|team|okr|message|work
    entity_id TEXT NOT NULL,
    payload TEXT,                -- JSON event data
    actor_id TEXT,               -- who triggered (optional)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_entity ON events(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_events_actor ON events(actor_id);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at);

-- ===================
-- OKR TABLES
-- ===================

-- OKRs cascade: Board -> CEO -> Directors -> Managers -> Workers
-- Every OKR has an owner and optional parent for hierarchy
-- key_results is JSON: [{"metric": "...", "target": N, "current": N, "unit": "..."}]
CREATE TABLE IF NOT EXISTS okrs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    owner_worker_id TEXT NOT NULL,
    parent_okr_id TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('draft', 'active', 'completed', 'cancelled')),
    key_results TEXT,
    due_date DATE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (owner_worker_id) REFERENCES workers(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_okr_id) REFERENCES okrs(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_okrs_owner ON okrs(owner_worker_id);
CREATE INDEX IF NOT EXISTS idx_okrs_parent ON okrs(parent_okr_id);
CREATE INDEX IF NOT EXISTS idx_okrs_status ON okrs(status);

-- Link work items to OKRs
-- Every work item should link to an objective for strategic alignment
CREATE TABLE IF NOT EXISTS work_okr_links (
    work_id TEXT NOT NULL,
    okr_id TEXT NOT NULL,
    link_type TEXT NOT NULL DEFAULT 'contributes' CHECK(link_type IN ('contributes', 'blocks', 'depends_on')),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (work_id, okr_id),
    FOREIGN KEY (okr_id) REFERENCES okrs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_work_okr_links_okr ON work_okr_links(okr_id);
CREATE INDEX IF NOT EXISTS idx_work_okr_links_work ON work_okr_links(work_id);

-- ===================
-- ESCALATIONS
-- ===================

-- Escalations track when a worker escalates an issue to another worker
-- Used for routing problems up the hierarchy or to specialists
CREATE TABLE IF NOT EXISTS escalations (
    id TEXT PRIMARY KEY,
    issue_id TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    escalated_to_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending', 'resolved', 'timeout')),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at DATETIME,
    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE,
    FOREIGN KEY (escalated_to_id) REFERENCES workers(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_escalations_issue ON escalations(issue_id);
CREATE INDEX IF NOT EXISTS idx_escalations_worker ON escalations(worker_id);
CREATE INDEX IF NOT EXISTS idx_escalations_escalated_to ON escalations(escalated_to_id);
CREATE INDEX IF NOT EXISTS idx_escalations_state ON escalations(state);
CREATE INDEX IF NOT EXISTS idx_escalations_created_at ON escalations(created_at);

-- ===================
-- LIFECYCLE CONFIGURATIONS
-- ===================

-- Org-configurable lifecycle states for bead types
-- Allows each org to define custom lifecycle flows per bead type
-- Format: JSON configuration with states, terminal_states, initial_state, transitions
CREATE TABLE IF NOT EXISTS lifecycle_configs (
    bead_type TEXT PRIMARY KEY,
    config TEXT NOT NULL,  -- JSON: {states: [], terminal_states: [], initial_state: str, transitions: {}}
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
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
        # Version 2: Add team_members table
        2: [
            """CREATE TABLE IF NOT EXISTS team_members (
                team_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('member', 'lead', 'admin')),
                joined_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (team_id, worker_id),
                FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
            )""",
            "CREATE INDEX IF NOT EXISTS idx_team_members_worker ON team_members(worker_id)",
        ],
        # Version 3: Add permissions tables
        3: [
            """CREATE TABLE IF NOT EXISTS permissions (
                id TEXT PRIMARY KEY,
                bead_id TEXT,
                grantee_type TEXT NOT NULL CHECK(grantee_type IN ('worker', 'team')),
                grantee_id TEXT NOT NULL,
                level INTEGER NOT NULL CHECK(level >= 0 AND level <= 5),
                granted_by TEXT,
                granted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(bead_id, grantee_type, grantee_id)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_permissions_bead ON permissions(bead_id)",
            "CREATE INDEX IF NOT EXISTS idx_permissions_grantee ON permissions(grantee_type, grantee_id)",
            """CREATE TABLE IF NOT EXISTS effective_permissions (
                worker_id TEXT NOT NULL,
                bead_id TEXT NOT NULL,
                level INTEGER NOT NULL CHECK(level >= 0 AND level <= 5),
                computed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (worker_id, bead_id),
                FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
            )""",
            "CREATE INDEX IF NOT EXISTS idx_effective_perm_level ON effective_permissions(level)",
            """CREATE TABLE IF NOT EXISTS permission_audit (
                id TEXT PRIMARY KEY,
                action TEXT NOT NULL CHECK(action IN ('grant', 'revoke', 'check', 'deny')),
                bead_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                level INTEGER,
                details TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""",
            "CREATE INDEX IF NOT EXISTS idx_perm_audit_bead ON permission_audit(bead_id)",
            "CREATE INDEX IF NOT EXISTS idx_perm_audit_worker ON permission_audit(worker_id)",
            "CREATE INDEX IF NOT EXISTS idx_perm_audit_action ON permission_audit(action)",
            "CREATE INDEX IF NOT EXISTS idx_perm_audit_time ON permission_audit(created_at)",
        ],
        # Version 4: Add notification_beads table
        4: [
            """CREATE TABLE IF NOT EXISTS notification_beads (
                id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'read', 'actioned', 'closed')),
                priority INTEGER NOT NULL DEFAULT 2 CHECK(priority >= 0 AND priority <= 4),
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                read_at DATETIME,
                actioned_at DATETIME,
                closed_at DATETIME,
                FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE,
                FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
                FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE,
                UNIQUE(worker_id, message_id)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_notif_beads_worker ON notification_beads(worker_id)",
            "CREATE INDEX IF NOT EXISTS idx_notif_beads_status ON notification_beads(status)",
            "CREATE INDEX IF NOT EXISTS idx_notif_beads_worker_status ON notification_beads(worker_id, status)",
            "CREATE INDEX IF NOT EXISTS idx_notif_beads_priority ON notification_beads(priority)",
            "CREATE INDEX IF NOT EXISTS idx_notif_beads_closed_at ON notification_beads(closed_at)",
        ],
        # Version 5: Add budget tables
        5: [
            """CREATE TABLE IF NOT EXISTS budget_pools (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                total_credits DECIMAL(15,2) NOT NULL DEFAULT 0,
                period_start DATETIME NOT NULL,
                period_end DATETIME NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS budget_allocations (
                id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                source_worker_id TEXT,
                pool_id TEXT,
                allocated_credits DECIMAL(15,2) NOT NULL,
                spent_credits DECIMAL(15,2) NOT NULL DEFAULT 0,
                reserved_credits DECIMAL(15,2) NOT NULL DEFAULT 0,
                period_start DATETIME NOT NULL,
                period_end DATETIME NOT NULL,
                can_delegate BOOLEAN NOT NULL DEFAULT FALSE,
                delegation_limit DECIMAL(15,2),
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE,
                FOREIGN KEY (source_worker_id) REFERENCES workers(id) ON DELETE SET NULL,
                FOREIGN KEY (pool_id) REFERENCES budget_pools(id) ON DELETE CASCADE,
                CHECK (
                    (source_worker_id IS NULL AND pool_id IS NOT NULL) OR
                    (source_worker_id IS NOT NULL AND pool_id IS NULL)
                ),
                CHECK (spent_credits + reserved_credits <= allocated_credits)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_budget_allocations_worker ON budget_allocations(worker_id)",
            "CREATE INDEX IF NOT EXISTS idx_budget_allocations_source ON budget_allocations(source_worker_id)",
            "CREATE INDEX IF NOT EXISTS idx_budget_allocations_period ON budget_allocations(period_start, period_end)",
            """CREATE TABLE IF NOT EXISTS budget_transactions (
                id TEXT PRIMARY KEY,
                allocation_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                type TEXT NOT NULL CHECK(type IN (
                    'allocation', 'spend', 'reserve', 'release',
                    'transfer_out', 'transfer_in', 'adjustment', 'refund'
                )),
                amount DECIMAL(15,2) NOT NULL,
                provider TEXT,
                model TEXT,
                input_tokens INTEGER,
                output_tokens INTEGER,
                reference_type TEXT,
                reference_id TEXT,
                description TEXT,
                metadata TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (allocation_id) REFERENCES budget_allocations(id) ON DELETE CASCADE,
                FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
            )""",
            "CREATE INDEX IF NOT EXISTS idx_budget_transactions_allocation ON budget_transactions(allocation_id)",
            "CREATE INDEX IF NOT EXISTS idx_budget_transactions_worker ON budget_transactions(worker_id)",
            "CREATE INDEX IF NOT EXISTS idx_budget_transactions_type ON budget_transactions(type)",
            "CREATE INDEX IF NOT EXISTS idx_budget_transactions_created ON budget_transactions(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_budget_transactions_provider ON budget_transactions(provider, model)",
            """CREATE TABLE IF NOT EXISTS budget_balances (
                allocation_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                allocated DECIMAL(15,2) NOT NULL,
                spent DECIMAL(15,2) NOT NULL,
                reserved DECIMAL(15,2) NOT NULL,
                available DECIMAL(15,2) NOT NULL,
                delegated DECIMAL(15,2) NOT NULL,
                period_start DATETIME NOT NULL,
                period_end DATETIME NOT NULL,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (allocation_id) REFERENCES budget_allocations(id) ON DELETE CASCADE,
                FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
            )""",
            "CREATE INDEX IF NOT EXISTS idx_budget_balances_worker ON budget_balances(worker_id)",
            "CREATE INDEX IF NOT EXISTS idx_budget_balances_available ON budget_balances(available)",
            """CREATE TRIGGER IF NOT EXISTS update_budget_balance_on_transaction
            AFTER INSERT ON budget_transactions
            BEGIN
                UPDATE budget_balances
                SET
                    spent = spent + CASE
                        WHEN NEW.type = 'spend' THEN ABS(NEW.amount)
                        WHEN NEW.type = 'refund' THEN -ABS(NEW.amount)
                        ELSE 0
                    END,
                    reserved = reserved + CASE
                        WHEN NEW.type = 'reserve' THEN ABS(NEW.amount)
                        WHEN NEW.type = 'release' THEN -ABS(NEW.amount)
                        ELSE 0
                    END,
                    delegated = delegated + CASE
                        WHEN NEW.type = 'transfer_out' THEN ABS(NEW.amount)
                        ELSE 0
                    END,
                    allocated = allocated + CASE
                        WHEN NEW.type = 'allocation' THEN NEW.amount
                        WHEN NEW.type = 'transfer_in' THEN NEW.amount
                        WHEN NEW.type = 'adjustment' THEN NEW.amount
                        ELSE 0
                    END,
                    available = (
                        allocated + CASE
                            WHEN NEW.type = 'allocation' THEN NEW.amount
                            WHEN NEW.type = 'transfer_in' THEN NEW.amount
                            WHEN NEW.type = 'adjustment' THEN NEW.amount
                            ELSE 0
                        END
                    ) - (
                        spent + CASE
                            WHEN NEW.type = 'spend' THEN ABS(NEW.amount)
                            WHEN NEW.type = 'refund' THEN -ABS(NEW.amount)
                            ELSE 0
                        END
                    ) - (
                        reserved + CASE
                            WHEN NEW.type = 'reserve' THEN ABS(NEW.amount)
                            WHEN NEW.type = 'release' THEN -ABS(NEW.amount)
                            ELSE 0
                        END
                    ) - (
                        delegated + CASE
                            WHEN NEW.type = 'transfer_out' THEN ABS(NEW.amount)
                            ELSE 0
                        END
                    ),
                    updated_at = CURRENT_TIMESTAMP
                WHERE allocation_id = NEW.allocation_id;
            END""",
        ],
        # Version 6: Add events table for audit trail
        6: [
            """CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                payload TEXT,
                actor_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            "CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)",
            "CREATE INDEX IF NOT EXISTS idx_events_entity ON events(entity_type, entity_id)",
            "CREATE INDEX IF NOT EXISTS idx_events_actor ON events(actor_id)",
            "CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at)",
        ],
        # Version 7: Add hiring authority cascade columns to workers
        7: [
            "ALTER TABLE workers ADD COLUMN hiring_authority_scope TEXT",
            "ALTER TABLE workers ADD COLUMN delegated_budget INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE workers ADD COLUMN max_reports INTEGER NOT NULL DEFAULT 10",
        ],
        # Version 8: Add expires_at column to notification_beads for ephemeral cleanup
        8: [
            "ALTER TABLE notification_beads ADD COLUMN expires_at DATETIME",
            "CREATE INDEX IF NOT EXISTS idx_notif_beads_expires_at ON notification_beads(expires_at)",
        ],
        # Version 9: Add OKR tables for cascade objectives
        9: [
            """CREATE TABLE IF NOT EXISTS okrs (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                owner_worker_id TEXT NOT NULL,
                parent_okr_id TEXT,
                status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('draft', 'active', 'completed', 'cancelled')),
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_worker_id) REFERENCES workers(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_okr_id) REFERENCES okrs(id) ON DELETE SET NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_okrs_owner ON okrs(owner_worker_id)",
            "CREATE INDEX IF NOT EXISTS idx_okrs_parent ON okrs(parent_okr_id)",
            "CREATE INDEX IF NOT EXISTS idx_okrs_status ON okrs(status)",
            """CREATE TABLE IF NOT EXISTS work_okr_links (
                work_id TEXT NOT NULL,
                okr_id TEXT NOT NULL,
                link_type TEXT NOT NULL DEFAULT 'contributes' CHECK(link_type IN ('contributes', 'blocks', 'depends_on')),
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (work_id, okr_id),
                FOREIGN KEY (okr_id) REFERENCES okrs(id) ON DELETE CASCADE
            )""",
            "CREATE INDEX IF NOT EXISTS idx_work_okr_links_okr ON work_okr_links(okr_id)",
            "CREATE INDEX IF NOT EXISTS idx_work_okr_links_work ON work_okr_links(work_id)",
        ],
        # Version 10: Add offboarding_ask_bead_id for tracking storage review workflow
        10: [
            "ALTER TABLE workers ADD COLUMN offboarding_ask_bead_id TEXT",
        ],
        # Version 11: Add sessions table for session persistence
        11: [
            """CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL UNIQUE,
                provider TEXT NOT NULL,
                command TEXT NOT NULL,
                args TEXT,
                working_directory TEXT,
                tmux_session_name TEXT,
                pid INTEGER,
                state TEXT NOT NULL CHECK(state IN ('starting', 'idle', 'running', 'stopped', 'crashed')),
                started_at DATETIME,
                stopped_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
            )""",
            "CREATE INDEX IF NOT EXISTS idx_sessions_worker ON sessions(worker_id)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_state ON sessions(state)",
        ],
        # Version 12: Add missing indexes on foreign key columns for join performance
        12: [
            "CREATE INDEX IF NOT EXISTS idx_messages_parent ON messages(parent_id)",
            "CREATE INDEX IF NOT EXISTS idx_channel_subs_worker ON channel_subscriptions(worker_id)",
            "CREATE INDEX IF NOT EXISTS idx_notif_beads_message ON notification_beads(message_id)",
            "CREATE INDEX IF NOT EXISTS idx_notif_beads_channel ON notification_beads(channel_id)",
            "CREATE INDEX IF NOT EXISTS idx_budget_allocations_pool ON budget_allocations(pool_id)",
        ],
        # Version 13: Add state_version column to sessions for optimistic locking (race condition fix)
        13: [
            "ALTER TABLE sessions ADD COLUMN state_version INTEGER NOT NULL DEFAULT 0",
        ],
        # Version 14: Add escalations table for tracking issue escalations
        14: [
            """CREATE TABLE IF NOT EXISTS escalations (
                id TEXT PRIMARY KEY,
                issue_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                escalated_to_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending', 'resolved', 'timeout')),
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                resolved_at DATETIME,
                FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE,
                FOREIGN KEY (escalated_to_id) REFERENCES workers(id) ON DELETE CASCADE
            )""",
            "CREATE INDEX IF NOT EXISTS idx_escalations_issue ON escalations(issue_id)",
            "CREATE INDEX IF NOT EXISTS idx_escalations_worker ON escalations(worker_id)",
            "CREATE INDEX IF NOT EXISTS idx_escalations_escalated_to ON escalations(escalated_to_id)",
            "CREATE INDEX IF NOT EXISTS idx_escalations_state ON escalations(state)",
            "CREATE INDEX IF NOT EXISTS idx_escalations_created_at ON escalations(created_at)",
        ],
        # Version 15: Add key_results and due_date columns to okrs for progress tracking
        15: [
            "ALTER TABLE okrs ADD COLUMN key_results TEXT",  # JSON array of {metric, target, current, unit}
            "ALTER TABLE okrs ADD COLUMN due_date DATE",
        ],
        # Version 16: Add lifecycle_configs table for org-configurable bead lifecycle states
        16: [
            """CREATE TABLE IF NOT EXISTS lifecycle_configs (
                bead_type TEXT PRIMARY KEY,
                config TEXT NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""",
        ],
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
