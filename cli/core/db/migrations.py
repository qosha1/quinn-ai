"""
Database migration logic.

Contains migration definitions and application logic for schema evolution.
"""

import logging
import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .connection import Database

_logger = logging.getLogger(__name__)


def migrate_database(db: "Database", from_version: int, to_version: int) -> None:
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
        # Version 17: Add delegation tracking tables for hiring authority cascade
        17: [
            # Add delegation_version column to workers for optimistic locking
            "ALTER TABLE workers ADD COLUMN delegation_version INTEGER NOT NULL DEFAULT 0",
            # Add delegated_by column to workers for quick lookup (denormalized)
            "ALTER TABLE workers ADD COLUMN delegated_by TEXT",
            # Add delegation_expires_at column for time-limited delegations
            "ALTER TABLE workers ADD COLUMN delegation_expires_at DATETIME",
            # Create delegation_grants table for tracking active/revoked delegations
            """CREATE TABLE IF NOT EXISTS delegation_grants (
                id TEXT PRIMARY KEY,
                delegator_id TEXT NOT NULL,
                delegate_id TEXT NOT NULL,
                scope TEXT NOT NULL,
                budget_amount INTEGER NOT NULL,
                granted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME,
                revoked_at DATETIME,
                revoked_by TEXT,
                revoke_reason TEXT,
                granted_by_cli_user TEXT,
                metadata TEXT,
                FOREIGN KEY (delegator_id) REFERENCES workers(id) ON DELETE CASCADE,
                FOREIGN KEY (delegate_id) REFERENCES workers(id) ON DELETE CASCADE,
                CHECK (delegator_id != delegate_id),
                CHECK (budget_amount >= 0)
            )""",
            # Indexes for delegation_grants
            "CREATE INDEX IF NOT EXISTS idx_delegation_grants_delegator ON delegation_grants(delegator_id)",
            "CREATE INDEX IF NOT EXISTS idx_delegation_grants_delegate ON delegation_grants(delegate_id)",
            "CREATE INDEX IF NOT EXISTS idx_delegation_grants_active ON delegation_grants(revoked_at) WHERE revoked_at IS NULL",
            "CREATE INDEX IF NOT EXISTS idx_delegation_grants_expires ON delegation_grants(expires_at) WHERE expires_at IS NOT NULL AND revoked_at IS NULL",
            # Create delegation_audit table for immutable audit trail
            """CREATE TABLE IF NOT EXISTS delegation_audit (
                id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL CHECK(event_type IN (
                    'granted', 'revoked', 'expired', 'cascade_revoked',
                    'modified', 'terminated_revoked'
                )),
                delegator_id TEXT NOT NULL,
                delegate_id TEXT NOT NULL,
                delegation_grant_id TEXT,
                scope_before TEXT,
                scope_after TEXT,
                budget_before INTEGER,
                budget_after INTEGER,
                performed_by TEXT NOT NULL,
                performed_by_cli_user TEXT,
                reason TEXT,
                timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (delegator_id) REFERENCES workers(id) ON DELETE RESTRICT,
                FOREIGN KEY (delegate_id) REFERENCES workers(id) ON DELETE RESTRICT,
                FOREIGN KEY (delegation_grant_id) REFERENCES delegation_grants(id) ON DELETE SET NULL
            )""",
            # Indexes for delegation_audit
            "CREATE INDEX IF NOT EXISTS idx_delegation_audit_delegate ON delegation_audit(delegate_id)",
            "CREATE INDEX IF NOT EXISTS idx_delegation_audit_delegator ON delegation_audit(delegator_id)",
            "CREATE INDEX IF NOT EXISTS idx_delegation_audit_timestamp ON delegation_audit(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_delegation_audit_event_type ON delegation_audit(event_type)",
            "CREATE INDEX IF NOT EXISTS idx_delegation_audit_grant ON delegation_audit(delegation_grant_id)",
            # Index on workers.delegated_by
            "CREATE INDEX IF NOT EXISTS idx_workers_delegated_by ON workers(delegated_by) WHERE delegated_by IS NOT NULL",
            # Index on workers.delegation_expires_at
            "CREATE INDEX IF NOT EXISTS idx_workers_delegation_expires ON workers(delegation_expires_at) WHERE delegation_expires_at IS NOT NULL",
            # Trigger: Prevent modification of audit records (immutability)
            """CREATE TRIGGER IF NOT EXISTS prevent_delegation_audit_modification
            BEFORE UPDATE ON delegation_audit
            BEGIN
                SELECT RAISE(ABORT, 'Delegation audit records are immutable');
            END""",
            # Trigger: Prevent deletion of audit records
            """CREATE TRIGGER IF NOT EXISTS prevent_delegation_audit_deletion
            BEFORE DELETE ON delegation_audit
            BEGIN
                SELECT RAISE(ABORT, 'Delegation audit records cannot be deleted');
            END""",
            # Trigger: Auto-revoke delegations when worker is terminated
            """CREATE TRIGGER IF NOT EXISTS revoke_delegations_on_termination
            AFTER UPDATE OF status ON workers
            FOR EACH ROW
            WHEN NEW.status = 'terminated' AND OLD.status != 'terminated'
            BEGIN
                -- Revoke all delegations granted BY this worker
                UPDATE delegation_grants
                SET revoked_at = CURRENT_TIMESTAMP,
                    revoked_by = 'system',
                    revoke_reason = 'delegator terminated'
                WHERE delegator_id = NEW.id AND revoked_at IS NULL;

                -- Revoke delegation granted TO this worker
                UPDATE delegation_grants
                SET revoked_at = CURRENT_TIMESTAMP,
                    revoked_by = 'system',
                    revoke_reason = 'delegate terminated'
                WHERE delegate_id = NEW.id AND revoked_at IS NULL;

                -- Clear worker's delegated authority
                UPDATE workers
                SET hiring_authority_scope = NULL,
                    delegated_budget = 0,
                    delegated_by = NULL,
                    delegation_expires_at = NULL,
                    delegation_version = delegation_version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = NEW.id;
            END""",
            # Trigger: Auto-log delegation grants to audit table
            """CREATE TRIGGER IF NOT EXISTS log_delegation_grant
            AFTER INSERT ON delegation_grants
            FOR EACH ROW
            BEGIN
                INSERT INTO delegation_audit (
                    id,
                    event_type,
                    delegator_id,
                    delegate_id,
                    delegation_grant_id,
                    scope_after,
                    budget_after,
                    performed_by,
                    reason,
                    timestamp
                ) VALUES (
                    'audit-' || hex(randomblob(8)),
                    'granted',
                    NEW.delegator_id,
                    NEW.delegate_id,
                    NEW.id,
                    NEW.scope,
                    NEW.budget_amount,
                    NEW.delegator_id,
                    'delegation granted',
                    NEW.granted_at
                );
            END""",
            # Trigger: Auto-log delegation revocations to audit table
            """CREATE TRIGGER IF NOT EXISTS log_delegation_revoke
            AFTER UPDATE OF revoked_at ON delegation_grants
            FOR EACH ROW
            WHEN NEW.revoked_at IS NOT NULL AND OLD.revoked_at IS NULL
            BEGIN
                INSERT INTO delegation_audit (
                    id,
                    event_type,
                    delegator_id,
                    delegate_id,
                    delegation_grant_id,
                    performed_by,
                    reason,
                    timestamp
                ) VALUES (
                    'audit-' || hex(randomblob(8)),
                    CASE
                        WHEN NEW.revoke_reason LIKE 'cascade%' THEN 'cascade_revoked'
                        WHEN NEW.revoke_reason LIKE '%terminated%' THEN 'terminated_revoked'
                        ELSE 'revoked'
                    END,
                    NEW.delegator_id,
                    NEW.delegate_id,
                    NEW.id,
                    COALESCE(NEW.revoked_by, 'system'),
                    NEW.revoke_reason,
                    NEW.revoked_at
                );
            END""",
        ],
        # Version 18: Add name column to org_state for org branding
        18: [
            "ALTER TABLE org_state ADD COLUMN name TEXT NOT NULL DEFAULT 'My Organization'",
        ],
    }

    for version in range(from_version + 1, to_version + 1):
        if version in migrations:
            for sql in migrations[version]:
                try:
                    db.execute(sql)
                except sqlite3.OperationalError as e:
                    # Skip if column/table already exists (idempotent migrations)
                    if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                        continue
                    # Re-raise other operational errors
                    raise

    # Update schema version
    db.execute(
        "UPDATE config SET value = ? WHERE key = 'schema_version'",
        (str(to_version),)
    )
    db.connection.commit()
