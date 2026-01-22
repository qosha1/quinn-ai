"""
Org-chart management for QuinnAI CLI.

Provides functions to regenerate the org-chart YAML from database state.
The org-chart is the git-tracked output of hiring decisions.
"""

import subprocess
from pathlib import Path
from typing import Optional

import yaml

from .db import Database
from .queries import get_worker, get_workers_by_manager


# Org-chart file paths (no magic values in function bodies)
ORG_CHART_DIR = "org-chart"
ORG_CHART_CURRENT = "current.yaml"
ORG_CHART_VERSION = "1.0"


def git_commit_org_chart(
    org_path: Path,
    change_type: str,
    worker_name: Optional[str] = None,
    worker_role: Optional[str] = None,
    details: Optional[str] = None,
) -> bool:
    """Commit org-chart changes to git.

    Auto-commits org-chart/current.yaml after updates. Gracefully handles
    non-git repos by returning False without raising.

    Args:
        org_path: Path to the org folder (git repo root)
        change_type: Type of change (hired, terminated, promoted, updated)
        worker_name: Name of the affected worker (optional)
        worker_role: Role of the affected worker (optional)
        details: Additional details for commit message (optional)

    Returns:
        True if commit succeeded, False if git not available or commit failed
    """
    chart_path = org_path / ORG_CHART_DIR / ORG_CHART_CURRENT

    # Build commit message
    if worker_name and worker_role:
        message = f"org-chart: {change_type} {worker_name} as {worker_role}"
    elif worker_name:
        message = f"org-chart: {change_type} {worker_name}"
    else:
        message = f"org-chart: {change_type}"

    if details:
        message = f"{message}\n\n{details}"

    try:
        # Check if org_path is a git repo
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=org_path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return False  # Not a git repo

        # Stage the org-chart file
        result = subprocess.run(
            ["git", "add", str(chart_path.relative_to(org_path))],
            cwd=org_path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return False

        # Check if there are staged changes
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=org_path,
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            return False  # No changes to commit

        # Commit the changes
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=org_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        # Git not available, timeout, or other OS error
        return False


def update_org_chart(db: Database, org_path: Path) -> Path:
    """Regenerate org-chart/current.yaml from database state.

    Walks the worker hierarchy starting from the root (worker with no manager)
    and builds the complete org-chart YAML file.

    Args:
        db: Database instance
        org_path: Path to the org folder

    Returns:
        Path to the updated org-chart file

    Raises:
        ValueError: If no root worker (CEO) is found
    """
    # Find the root worker (no manager_id)
    root_worker = _find_root_worker(db)
    if root_worker is None:
        raise ValueError("No root worker (CEO) found in database")

    # Build the org-chart structure
    workers_dict = {}
    hierarchy = {"root": root_worker.id}

    # Recursively build worker entries
    _build_worker_entry(db, root_worker, workers_dict)

    org_chart = {
        "version": ORG_CHART_VERSION,
        "workers": workers_dict,
        "hierarchy": hierarchy,
    }

    # Write to file
    chart_path = org_path / ORG_CHART_DIR / ORG_CHART_CURRENT
    chart_path.parent.mkdir(parents=True, exist_ok=True)

    with open(chart_path, "w") as f:
        yaml.dump(org_chart, f, default_flow_style=False, sort_keys=False)

    return chart_path


def _find_root_worker(db: Database):
    """Find the root worker (CEO) - worker with no manager.

    Args:
        db: Database instance

    Returns:
        Worker dataclass or None if not found
    """
    row = db.fetchone(
        "SELECT * FROM workers WHERE manager_id IS NULL AND status != 'terminated'"
    )
    if row is None:
        # Fallback: check for any root worker including terminated
        row = db.fetchone("SELECT * FROM workers WHERE manager_id IS NULL")

    if row is None:
        return None

    # Import here to avoid circular imports
    import json
    from .queries import Worker as WorkerData

    return WorkerData(
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


def _build_worker_entry(db: Database, worker, workers_dict: dict) -> None:
    """Recursively build worker entry and its reports.

    Args:
        db: Database instance
        worker: Worker dataclass
        workers_dict: Dict to populate with worker entries
    """
    # Get direct reports
    reports = get_workers_by_manager(db, worker.id)
    report_ids = [r.id for r in reports]

    # Add this worker's entry
    workers_dict[worker.id] = {
        "name": worker.name,
        "role": worker.role,
        "lifecycle": worker.status,
        "manager": worker.manager_id,
        "reports": report_ids,
    }

    # Recursively add reports
    for report in reports:
        _build_worker_entry(db, report, workers_dict)
