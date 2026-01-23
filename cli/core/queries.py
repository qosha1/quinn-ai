"""
Query helpers for common database operations.

Provides high-level functions for interacting with quinn.db without
writing raw SQL. All functions are organized by entity type.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from .db import Database
from shared.enums import OrgStatus


# ===================
# DATA CLASSES
# ===================

@dataclass
class OrgState:
    """Organization state."""
    id: str
    name: str
    status: str
    ceo_worker_id: Optional[str]
    started_at: Optional[datetime]
    stopped_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


@dataclass
class Team:
    """Team definition."""
    id: str
    name: str
    parent_team_id: Optional[str]
    lead_id: Optional[str]
    channel_id: Optional[str]
    created_at: datetime


@dataclass
class Worker:
    """Worker definition."""
    id: str
    name: str
    role: str
    team_id: str
    manager_id: Optional[str]
    status: str
    skills: dict[str, int]
    cost: int
    hiring_authority_scope: Optional[str]
    delegated_budget: int
    max_reports: int
    created_at: datetime
    updated_at: datetime


@dataclass
class WorkerState:
    """Worker runtime state."""
    worker_id: str
    runtime_status: str
    current_task_id: Optional[str]
    pid: Optional[int]
    started_at: Optional[datetime]
    last_activity: Optional[datetime]
    tasks_completed: int
    tasks_failed: int
    updated_at: datetime


@dataclass
class Channel:
    """Communication channel."""
    id: str
    name: str
    type: str
    team_id: Optional[str]
    created_at: datetime


@dataclass
class Message:
    """Message in a channel."""
    id: str
    channel_id: str
    thread_id: Optional[str]
    parent_id: Optional[str]
    from_worker_id: str
    content: str
    priority: int
    time_sensitivity: str
    created_at: datetime


# ===================
# ID GENERATION
# ===================

def generate_id(prefix: str = "") -> str:
    """Generate a unique ID.

    Args:
        prefix: Optional prefix for the ID

    Returns:
        Unique identifier string
    """
    short_uuid = str(uuid.uuid4())[:8]
    return f"{prefix}-{short_uuid}" if prefix else short_uuid


# ===================
# ORG STATE QUERIES
# ===================

def get_org_state(db: Database) -> Optional[OrgState]:
    """Get the current org state.

    Args:
        db: Database instance

    Returns:
        OrgState or None if not initialized
    """
    row = db.fetchone("SELECT * FROM org_state WHERE id = 'default'")
    if not row:
        return None

    return OrgState(
        id=row["id"],
        name=row["name"] if row["name"] else "My Organization",
        status=row["status"],
        ceo_worker_id=row["ceo_worker_id"],
        started_at=row["started_at"],
        stopped_at=row["stopped_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def update_org_status(
    db: Database,
    status: str,
    ceo_worker_id: Optional[str] = None,
) -> None:
    """Update org status.

    Args:
        db: Database instance
        status: New status ('uninitialized', 'initialized', 'running', 'stopped')
        ceo_worker_id: Optional CEO worker ID to set
    """
    now = datetime.now()
    if status == OrgStatus.RUNNING.value:
        db.execute(
            """UPDATE org_state SET status = ?, ceo_worker_id = ?,
               started_at = ?, updated_at = ? WHERE id = 'default'""",
            (status, ceo_worker_id, now, now)
        )
    elif status == OrgStatus.STOPPED.value:
        db.execute(
            """UPDATE org_state SET status = ?, stopped_at = ?,
               updated_at = ? WHERE id = 'default'""",
            (status, now, now)
        )
    else:
        db.execute(
            """UPDATE org_state SET status = ?, ceo_worker_id = ?,
               updated_at = ? WHERE id = 'default'""",
            (status, ceo_worker_id, now)
        )
    db.connection.commit()


# ===================
# TEAM QUERIES
# ===================

def create_team(
    db: Database,
    name: str,
    parent_team_id: Optional[str] = None,
    lead_id: Optional[str] = None,
    team_id: Optional[str] = None,
    auto_create_channel: bool = True,
) -> Team:
    """Create a new team.

    Args:
        db: Database instance
        name: Team name
        parent_team_id: Optional parent team for hierarchy
        lead_id: Optional team lead worker ID
        team_id: Optional custom ID (generated if not provided)
        auto_create_channel: Create a team channel automatically (default True)

    Returns:
        Created Team
    """
    if team_id is None:
        team_id = generate_id("team")

    now = datetime.now()
    channel_id = None

    # Create the team first (before channel, due to foreign key constraint)
    db.execute(
        """INSERT INTO teams (id, name, parent_team_id, lead_id, channel_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (team_id, name, parent_team_id, lead_id, None, now)
    )
    db.connection.commit()

    # Then create a channel for the team and update the team
    if auto_create_channel:
        channel_name = name.lower().replace(" ", "-")
        channel = create_channel(
            db,
            name=channel_name,
            channel_type="team",
            team_id=team_id,
        )
        channel_id = channel.id
        # Update team with channel_id
        db.execute(
            "UPDATE teams SET channel_id = ? WHERE id = ?",
            (channel_id, team_id)
        )
        db.connection.commit()

    return Team(
        id=team_id,
        name=name,
        parent_team_id=parent_team_id,
        lead_id=lead_id,
        channel_id=channel_id,
        created_at=now,
    )


def get_team(db: Database, team_id: str) -> Optional[Team]:
    """Get a team by ID.

    Args:
        db: Database instance
        team_id: Team ID

    Returns:
        Team or None
    """
    row = db.fetchone("SELECT * FROM teams WHERE id = ?", (team_id,))
    if not row:
        return None

    return Team(
        id=row["id"],
        name=row["name"],
        parent_team_id=row["parent_team_id"],
        lead_id=row["lead_id"],
        channel_id=row["channel_id"],
        created_at=row["created_at"],
    )


def get_team_channel(db: Database, team_id: str) -> Optional[Channel]:
    """Get the channel for a team.

    Args:
        db: Database instance
        team_id: Team ID

    Returns:
        Channel or None if no channel exists for team
    """
    row = db.fetchone(
        "SELECT * FROM channels WHERE team_id = ? AND type = 'team'",
        (team_id,)
    )
    if not row:
        return None

    return Channel(
        id=row["id"],
        name=row["name"],
        type=row["type"],
        team_id=row["team_id"],
        created_at=row["created_at"],
    )


def get_team_children(db: Database, team_id: str) -> list[Team]:
    """Get child teams of a team.

    Args:
        db: Database instance
        team_id: Parent team ID

    Returns:
        List of child teams
    """
    rows = db.fetchall(
        "SELECT * FROM teams WHERE parent_team_id = ?",
        (team_id,)
    )
    return [
        Team(
            id=row["id"],
            name=row["name"],
            parent_team_id=row["parent_team_id"],
            lead_id=row["lead_id"],
            channel_id=row["channel_id"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_all_teams(db: Database) -> list[Team]:
    """Get all teams.

    Args:
        db: Database instance

    Returns:
        List of all teams
    """
    rows = db.fetchall("SELECT * FROM teams ORDER BY created_at")
    return [
        Team(
            id=row["id"],
            name=row["name"],
            parent_team_id=row["parent_team_id"],
            lead_id=row["lead_id"],
            channel_id=row["channel_id"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


# ===================
# WORKER QUERIES
# ===================

def create_worker(
    db: Database,
    name: str,
    role: str,
    team_id: str,
    cost: int,
    manager_id: Optional[str] = None,
    skills: Optional[dict[str, int]] = None,
    worker_id: Optional[str] = None,
    hiring_authority_scope: Optional[str] = None,
    delegated_budget: int = 0,
    max_reports: int = 10,
) -> Worker:
    """Create a new worker.

    Args:
        db: Database instance
        name: Worker name
        role: Worker role
        team_id: Team ID
        cost: Cost score (0-100)
        manager_id: Optional manager worker ID
        skills: Optional skills dict
        worker_id: Optional custom ID
        hiring_authority_scope: Optional JSON serialized HiringScope
        delegated_budget: Budget worker can delegate for hiring
        max_reports: Maximum direct reports allowed

    Returns:
        Created Worker
    """
    if worker_id is None:
        worker_id = generate_id("wrkr")

    if skills is None:
        skills = {}

    now = datetime.now()
    skills_json = json.dumps(skills)

    db.execute(
        """INSERT INTO workers
           (id, name, role, team_id, manager_id, status, skills, cost,
            hiring_authority_scope, delegated_budget, max_reports, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)""",
        (worker_id, name, role, team_id, manager_id, skills_json, cost,
         hiring_authority_scope, delegated_budget, max_reports, now, now)
    )
    db.connection.commit()

    return Worker(
        id=worker_id,
        name=name,
        role=role,
        team_id=team_id,
        manager_id=manager_id,
        status="pending",
        skills=skills,
        cost=cost,
        hiring_authority_scope=hiring_authority_scope,
        delegated_budget=delegated_budget,
        max_reports=max_reports,
        created_at=now,
        updated_at=now,
    )


def get_worker(db: Database, worker_id: str) -> Optional[Worker]:
    """Get a worker by ID.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        Worker or None
    """
    row = db.fetchone("SELECT * FROM workers WHERE id = ?", (worker_id,))
    if not row:
        return None

    return Worker(
        id=row["id"],
        name=row["name"],
        role=row["role"],
        team_id=row["team_id"],
        manager_id=row["manager_id"],
        status=row["status"],
        skills=json.loads(row["skills"]),
        cost=row["cost"],
        hiring_authority_scope=row["hiring_authority_scope"],
        delegated_budget=row["delegated_budget"],
        max_reports=row["max_reports"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def get_worker_by_name(db: Database, name: str) -> Optional[Worker]:
    """Get a worker by name.

    Args:
        db: Database instance
        name: Worker name (case-insensitive)

    Returns:
        Worker or None
    """
    row = db.fetchone(
        "SELECT * FROM workers WHERE LOWER(name) = LOWER(?)",
        (name,)
    )
    if not row:
        return None

    return Worker(
        id=row["id"],
        name=row["name"],
        role=row["role"],
        team_id=row["team_id"],
        manager_id=row["manager_id"],
        status=row["status"],
        skills=json.loads(row["skills"]),
        cost=row["cost"],
        hiring_authority_scope=row["hiring_authority_scope"],
        delegated_budget=row["delegated_budget"],
        max_reports=row["max_reports"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def update_worker_status(db: Database, worker_id: str, status: str) -> None:
    """Update worker lifecycle status.

    Args:
        db: Database instance
        worker_id: Worker ID
        status: New status
    """
    now = datetime.now()
    db.execute(
        "UPDATE workers SET status = ?, updated_at = ? WHERE id = ?",
        (status, now, worker_id)
    )
    db.connection.commit()


def get_workers_by_status(db: Database, status: str) -> list[Worker]:
    """Get workers by status.

    Args:
        db: Database instance
        status: Worker status to filter by

    Returns:
        List of matching workers
    """
    rows = db.fetchall("SELECT * FROM workers WHERE status = ?", (status,))
    return [
        Worker(
            id=row["id"],
            name=row["name"],
            role=row["role"],
            team_id=row["team_id"],
            manager_id=row["manager_id"],
            status=row["status"],
            skills=json.loads(row["skills"]),
            cost=row["cost"],
            hiring_authority_scope=row["hiring_authority_scope"],
            delegated_budget=row["delegated_budget"],
            max_reports=row["max_reports"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def get_workers_by_manager(db: Database, manager_id: str) -> list[Worker]:
    """Get direct reports of a manager.

    Args:
        db: Database instance
        manager_id: Manager's worker ID

    Returns:
        List of direct reports
    """
    rows = db.fetchall("SELECT * FROM workers WHERE manager_id = ?", (manager_id,))
    return [
        Worker(
            id=row["id"],
            name=row["name"],
            role=row["role"],
            team_id=row["team_id"],
            manager_id=row["manager_id"],
            status=row["status"],
            skills=json.loads(row["skills"]),
            cost=row["cost"],
            hiring_authority_scope=row["hiring_authority_scope"],
            delegated_budget=row["delegated_budget"],
            max_reports=row["max_reports"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def get_team_workers(db: Database, team_id: str) -> list[Worker]:
    """Get all workers in a team.

    Args:
        db: Database instance
        team_id: Team ID

    Returns:
        List of workers in team
    """
    rows = db.fetchall("SELECT * FROM workers WHERE team_id = ?", (team_id,))
    return [
        Worker(
            id=row["id"],
            name=row["name"],
            role=row["role"],
            team_id=row["team_id"],
            manager_id=row["manager_id"],
            status=row["status"],
            skills=json.loads(row["skills"]),
            cost=row["cost"],
            hiring_authority_scope=row["hiring_authority_scope"],
            delegated_budget=row["delegated_budget"],
            max_reports=row["max_reports"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


# ===================
# WORKER STATE QUERIES
# ===================

def create_worker_state(
    db: Database,
    worker_id: str,
    pid: Optional[int] = None,
) -> WorkerState:
    """Create worker runtime state.

    Args:
        db: Database instance
        worker_id: Worker ID
        pid: Process ID

    Returns:
        Created WorkerState
    """
    now = datetime.now()
    db.execute(
        """INSERT INTO worker_state
           (worker_id, runtime_status, pid, started_at, last_activity, updated_at)
           VALUES (?, 'starting', ?, ?, ?, ?)""",
        (worker_id, pid, now, now, now)
    )
    db.connection.commit()

    return WorkerState(
        worker_id=worker_id,
        runtime_status="starting",
        current_task_id=None,
        pid=pid,
        started_at=now,
        last_activity=now,
        tasks_completed=0,
        tasks_failed=0,
        updated_at=now,
    )


def get_worker_state(db: Database, worker_id: str) -> Optional[WorkerState]:
    """Get worker runtime state.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        WorkerState or None
    """
    row = db.fetchone("SELECT * FROM worker_state WHERE worker_id = ?", (worker_id,))
    if not row:
        return None

    return WorkerState(
        worker_id=row["worker_id"],
        runtime_status=row["runtime_status"],
        current_task_id=row["current_task_id"],
        pid=row["pid"],
        started_at=row["started_at"],
        last_activity=row["last_activity"],
        tasks_completed=row["tasks_completed"],
        tasks_failed=row["tasks_failed"],
        updated_at=row["updated_at"],
    )


def update_worker_runtime_status(
    db: Database,
    worker_id: str,
    runtime_status: str,
    current_task_id: Optional[str] = None,
) -> None:
    """Update worker runtime status.

    Args:
        db: Database instance
        worker_id: Worker ID
        runtime_status: New runtime status
        current_task_id: Optional current task
    """
    now = datetime.now()
    db.execute(
        """UPDATE worker_state SET runtime_status = ?, current_task_id = ?,
           last_activity = ?, updated_at = ? WHERE worker_id = ?""",
        (runtime_status, current_task_id, now, now, worker_id)
    )
    db.connection.commit()


def record_worker_heartbeat(db: Database, worker_id: str) -> None:
    """Record worker heartbeat.

    Args:
        db: Database instance
        worker_id: Worker ID
    """
    now = datetime.now()
    db.execute(
        "UPDATE worker_state SET last_activity = ?, updated_at = ? WHERE worker_id = ?",
        (now, now, worker_id)
    )
    db.connection.commit()


def increment_worker_task_count(
    db: Database,
    worker_id: str,
    completed: bool = True,
) -> None:
    """Increment worker task count.

    Args:
        db: Database instance
        worker_id: Worker ID
        completed: True if completed, False if failed
    """
    now = datetime.now()
    if completed:
        db.execute(
            "UPDATE worker_state SET tasks_completed = tasks_completed + 1, updated_at = ? WHERE worker_id = ?",
            (now, worker_id)
        )
    else:
        db.execute(
            "UPDATE worker_state SET tasks_failed = tasks_failed + 1, updated_at = ? WHERE worker_id = ?",
            (now, worker_id)
        )
    db.connection.commit()


def get_workers_by_runtime_status(db: Database, runtime_status: str) -> list[WorkerState]:
    """Get worker states by runtime status.

    Args:
        db: Database instance
        runtime_status: Runtime status to filter by

    Returns:
        List of matching worker states
    """
    rows = db.fetchall(
        "SELECT * FROM worker_state WHERE runtime_status = ?",
        (runtime_status,)
    )
    return [
        WorkerState(
            worker_id=row["worker_id"],
            runtime_status=row["runtime_status"],
            current_task_id=row["current_task_id"],
            pid=row["pid"],
            started_at=row["started_at"],
            last_activity=row["last_activity"],
            tasks_completed=row["tasks_completed"],
            tasks_failed=row["tasks_failed"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


# ===================
# CHANNEL QUERIES
# ===================

def create_channel(
    db: Database,
    name: str,
    channel_type: str,
    team_id: Optional[str] = None,
    channel_id: Optional[str] = None,
) -> Channel:
    """Create a new channel.

    Args:
        db: Database instance
        name: Channel name
        channel_type: 'team', 'topic', or 'direct'
        team_id: Optional team ID for team channels
        channel_id: Optional custom ID

    Returns:
        Created Channel
    """
    if channel_id is None:
        channel_id = generate_id("chan")

    now = datetime.now()
    db.execute(
        "INSERT INTO channels (id, name, type, team_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (channel_id, name, channel_type, team_id, now)
    )
    db.connection.commit()

    return Channel(
        id=channel_id,
        name=name,
        type=channel_type,
        team_id=team_id,
        created_at=now,
    )


def create_direct_channel(
    db: Database,
    worker1_id: str,
    worker2_id: str,
    channel_id: Optional[str] = None,
) -> Channel:
    """Create a direct message channel between two workers.

    Creates a channel and subscribes both workers. Direct channels are
    restricted to only these two participants.

    Args:
        db: Database instance
        worker1_id: First worker ID
        worker2_id: Second worker ID
        channel_id: Optional custom channel ID

    Returns:
        Created Channel with both workers subscribed

    Raises:
        ChannelAccessError: If either worker doesn't exist
    """
    # Validate both workers exist
    worker1 = get_worker(db, worker1_id)
    if not worker1:
        raise ChannelAccessError(worker1_id, "new", "Worker not found")

    worker2 = get_worker(db, worker2_id)
    if not worker2:
        raise ChannelAccessError(worker2_id, "new", "Worker not found")

    # Generate consistent channel name (sorted IDs for uniqueness)
    sorted_ids = sorted([worker1_id, worker2_id])
    channel_name = f"dm-{sorted_ids[0][:8]}-{sorted_ids[1][:8]}"

    # Check if channel already exists between these workers
    existing = get_channel_by_name(db, channel_name)
    if existing:
        return existing

    # Create the channel
    channel = create_channel(db, channel_name, "direct", channel_id=channel_id)

    # Subscribe both workers (skip_validation since we just validated)
    subscribe_to_channel(db, channel.id, worker1_id, skip_validation=True)
    subscribe_to_channel(db, channel.id, worker2_id, skip_validation=True)

    return channel


def get_or_create_direct_channel(
    db: Database,
    worker1_id: str,
    worker2_id: str,
) -> Channel:
    """Get an existing direct channel or create one between two workers.

    Args:
        db: Database instance
        worker1_id: First worker ID
        worker2_id: Second worker ID

    Returns:
        Direct channel between the two workers
    """
    # Generate consistent channel name
    sorted_ids = sorted([worker1_id, worker2_id])
    channel_name = f"dm-{sorted_ids[0][:8]}-{sorted_ids[1][:8]}"

    existing = get_channel_by_name(db, channel_name)
    if existing:
        return existing

    return create_direct_channel(db, worker1_id, worker2_id)


def get_channel(db: Database, channel_id: str) -> Optional[Channel]:
    """Get a channel by ID.

    Args:
        db: Database instance
        channel_id: Channel ID

    Returns:
        Channel or None
    """
    row = db.fetchone("SELECT * FROM channels WHERE id = ?", (channel_id,))
    if not row:
        return None

    return Channel(
        id=row["id"],
        name=row["name"],
        type=row["type"],
        team_id=row["team_id"],
        created_at=row["created_at"],
    )


def get_channel_by_name(db: Database, name: str) -> Optional[Channel]:
    """Get a channel by name.

    Args:
        db: Database instance
        name: Channel name (case-insensitive)

    Returns:
        Channel or None
    """
    row = db.fetchone(
        "SELECT * FROM channels WHERE LOWER(name) = LOWER(?)",
        (name,)
    )
    if not row:
        return None

    return Channel(
        id=row["id"],
        name=row["name"],
        type=row["type"],
        team_id=row["team_id"],
        created_at=row["created_at"],
    )


def create_default_org_channels(db: Database) -> list[Channel]:
    """Create default org-wide channels.

    Creates 'general' for org-wide announcements and 'escalations'
    for escalation messages. Skips channels that already exist.

    Args:
        db: Database instance

    Returns:
        List of created channels
    """
    default_channels = [
        ("general", "topic"),      # org-wide announcements
        ("escalations", "topic"),  # for escalation messages
    ]

    created = []
    for name, channel_type in default_channels:
        # Check if channel already exists
        existing = get_channel_by_name(db, name)
        if existing is None:
            channel = create_channel(db, name, channel_type)
            created.append(channel)

    return created


class ChannelAccessError(Exception):
    """Raised when a worker cannot access a channel."""

    def __init__(self, worker_id: str, channel_id: str, reason: str):
        self.worker_id = worker_id
        self.channel_id = channel_id
        self.reason = reason
        super().__init__(f"Worker '{worker_id}' cannot access channel '{channel_id}': {reason}")


def can_subscribe_to_channel(db: Database, channel_id: str, worker_id: str) -> tuple[bool, str]:
    """Check if a worker can subscribe to a channel.

    Validates channel access based on channel type:
    - topic: Any worker can subscribe (org-wide channels)
    - team: Only team members can subscribe
    - direct: Only the two participants can subscribe

    Args:
        db: Database instance
        channel_id: Channel ID
        worker_id: Worker ID

    Returns:
        Tuple of (can_subscribe: bool, reason: str)
    """
    channel = get_channel(db, channel_id)
    if not channel:
        return False, "Channel not found"

    worker = get_worker(db, worker_id)
    if not worker:
        return False, "Worker not found"

    if channel.type == "topic":
        # Topic channels are open to all workers in the org
        return True, "Topic channels are open to all"

    elif channel.type == "team":
        # Team channels require team membership
        if not channel.team_id:
            return False, "Team channel has no team_id"

        # Check if worker is in this team (primary team or team_members)
        if worker.team_id == channel.team_id:
            return True, "Worker is in the team"

        # Check team_members table for additional memberships
        membership = db.fetchone(
            "SELECT 1 FROM team_members WHERE team_id = ? AND worker_id = ?",
            (channel.team_id, worker_id)
        )
        if membership:
            return True, "Worker is a team member"

        return False, "Worker is not a member of the team"

    elif channel.type == "direct":
        # Direct channels: check if worker is one of the two participants
        # Direct channel names follow format "dm-{worker1_id}-{worker2_id}"
        # or we check existing subscribers (should be at most 2)
        subscribers = get_channel_subscribers(db, channel_id)

        if len(subscribers) < 2:
            # Channel not yet fully set up, check if this is an allowed participant
            # For direct channels, the creator and target should both be able to join
            # We allow subscription if there are fewer than 2 subscribers
            if len(subscribers) == 0:
                return True, "First participant in direct channel"
            elif len(subscribers) == 1 and worker_id not in subscribers:
                return True, "Second participant in direct channel"
            elif worker_id in subscribers:
                return True, "Already subscribed"

        # If already 2 subscribers, only they can access
        if worker_id in subscribers:
            return True, "Worker is a direct channel participant"

        return False, "Worker is not a participant in this direct channel"

    else:
        # Unknown channel type - deny by default
        return False, f"Unknown channel type: {channel.type}"


def subscribe_to_channel(
    db: Database,
    channel_id: str,
    worker_id: str,
    skip_validation: bool = False,
) -> None:
    """Subscribe a worker to a channel.

    Validates that the worker is allowed to subscribe based on channel type:
    - topic: Any worker can subscribe
    - team: Only team members can subscribe
    - direct: Only the two participants can subscribe

    Args:
        db: Database instance
        channel_id: Channel ID
        worker_id: Worker ID
        skip_validation: Skip permission checks (for internal/system use only)

    Raises:
        ChannelAccessError: If worker cannot subscribe to this channel
    """
    if not skip_validation:
        can_subscribe, reason = can_subscribe_to_channel(db, channel_id, worker_id)
        if not can_subscribe:
            raise ChannelAccessError(worker_id, channel_id, reason)

    now = datetime.now()
    db.execute(
        "INSERT OR IGNORE INTO channel_subscriptions (channel_id, worker_id, subscribed_at) VALUES (?, ?, ?)",
        (channel_id, worker_id, now)
    )
    db.connection.commit()


def is_subscribed_to_channel(db: Database, channel_id: str, worker_id: str) -> bool:
    """Check if a worker is subscribed to a channel.

    Args:
        db: Database instance
        channel_id: Channel ID
        worker_id: Worker ID

    Returns:
        True if subscribed, False otherwise
    """
    row = db.fetchone(
        "SELECT 1 FROM channel_subscriptions WHERE channel_id = ? AND worker_id = ?",
        (channel_id, worker_id)
    )
    return row is not None


def unsubscribe_from_channel(db: Database, channel_id: str, worker_id: str) -> None:
    """Unsubscribe a worker from a channel.

    Args:
        db: Database instance
        channel_id: Channel ID
        worker_id: Worker ID
    """
    db.execute(
        "DELETE FROM channel_subscriptions WHERE channel_id = ? AND worker_id = ?",
        (channel_id, worker_id)
    )
    db.connection.commit()


def get_channel_subscribers(db: Database, channel_id: str) -> list[str]:
    """Get subscriber worker IDs for a channel.

    Args:
        db: Database instance
        channel_id: Channel ID

    Returns:
        List of worker IDs
    """
    rows = db.fetchall(
        "SELECT worker_id FROM channel_subscriptions WHERE channel_id = ?",
        (channel_id,)
    )
    return [row["worker_id"] for row in rows]


def get_worker_channels(db: Database, worker_id: str) -> list[Channel]:
    """Get channels a worker is subscribed to.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        List of channels
    """
    rows = db.fetchall(
        """SELECT c.* FROM channels c
           JOIN channel_subscriptions cs ON c.id = cs.channel_id
           WHERE cs.worker_id = ?""",
        (worker_id,)
    )
    return [
        Channel(
            id=row["id"],
            name=row["name"],
            type=row["type"],
            team_id=row["team_id"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def unsubscribe_from_all_channels(db: Database, worker_id: str) -> int:
    """Unsubscribe a worker from all channels.

    Used during worker termination to clean up channel subscriptions.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        Number of channels unsubscribed from
    """
    cursor = db.execute(
        "DELETE FROM channel_subscriptions WHERE worker_id = ?",
        (worker_id,)
    )
    db.connection.commit()
    return cursor.rowcount


# ===================
# MESSAGE QUERIES
# ===================

def create_message(
    db: Database,
    channel_id: str,
    from_worker_id: str,
    content: str,
    thread_id: Optional[str] = None,
    parent_id: Optional[str] = None,
    priority: int = 2,
    time_sensitivity: str = "whenever",
    message_id: Optional[str] = None,
) -> Message:
    """Create a new message.

    Args:
        db: Database instance
        channel_id: Channel ID
        from_worker_id: Sender worker ID
        content: Message content
        thread_id: Optional thread ID
        parent_id: Optional parent message ID
        priority: Priority 0-4 (default 2)
        time_sensitivity: Urgency level
        message_id: Optional custom ID

    Returns:
        Created Message
    """
    if message_id is None:
        message_id = generate_id("msg")

    now = datetime.now()
    db.execute(
        """INSERT INTO messages
           (id, channel_id, thread_id, parent_id, from_worker_id, content,
            priority, time_sensitivity, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (message_id, channel_id, thread_id, parent_id, from_worker_id,
         content, priority, time_sensitivity, now)
    )
    db.connection.commit()

    return Message(
        id=message_id,
        channel_id=channel_id,
        thread_id=thread_id,
        parent_id=parent_id,
        from_worker_id=from_worker_id,
        content=content,
        priority=priority,
        time_sensitivity=time_sensitivity,
        created_at=now,
    )


def create_message_with_notifications(
    db: Database,
    channel_id: str,
    from_worker_id: str,
    content: str,
    thread_id: Optional[str] = None,
    parent_id: Optional[str] = None,
    priority: int = 2,
    time_sensitivity: str = "whenever",
    message_id: Optional[str] = None,
) -> Message:
    """Create a new message and notify all channel subscribers.

    This is the recommended way to send messages when you want subscribers
    to be notified. It creates the message and then creates notification
    beads for all channel subscribers (except the sender).

    Args:
        db: Database instance
        channel_id: Channel ID
        from_worker_id: Sender worker ID
        content: Message content
        thread_id: Optional thread ID
        parent_id: Optional parent message ID
        priority: Priority 0-4 (default 2)
        time_sensitivity: Urgency level
        message_id: Optional custom ID

    Returns:
        Created Message
    """
    # Import here to avoid circular imports
    from .notifications import create_notifications_for_message

    # Create the message first
    message = create_message(
        db=db,
        channel_id=channel_id,
        from_worker_id=from_worker_id,
        content=content,
        thread_id=thread_id,
        parent_id=parent_id,
        priority=priority,
        time_sensitivity=time_sensitivity,
        message_id=message_id,
    )

    # Create notifications for all subscribers
    create_notifications_for_message(
        db=db,
        message_id=message.id,
        channel_id=channel_id,
        from_worker_id=from_worker_id,
        priority=priority,
    )

    return message


def get_message(db: Database, message_id: str) -> Optional[Message]:
    """Get a message by ID.

    Args:
        db: Database instance
        message_id: Message ID

    Returns:
        Message or None
    """
    row = db.fetchone("SELECT * FROM messages WHERE id = ?", (message_id,))
    if not row:
        return None

    return Message(
        id=row["id"],
        channel_id=row["channel_id"],
        thread_id=row["thread_id"],
        parent_id=row["parent_id"],
        from_worker_id=row["from_worker_id"],
        content=row["content"],
        priority=row["priority"],
        time_sensitivity=row["time_sensitivity"],
        created_at=row["created_at"],
    )


def get_channel_messages(
    db: Database,
    channel_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[Message]:
    """Get messages in a channel.

    Args:
        db: Database instance
        channel_id: Channel ID
        limit: Max messages to return
        offset: Offset for pagination

    Returns:
        List of messages, newest first
    """
    rows = db.fetchall(
        """SELECT * FROM messages WHERE channel_id = ?
           ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (channel_id, limit, offset)
    )
    return [
        Message(
            id=row["id"],
            channel_id=row["channel_id"],
            thread_id=row["thread_id"],
            parent_id=row["parent_id"],
            from_worker_id=row["from_worker_id"],
            content=row["content"],
            priority=row["priority"],
            time_sensitivity=row["time_sensitivity"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_thread_messages(db: Database, thread_id: str) -> list[Message]:
    """Get all messages in a thread.

    Args:
        db: Database instance
        thread_id: Thread ID

    Returns:
        List of messages in thread order
    """
    rows = db.fetchall(
        "SELECT * FROM messages WHERE thread_id = ? ORDER BY created_at ASC",
        (thread_id,)
    )
    return [
        Message(
            id=row["id"],
            channel_id=row["channel_id"],
            thread_id=row["thread_id"],
            parent_id=row["parent_id"],
            from_worker_id=row["from_worker_id"],
            content=row["content"],
            priority=row["priority"],
            time_sensitivity=row["time_sensitivity"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def search_messages(
    db: Database,
    query: str,
    channel_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Message]:
    """Search messages using full-text search.

    Args:
        db: Database instance
        query: Search query (supports FTS5 syntax: AND, OR, NOT, phrases "like this")
        channel_id: Optional filter to specific channel
        limit: Max messages to return
        offset: Offset for pagination

    Returns:
        List of matching messages, ranked by relevance
    """
    if channel_id:
        rows = db.fetchall(
            """SELECT m.* FROM messages m
               JOIN messages_fts fts ON m.rowid = fts.rowid
               WHERE messages_fts MATCH ? AND m.channel_id = ?
               ORDER BY rank LIMIT ? OFFSET ?""",
            (query, channel_id, limit, offset)
        )
    else:
        rows = db.fetchall(
            """SELECT m.* FROM messages m
               JOIN messages_fts fts ON m.rowid = fts.rowid
               WHERE messages_fts MATCH ?
               ORDER BY rank LIMIT ? OFFSET ?""",
            (query, limit, offset)
        )

    return [
        Message(
            id=row["id"],
            channel_id=row["channel_id"],
            thread_id=row["thread_id"],
            parent_id=row["parent_id"],
            from_worker_id=row["from_worker_id"],
            content=row["content"],
            priority=row["priority"],
            time_sensitivity=row["time_sensitivity"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def add_message_ref(
    db: Database,
    message_id: str,
    ref_type: str,
    ref_id: str,
) -> None:
    """Add a reference from a message to a bead/ask/okr.

    Args:
        db: Database instance
        message_id: Message ID
        ref_type: Type of reference ('bead', 'ask', 'okr')
        ref_id: ID of referenced item
    """
    db.execute(
        "INSERT OR IGNORE INTO message_refs (message_id, ref_type, ref_id) VALUES (?, ?, ?)",
        (message_id, ref_type, ref_id)
    )
    db.connection.commit()


def get_message_refs(db: Database, message_id: str) -> list[tuple[str, str]]:
    """Get references from a message.

    Args:
        db: Database instance
        message_id: Message ID

    Returns:
        List of (ref_type, ref_id) tuples
    """
    rows = db.fetchall(
        "SELECT ref_type, ref_id FROM message_refs WHERE message_id = ?",
        (message_id,)
    )
    return [(row["ref_type"], row["ref_id"]) for row in rows]


# ===================
# CONFIG QUERIES
# ===================

def get_config(db: Database, key: str) -> Optional[str]:
    """Get a config value.

    Args:
        db: Database instance
        key: Config key

    Returns:
        Config value or None
    """
    row = db.fetchone("SELECT value FROM config WHERE key = ?", (key,))
    return row["value"] if row else None


def set_config(db: Database, key: str, value: str) -> None:
    """Set a config value.

    Args:
        db: Database instance
        key: Config key
        value: Config value
    """
    db.execute(
        "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
        (key, value)
    )
    db.connection.commit()


# ===================
# TEAM MEMBER QUERIES
# ===================

@dataclass
class TeamMember:
    """Team membership record."""
    team_id: str
    worker_id: str
    role: str
    joined_at: datetime


def add_team_member(
    db: Database,
    team_id: str,
    worker_id: str,
    role: str = "member",
) -> TeamMember:
    """Add a worker to a team with a role.

    Args:
        db: Database instance
        team_id: Team ID
        worker_id: Worker ID
        role: Role in team ('member', 'lead', 'admin')

    Returns:
        Created TeamMember
    """
    now = datetime.now()
    db.execute(
        "INSERT INTO team_members (team_id, worker_id, role, joined_at) VALUES (?, ?, ?, ?)",
        (team_id, worker_id, role, now)
    )
    db.connection.commit()

    return TeamMember(
        team_id=team_id,
        worker_id=worker_id,
        role=role,
        joined_at=now,
    )


def get_team_member(db: Database, team_id: str, worker_id: str) -> Optional[TeamMember]:
    """Get a team membership record.

    Args:
        db: Database instance
        team_id: Team ID
        worker_id: Worker ID

    Returns:
        TeamMember or None
    """
    row = db.fetchone(
        "SELECT * FROM team_members WHERE team_id = ? AND worker_id = ?",
        (team_id, worker_id)
    )
    if not row:
        return None

    return TeamMember(
        team_id=row["team_id"],
        worker_id=row["worker_id"],
        role=row["role"],
        joined_at=row["joined_at"],
    )


def update_team_member_role(db: Database, team_id: str, worker_id: str, role: str) -> None:
    """Update a worker's role in a team.

    Args:
        db: Database instance
        team_id: Team ID
        worker_id: Worker ID
        role: New role
    """
    db.execute(
        "UPDATE team_members SET role = ? WHERE team_id = ? AND worker_id = ?",
        (role, team_id, worker_id)
    )
    db.connection.commit()


def remove_team_member(db: Database, team_id: str, worker_id: str) -> bool:
    """Remove a worker from a team.

    Args:
        db: Database instance
        team_id: Team ID
        worker_id: Worker ID

    Returns:
        True if removed, False if not found
    """
    cursor = db.execute(
        "DELETE FROM team_members WHERE team_id = ? AND worker_id = ?",
        (team_id, worker_id)
    )
    db.connection.commit()
    return cursor.rowcount > 0


def get_team_members_list(db: Database, team_id: str) -> list[TeamMember]:
    """Get all members of a team.

    Args:
        db: Database instance
        team_id: Team ID

    Returns:
        List of TeamMember records
    """
    rows = db.fetchall(
        "SELECT * FROM team_members WHERE team_id = ?",
        (team_id,)
    )
    return [
        TeamMember(
            team_id=row["team_id"],
            worker_id=row["worker_id"],
            role=row["role"],
            joined_at=row["joined_at"],
        )
        for row in rows
    ]


def get_worker_team_memberships(db: Database, worker_id: str) -> list[TeamMember]:
    """Get all team memberships for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        List of TeamMember records
    """
    rows = db.fetchall(
        "SELECT * FROM team_members WHERE worker_id = ?",
        (worker_id,)
    )
    return [
        TeamMember(
            team_id=row["team_id"],
            worker_id=row["worker_id"],
            role=row["role"],
            joined_at=row["joined_at"],
        )
        for row in rows
    ]


def get_team_members_by_role(db: Database, team_id: str, role: str) -> list[TeamMember]:
    """Get team members with a specific role.

    Args:
        db: Database instance
        team_id: Team ID
        role: Role to filter by

    Returns:
        List of TeamMember records
    """
    rows = db.fetchall(
        "SELECT * FROM team_members WHERE team_id = ? AND role = ?",
        (team_id, role)
    )
    return [
        TeamMember(
            team_id=row["team_id"],
            worker_id=row["worker_id"],
            role=row["role"],
            joined_at=row["joined_at"],
        )
        for row in rows
    ]


# ===================
# PERMISSION QUERIES
# ===================

@dataclass
class Permission:
    """Permission grant record."""
    id: str
    bead_id: Optional[str]
    grantee_type: str
    grantee_id: str
    level: int
    granted_by: Optional[str]
    granted_at: datetime


def grant_permission(
    db: Database,
    grantee_type: str,
    grantee_id: str,
    level: int,
    bead_id: Optional[str] = None,
    granted_by: Optional[str] = None,
    permission_id: Optional[str] = None,
) -> Permission:
    """Grant a permission.

    Args:
        db: Database instance
        grantee_type: 'worker' or 'team'
        grantee_id: Worker or team ID
        level: Permission level (0-5)
        bead_id: Optional bead ID (None for global permissions)
        granted_by: Worker ID who granted this
        permission_id: Optional custom ID

    Returns:
        Created Permission
    """
    if permission_id is None:
        permission_id = generate_id("perm")

    now = datetime.now()
    db.execute(
        """INSERT OR REPLACE INTO permissions
           (id, bead_id, grantee_type, grantee_id, level, granted_by, granted_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (permission_id, bead_id, grantee_type, grantee_id, level, granted_by, now)
    )
    db.connection.commit()

    return Permission(
        id=permission_id,
        bead_id=bead_id,
        grantee_type=grantee_type,
        grantee_id=grantee_id,
        level=level,
        granted_by=granted_by,
        granted_at=now,
    )


def get_permission(db: Database, permission_id: str) -> Optional[Permission]:
    """Get a permission by ID.

    Args:
        db: Database instance
        permission_id: Permission ID

    Returns:
        Permission or None
    """
    row = db.fetchone("SELECT * FROM permissions WHERE id = ?", (permission_id,))
    if not row:
        return None

    return Permission(
        id=row["id"],
        bead_id=row["bead_id"],
        grantee_type=row["grantee_type"],
        grantee_id=row["grantee_id"],
        level=row["level"],
        granted_by=row["granted_by"],
        granted_at=row["granted_at"],
    )


def get_permission_for_grantee(
    db: Database,
    bead_id: Optional[str],
    grantee_type: str,
    grantee_id: str,
) -> Optional[Permission]:
    """Get a permission for a specific grantee on a bead.

    Args:
        db: Database instance
        bead_id: Bead ID (or None for global)
        grantee_type: 'worker' or 'team'
        grantee_id: Worker or team ID

    Returns:
        Permission or None
    """
    if bead_id is None:
        row = db.fetchone(
            """SELECT * FROM permissions
               WHERE bead_id IS NULL AND grantee_type = ? AND grantee_id = ?""",
            (grantee_type, grantee_id)
        )
    else:
        row = db.fetchone(
            """SELECT * FROM permissions
               WHERE bead_id = ? AND grantee_type = ? AND grantee_id = ?""",
            (bead_id, grantee_type, grantee_id)
        )

    if not row:
        return None

    return Permission(
        id=row["id"],
        bead_id=row["bead_id"],
        grantee_type=row["grantee_type"],
        grantee_id=row["grantee_id"],
        level=row["level"],
        granted_by=row["granted_by"],
        granted_at=row["granted_at"],
    )


def revoke_permission(db: Database, permission_id: str) -> bool:
    """Revoke a permission by ID.

    Args:
        db: Database instance
        permission_id: Permission ID

    Returns:
        True if revoked, False if not found
    """
    cursor = db.execute("DELETE FROM permissions WHERE id = ?", (permission_id,))
    db.connection.commit()
    return cursor.rowcount > 0


def revoke_permission_for_grantee(
    db: Database,
    bead_id: Optional[str],
    grantee_type: str,
    grantee_id: str,
) -> bool:
    """Revoke a permission for a specific grantee on a bead.

    Args:
        db: Database instance
        bead_id: Bead ID (or None for global)
        grantee_type: 'worker' or 'team'
        grantee_id: Worker or team ID

    Returns:
        True if revoked, False if not found
    """
    if bead_id is None:
        cursor = db.execute(
            """DELETE FROM permissions
               WHERE bead_id IS NULL AND grantee_type = ? AND grantee_id = ?""",
            (grantee_type, grantee_id)
        )
    else:
        cursor = db.execute(
            """DELETE FROM permissions
               WHERE bead_id = ? AND grantee_type = ? AND grantee_id = ?""",
            (bead_id, grantee_type, grantee_id)
        )
    db.connection.commit()
    return cursor.rowcount > 0


def get_permissions_for_bead(db: Database, bead_id: str) -> list[Permission]:
    """Get all permissions for a bead.

    Args:
        db: Database instance
        bead_id: Bead ID

    Returns:
        List of Permission records
    """
    rows = db.fetchall("SELECT * FROM permissions WHERE bead_id = ?", (bead_id,))
    return [
        Permission(
            id=row["id"],
            bead_id=row["bead_id"],
            grantee_type=row["grantee_type"],
            grantee_id=row["grantee_id"],
            level=row["level"],
            granted_by=row["granted_by"],
            granted_at=row["granted_at"],
        )
        for row in rows
    ]


def get_permissions_for_worker(db: Database, worker_id: str) -> list[Permission]:
    """Get all direct permissions for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        List of Permission records
    """
    rows = db.fetchall(
        "SELECT * FROM permissions WHERE grantee_type = 'worker' AND grantee_id = ?",
        (worker_id,)
    )
    return [
        Permission(
            id=row["id"],
            bead_id=row["bead_id"],
            grantee_type=row["grantee_type"],
            grantee_id=row["grantee_id"],
            level=row["level"],
            granted_by=row["granted_by"],
            granted_at=row["granted_at"],
        )
        for row in rows
    ]


def get_permissions_for_team(db: Database, team_id: str) -> list[Permission]:
    """Get all permissions for a team.

    Args:
        db: Database instance
        team_id: Team ID

    Returns:
        List of Permission records
    """
    rows = db.fetchall(
        "SELECT * FROM permissions WHERE grantee_type = 'team' AND grantee_id = ?",
        (team_id,)
    )
    return [
        Permission(
            id=row["id"],
            bead_id=row["bead_id"],
            grantee_type=row["grantee_type"],
            grantee_id=row["grantee_id"],
            level=row["level"],
            granted_by=row["granted_by"],
            granted_at=row["granted_at"],
        )
        for row in rows
    ]


# ===================
# EFFECTIVE PERMISSION QUERIES
# ===================

@dataclass
class EffectivePermission:
    """Computed effective permission record."""
    worker_id: str
    bead_id: str
    level: int
    computed_at: datetime


def set_effective_permission(
    db: Database,
    worker_id: str,
    bead_id: str,
    level: int,
) -> EffectivePermission:
    """Set or update effective permission for a worker on a bead.

    Args:
        db: Database instance
        worker_id: Worker ID
        bead_id: Bead ID
        level: Computed permission level

    Returns:
        EffectivePermission record
    """
    now = datetime.now()
    db.execute(
        """INSERT OR REPLACE INTO effective_permissions
           (worker_id, bead_id, level, computed_at)
           VALUES (?, ?, ?, ?)""",
        (worker_id, bead_id, level, now)
    )
    db.connection.commit()

    return EffectivePermission(
        worker_id=worker_id,
        bead_id=bead_id,
        level=level,
        computed_at=now,
    )


def get_effective_permission(
    db: Database,
    worker_id: str,
    bead_id: str,
) -> Optional[EffectivePermission]:
    """Get effective permission for a worker on a bead.

    Args:
        db: Database instance
        worker_id: Worker ID
        bead_id: Bead ID

    Returns:
        EffectivePermission or None
    """
    row = db.fetchone(
        "SELECT * FROM effective_permissions WHERE worker_id = ? AND bead_id = ?",
        (worker_id, bead_id)
    )
    if not row:
        return None

    return EffectivePermission(
        worker_id=row["worker_id"],
        bead_id=row["bead_id"],
        level=row["level"],
        computed_at=row["computed_at"],
    )


def delete_effective_permission(db: Database, worker_id: str, bead_id: str) -> bool:
    """Delete effective permission for a worker on a bead.

    Args:
        db: Database instance
        worker_id: Worker ID
        bead_id: Bead ID

    Returns:
        True if deleted, False if not found
    """
    cursor = db.execute(
        "DELETE FROM effective_permissions WHERE worker_id = ? AND bead_id = ?",
        (worker_id, bead_id)
    )
    db.connection.commit()
    return cursor.rowcount > 0


def delete_effective_permissions_for_bead(db: Database, bead_id: str) -> int:
    """Delete all effective permissions for a bead.

    Args:
        db: Database instance
        bead_id: Bead ID

    Returns:
        Number of records deleted
    """
    cursor = db.execute(
        "DELETE FROM effective_permissions WHERE bead_id = ?",
        (bead_id,)
    )
    db.connection.commit()
    return cursor.rowcount


# ===================
# PERMISSION AUDIT QUERIES
# ===================

@dataclass
class PermissionAudit:
    """Permission audit log entry."""
    id: str
    action: str
    bead_id: str
    worker_id: str
    level: Optional[int]
    details: Optional[str]
    created_at: datetime


def log_permission_audit(
    db: Database,
    action: str,
    bead_id: str,
    worker_id: str,
    level: Optional[int] = None,
    details: Optional[str] = None,
    audit_id: Optional[str] = None,
) -> PermissionAudit:
    """Log a permission audit entry.

    Args:
        db: Database instance
        action: 'grant', 'revoke', 'check', or 'deny'
        bead_id: Bead ID
        worker_id: Worker ID
        level: Permission level (optional)
        details: Additional details as JSON string
        audit_id: Optional custom ID

    Returns:
        Created PermissionAudit
    """
    if audit_id is None:
        audit_id = generate_id("audit")

    now = datetime.now()
    db.execute(
        """INSERT INTO permission_audit
           (id, action, bead_id, worker_id, level, details, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (audit_id, action, bead_id, worker_id, level, details, now)
    )
    db.connection.commit()

    return PermissionAudit(
        id=audit_id,
        action=action,
        bead_id=bead_id,
        worker_id=worker_id,
        level=level,
        details=details,
        created_at=now,
    )


def get_permission_audit_for_bead(
    db: Database,
    bead_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[PermissionAudit]:
    """Get audit log entries for a bead.

    Args:
        db: Database instance
        bead_id: Bead ID
        limit: Max entries to return
        offset: Offset for pagination

    Returns:
        List of PermissionAudit records
    """
    rows = db.fetchall(
        """SELECT * FROM permission_audit
           WHERE bead_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (bead_id, limit, offset)
    )
    return [
        PermissionAudit(
            id=row["id"],
            action=row["action"],
            bead_id=row["bead_id"],
            worker_id=row["worker_id"],
            level=row["level"],
            details=row["details"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_permission_audit_for_worker(
    db: Database,
    worker_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[PermissionAudit]:
    """Get audit log entries for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID
        limit: Max entries to return
        offset: Offset for pagination

    Returns:
        List of PermissionAudit records
    """
    rows = db.fetchall(
        """SELECT * FROM permission_audit
           WHERE worker_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (worker_id, limit, offset)
    )
    return [
        PermissionAudit(
            id=row["id"],
            action=row["action"],
            bead_id=row["bead_id"],
            worker_id=row["worker_id"],
            level=row["level"],
            details=row["details"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_permission_denials(
    db: Database,
    limit: int = 50,
    offset: int = 0,
) -> list[PermissionAudit]:
    """Get recent permission denials.

    Args:
        db: Database instance
        limit: Max entries to return
        offset: Offset for pagination

    Returns:
        List of PermissionAudit records with action='deny'
    """
    rows = db.fetchall(
        """SELECT * FROM permission_audit
           WHERE action = 'deny' ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (limit, offset)
    )
    return [
        PermissionAudit(
            id=row["id"],
            action=row["action"],
            bead_id=row["bead_id"],
            worker_id=row["worker_id"],
            level=row["level"],
            details=row["details"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


# ===================
# BUDGET DATA CLASSES
# ===================

@dataclass
class BudgetPool:
    """Organization budget pool."""
    id: str
    name: str
    total_credits: float
    period_start: datetime
    period_end: datetime
    created_at: datetime
    updated_at: datetime


@dataclass
class BudgetAllocation:
    """Budget allocation for a worker."""
    id: str
    worker_id: str
    source_worker_id: Optional[str]
    pool_id: Optional[str]
    allocated_credits: float
    spent_credits: float
    reserved_credits: float
    period_start: datetime
    period_end: datetime
    can_delegate: bool
    delegation_limit: Optional[float]
    created_at: datetime
    updated_at: datetime


@dataclass
class BudgetTransaction:
    """Budget transaction record."""
    id: str
    allocation_id: str
    worker_id: str
    type: str
    amount: float
    provider: Optional[str]
    model: Optional[str]
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    reference_type: Optional[str]
    reference_id: Optional[str]
    description: Optional[str]
    metadata: Optional[str]
    created_at: datetime


@dataclass
class BudgetBalance:
    """Materialized budget balance."""
    allocation_id: str
    worker_id: str
    allocated: float
    spent: float
    reserved: float
    available: float
    delegated: float
    period_start: datetime
    period_end: datetime
    updated_at: datetime


# ===================
# BUDGET POOL QUERIES
# ===================

def create_budget_pool(
    db: Database,
    name: str,
    total_credits: float,
    period_start: datetime,
    period_end: datetime,
    pool_id: Optional[str] = None,
) -> BudgetPool:
    """Create a new budget pool.

    Args:
        db: Database instance
        name: Pool name
        total_credits: Total credits in pool (must be positive)
        period_start: Period start datetime
        period_end: Period end datetime
        pool_id: Optional custom ID

    Returns:
        Created BudgetPool

    Raises:
        ValueError: If total_credits is not positive
    """
    if total_credits <= 0:
        raise ValueError(f"Total credits must be positive, got {total_credits:.2f}")

    if pool_id is None:
        pool_id = generate_id("pool")

    now = datetime.now()
    db.execute(
        """INSERT INTO budget_pools
           (id, name, total_credits, period_start, period_end, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (pool_id, name, total_credits, period_start, period_end, now, now)
    )
    db.connection.commit()

    return BudgetPool(
        id=pool_id,
        name=name,
        total_credits=total_credits,
        period_start=period_start,
        period_end=period_end,
        created_at=now,
        updated_at=now,
    )


def get_budget_pool(db: Database, pool_id: str) -> Optional[BudgetPool]:
    """Get a budget pool by ID.

    Args:
        db: Database instance
        pool_id: Pool ID

    Returns:
        BudgetPool or None
    """
    row = db.fetchone("SELECT * FROM budget_pools WHERE id = ?", (pool_id,))
    if not row:
        return None

    return BudgetPool(
        id=row["id"],
        name=row["name"],
        total_credits=float(row["total_credits"]),
        period_start=row["period_start"],
        period_end=row["period_end"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def get_all_budget_pools(db: Database) -> list[BudgetPool]:
    """Get all budget pools.

    Args:
        db: Database instance

    Returns:
        List of all budget pools
    """
    rows = db.fetchall("SELECT * FROM budget_pools ORDER BY created_at DESC")
    return [
        BudgetPool(
            id=row["id"],
            name=row["name"],
            total_credits=float(row["total_credits"]),
            period_start=row["period_start"],
            period_end=row["period_end"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def update_budget_pool(
    db: Database,
    pool_id: str,
    total_credits: Optional[float] = None,
    name: Optional[str] = None,
) -> None:
    """Update a budget pool.

    Args:
        db: Database instance
        pool_id: Pool ID
        total_credits: Optional new total credits
        name: Optional new name
    """
    now = datetime.now()
    updates = ["updated_at = ?"]
    params: list = [now]

    if total_credits is not None:
        updates.append("total_credits = ?")
        params.append(total_credits)
    if name is not None:
        updates.append("name = ?")
        params.append(name)

    params.append(pool_id)
    db.execute(
        f"UPDATE budget_pools SET {', '.join(updates)} WHERE id = ?",
        tuple(params)
    )
    db.connection.commit()


def delete_budget_pool(db: Database, pool_id: str) -> None:
    """Delete a budget pool.

    Args:
        db: Database instance
        pool_id: Pool ID to delete
    """
    db.execute("DELETE FROM budget_pools WHERE id = ?", (pool_id,))
    db.connection.commit()


# ===================
# BUDGET ALLOCATION QUERIES
# ===================

def create_budget_allocation(
    db: Database,
    worker_id: str,
    allocated_credits: float,
    period_start: datetime,
    period_end: datetime,
    source_worker_id: Optional[str] = None,
    pool_id: Optional[str] = None,
    can_delegate: bool = False,
    delegation_limit: Optional[float] = None,
    allocation_id: Optional[str] = None,
) -> BudgetAllocation:
    """Create a budget allocation.

    Either source_worker_id or pool_id must be provided, but not both.

    Args:
        db: Database instance
        worker_id: Worker receiving the allocation
        allocated_credits: Credits being allocated (must be positive)
        period_start: Period start datetime
        period_end: Period end datetime
        source_worker_id: Manager delegating budget (mutually exclusive with pool_id)
        pool_id: Pool providing budget (mutually exclusive with source_worker_id)
        can_delegate: Whether worker can delegate to subordinates
        delegation_limit: Max credits delegatable to single subordinate (must be positive if set)
        allocation_id: Optional custom ID

    Returns:
        Created BudgetAllocation

    Raises:
        ValueError: If allocated_credits is not positive, or if delegation_limit is set but not positive
    """
    if allocated_credits <= 0:
        raise ValueError(f"Allocated credits must be positive, got {allocated_credits:.2f}")

    if delegation_limit is not None and delegation_limit <= 0:
        raise ValueError(f"Delegation limit must be positive, got {delegation_limit:.2f}")

    if allocation_id is None:
        allocation_id = generate_id("alloc")

    now = datetime.now()
    db.execute(
        """INSERT INTO budget_allocations
           (id, worker_id, source_worker_id, pool_id, allocated_credits,
            spent_credits, reserved_credits, period_start, period_end,
            can_delegate, delegation_limit, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?, ?)""",
        (allocation_id, worker_id, source_worker_id, pool_id, allocated_credits,
         period_start, period_end, can_delegate, delegation_limit, now, now)
    )
    db.connection.commit()

    return BudgetAllocation(
        id=allocation_id,
        worker_id=worker_id,
        source_worker_id=source_worker_id,
        pool_id=pool_id,
        allocated_credits=allocated_credits,
        spent_credits=0.0,
        reserved_credits=0.0,
        period_start=period_start,
        period_end=period_end,
        can_delegate=can_delegate,
        delegation_limit=delegation_limit,
        created_at=now,
        updated_at=now,
    )


def get_budget_allocation(db: Database, allocation_id: str) -> Optional[BudgetAllocation]:
    """Get a budget allocation by ID.

    Args:
        db: Database instance
        allocation_id: Allocation ID

    Returns:
        BudgetAllocation or None
    """
    row = db.fetchone("SELECT * FROM budget_allocations WHERE id = ?", (allocation_id,))
    if not row:
        return None

    return BudgetAllocation(
        id=row["id"],
        worker_id=row["worker_id"],
        source_worker_id=row["source_worker_id"],
        pool_id=row["pool_id"],
        allocated_credits=float(row["allocated_credits"]),
        spent_credits=float(row["spent_credits"]),
        reserved_credits=float(row["reserved_credits"]),
        period_start=row["period_start"],
        period_end=row["period_end"],
        can_delegate=bool(row["can_delegate"]),
        delegation_limit=float(row["delegation_limit"]) if row["delegation_limit"] else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def get_worker_allocations(db: Database, worker_id: str) -> list[BudgetAllocation]:
    """Get all allocations for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        List of allocations for the worker
    """
    rows = db.fetchall(
        "SELECT * FROM budget_allocations WHERE worker_id = ? ORDER BY period_start DESC",
        (worker_id,)
    )
    return [
        BudgetAllocation(
            id=row["id"],
            worker_id=row["worker_id"],
            source_worker_id=row["source_worker_id"],
            pool_id=row["pool_id"],
            allocated_credits=float(row["allocated_credits"]),
            spent_credits=float(row["spent_credits"]),
            reserved_credits=float(row["reserved_credits"]),
            period_start=row["period_start"],
            period_end=row["period_end"],
            can_delegate=bool(row["can_delegate"]),
            delegation_limit=float(row["delegation_limit"]) if row["delegation_limit"] else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def get_current_allocation(
    db: Database,
    worker_id: str,
    as_of: Optional[datetime] = None,
) -> Optional[BudgetAllocation]:
    """Get the current allocation for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID
        as_of: Optional datetime to check (defaults to now)

    Returns:
        Current BudgetAllocation or None
    """
    if as_of is None:
        as_of = datetime.now()

    row = db.fetchone(
        """SELECT * FROM budget_allocations
           WHERE worker_id = ? AND period_start <= ? AND period_end >= ?
           ORDER BY period_start DESC LIMIT 1""",
        (worker_id, as_of, as_of)
    )
    if not row:
        return None

    return BudgetAllocation(
        id=row["id"],
        worker_id=row["worker_id"],
        source_worker_id=row["source_worker_id"],
        pool_id=row["pool_id"],
        allocated_credits=float(row["allocated_credits"]),
        spent_credits=float(row["spent_credits"]),
        reserved_credits=float(row["reserved_credits"]),
        period_start=row["period_start"],
        period_end=row["period_end"],
        can_delegate=bool(row["can_delegate"]),
        delegation_limit=float(row["delegation_limit"]) if row["delegation_limit"] else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def get_allocations_by_pool(db: Database, pool_id: str) -> list[BudgetAllocation]:
    """Get all allocations from a pool.

    Args:
        db: Database instance
        pool_id: Pool ID

    Returns:
        List of allocations from the pool
    """
    rows = db.fetchall(
        "SELECT * FROM budget_allocations WHERE pool_id = ?",
        (pool_id,)
    )
    return [
        BudgetAllocation(
            id=row["id"],
            worker_id=row["worker_id"],
            source_worker_id=row["source_worker_id"],
            pool_id=row["pool_id"],
            allocated_credits=float(row["allocated_credits"]),
            spent_credits=float(row["spent_credits"]),
            reserved_credits=float(row["reserved_credits"]),
            period_start=row["period_start"],
            period_end=row["period_end"],
            can_delegate=bool(row["can_delegate"]),
            delegation_limit=float(row["delegation_limit"]) if row["delegation_limit"] else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def update_allocation_spend(
    db: Database,
    allocation_id: str,
    spent_credits: float,
    reserved_credits: float,
) -> None:
    """Update spend and reserve amounts on an allocation.

    Args:
        db: Database instance
        allocation_id: Allocation ID
        spent_credits: New spent amount
        reserved_credits: New reserved amount
    """
    now = datetime.now()
    db.execute(
        """UPDATE budget_allocations
           SET spent_credits = ?, reserved_credits = ?, updated_at = ?
           WHERE id = ?""",
        (spent_credits, reserved_credits, now, allocation_id)
    )
    db.connection.commit()


def delete_budget_allocation(db: Database, allocation_id: str) -> None:
    """Delete a budget allocation.

    Args:
        db: Database instance
        allocation_id: Allocation ID to delete
    """
    db.execute("DELETE FROM budget_allocations WHERE id = ?", (allocation_id,))
    db.connection.commit()


# ===================
# BUDGET TRANSACTION QUERIES
# ===================

def create_budget_transaction(
    db: Database,
    allocation_id: str,
    worker_id: str,
    transaction_type: str,
    amount: float,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    reference_type: Optional[str] = None,
    reference_id: Optional[str] = None,
    description: Optional[str] = None,
    metadata: Optional[str] = None,
    transaction_id: Optional[str] = None,
) -> BudgetTransaction:
    """Create a budget transaction.

    Args:
        db: Database instance
        allocation_id: Allocation ID
        worker_id: Worker ID
        transaction_type: Type ('allocation', 'spend', 'reserve', etc.)
        amount: Transaction amount (positive in, negative out)
        provider: Optional provider name (for spend)
        model: Optional model name (for spend)
        input_tokens: Optional input token count
        output_tokens: Optional output token count
        reference_type: Optional reference type ('task', 'message')
        reference_id: Optional reference ID
        description: Optional description
        metadata: Optional JSON metadata
        transaction_id: Optional custom ID

    Returns:
        Created BudgetTransaction
    """
    if transaction_id is None:
        transaction_id = generate_id("txn")

    now = datetime.now()
    db.execute(
        """INSERT INTO budget_transactions
           (id, allocation_id, worker_id, type, amount, provider, model,
            input_tokens, output_tokens, reference_type, reference_id,
            description, metadata, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (transaction_id, allocation_id, worker_id, transaction_type, amount,
         provider, model, input_tokens, output_tokens, reference_type,
         reference_id, description, metadata, now)
    )
    db.connection.commit()

    return BudgetTransaction(
        id=transaction_id,
        allocation_id=allocation_id,
        worker_id=worker_id,
        type=transaction_type,
        amount=amount,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reference_type=reference_type,
        reference_id=reference_id,
        description=description,
        metadata=metadata,
        created_at=now,
    )


def get_budget_transaction(db: Database, transaction_id: str) -> Optional[BudgetTransaction]:
    """Get a budget transaction by ID.

    Args:
        db: Database instance
        transaction_id: Transaction ID

    Returns:
        BudgetTransaction or None
    """
    row = db.fetchone("SELECT * FROM budget_transactions WHERE id = ?", (transaction_id,))
    if not row:
        return None

    return BudgetTransaction(
        id=row["id"],
        allocation_id=row["allocation_id"],
        worker_id=row["worker_id"],
        type=row["type"],
        amount=float(row["amount"]),
        provider=row["provider"],
        model=row["model"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        reference_type=row["reference_type"],
        reference_id=row["reference_id"],
        description=row["description"],
        metadata=row["metadata"],
        created_at=row["created_at"],
    )


def get_transactions_by_allocation(
    db: Database,
    allocation_id: str,
    limit: int = 100,
    offset: int = 0,
) -> list[BudgetTransaction]:
    """Get transactions for an allocation.

    Args:
        db: Database instance
        allocation_id: Allocation ID
        limit: Max transactions to return
        offset: Offset for pagination

    Returns:
        List of transactions, newest first
    """
    rows = db.fetchall(
        """SELECT * FROM budget_transactions
           WHERE allocation_id = ?
           ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (allocation_id, limit, offset)
    )
    return [
        BudgetTransaction(
            id=row["id"],
            allocation_id=row["allocation_id"],
            worker_id=row["worker_id"],
            type=row["type"],
            amount=float(row["amount"]),
            provider=row["provider"],
            model=row["model"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            reference_type=row["reference_type"],
            reference_id=row["reference_id"],
            description=row["description"],
            metadata=row["metadata"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_transactions_by_worker(
    db: Database,
    worker_id: str,
    transaction_type: Optional[str] = None,
    since: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[BudgetTransaction]:
    """Get transactions for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID
        transaction_type: Optional filter by type
        since: Optional filter by time
        limit: Max transactions to return
        offset: Offset for pagination

    Returns:
        List of transactions, newest first
    """
    query = "SELECT * FROM budget_transactions WHERE worker_id = ?"
    params: list = [worker_id]

    if transaction_type:
        query += " AND type = ?"
        params.append(transaction_type)
    if since:
        query += " AND created_at >= ?"
        params.append(since)

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = db.fetchall(query, tuple(params))
    return [
        BudgetTransaction(
            id=row["id"],
            allocation_id=row["allocation_id"],
            worker_id=row["worker_id"],
            type=row["type"],
            amount=float(row["amount"]),
            provider=row["provider"],
            model=row["model"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            reference_type=row["reference_type"],
            reference_id=row["reference_id"],
            description=row["description"],
            metadata=row["metadata"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


# ===================
# BUDGET BALANCE QUERIES
# ===================

def create_budget_balance(
    db: Database,
    allocation_id: str,
    worker_id: str,
    allocated: float,
    period_start: datetime,
    period_end: datetime,
) -> BudgetBalance:
    """Create a budget balance record.

    Args:
        db: Database instance
        allocation_id: Allocation ID
        worker_id: Worker ID
        allocated: Initial allocated amount
        period_start: Period start
        period_end: Period end

    Returns:
        Created BudgetBalance
    """
    now = datetime.now()
    db.execute(
        """INSERT INTO budget_balances
           (allocation_id, worker_id, allocated, spent, reserved, available,
            delegated, period_start, period_end, updated_at)
           VALUES (?, ?, ?, 0, 0, ?, 0, ?, ?, ?)""",
        (allocation_id, worker_id, allocated, allocated, period_start, period_end, now)
    )
    db.connection.commit()

    return BudgetBalance(
        allocation_id=allocation_id,
        worker_id=worker_id,
        allocated=allocated,
        spent=0.0,
        reserved=0.0,
        available=allocated,
        delegated=0.0,
        period_start=period_start,
        period_end=period_end,
        updated_at=now,
    )


def get_budget_balance(db: Database, allocation_id: str) -> Optional[BudgetBalance]:
    """Get budget balance for an allocation.

    Args:
        db: Database instance
        allocation_id: Allocation ID

    Returns:
        BudgetBalance or None
    """
    row = db.fetchone("SELECT * FROM budget_balances WHERE allocation_id = ?", (allocation_id,))
    if not row:
        return None

    return BudgetBalance(
        allocation_id=row["allocation_id"],
        worker_id=row["worker_id"],
        allocated=float(row["allocated"]),
        spent=float(row["spent"]),
        reserved=float(row["reserved"]),
        available=float(row["available"]),
        delegated=float(row["delegated"]),
        period_start=row["period_start"],
        period_end=row["period_end"],
        updated_at=row["updated_at"],
    )


def get_worker_balance(
    db: Database,
    worker_id: str,
    as_of: Optional[datetime] = None,
) -> Optional[BudgetBalance]:
    """Get current budget balance for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID
        as_of: Optional datetime (defaults to now)

    Returns:
        Current BudgetBalance or None
    """
    if as_of is None:
        as_of = datetime.now()

    row = db.fetchone(
        """SELECT * FROM budget_balances
           WHERE worker_id = ? AND period_start <= ? AND period_end >= ?
           ORDER BY period_start DESC LIMIT 1""",
        (worker_id, as_of, as_of)
    )
    if not row:
        return None

    return BudgetBalance(
        allocation_id=row["allocation_id"],
        worker_id=row["worker_id"],
        allocated=float(row["allocated"]),
        spent=float(row["spent"]),
        reserved=float(row["reserved"]),
        available=float(row["available"]),
        delegated=float(row["delegated"]),
        period_start=row["period_start"],
        period_end=row["period_end"],
        updated_at=row["updated_at"],
    )


def get_all_worker_balances(db: Database) -> list[BudgetBalance]:
    """Get all current budget balances.

    Args:
        db: Database instance

    Returns:
        List of all budget balances
    """
    now = datetime.now()
    rows = db.fetchall(
        """SELECT * FROM budget_balances
           WHERE period_start <= ? AND period_end >= ?
           ORDER BY worker_id""",
        (now, now)
    )
    return [
        BudgetBalance(
            allocation_id=row["allocation_id"],
            worker_id=row["worker_id"],
            allocated=float(row["allocated"]),
            spent=float(row["spent"]),
            reserved=float(row["reserved"]),
            available=float(row["available"]),
            delegated=float(row["delegated"]),
            period_start=row["period_start"],
            period_end=row["period_end"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def delete_budget_balance(db: Database, allocation_id: str) -> None:
    """Delete a budget balance.

    Args:
        db: Database instance
        allocation_id: Allocation ID
    """
    db.execute("DELETE FROM budget_balances WHERE allocation_id = ?", (allocation_id,))
    db.connection.commit()


def get_pool_allocated_total(db: Database, pool_id: str) -> float:
    """Get total allocated credits from a pool.

    Args:
        db: Database instance
        pool_id: Pool ID

    Returns:
        Total allocated credits
    """
    row = db.fetchone(
        "SELECT COALESCE(SUM(allocated_credits), 0) as total FROM budget_allocations WHERE pool_id = ?",
        (pool_id,)
    )
    return float(row["total"]) if row else 0.0


def is_worker_manager(db: Database, worker_id: str) -> bool:
    """Check if worker has any direct reports.

    Args:
        db: Database instance
        worker_id: Worker ID to check

    Returns:
        True if worker has direct reports
    """
    row = db.fetchone(
        "SELECT 1 FROM workers WHERE manager_id = ? LIMIT 1",
        (worker_id,)
    )
    return row is not None


# ===================
# OKR DATA CLASSES
# ===================

@dataclass
class KeyResult:
    """A single measurable key result."""
    metric: str  # e.g., "lighthouse_score", "test_coverage"
    target: float  # target value
    current: float  # current value
    unit: str  # e.g., "%", "count", "seconds"

    def progress(self) -> float:
        """Calculate progress as percentage (0-100)."""
        if self.target == 0:
            return 100.0 if self.current >= 0 else 0.0
        return min(100.0, (self.current / self.target) * 100)

    def is_met(self) -> bool:
        """Check if target is met."""
        return self.current >= self.target


@dataclass
class OKR:
    """Objective and Key Result definition."""
    id: str
    title: str
    description: Optional[str]
    owner_worker_id: str
    parent_okr_id: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    key_results: list[KeyResult] = field(default_factory=list)
    due_date: Optional[date] = None

    def progress(self) -> float:
        """Calculate overall progress across all key results."""
        if not self.key_results:
            return 0.0
        return sum(kr.progress() for kr in self.key_results) / len(self.key_results)

    def all_key_results_met(self) -> bool:
        """Check if all key results are met."""
        return all(kr.is_met() for kr in self.key_results) if self.key_results else False


@dataclass
class WorkOKRLink:
    """Link between a work item and an OKR."""
    work_id: str
    okr_id: str
    link_type: str
    created_at: datetime


# ===================
# OKR QUERIES
# ===================

def create_okr(
    db: Database,
    title: str,
    owner_id: str,
    parent_id: Optional[str] = None,
    description: Optional[str] = None,
    status: str = "active",
    okr_id: Optional[str] = None,
    key_results: Optional[list[KeyResult]] = None,
    due_date: Optional[date] = None,
) -> OKR:
    """Create a new OKR.

    OKRs cascade: Board -> CEO -> Directors -> Managers -> Workers.
    Each OKR can have a parent OKR to form the hierarchy.

    Args:
        db: Database instance
        title: OKR title
        owner_id: Worker ID who owns this OKR
        parent_id: Optional parent OKR ID for cascade
        description: Optional description
        status: OKR status ('draft', 'active', 'completed', 'cancelled')
        okr_id: Optional custom ID (generated if not provided)
        key_results: Optional list of measurable key results
        due_date: Optional due date for the OKR

    Returns:
        Created OKR
    """
    if okr_id is None:
        okr_id = generate_id("okr")

    now = datetime.now()
    kr_json = None
    if key_results:
        kr_json = json.dumps([
            {"metric": kr.metric, "target": kr.target, "current": kr.current, "unit": kr.unit}
            for kr in key_results
        ])

    db.execute(
        """INSERT INTO okrs
           (id, title, description, owner_worker_id, parent_okr_id, status, key_results, due_date, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (okr_id, title, description, owner_id, parent_id, status, kr_json, due_date, now, now)
    )
    db.connection.commit()

    return OKR(
        id=okr_id,
        title=title,
        description=description,
        owner_worker_id=owner_id,
        parent_okr_id=parent_id,
        status=status,
        created_at=now,
        updated_at=now,
        key_results=key_results or [],
        due_date=due_date,
    )


def _parse_key_results(kr_json: Optional[str]) -> list[KeyResult]:
    """Parse key results from JSON string."""
    if not kr_json:
        return []
    try:
        data = json.loads(kr_json)
        return [
            KeyResult(
                metric=kr["metric"],
                target=kr["target"],
                current=kr["current"],
                unit=kr["unit"],
            )
            for kr in data
        ]
    except (json.JSONDecodeError, KeyError):
        return []


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parse date from string."""
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str) if isinstance(date_str, str) else date_str
    except ValueError:
        return None


def _get_row_value(row: dict, key: str, default=None):
    """Safely get value from sqlite3.Row or dict."""
    try:
        return row[key]
    except (KeyError, IndexError):
        return default


def get_okr(db: Database, okr_id: str) -> Optional[OKR]:
    """Get an OKR by ID.

    Args:
        db: Database instance
        okr_id: OKR ID

    Returns:
        OKR or None
    """
    row = db.fetchone("SELECT * FROM okrs WHERE id = ?", (okr_id,))
    if not row:
        return None

    return OKR(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        owner_worker_id=row["owner_worker_id"],
        parent_okr_id=row["parent_okr_id"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        key_results=_parse_key_results(_get_row_value(row, "key_results")),
        due_date=_parse_date(_get_row_value(row, "due_date")),
    )


def update_okr_status(db: Database, okr_id: str, status: str) -> None:
    """Update OKR status.

    Args:
        db: Database instance
        okr_id: OKR ID
        status: New status ('draft', 'active', 'completed', 'cancelled')
    """
    now = datetime.now()
    db.execute(
        "UPDATE okrs SET status = ?, updated_at = ? WHERE id = ?",
        (status, now, okr_id)
    )
    db.connection.commit()


def get_okrs_by_owner(db: Database, owner_id: str) -> list[OKR]:
    """Get all OKRs owned by a worker.

    Args:
        db: Database instance
        owner_id: Worker ID

    Returns:
        List of OKRs owned by the worker
    """
    rows = db.fetchall(
        "SELECT * FROM okrs WHERE owner_worker_id = ? ORDER BY created_at DESC",
        (owner_id,)
    )
    return [
        OKR(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            owner_worker_id=row["owner_worker_id"],
            parent_okr_id=row["parent_okr_id"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            key_results=_parse_key_results(_get_row_value(row, "key_results")),
            due_date=_parse_date(_get_row_value(row, "due_date")),
        )
        for row in rows
    ]


def get_child_okrs(db: Database, parent_id: str) -> list[OKR]:
    """Get OKRs that have the given OKR as their parent.

    Args:
        db: Database instance
        parent_id: Parent OKR ID

    Returns:
        List of child OKRs
    """
    rows = db.fetchall(
        "SELECT * FROM okrs WHERE parent_okr_id = ? ORDER BY created_at",
        (parent_id,)
    )
    return [
        OKR(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            owner_worker_id=row["owner_worker_id"],
            parent_okr_id=row["parent_okr_id"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            key_results=_parse_key_results(_get_row_value(row, "key_results")),
            due_date=_parse_date(_get_row_value(row, "due_date")),
        )
        for row in rows
    ]


def update_okr_key_result(
    db: Database,
    okr_id: str,
    metric: str,
    current: float,
) -> Optional[OKR]:
    """Update a key result's current value.

    Args:
        db: Database instance
        okr_id: OKR ID
        metric: Key result metric name to update
        current: New current value

    Returns:
        Updated OKR, or None if not found or metric doesn't exist
    """
    okr = get_okr(db, okr_id)
    if not okr:
        return None

    # Find and update the key result
    updated = False
    for kr in okr.key_results:
        if kr.metric == metric:
            kr.current = current
            updated = True
            break

    if not updated:
        return None

    # Save back to database
    kr_json = json.dumps([
        {"metric": kr.metric, "target": kr.target, "current": kr.current, "unit": kr.unit}
        for kr in okr.key_results
    ])
    now = datetime.now()
    db.execute(
        "UPDATE okrs SET key_results = ?, updated_at = ? WHERE id = ?",
        (kr_json, now, okr_id)
    )
    db.connection.commit()

    okr.updated_at = now
    return okr


def add_okr_key_result(
    db: Database,
    okr_id: str,
    metric: str,
    target: float,
    unit: str,
    current: float = 0.0,
) -> Optional[OKR]:
    """Add a new key result to an OKR.

    Args:
        db: Database instance
        okr_id: OKR ID
        metric: Key result metric name
        target: Target value
        unit: Unit of measurement
        current: Initial current value (default 0)

    Returns:
        Updated OKR, or None if OKR not found
    """
    okr = get_okr(db, okr_id)
    if not okr:
        return None

    # Check if metric already exists
    for kr in okr.key_results:
        if kr.metric == metric:
            return None  # Duplicate metric

    # Add new key result
    okr.key_results.append(KeyResult(metric=metric, target=target, current=current, unit=unit))

    # Save back to database
    kr_json = json.dumps([
        {"metric": kr.metric, "target": kr.target, "current": kr.current, "unit": kr.unit}
        for kr in okr.key_results
    ])
    now = datetime.now()
    db.execute(
        "UPDATE okrs SET key_results = ?, updated_at = ? WHERE id = ?",
        (kr_json, now, okr_id)
    )
    db.connection.commit()

    okr.updated_at = now
    return okr


@dataclass
class OKRTreeNode:
    """Node in an OKR hierarchy tree."""
    okr: OKR
    children: list["OKRTreeNode"]


def get_okr_hierarchy(db: Database, root_okr_id: str) -> Optional[OKRTreeNode]:
    """Get the full OKR hierarchy starting from a root OKR.

    Recursively builds the tree of OKRs cascading down from the root.

    Args:
        db: Database instance
        root_okr_id: The root OKR ID to start from

    Returns:
        OKRTreeNode representing the hierarchy, or None if root not found
    """
    root = get_okr(db, root_okr_id)
    if not root:
        return None

    def build_tree(okr: OKR) -> OKRTreeNode:
        children = get_child_okrs(db, okr.id)
        return OKRTreeNode(
            okr=okr,
            children=[build_tree(child) for child in children],
        )

    return build_tree(root)


def get_okr_ancestors(db: Database, okr_id: str) -> list[OKR]:
    """Get all ancestor OKRs (parent, grandparent, etc.) up to the root.

    Args:
        db: Database instance
        okr_id: OKR ID to start from

    Returns:
        List of ancestor OKRs, from immediate parent to root
    """
    ancestors = []
    current_okr = get_okr(db, okr_id)

    while current_okr and current_okr.parent_okr_id:
        parent = get_okr(db, current_okr.parent_okr_id)
        if parent:
            ancestors.append(parent)
            current_okr = parent
        else:
            break

    return ancestors


# ===================
# WORK-OKR LINK QUERIES
# ===================

def link_work_to_okr(
    db: Database,
    work_id: str,
    okr_id: str,
    link_type: str = "contributes",
) -> WorkOKRLink:
    """Link a work item to an OKR.

    Every work item should link to an objective for strategic alignment.

    Args:
        db: Database instance
        work_id: Work item ID (e.g., bead ID)
        okr_id: OKR ID to link to
        link_type: Type of link ('contributes', 'blocks', 'depends_on')

    Returns:
        Created WorkOKRLink
    """
    now = datetime.now()
    db.execute(
        """INSERT OR REPLACE INTO work_okr_links
           (work_id, okr_id, link_type, created_at)
           VALUES (?, ?, ?, ?)""",
        (work_id, okr_id, link_type, now)
    )
    db.connection.commit()

    return WorkOKRLink(
        work_id=work_id,
        okr_id=okr_id,
        link_type=link_type,
        created_at=now,
    )


def unlink_work_from_okr(db: Database, work_id: str, okr_id: str) -> bool:
    """Remove link between work item and OKR.

    Args:
        db: Database instance
        work_id: Work item ID
        okr_id: OKR ID

    Returns:
        True if link was removed, False if not found
    """
    cursor = db.execute(
        "DELETE FROM work_okr_links WHERE work_id = ? AND okr_id = ?",
        (work_id, okr_id)
    )
    db.connection.commit()
    return cursor.rowcount > 0


def get_work_okr_link(
    db: Database,
    work_id: str,
    okr_id: str,
) -> Optional[WorkOKRLink]:
    """Get a specific work-OKR link.

    Args:
        db: Database instance
        work_id: Work item ID
        okr_id: OKR ID

    Returns:
        WorkOKRLink or None
    """
    row = db.fetchone(
        "SELECT * FROM work_okr_links WHERE work_id = ? AND okr_id = ?",
        (work_id, okr_id)
    )
    if not row:
        return None

    return WorkOKRLink(
        work_id=row["work_id"],
        okr_id=row["okr_id"],
        link_type=row["link_type"],
        created_at=row["created_at"],
    )


def get_work_for_okr(db: Database, okr_id: str) -> list[WorkOKRLink]:
    """Get all work items linked to an OKR.

    Args:
        db: Database instance
        okr_id: OKR ID

    Returns:
        List of WorkOKRLink records
    """
    rows = db.fetchall(
        "SELECT * FROM work_okr_links WHERE okr_id = ? ORDER BY created_at",
        (okr_id,)
    )
    return [
        WorkOKRLink(
            work_id=row["work_id"],
            okr_id=row["okr_id"],
            link_type=row["link_type"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_okrs_for_work(db: Database, work_id: str) -> list[WorkOKRLink]:
    """Get all OKRs linked to a work item.

    Args:
        db: Database instance
        work_id: Work item ID

    Returns:
        List of WorkOKRLink records
    """
    rows = db.fetchall(
        "SELECT * FROM work_okr_links WHERE work_id = ? ORDER BY created_at",
        (work_id,)
    )
    return [
        WorkOKRLink(
            work_id=row["work_id"],
            okr_id=row["okr_id"],
            link_type=row["link_type"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_work_for_okr_hierarchy(db: Database, root_okr_id: str) -> list[WorkOKRLink]:
    """Get all work items linked to an OKR and all its descendants.

    This is useful for seeing all work contributing to a high-level objective.

    Args:
        db: Database instance
        root_okr_id: Root OKR ID

    Returns:
        List of all WorkOKRLink records for the hierarchy
    """
    all_links = []

    def collect_links(okr_id: str) -> None:
        # Get links for this OKR
        links = get_work_for_okr(db, okr_id)
        all_links.extend(links)

        # Recurse into children
        children = get_child_okrs(db, okr_id)
        for child in children:
            collect_links(child.id)

    collect_links(root_okr_id)
    return all_links
