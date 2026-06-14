CREATE TABLE org_state (
    id TEXT PRIMARY KEY CHECK(id = 'default'),  -- Singleton: only 'default' allowed
    name TEXT NOT NULL DEFAULT 'My Organization',
    status TEXT NOT NULL CHECK(status IN ('uninitialized', 'initialized', 'running', 'stopped')),
    ceo_worker_id TEXT,
    started_at DATETIME,
    stopped_at DATETIME,
    -- Host mode (host-mode-init): when this org overlays an existing project,
    -- project_root holds the absolute path to that project. NULL for greenfield orgs.
    -- is_host_mode := (project_root IS NOT NULL)
    project_root TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE teams (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    parent_team_id TEXT,
    lead_id TEXT,
    channel_id TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    template_type TEXT,
    ttl_hours INTEGER,
    ttl_started_at DATETIME,
    status TEXT NOT NULL DEFAULT 'active',
    FOREIGN KEY (parent_team_id) REFERENCES teams(id) ON DELETE SET NULL,
    FOREIGN KEY (lead_id) REFERENCES workers(id) ON DELETE SET NULL,
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE SET NULL
);

CREATE INDEX idx_teams_parent ON teams(parent_team_id);

CREATE INDEX idx_teams_lead ON teams(lead_id);

CREATE TABLE workers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    team_id TEXT NOT NULL,
    manager_id TEXT,
    status TEXT NOT NULL CHECK(status IN ('pending', 'onboarding', 'active', 'offboarding', 'suspended', 'terminated')),
    skills TEXT NOT NULL DEFAULT '{}',
    cost INTEGER NOT NULL CHECK(cost >= 0 AND cost <= 100),
    -- Hiring authority cascade fields
    hiring_authority_scope TEXT,
    delegated_budget INTEGER NOT NULL DEFAULT 0,
    max_reports INTEGER NOT NULL DEFAULT 10,
    -- Delegation tracking fields (v17)
    delegation_version INTEGER NOT NULL DEFAULT 0,
    delegated_by TEXT,
    delegation_expires_at DATETIME,
    -- Offboarding workflow tracking
    offboarding_ask_bead_id TEXT,
    -- Provider preference (v20)
    preferred_provider TEXT,
    -- Per-worker CLI tool dependencies (v25): JSON array of {name, description, install_cmd, check_cmd}
    tools TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE RESTRICT,
    FOREIGN KEY (manager_id) REFERENCES workers(id) ON DELETE SET NULL
);

CREATE INDEX idx_workers_team ON workers(team_id);

CREATE INDEX idx_workers_status ON workers(status);

CREATE INDEX idx_workers_manager ON workers(manager_id);

CREATE INDEX idx_workers_delegated_by ON workers(delegated_by) WHERE delegated_by IS NOT NULL;

CREATE INDEX idx_workers_delegation_expires ON workers(delegation_expires_at) WHERE delegation_expires_at IS NOT NULL;

CREATE TABLE worker_state (
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

CREATE INDEX idx_worker_state_status ON worker_state(runtime_status);

CREATE TABLE sessions (
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

CREATE INDEX idx_sessions_worker ON sessions(worker_id);

CREATE INDEX idx_sessions_state ON sessions(state);

CREATE INDEX idx_sessions_last_activity ON sessions(last_activity);

CREATE TABLE channels (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('team', 'topic', 'direct')),
    team_id TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
);

CREATE INDEX idx_channels_type ON channels(type);

CREATE INDEX idx_channels_team ON channels(team_id);

CREATE TABLE channel_subscriptions (
    channel_id TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    subscribed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (channel_id, worker_id),
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE,
    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
);

CREATE INDEX idx_channel_subs_worker ON channel_subscriptions(worker_id);

CREATE TABLE messages (
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

CREATE INDEX idx_messages_channel ON messages(channel_id);

CREATE INDEX idx_messages_thread ON messages(thread_id);

CREATE INDEX idx_messages_from_worker ON messages(from_worker_id);

CREATE INDEX idx_messages_created_at ON messages(created_at);

CREATE INDEX idx_messages_priority ON messages(priority);

CREATE INDEX idx_messages_parent ON messages(parent_id);

CREATE TABLE message_refs (
    message_id TEXT NOT NULL,
    ref_type TEXT NOT NULL,
    ref_id TEXT NOT NULL,
    PRIMARY KEY (message_id, ref_type, ref_id),
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
);

CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE VIRTUAL TABLE messages_fts USING fts5(
    content,
    content='messages',
    content_rowid='rowid'
);

CREATE TRIGGER messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (NEW.rowid, NEW.content);
END;

CREATE TRIGGER messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', OLD.rowid, OLD.content);
END;

CREATE TRIGGER messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', OLD.rowid, OLD.content);
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES (NEW.rowid, NEW.content);
END;

CREATE TABLE team_members (
    team_id TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('member', 'lead', 'admin')),
    joined_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (team_id, worker_id),
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
);

CREATE INDEX idx_team_members_worker ON team_members(worker_id);

CREATE TABLE permissions (
    id TEXT PRIMARY KEY,
    bead_id TEXT,
    grantee_type TEXT NOT NULL CHECK(grantee_type IN ('worker', 'team')),
    grantee_id TEXT NOT NULL,
    level INTEGER NOT NULL CHECK(level >= 0 AND level <= 5),
    granted_by TEXT,
    granted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bead_id, grantee_type, grantee_id)
);

CREATE INDEX idx_permissions_bead ON permissions(bead_id);

CREATE INDEX idx_permissions_grantee ON permissions(grantee_type, grantee_id);

CREATE TABLE effective_permissions (
    worker_id TEXT NOT NULL,
    bead_id TEXT NOT NULL,
    level INTEGER NOT NULL CHECK(level >= 0 AND level <= 5),
    computed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (worker_id, bead_id),
    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
);

CREATE INDEX idx_effective_perm_level ON effective_permissions(level);

CREATE TABLE permission_audit (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL CHECK(action IN ('grant', 'revoke', 'check', 'deny')),
    bead_id TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    level INTEGER,
    details TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_perm_audit_bead ON permission_audit(bead_id);

CREATE INDEX idx_perm_audit_worker ON permission_audit(worker_id);

CREATE INDEX idx_perm_audit_action ON permission_audit(action);

CREATE INDEX idx_perm_audit_time ON permission_audit(created_at);

CREATE TABLE notification_beads (
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

CREATE INDEX idx_notif_beads_worker ON notification_beads(worker_id);

CREATE INDEX idx_notif_beads_status ON notification_beads(status);

CREATE INDEX idx_notif_beads_worker_status ON notification_beads(worker_id, status);

CREATE INDEX idx_notif_beads_priority ON notification_beads(priority);

CREATE INDEX idx_notif_beads_closed_at ON notification_beads(closed_at);

CREATE INDEX idx_notif_beads_expires_at ON notification_beads(expires_at);

CREATE INDEX idx_notif_beads_message ON notification_beads(message_id);

CREATE INDEX idx_notif_beads_channel ON notification_beads(channel_id);

CREATE TABLE budget_pools (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    total_credits DECIMAL(15,2) NOT NULL DEFAULT 0,
    period_start DATETIME NOT NULL,
    period_end DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE budget_allocations (
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

CREATE INDEX idx_budget_allocations_worker ON budget_allocations(worker_id);

CREATE INDEX idx_budget_allocations_source ON budget_allocations(source_worker_id);

CREATE INDEX idx_budget_allocations_period ON budget_allocations(period_start, period_end);

CREATE INDEX idx_budget_allocations_pool ON budget_allocations(pool_id);

CREATE TABLE budget_transactions (
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

CREATE INDEX idx_budget_transactions_allocation ON budget_transactions(allocation_id);

CREATE INDEX idx_budget_transactions_worker ON budget_transactions(worker_id);

CREATE INDEX idx_budget_transactions_type ON budget_transactions(type);

CREATE INDEX idx_budget_transactions_created ON budget_transactions(created_at);

CREATE INDEX idx_budget_transactions_provider ON budget_transactions(provider, model);

CREATE TABLE budget_balances (
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

CREATE INDEX idx_budget_balances_worker ON budget_balances(worker_id);

CREATE INDEX idx_budget_balances_available ON budget_balances(available);

CREATE TRIGGER update_budget_balance_on_transaction
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

CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,    -- worker.hired|worker.fired|okr.created|...
    entity_type TEXT NOT NULL,   -- worker|team|okr|message|work
    entity_id TEXT NOT NULL,
    payload TEXT,                -- JSON event data
    actor_id TEXT,               -- who triggered (optional)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_events_type ON events(event_type);

CREATE INDEX idx_events_entity ON events(entity_type, entity_id);

CREATE INDEX idx_events_actor ON events(actor_id);

CREATE INDEX idx_events_created_at ON events(created_at);

CREATE TABLE okrs (
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

CREATE INDEX idx_okrs_owner ON okrs(owner_worker_id);

CREATE INDEX idx_okrs_parent ON okrs(parent_okr_id);

CREATE INDEX idx_okrs_status ON okrs(status);

CREATE TABLE work_okr_links (
    work_id TEXT NOT NULL,
    okr_id TEXT NOT NULL,
    link_type TEXT NOT NULL DEFAULT 'contributes' CHECK(link_type IN ('contributes', 'blocks', 'depends_on')),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (work_id, okr_id),
    FOREIGN KEY (okr_id) REFERENCES okrs(id) ON DELETE CASCADE
);

CREATE INDEX idx_work_okr_links_okr ON work_okr_links(okr_id);

CREATE INDEX idx_work_okr_links_work ON work_okr_links(work_id);

CREATE TABLE escalations (
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

CREATE INDEX idx_escalations_issue ON escalations(issue_id);

CREATE INDEX idx_escalations_worker ON escalations(worker_id);

CREATE INDEX idx_escalations_escalated_to ON escalations(escalated_to_id);

CREATE INDEX idx_escalations_state ON escalations(state);

CREATE INDEX idx_escalations_created_at ON escalations(created_at);

CREATE TABLE lifecycle_configs (
    bead_type TEXT PRIMARY KEY,
    config TEXT NOT NULL,  -- JSON: {states: [], terminal_states: [], initial_state: str, transitions: {}}
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE delegation_grants (
    id TEXT PRIMARY KEY,
    delegator_id TEXT NOT NULL,           -- Who granted the authority
    delegate_id TEXT NOT NULL,            -- Who received authority
    scope TEXT NOT NULL,                  -- HiringScope JSON
    budget_amount INTEGER NOT NULL,       -- Budget delegated
    granted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,                  -- Optional time-limited delegation
    revoked_at DATETIME,                  -- NULL = active, populated = revoked
    revoked_by TEXT,                      -- Worker ID who revoked
    revoke_reason TEXT,                   -- Human-readable reason
    granted_by_cli_user TEXT,             -- Optional CLI user who initiated
    metadata TEXT,                        -- JSON for extensibility
    FOREIGN KEY (delegator_id) REFERENCES workers(id) ON DELETE CASCADE,
    FOREIGN KEY (delegate_id) REFERENCES workers(id) ON DELETE CASCADE,
    CHECK (delegator_id != delegate_id),
    CHECK (budget_amount >= 0)
);

CREATE INDEX idx_delegation_grants_delegator ON delegation_grants(delegator_id);

CREATE INDEX idx_delegation_grants_delegate ON delegation_grants(delegate_id);

CREATE INDEX idx_delegation_grants_active ON delegation_grants(revoked_at) WHERE revoked_at IS NULL;

CREATE INDEX idx_delegation_grants_expires ON delegation_grants(expires_at) WHERE expires_at IS NOT NULL AND revoked_at IS NULL;

CREATE TABLE delegation_audit (
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
);

CREATE INDEX idx_delegation_audit_delegate ON delegation_audit(delegate_id);

CREATE INDEX idx_delegation_audit_delegator ON delegation_audit(delegator_id);

CREATE INDEX idx_delegation_audit_timestamp ON delegation_audit(timestamp);

CREATE INDEX idx_delegation_audit_event_type ON delegation_audit(event_type);

CREATE INDEX idx_delegation_audit_grant ON delegation_audit(delegation_grant_id);

CREATE TRIGGER prevent_delegation_audit_modification
BEFORE UPDATE ON delegation_audit
BEGIN
    SELECT RAISE(ABORT, 'Delegation audit records are immutable');
END;

CREATE TRIGGER prevent_delegation_audit_deletion
BEFORE DELETE ON delegation_audit
BEGIN
    SELECT RAISE(ABORT, 'Delegation audit records cannot be deleted');
END;

CREATE TRIGGER revoke_delegations_on_termination
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
END;

CREATE TRIGGER log_delegation_grant
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
END;

CREATE TRIGGER log_delegation_revoke
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
END;

CREATE TABLE worker_escalation_state (
    worker_id TEXT PRIMARY KEY,
    current_state TEXT NOT NULL DEFAULT 'normal'
        CHECK(current_state IN ('normal', 'idle_warning', 'escalated_pending', 'escalated_resolved')),
    last_activity_at DATETIME NOT NULL,
    idle_since DATETIME,
    escalation_created_at DATETIME,
    escalation_id TEXT,
    escalation_target_id TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE,
    FOREIGN KEY (escalation_target_id) REFERENCES workers(id) ON DELETE SET NULL
);

CREATE INDEX idx_escalation_state_worker ON worker_escalation_state(worker_id);

CREATE INDEX idx_escalation_state_status ON worker_escalation_state(current_state);

CREATE INDEX idx_escalation_state_idle_since ON worker_escalation_state(idle_since) WHERE idle_since IS NOT NULL;

CREATE TABLE status_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL CHECK(entity_type IN ('worker', 'worker_state', 'session')),
    entity_id TEXT NOT NULL,
    old_status TEXT NOT NULL,
    new_status TEXT NOT NULL,
    changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_status_changes_entity ON status_changes(entity_type, entity_id);

CREATE INDEX idx_status_changes_changed_at ON status_changes(changed_at);

CREATE INDEX idx_status_changes_id_asc ON status_changes(id ASC);

CREATE TABLE status_change_cursors (
    client_id TEXT PRIMARY KEY,
    last_change_id INTEGER NOT NULL DEFAULT 0,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER log_worker_status_change
AFTER UPDATE OF status ON workers
FOR EACH ROW
WHEN OLD.status != NEW.status
BEGIN
    INSERT INTO status_changes (entity_type, entity_id, old_status, new_status, changed_at)
    VALUES ('worker', NEW.id, OLD.status, NEW.status, CURRENT_TIMESTAMP);
END;

CREATE TRIGGER log_worker_runtime_status_change
AFTER UPDATE OF runtime_status ON worker_state
FOR EACH ROW
WHEN OLD.runtime_status != NEW.runtime_status
BEGIN
    INSERT INTO status_changes (entity_type, entity_id, old_status, new_status, changed_at)
    VALUES ('worker_state', NEW.worker_id, OLD.runtime_status, NEW.runtime_status, CURRENT_TIMESTAMP);
END;

CREATE TRIGGER log_session_state_change
AFTER UPDATE OF state ON sessions
FOR EACH ROW
WHEN OLD.state != NEW.state
BEGIN
    INSERT INTO status_changes (entity_type, entity_id, old_status, new_status, changed_at)
    VALUES ('session', NEW.id, OLD.state, NEW.state, CURRENT_TIMESTAMP);
END;

CREATE TABLE worker_resume_states (
    id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL UNIQUE,

    -- Current work state snapshot
    current_task_id TEXT,
    current_task_context TEXT,  -- JSON: serialized task context

    -- Activity state
    last_activity_at DATETIME,
    tasks_completed INTEGER NOT NULL DEFAULT 0,
    tasks_failed INTEGER NOT NULL DEFAULT 0,

    -- Session state
    session_provider TEXT,
    session_model TEXT,
    working_directory TEXT,

    -- Acknowledgement tracking
    wrapup_requested_at DATETIME,
    wrapup_acked_at DATETIME,
    ack_message TEXT,  -- Optional worker message about state

    -- Lifecycle
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL,
    consumed_at DATETIME,  -- Set when used for resume

    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
);

CREATE INDEX idx_worker_resume_worker ON worker_resume_states(worker_id);

CREATE INDEX idx_worker_resume_expires ON worker_resume_states(expires_at) WHERE consumed_at IS NULL;

CREATE INDEX idx_worker_resume_wrapup ON worker_resume_states(wrapup_requested_at) WHERE wrapup_acked_at IS NULL;

CREATE TABLE activity_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    worker_id TEXT NOT NULL,
    activity_type TEXT NOT NULL CHECK(activity_type IN (
        'bead_update', 'message_sent', 'code_commit',
        'file_change', 'session_output', 'heartbeat'
    )),
    signal_strength INTEGER NOT NULL CHECK(signal_strength >= 1 AND signal_strength <= 5),
    metadata TEXT,  -- JSON
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
);

CREATE INDEX idx_activity_signals_worker ON activity_signals(worker_id, created_at DESC);

CREATE INDEX idx_activity_signals_recent ON activity_signals(created_at DESC);
