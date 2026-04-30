"""Worker and worker state queries."""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any

from ..db import Database
from .common import generate_id


def _row_to_worker(row: Any) -> "Worker":
    """Convert a database row to a Worker instance.

    Handles optional fields like preferred_provider that may not exist in older DBs.

    Args:
        row: sqlite3.Row or dict-like object

    Returns:
        Worker instance
    """
    # Convert to dict for optional field access
    row_dict = dict(row)

    return Worker(
        id=row_dict["id"],
        name=row_dict["name"],
        role=row_dict["role"],
        team_id=row_dict["team_id"],
        manager_id=row_dict["manager_id"],
        status=row_dict["status"],
        skills=json.loads(row_dict["skills"]) if row_dict["skills"] else {},
        cost=row_dict["cost"],
        hiring_authority_scope=row_dict.get("hiring_authority_scope"),
        delegated_budget=row_dict.get("delegated_budget", 0),
        max_reports=row_dict.get("max_reports", 10),
        preferred_provider=row_dict.get("preferred_provider"),
        created_at=row_dict["created_at"],
        updated_at=row_dict["updated_at"],
    )


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
    preferred_provider: Optional[str]
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
    preferred_provider: Optional[str] = None,
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
        preferred_provider: Optional preferred CLI provider (e.g., claude_code, cursor)

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
            hiring_authority_scope, delegated_budget, max_reports, preferred_provider,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?)""",
        (worker_id, name, role, team_id, manager_id, skills_json, cost,
         hiring_authority_scope, delegated_budget, max_reports, preferred_provider, now, now)
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
        preferred_provider=preferred_provider,
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

    return _row_to_worker(row)


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

    return _row_to_worker(row)


def get_workers_by_role(db: Database, role: str) -> list[Worker]:
    """Get all workers with a given role.

    Args:
        db: Database instance
        role: Role to match (case-insensitive, e.g. 'CEO', 'director')

    Returns:
        List of matching workers (may be empty or have multiple entries)
    """
    rows = db.fetchall(
        "SELECT * FROM workers WHERE LOWER(role) = LOWER(?)",
        (role,)
    )
    return [_row_to_worker(row) for row in rows]


def resolve_worker(db: Database, selector: str) -> Optional[Worker]:
    """Resolve a worker selector (name, id, or role) to a single Worker.

    Tries in order:
    1. Exact ID match
    2. Case-insensitive name match
    3. Case-insensitive role match — only succeeds if exactly ONE worker
       holds that role (so 'ceo' resolves to the unique CEO, but 'engineer'
       won't if there are five engineers).

    Returns None if no match. Returns None for ambiguous role match too;
    callers can re-query get_workers_by_role to disambiguate.
    """
    by_id = get_worker(db, selector)
    if by_id is not None:
        return by_id

    by_name = get_worker_by_name(db, selector)
    if by_name is not None:
        return by_name

    by_role = get_workers_by_role(db, selector)
    if len(by_role) == 1:
        return by_role[0]

    return None


def update_worker_status(db: Database, worker_id: str, status: str) -> None:
    """Update worker lifecycle status.

    Publishes WORKER_STATUS_CHANGED event if event bus is available.

    Args:
        db: Database instance
        worker_id: Worker ID
        status: New status
    """
    # Get old status for event publishing
    old_row = db.fetchone("SELECT status FROM workers WHERE id = ?", (worker_id,))
    old_status = old_row["status"] if old_row else None

    now = datetime.now()
    db.execute(
        "UPDATE workers SET status = ?, updated_at = ? WHERE id = ?",
        (status, now, worker_id)
    )
    db.connection.commit()

    # Publish event if status actually changed
    if old_status and old_status != status:
        from ..events import EventType, get_event_bus, ENTITY_TYPE_WORKER
        bus = get_event_bus()
        if bus:
            bus.publish(
                event_type=EventType.WORKER_STATUS_CHANGED,
                entity_type=ENTITY_TYPE_WORKER,
                entity_id=worker_id,
                payload={
                    "old_status": old_status,
                    "new_status": status,
                    "worker_id": worker_id,
                    "changed_at": now.isoformat(),
                },
            )


def get_workers_by_status(db: Database, status: str) -> list[Worker]:
    """Get workers by status.

    Args:
        db: Database instance
        status: Worker status to filter by

    Returns:
        List of matching workers
    """
    rows = db.fetchall("SELECT * FROM workers WHERE status = ?", (status,))
    return [_row_to_worker(row) for row in rows]


def get_workers_by_manager(db: Database, manager_id: str) -> list[Worker]:
    """Get direct reports of a manager.

    Args:
        db: Database instance
        manager_id: Manager's worker ID

    Returns:
        List of direct reports
    """
    rows = db.fetchall("SELECT * FROM workers WHERE manager_id = ?", (manager_id,))
    return [_row_to_worker(row) for row in rows]


def get_team_workers(db: Database, team_id: str) -> list[Worker]:
    """Get all workers in a team.

    Args:
        db: Database instance
        team_id: Team ID

    Returns:
        List of workers in team
    """
    rows = db.fetchall("SELECT * FROM workers WHERE team_id = ?", (team_id,))
    return [_row_to_worker(row) for row in rows]


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

    Creates worker_state row if it doesn't exist (upsert).
    Publishes WORKER_RUNTIME_STATUS_CHANGED event if event bus is available.

    Args:
        db: Database instance
        worker_id: Worker ID
        runtime_status: New runtime status
        current_task_id: Optional current task
    """
    # Get old status for event publishing
    old_row = db.fetchone(
        "SELECT runtime_status FROM worker_state WHERE worker_id = ?",
        (worker_id,)
    )
    old_status = old_row["runtime_status"] if old_row else None

    now = datetime.now()

    # Try to update existing row first
    result = db.execute(
        """UPDATE worker_state SET runtime_status = ?, current_task_id = ?,
           last_activity = ?, updated_at = ? WHERE worker_id = ?""",
        (runtime_status, current_task_id, now, now, worker_id)
    )

    # If no row was updated, create it
    if result.rowcount == 0:
        db.execute(
            """INSERT INTO worker_state
               (worker_id, runtime_status, current_task_id, started_at, last_activity, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (worker_id, runtime_status, current_task_id, now, now, now)
        )
        old_status = None  # New row, no old status

    db.connection.commit()

    # Publish event if status actually changed
    if old_status is None or old_status != runtime_status:
        from ..events import EventType, get_event_bus, ENTITY_TYPE_WORKER
        bus = get_event_bus()
        if bus:
            bus.publish(
                event_type=EventType.WORKER_RUNTIME_STATUS_CHANGED,
                entity_type=ENTITY_TYPE_WORKER,
                entity_id=worker_id,
                payload={
                    "old_status": old_status or "none",
                    "new_status": runtime_status,
                    "worker_id": worker_id,
                    "changed_at": now.isoformat(),
                },
            )


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


def get_all_workers_for_topology(db: Database) -> list[dict]:
    """Get all workers for building org topology.

    Returns minimal worker data needed for topology construction.

    Args:
        db: Database instance

    Returns:
        List of dicts with id, name, manager_id, role
    """
    rows = db.fetchall("SELECT id, name, manager_id, role FROM workers")
    return [dict(row) for row in rows]


def get_root_worker(db: Database) -> Optional[Worker]:
    """Get the root worker (CEO) - worker with no manager.

    Args:
        db: Database instance

    Returns:
        Worker dataclass or None if not found
    """
    # Try active workers first
    row = db.fetchone(
        "SELECT * FROM workers WHERE manager_id IS NULL AND status != 'terminated'"
    )

    # Fallback: check for any root worker including terminated
    if row is None:
        row = db.fetchone("SELECT * FROM workers WHERE manager_id IS NULL")

    if row is None:
        return None

    return _row_to_worker(row)


def update_worker_preferred_provider(
    db: Database,
    worker_id: str,
    preferred_provider: Optional[str],
) -> None:
    """Update worker's preferred provider.

    Args:
        db: Database instance
        worker_id: Worker ID
        preferred_provider: Provider name or None to clear
    """
    now = datetime.now()
    db.execute(
        "UPDATE workers SET preferred_provider = ?, updated_at = ? WHERE id = ?",
        (preferred_provider, now, worker_id)
    )
    db.connection.commit()


def get_worker_preferred_provider(db: Database, worker_id: str) -> Optional[str]:
    """Get worker's preferred provider.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        Provider name or None
    """
    row = db.fetchone(
        "SELECT preferred_provider FROM workers WHERE id = ?",
        (worker_id,)
    )
    if not row:
        return None
    return row["preferred_provider"]


def set_worker_tools(db: Database, worker_id: str, tools: list[dict]) -> None:
    """Persist a worker's extra CLI tool dependencies.

    Args:
        db: Database instance
        worker_id: Worker ID
        tools: List of tool dicts with keys name, description, install_cmd, check_cmd
    """
    now = datetime.now()
    db.execute(
        "UPDATE workers SET tools = ?, updated_at = ? WHERE id = ?",
        (json.dumps(tools), now, worker_id),
    )
    db.connection.commit()


def get_worker_tools(db: Database, worker_id: str) -> list[dict]:
    """Retrieve a worker's extra CLI tool dependencies.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        List of tool dicts, or empty list if none set
    """
    row = db.fetchone("SELECT tools FROM workers WHERE id = ?", (worker_id,))
    if not row or not row["tools"]:
        return []
    return json.loads(row["tools"])


def get_worker_continuation_context(db: Database, worker_id: str) -> dict:
    """Get context data for continuation prompts.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        Dict with keys:
        - worker_id: Worker ID
        - worker_name: Worker name
        - manager_id: Manager worker ID (or "ceo" if no manager)
        - team_channel: Team channel name (or "general" if no team)
        - current_task_id: Current task ID (or "your-task" if none)
    """
    row = db.fetchone(
        """SELECT w.id, w.name, w.manager_id,
                  ws.current_task_id,
                  t.name as team_name
           FROM workers w
           LEFT JOIN worker_state ws ON w.id = ws.worker_id
           LEFT JOIN teams t ON w.team_id = t.id
           WHERE w.id = ?""",
        (worker_id,)
    )

    if not row:
        # Fallback context if worker not found
        return {
            "worker_id": worker_id,
            "worker_name": "Worker",
            "manager_id": "ceo",
            "team_channel": "general",
            "current_task_id": "your-task",
        }

    return {
        "worker_id": worker_id,
        "worker_name": row["name"],
        "manager_id": row["manager_id"] or "ceo",
        "team_channel": row["team_name"] or "general",
        "current_task_id": row["current_task_id"] or "your-task",
    }


__all__ = [
    "Worker",
    "WorkerState",
    "create_worker",
    "get_worker",
    "get_worker_by_name",
    "update_worker_status",
    "get_workers_by_status",
    "get_workers_by_manager",
    "get_team_workers",
    "get_all_workers_for_topology",
    "get_root_worker",
    "is_worker_manager",
    "create_worker_state",
    "get_worker_state",
    "update_worker_runtime_status",
    "record_worker_heartbeat",
    "increment_worker_task_count",
    "get_workers_by_runtime_status",
    "update_worker_preferred_provider",
    "get_worker_preferred_provider",
    "set_worker_tools",
    "get_worker_tools",
    "get_worker_continuation_context",
]
