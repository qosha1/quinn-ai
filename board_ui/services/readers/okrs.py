"""Read OKRs and the CEO briefing file."""

import json
from pathlib import Path
from typing import Any, Optional

from ...interfaces.org_connection import OKRInfo
from ._helpers import parse_datetime


class OKRReader:
    """Read OKRs (with their key results) and the CEO briefing file."""

    def __init__(self, db: Any, org_path: Path) -> None:
        self._db = db
        self._org_path = org_path

    def get_okrs(self, owner_id: Optional[str] = None) -> list[OKRInfo]:
        """Get OKRs, optionally filtered by owner."""
        if owner_id:
            rows = self._db.fetchall(
                """SELECT o.*, w.name as owner_name
                   FROM okrs o
                   JOIN workers w ON o.owner_worker_id = w.id
                   WHERE o.owner_worker_id = ?
                   ORDER BY o.parent_okr_id NULLS FIRST, o.created_at""",
                (owner_id,),
            )
        else:
            rows = self._db.fetchall(
                """SELECT o.*, w.name as owner_name
                   FROM okrs o
                   JOIN workers w ON o.owner_worker_id = w.id
                   ORDER BY o.parent_okr_id NULLS FIRST, o.created_at"""
            )

        return [
            OKRInfo(
                id=row["id"],
                title=row["title"],
                description=row["description"],
                owner_name=row["owner_name"],
                owner_id=row["owner_worker_id"],
                status=row["status"],
                parent_id=row["parent_okr_id"],
                key_results=self._parse_key_results(row["key_results"]),
                due_date=parse_datetime(row["due_date"]),
                children_count=self._count_child_okrs(row["id"]),
            )
            for row in rows
        ]

    def get_current_briefing(self) -> Optional[str]:
        """Get current CEO briefing from config file."""
        briefing_path = self._org_path / "config" / "ceo_briefing.md"
        if briefing_path.exists():
            return briefing_path.read_text()
        return None

    def _parse_key_results(self, kr_json: Optional[str]) -> list[dict[str, Any]]:
        if not kr_json:
            return []
        try:
            return json.loads(kr_json)
        except (json.JSONDecodeError, TypeError):
            return []

    def _count_child_okrs(self, okr_id: str) -> int:
        row = self._db.fetchone(
            "SELECT COUNT(*) as count FROM okrs WHERE parent_okr_id = ?",
            (okr_id,),
        )
        return row["count"] if row else 0
