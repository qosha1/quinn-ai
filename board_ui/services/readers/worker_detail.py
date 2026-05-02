"""Read rich per-worker context for the worker detail panel."""

import subprocess
from pathlib import Path
from typing import Any

from ...interfaces.org_connection import WorkerDetail
from shared.core.tools import OrgToolsConfig, merge_tool_lists, ToolDependency


_BRIEFING_EXCERPT_LINES = 40
_STORAGE_TREE_MAX_DEPTH = 2
_RECENT_MESSAGES_LIMIT = 5
_ACTIVE_BEADS_LIMIT = 8


class WorkerDetailReader:
    """Reads all context needed for the WorkerDetailPanel."""

    def __init__(self, db: Any, org_path: Path) -> None:
        self._db = db
        self._org_path = org_path

    def get_worker_detail(self, worker_id: str) -> WorkerDetail:
        return WorkerDetail(
            worker_id=worker_id,
            tools=self._load_tools(worker_id),
            storage_tree=self._build_storage_tree(worker_id),
            active_beads=self._load_active_beads(worker_id),
            recent_messages=self._load_recent_messages(worker_id),
            briefing_excerpt=self._load_briefing_excerpt(worker_id),
        )

    def _load_tools(self, worker_id: str) -> list[dict]:
        org_config = OrgToolsConfig.load_from_yaml(
            self._org_path / "config" / "tools.yaml"
        )
        try:
            from cli.core.queries import get_worker_tools
            raw = get_worker_tools(self._db, worker_id)
            worker_tools = [
                ToolDependency(
                    name=t["name"],
                    description=t.get("description", ""),
                    install_cmd=t.get("install_cmd", ""),
                    check_cmd=t.get("check_cmd", ""),
                )
                for t in raw
            ]
        except Exception:
            worker_tools = []
        merged = merge_tool_lists(org_config.tools, worker_tools)
        return [
            {"name": t.name, "description": t.description, "install_cmd": t.install_cmd}
            for t in merged
        ]

    def _build_storage_tree(self, worker_id: str) -> dict:
        worker_dir = self._find_worker_dir(worker_id)
        if not worker_dir or not worker_dir.exists():
            return {}
        return _walk_tree(worker_dir, depth=0, max_depth=_STORAGE_TREE_MAX_DEPTH)

    def _find_worker_dir(self, worker_id: str) -> Path | None:
        try:
            from cli.core.storage import StorageManager
            storage = StorageManager(self._org_path, db=self._db)
            return storage.get_worker_path(worker_id)
        except Exception:
            pass
        # Fallback: scan storage/workers/** for a directory named worker_id
        workers_root = self._org_path / "storage" / "workers"
        if workers_root.exists():
            for candidate in workers_root.rglob(worker_id):
                if candidate.is_dir():
                    return candidate
        return None

    def _load_briefing_excerpt(self, worker_id: str) -> str:
        worker_dir = self._find_worker_dir(worker_id)
        if not worker_dir:
            return ""
        briefing = worker_dir / "BRIEFING.md"
        if not briefing.exists():
            return ""
        lines = briefing.read_text(errors="replace").splitlines()
        return "\n".join(lines[:_BRIEFING_EXCERPT_LINES])

    def _load_active_beads(self, worker_id: str) -> list[dict]:
        try:
            result = subprocess.run(
                [
                    "bd", "list",
                    f"--assignee={worker_id}",
                    "--status=open,in_progress",
                    f"-n={_ACTIVE_BEADS_LIMIT}",
                    "--json",
                ],
                capture_output=True, text=True, timeout=5,
                cwd=str(self._org_path),
            )
            if result.returncode == 0:
                import json
                return json.loads(result.stdout) if result.stdout.strip() else []
        except Exception:
            pass
        return []

    def _load_recent_messages(self, worker_id: str) -> list[dict]:
        try:
            rows = self._db.fetchall(
                """
                SELECT m.body, w.name as sender, m.created_at
                FROM messages m
                JOIN workers w ON m.sender_id = w.id
                WHERE m.channel_id IN (
                    SELECT channel_id FROM channel_subscriptions WHERE worker_id = ?
                )
                ORDER BY m.created_at DESC
                LIMIT ?
                """,
                (worker_id, _RECENT_MESSAGES_LIMIT),
            )
            return [
                {"sender": r["sender"], "body": r["body"][:120], "ts": str(r["created_at"])[:16]}
                for r in (rows or [])
            ]
        except Exception:
            return []


def _walk_tree(path: Path, depth: int, max_depth: int) -> dict:
    result: dict = {}
    if depth >= max_depth:
        return result
    try:
        for child in sorted(path.iterdir()):
            if child.name.startswith("."):
                continue
            if child.is_dir():
                result[child.name + "/"] = _walk_tree(child, depth + 1, max_depth)
            else:
                result[child.name] = None
    except PermissionError:
        pass
    return result
