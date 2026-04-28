"""Read org health: per-worker OKR coverage, task assignment, session state."""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from ...interfaces.org_connection import HealthIssue, HealthStatus
from ...logging_config import get_board_logger

logger = get_board_logger(__name__)


class HealthReader:
    """Compute org-level health from per-worker OKR / task / session signals."""

    def __init__(self, db: Any, org_path: Path) -> None:
        self._db = db
        self._org_path = org_path

    def get_health_status(self) -> HealthStatus:
        """Get organization health status."""
        issues: list[HealthIssue] = []
        workers_with_issues_set: set[str] = set()

        workers = self._db.fetchall(
            """SELECT id, name, status FROM workers WHERE status = 'active'"""
        )

        for worker in workers:
            worker_id = worker["id"]
            worker_name = worker["name"]

            self._check_okr_coverage(worker_id, worker_name, issues, workers_with_issues_set)
            self._check_task_assignment(worker_id, worker_name, issues, workers_with_issues_set)
            self._check_session_health(worker_id, worker_name, issues, workers_with_issues_set)

        total_workers = len(workers)
        return HealthStatus(
            overall_score=self._compute_overall_score(total_workers, issues),
            issues=issues,
            workers_with_issues=len(workers_with_issues_set),
            total_workers=total_workers,
            last_checked=datetime.now(),
        )

    def _check_okr_coverage(
        self,
        worker_id: str,
        worker_name: str,
        issues: list[HealthIssue],
        with_issues: set[str],
    ) -> None:
        okr_count = self._db.fetchone(
            """SELECT COUNT(*) as count FROM okrs
               WHERE owner_worker_id = ? AND status = 'active'""",
            (worker_id,),
        )["count"]

        if okr_count == 0:
            issues.append(
                HealthIssue(
                    worker_id=worker_id,
                    worker_name=worker_name,
                    issue_type="no_okrs",
                    severity="warning",
                    message=f"{worker_name} has no active OKRs assigned",
                )
            )
            with_issues.add(worker_id)

    def _check_task_assignment(
        self,
        worker_id: str,
        worker_name: str,
        issues: list[HealthIssue],
        with_issues: set[str],
    ) -> None:
        try:
            result = subprocess.run(
                ["bd", "list", "--assignee", worker_id, "--status=open,in_progress", "--json"],
                cwd=self._org_path,
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                beads = json.loads(result.stdout)
                if len(beads) == 0:
                    issues.append(
                        HealthIssue(
                            worker_id=worker_id,
                            worker_name=worker_name,
                            issue_type="no_tasks",
                            severity="info",
                            message=f"{worker_name} has no open tasks assigned",
                        )
                    )
                    with_issues.add(worker_id)
        except (subprocess.TimeoutExpired, Exception) as e:
            logger.debug(f"Skipping task check for {worker_name}: {e}")

    def _check_session_health(
        self,
        worker_id: str,
        worker_name: str,
        issues: list[HealthIssue],
        with_issues: set[str],
    ) -> None:
        session = self._db.fetchone(
            """SELECT state FROM sessions
               WHERE worker_id = ? AND state != 'stopped'
               ORDER BY created_at DESC LIMIT 1""",
            (worker_id,),
        )
        if session and session["state"] == "crashed":
            issues.append(
                HealthIssue(
                    worker_id=worker_id,
                    worker_name=worker_name,
                    issue_type="crashed_session",
                    severity="error",
                    message=f"{worker_name} has a crashed session",
                )
            )
            with_issues.add(worker_id)

    def _compute_overall_score(self, total_workers: int, issues: list[HealthIssue]) -> str:
        if total_workers == 0:
            return "healthy"
        if any(i.severity == "critical" for i in issues):
            return "critical"
        if any(i.severity == "warning" for i in issues):
            return "warning"
        return "healthy"
