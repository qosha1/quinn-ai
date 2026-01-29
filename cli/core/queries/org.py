"""Organization state queries."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..constants import DEFAULT_ORG_ID
from ..db import Database
from shared.enums import OrgStatus


@dataclass
class OrgState:
    """Organization state."""
    id: str
    name: str
    status: str
    ceo_worker_id: Optional[str]
    started_at: Optional[datetime]
    stopped_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


def get_org_state(db: Database) -> Optional[OrgState]:
    """Get the current org state.

    Args:
        db: Database instance

    Returns:
        OrgState or None if not initialized
    """
    row = db.fetchone(f"SELECT * FROM org_state WHERE id = '{DEFAULT_ORG_ID}'")
    if not row:
        return None

    return OrgState(
        id=row["id"],
        name=row["name"] if row["name"] else "My Organization",
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
    if status == OrgStatus.RUNNING.value:
        db.execute(
            """UPDATE org_state SET status = ?, ceo_worker_id = ?,
               started_at = ?, updated_at = ? WHERE id = ?""",
            (status, ceo_worker_id, now, now, DEFAULT_ORG_ID)
        )
    elif status == OrgStatus.STOPPED.value:
        db.execute(
            """UPDATE org_state SET status = ?, stopped_at = ?,
               updated_at = ? WHERE id = ?""",
            (status, now, now, DEFAULT_ORG_ID)
        )
    else:
        db.execute(
            """UPDATE org_state SET status = ?, ceo_worker_id = ?,
               updated_at = ? WHERE id = ?""",
            (status, ceo_worker_id, now, DEFAULT_ORG_ID)
        )
    db.connection.commit()


__all__ = [
    "OrgState",
    "get_org_state",
    "update_org_status",
]
