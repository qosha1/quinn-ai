"""Worker and worker state queries."""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..db import Database
from .common import generate_id


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

    Args:
        db: Database instance
        worker_id: Worker ID
        runtime_status: New runtime status
        current_task_id: Optional current task
    """
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

    import json
    return Worker(
        id=row["id"],
        name=row["name"],
        role=row["role"],
        team_id=row["team_id"],
        manager_id=row["manager_id"],
        status=row["status"],
        skills=json.loads(row["skills"]) if row["skills"] else {},
        cost=row["cost"],
        hiring_authority_scope=row["hiring_authority_scope"],
        delegated_budget=row["delegated_budget"],
        max_reports=row["max_reports"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


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
]
