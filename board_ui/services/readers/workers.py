"""Read worker state and session info."""

from pathlib import Path
from typing import Any, Optional

from ...interfaces.org_connection import WorkerInfo
from ._helpers import (
    DEFAULT_ORG_ID,
    parse_session_state,
    parse_worker_status,
)


class WorkerReader:
    """Read worker rows joined with team and live session state."""

    def __init__(self, db: Any, org_path: Path) -> None:
        self._db = db
        self._org_path = org_path

    def get_workers(self) -> list[WorkerInfo]:
        """Get all workers in the org."""
        rows = self._db.fetchall(
            """SELECT w.*, t.name as team_name
               FROM workers w
               JOIN teams t ON w.team_id = t.id
               ORDER BY w.manager_id NULLS FIRST, w.created_at"""
        )

        session_states = self._get_worker_session_states()
        ceo_id = self._get_ceo_id()

        workers: list[WorkerInfo] = []
        for row in rows:
            workers.append(self._build_worker_info(row, session_states.get(row["id"], {}), ceo_id))
        return workers

    def get_worker(self, worker_id: str) -> Optional[WorkerInfo]:
        """Get a specific worker by ID."""
        row = self._db.fetchone(
            """SELECT w.*, t.name as team_name
               FROM workers w
               JOIN teams t ON w.team_id = t.id
               WHERE w.id = ?""",
            (worker_id,),
        )
        if not row:
            return None

        session_info = self._get_worker_session_state(worker_id)
        ceo_id = self._get_ceo_id()
        return self._build_worker_info(row, session_info, ceo_id)

    def get_ceo(self) -> Optional[WorkerInfo]:
        """Get the CEO worker."""
        ceo_id = self._get_ceo_id()
        if not ceo_id:
            return None
        return self.get_worker(ceo_id)

    def _get_ceo_id(self) -> Optional[str]:
        org_row = self._db.fetchone(
            "SELECT ceo_worker_id FROM org_state WHERE id = ?", (DEFAULT_ORG_ID,)
        )
        return org_row["ceo_worker_id"] if org_row else None

    def _build_worker_info(
        self,
        row: Any,
        session_info: dict,
        ceo_id: Optional[str],
    ) -> WorkerInfo:
        worker_id = row["id"]
        manager_id = row["manager_id"]
        is_ceo = worker_id == ceo_id
        is_manager = (manager_id is None) and not is_ceo
        session_mode = "autonomous" if (is_ceo or is_manager) else "interactive"

        return WorkerInfo(
            id=worker_id,
            name=row["name"],
            role=row["role"],
            team_name=row["team_name"],
            status=parse_worker_status(row["status"]),
            session_state=parse_session_state(session_info.get("state")),
            tmux_session_name=session_info.get("tmux_session_name"),
            manager_id=manager_id,
            current_task=session_info.get("current_task_id"),
            is_ceo=is_ceo,
            session_mode=session_mode,
        )

    def _get_worker_session_states(self) -> dict[str, dict]:
        """Get session states for all workers (sessions table + worker_state)."""
        rows = self._db.fetchall(
            """SELECT worker_id, state, tmux_session_name FROM sessions"""
        )

        result: dict[str, dict] = {}
        for row in rows:
            result[row["worker_id"]] = {
                "state": row["state"],
                "tmux_session_name": row["tmux_session_name"],
            }

        state_rows = self._db.fetchall(
            """SELECT worker_id, current_task_id, runtime_status FROM worker_state"""
        )
        for row in state_rows:
            worker_id = row["worker_id"]
            if worker_id not in result:
                result[worker_id] = {"state": row["runtime_status"]}
            result[worker_id]["current_task_id"] = row["current_task_id"]

        return result

    def _get_worker_session_state(self, worker_id: str) -> dict:
        """Get session state for one worker."""
        row = self._db.fetchone(
            """SELECT state, tmux_session_name
               FROM sessions WHERE worker_id = ?""",
            (worker_id,),
        )
        result: dict = {}
        if row:
            result = {
                "state": row["state"],
                "tmux_session_name": row["tmux_session_name"],
            }

        state_row = self._db.fetchone(
            """SELECT current_task_id, runtime_status
               FROM worker_state WHERE worker_id = ?""",
            (worker_id,),
        )
        if state_row:
            if "state" not in result:
                result["state"] = state_row["runtime_status"]
            result["current_task_id"] = state_row["current_task_id"]

        return result
