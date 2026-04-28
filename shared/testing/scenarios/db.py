"""Read-only SQLite handle + lookup helpers for the scenario harness."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class DBHandle:
    """Wraps a read-only SQLite connection to the org's quinn.db."""

    def __init__(self, org_path: Path):
        db_path = org_path / "live" / "quinn.db"
        if not db_path.exists():
            raise FileNotFoundError(f"DB not found at {db_path} — was 'init' op run?")
        # Open read-only via URI to prevent accidental writes from assertions.
        self.conn = sqlite3.connect(
            f"file:{db_path}?mode=ro", uri=True
        )
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    # --- Helpers used by predicates ---

    def org_status(self) -> str | None:
        row = self.conn.execute(
            "SELECT status FROM org_state WHERE id='default'"
        ).fetchone()
        return row["status"] if row else None

    def find_worker_by_name(self, name: str) -> sqlite3.Row | None:
        """Case-insensitive lookup. 'ceo' alias resolves to the CEO worker."""
        if name.lower() == "ceo":
            row = self.conn.execute(
                "SELECT w.* FROM workers w "
                "JOIN org_state o ON o.ceo_worker_id = w.id "
                "WHERE o.id='default'"
            ).fetchone()
            if row:
                return row
        return self.conn.execute(
            "SELECT * FROM workers WHERE LOWER(name)=LOWER(?)", (name,)
        ).fetchone()

    def worker_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS c FROM workers").fetchone()
        return row["c"] if row else 0

    def subordinate_names(self, manager_name: str) -> list[str]:
        manager = self.find_worker_by_name(manager_name)
        if manager is None:
            return []
        rows = self.conn.execute(
            "SELECT name FROM workers WHERE manager_id=? ORDER BY name",
            (manager["id"],),
        ).fetchall()
        return [r["name"].lower() for r in rows]

    def org_chart_depth(self) -> int:
        """Max depth of org chart (CEO=1)."""
        rows = self.conn.execute("SELECT id, manager_id FROM workers").fetchall()
        if not rows:
            return 0
        # Build adjacency
        children: dict[str | None, list[str]] = {}
        for r in rows:
            children.setdefault(r["manager_id"], []).append(r["id"])
        # Find roots (manager_id is None)
        roots = children.get(None, [])
        if not roots:
            return 0

        def depth(node: str) -> int:
            ch = children.get(node, [])
            return 1 + max((depth(c) for c in ch), default=0)

        return max(depth(r) for r in roots)

    def runtime_status(self, worker_name: str) -> str | None:
        worker = self.find_worker_by_name(worker_name)
        if worker is None:
            return None
        row = self.conn.execute(
            "SELECT runtime_status FROM worker_state WHERE worker_id=?",
            (worker["id"],),
        ).fetchone()
        return row["runtime_status"] if row else None
