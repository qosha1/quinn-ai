# CLI Database Specification

## Overview

The quinn.db SQLite database serves as the central persistence layer for all QuinnAI CLI operations. It stores org state, workers, teams, communication, and runtime state.

## Requirements

### Requirement: Single Central Database
The system SHALL use a single SQLite database (`quinn.db`) located in `live/quinn.db` within the org folder to store all runtime state.

#### Scenario: Database location
- **WHEN** an org folder is initialized
- **THEN** `live/quinn.db` SHALL be created with all required tables

#### Scenario: Database access
- **WHEN** any CLI command needs to read or write state
- **THEN** it SHALL use the central `quinn.db` database

### Requirement: Org State Table
The system SHALL maintain an `org_state` table to track the organization's lifecycle status.

#### Scenario: Org state schema
- **WHEN** the database is initialized
- **THEN** the `org_state` table SHALL contain:
  - `id` (TEXT PRIMARY KEY) - default 'default'
  - `status` (TEXT) - one of: 'uninitialized', 'initialized', 'running', 'stopped'
  - `ceo_worker_id` (TEXT) - reference to CEO worker
  - `started_at` (DATETIME) - when org was started
  - `stopped_at` (DATETIME) - when org was stopped
  - `created_at` (DATETIME) - row creation timestamp
  - `updated_at` (DATETIME) - last update timestamp

#### Scenario: Status constraints
- **WHEN** an org state status is set
- **THEN** it MUST be one of: 'uninitialized', 'initialized', 'running', 'stopped'

### Requirement: Teams Table
The system SHALL maintain a `teams` table to represent the hierarchical team structure.

#### Scenario: Teams schema
- **WHEN** the database is initialized
- **THEN** the `teams` table SHALL contain:
  - `id` (TEXT PRIMARY KEY) - unique team identifier
  - `name` (TEXT NOT NULL) - team display name
  - `parent_team_id` (TEXT) - reference to parent team for hierarchy
  - `created_at` (DATETIME) - row creation timestamp

#### Scenario: Team hierarchy
- **WHEN** a team has a parent
- **THEN** `parent_team_id` SHALL reference a valid team or be NULL for root teams

### Requirement: Workers Table
The system SHALL maintain a `workers` table to store all worker definitions (CEO, managers, ICs - all same base unit).

#### Scenario: Workers schema
- **WHEN** the database is initialized
- **THEN** the `workers` table SHALL contain:
  - `id` (TEXT PRIMARY KEY) - unique worker identifier
  - `name` (TEXT NOT NULL) - worker display name
  - `role` (TEXT NOT NULL) - worker's role designation
  - `team_id` (TEXT NOT NULL) - reference to worker's team
  - `manager_id` (TEXT) - reference to worker's manager (NULL for CEO)
  - `status` (TEXT NOT NULL) - worker lifecycle status
  - `skills` (TEXT NOT NULL DEFAULT '{}') - JSON object of skill scores (0-100)
  - `cost` (INTEGER NOT NULL) - relative cost score (0-100)
  - `created_at` (DATETIME) - row creation timestamp
  - `updated_at` (DATETIME) - last update timestamp

#### Scenario: Worker status constraints
- **WHEN** a worker status is set
- **THEN** it MUST be one of: 'pending', 'onboarding', 'active', 'offboarding', 'terminated'

#### Scenario: Worker cost constraints
- **WHEN** a worker cost is set
- **THEN** it MUST be between 0 and 100 inclusive

#### Scenario: Worker team relationship
- **WHEN** a worker is created
- **THEN** `team_id` MUST reference an existing team

### Requirement: Worker State Table
The system SHALL maintain a `worker_state` table to track runtime state for crash recovery and monitoring.

#### Scenario: Worker state schema
- **WHEN** the database is initialized
- **THEN** the `worker_state` table SHALL contain:
  - `worker_id` (TEXT PRIMARY KEY) - reference to worker
  - `runtime_status` (TEXT NOT NULL) - current runtime status
  - `current_task_id` (TEXT) - ID of task being worked on
  - `pid` (INTEGER) - process ID for crash detection
  - `started_at` (DATETIME) - when worker session started
  - `last_activity` (DATETIME) - last heartbeat timestamp
  - `tasks_completed` (INTEGER NOT NULL DEFAULT 0) - completed task count
  - `tasks_failed` (INTEGER NOT NULL DEFAULT 0) - failed task count
  - `updated_at` (DATETIME) - last update timestamp

#### Scenario: Runtime status constraints
- **WHEN** a worker runtime status is set
- **THEN** it MUST be one of: 'starting', 'running', 'idle', 'stopped', 'crashed'

#### Scenario: Worker state cascade
- **WHEN** a worker is deleted
- **THEN** their worker_state record SHALL be automatically deleted (CASCADE)

### Requirement: Channels Table
The system SHALL maintain a `channels` table for communication spaces (team, topic, direct).

#### Scenario: Channels schema
- **WHEN** the database is initialized
- **THEN** the `channels` table SHALL contain:
  - `id` (TEXT PRIMARY KEY) - unique channel identifier
  - `name` (TEXT NOT NULL) - channel display name
  - `type` (TEXT NOT NULL) - channel type
  - `team_id` (TEXT) - reference to team for team channels
  - `created_at` (DATETIME) - row creation timestamp

#### Scenario: Channel type constraints
- **WHEN** a channel type is set
- **THEN** it MUST be one of: 'team', 'topic', 'direct'

### Requirement: Channel Subscriptions Table
The system SHALL maintain a `channel_subscriptions` table to track which workers are in which channels.

#### Scenario: Channel subscriptions schema
- **WHEN** the database is initialized
- **THEN** the `channel_subscriptions` table SHALL contain:
  - `channel_id` (TEXT NOT NULL) - reference to channel
  - `worker_id` (TEXT NOT NULL) - reference to worker
  - `subscribed_at` (DATETIME) - when subscription was created
  - PRIMARY KEY (channel_id, worker_id)

#### Scenario: Subscription cascade
- **WHEN** a channel or worker is deleted
- **THEN** related subscriptions SHALL be automatically deleted (CASCADE)

### Requirement: Messages Table
The system SHALL maintain a `messages` table for permanent communication history. Messages are permanent knowledge - never deleted.

#### Scenario: Messages schema
- **WHEN** the database is initialized
- **THEN** the `messages` table SHALL contain:
  - `id` (TEXT PRIMARY KEY) - unique message identifier
  - `channel_id` (TEXT NOT NULL) - reference to channel
  - `thread_id` (TEXT) - groups messages in a thread
  - `parent_id` (TEXT) - reply to specific message
  - `from_worker_id` (TEXT NOT NULL) - sender worker
  - `content` (TEXT NOT NULL) - message content
  - `priority` (INTEGER NOT NULL DEFAULT 2) - priority level 0-4
  - `time_sensitivity` (TEXT NOT NULL DEFAULT 'whenever') - urgency level
  - `created_at` (DATETIME) - when message was sent

#### Scenario: Message priority constraints
- **WHEN** a message priority is set
- **THEN** it MUST be between 0 and 4 inclusive (0=critical, 4=backlog)

#### Scenario: Time sensitivity constraints
- **WHEN** a message time_sensitivity is set
- **THEN** it MUST be one of: 'immediate', 'hours', 'days', 'weeks', 'whenever'

#### Scenario: Message permanence
- **WHEN** a message is created
- **THEN** it SHALL NOT be deleted (messages are permanent knowledge)

### Requirement: Message References Table
The system SHALL maintain a `message_refs` table to link messages to beads, asks, or OKRs.

#### Scenario: Message refs schema
- **WHEN** the database is initialized
- **THEN** the `message_refs` table SHALL contain:
  - `message_id` (TEXT NOT NULL) - reference to message
  - `ref_type` (TEXT NOT NULL) - type of reference ('bead', 'ask', 'okr')
  - `ref_id` (TEXT NOT NULL) - ID of referenced item
  - PRIMARY KEY (message_id, ref_type, ref_id)

#### Scenario: Message ref cascade
- **WHEN** a message is deleted (which should never happen normally)
- **THEN** related refs SHALL be automatically deleted (CASCADE)

### Requirement: Config Table
The system SHALL maintain a `config` table for key-value configuration storage.

#### Scenario: Config schema
- **WHEN** the database is initialized
- **THEN** the `config` table SHALL contain:
  - `key` (TEXT PRIMARY KEY) - configuration key
  - `value` (TEXT NOT NULL) - configuration value

### Requirement: Database Indexes
The system SHALL maintain indexes for efficient querying.

#### Scenario: Required indexes
- **WHEN** the database is initialized
- **THEN** the following indexes SHALL be created:
  - `idx_teams_parent` on teams(parent_team_id)
  - `idx_workers_team` on workers(team_id)
  - `idx_workers_status` on workers(status)
  - `idx_workers_manager` on workers(manager_id)
  - `idx_worker_state_status` on worker_state(runtime_status)
  - `idx_channels_type` on channels(type)
  - `idx_channels_team` on channels(team_id)
  - `idx_messages_channel` on messages(channel_id)
  - `idx_messages_thread` on messages(thread_id)
  - `idx_messages_from_worker` on messages(from_worker_id)
  - `idx_messages_created_at` on messages(created_at)
  - `idx_messages_priority` on messages(priority)

### Requirement: Migration Support
The system SHALL support database migrations for schema evolution.

#### Scenario: Schema version tracking
- **WHEN** the database is initialized or migrated
- **THEN** the current schema version SHALL be stored in the config table

#### Scenario: Migration idempotency
- **WHEN** migrations are run
- **THEN** they SHALL be idempotent (safe to run multiple times)
