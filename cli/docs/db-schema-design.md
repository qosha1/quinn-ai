# quinn.db Schema Design

## Research Summary

### Patterns from bottas
- BeadsMemory: JSONL-based execution records, thread-safe
- WorkerState: Per-worker JSON state files with PID tracking for crash recovery
- Separation of concerns: execution records vs state tracking

### Patterns from beads-org
- Extensive indexing on status/priority/assignee
- Content hash for deduplication
- Dependencies as edge table with types
- Hierarchical "ready work" views

## Schema

```sql
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
CREATE INDEX idx_teams_parent ON teams(parent_team_id);

-- Workers (everyone is a worker - CEO, manager, junior)
CREATE TABLE IF NOT EXISTS workers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    team_id TEXT NOT NULL,
    manager_id TEXT,
    status TEXT NOT NULL CHECK(status IN ('pending', 'onboarding', 'active', 'offboarding', 'terminated')),
    skills TEXT NOT NULL DEFAULT '{}',  -- JSON: {"coding": 80, "reasoning": 60}
    cost INTEGER NOT NULL CHECK(cost >= 0 AND cost <= 100),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE RESTRICT,
    FOREIGN KEY (manager_id) REFERENCES workers(id) ON DELETE SET NULL
);
CREATE INDEX idx_workers_team ON workers(team_id);
CREATE INDEX idx_workers_status ON workers(status);
CREATE INDEX idx_workers_manager ON workers(manager_id);

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
CREATE INDEX idx_worker_state_status ON worker_state(runtime_status);

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
CREATE INDEX idx_channels_type ON channels(type);
CREATE INDEX idx_channels_team ON channels(team_id);

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
    thread_id TEXT,           -- Groups messages in a thread
    parent_id TEXT,           -- Reply to specific message
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

-- Message references (links to beads, asks, etc.)
CREATE TABLE IF NOT EXISTS message_refs (
    message_id TEXT NOT NULL,
    ref_type TEXT NOT NULL,   -- 'bead', 'ask', 'okr'
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
```

## Relationships

```
org_state
    └── ceo_worker_id → workers.id

teams
    └── parent_team_id → teams.id (self-referential hierarchy)

workers
    ├── team_id → teams.id
    └── manager_id → workers.id (self-referential hierarchy)

worker_state
    └── worker_id → workers.id

channels
    └── team_id → teams.id (for team channels)

channel_subscriptions
    ├── channel_id → channels.id
    └── worker_id → workers.id

messages
    ├── channel_id → channels.id
    ├── from_worker_id → workers.id
    └── parent_id → messages.id (threading)

message_refs
    └── message_id → messages.id
```

## Key Queries

```sql
-- Get worker's assigned beads (via beads tables, not shown here)
-- Note: beads tables come from beads-org, integrated separately

-- Get worker's unread messages (via notification beads)
SELECT m.* FROM messages m
JOIN channel_subscriptions cs ON m.channel_id = cs.channel_id
WHERE cs.worker_id = ?
AND m.created_at > (SELECT last_read_at FROM ...)  -- Tracked via notification beads

-- Get team hierarchy
WITH RECURSIVE team_tree AS (
    SELECT id, name, parent_team_id, 0 as depth FROM teams WHERE id = ?
    UNION ALL
    SELECT t.id, t.name, t.parent_team_id, tt.depth + 1
    FROM teams t JOIN team_tree tt ON t.parent_team_id = tt.id
)
SELECT * FROM team_tree;

-- Get worker's direct reports
SELECT * FROM workers WHERE manager_id = ?;

-- Get org status
SELECT * FROM org_state WHERE id = 'default';
```

## Design Notes

1. **Notifications are beads** - Not a separate table. When message sent, notification beads created per subscriber.
2. **Messages are permanent** - No deleted_at, no updates to content. Append-only.
3. **Worker vs worker_state** - Separate tables: workers = org-chart identity, worker_state = runtime.
4. **Skills as JSON** - Flexible, no schema migration for new skills.
5. **Cost 0-100** - Relative, system maps to providers.
6. **Beads integration** - beads-org tables live alongside these. Notifications, tasks, asks are all beads.
