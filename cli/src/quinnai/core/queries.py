"""
Query helpers for common database operations.

Provides high-level functions for interacting with quinn.db without
writing raw SQL. All functions are organized by entity type.
"""

import json
import uuid
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

from .db import Database


# ===================
# DATA CLASSES
# ===================

@dataclass
class OrgState:
    """Organization state."""
    id: str
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
    if status == "running":
        db.execute(
            """UPDATE org_state SET status = ?, ceo_worker_id = ?,
               started_at = ?, updated_at = ? WHERE id = 'default'""",
            (status, ceo_worker_id, now, now)
        )
    elif status == "stopped":
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
    team_id: Optional[str] = None,
) -> Team:
    """Create a new team.

    Args:
        db: Database instance
        name: Team name
        parent_team_id: Optional parent team for hierarchy
        team_id: Optional custom ID (generated if not provided)

    Returns:
        Created Team
    """
    if team_id is None:
        team_id = generate_id("team")

    now = datetime.now()
    db.execute(
        "INSERT INTO teams (id, name, parent_team_id, created_at) VALUES (?, ?, ?, ?)",
        (team_id, name, parent_team_id, now)
    )
    db.connection.commit()

    return Team(
        id=team_id,
        name=name,
        parent_team_id=parent_team_id,
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
           (id, name, role, team_id, manager_id, status, skills, cost, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
        (worker_id, name, role, team_id, manager_id, skills_json, cost, now, now)
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
    column = "tasks_completed" if completed else "tasks_failed"
    db.execute(
        f"UPDATE worker_state SET {column} = {column} + 1, updated_at = ? WHERE worker_id = ?",
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


def subscribe_to_channel(db: Database, channel_id: str, worker_id: str) -> None:
    """Subscribe a worker to a channel.

    Args:
        db: Database instance
        channel_id: Channel ID
        worker_id: Worker ID
    """
    now = datetime.now()
    db.execute(
        "INSERT OR IGNORE INTO channel_subscriptions (channel_id, worker_id, subscribed_at) VALUES (?, ?, ?)",
        (channel_id, worker_id, now)
    )
    db.connection.commit()


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
