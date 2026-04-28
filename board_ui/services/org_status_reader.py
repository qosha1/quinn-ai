"""Peek at an org's status without holding a long-lived connection.

This is the discovery-time read: open quinn.db, grab status + counts, close.
Distinct from readers/org_state.py which assumes you already hold an open
connection and want richer typed state.
"""

import sqlite3
from pathlib import Path
from typing import Optional


def read_org_status(db_path: Path) -> tuple[str, Optional[str], int, int]:
    """Read org status from quinn.db with a short-lived sqlite connection.

    Returns:
        (status, ceo_worker_id, worker_count, active_session_count).
        On missing db: ("uninitialized", None, 0, 0).
        On sqlite error: ("error", None, 0, 0).
    """
    if not db_path.exists():
        return "uninitialized", None, 0, 0

    try:
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row

        cursor = conn.execute(
            "SELECT status, ceo_worker_id FROM org_state WHERE id = 'default'"
        )
        row = cursor.fetchone()

        if not row:
            conn.close()
            return "uninitialized", None, 0, 0

        status = row["status"]
        ceo_worker_id = row["ceo_worker_id"]

        cursor = conn.execute("SELECT COUNT(*) as count FROM workers")
        worker_count = cursor.fetchone()["count"]

        cursor = conn.execute(
            "SELECT COUNT(*) as count FROM sessions "
            "WHERE state IN ('starting', 'idle', 'running')"
        )
        active_session_count = cursor.fetchone()["count"]

        conn.close()
        return status, ceo_worker_id, worker_count, active_session_count

    except sqlite3.Error:
        return "error", None, 0, 0
