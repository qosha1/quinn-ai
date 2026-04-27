"""Read status_changes table for cursor-based polling."""

from typing import Any

from ...logging_config import get_board_logger

logger = get_board_logger(__name__)


class ChangeCursorReader:
    """Read the status_changes table for cursor-based change polling."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def get_status_changes_since_cursor(self, cursor_id: int) -> list[dict]:
        """Get status changes since a given cursor position."""
        try:
            rows = self._db.fetchall(
                """SELECT id, entity_type, entity_id, old_status, new_status, changed_at
                   FROM status_changes
                   WHERE id > ?
                   ORDER BY id ASC""",
                (cursor_id,),
            )
            return [
                {
                    "id": row["id"],
                    "entity_type": row["entity_type"],
                    "entity_id": row["entity_id"],
                    "old_status": row["old_status"],
                    "new_status": row["new_status"],
                    "changed_at": row["changed_at"],
                }
                for row in rows
            ]
        except Exception as e:
            logger.debug(f"Error fetching status changes: {e}")
            return []

    def get_last_status_change_id(self) -> int:
        """Get the latest status change ID."""
        try:
            row = self._db.fetchone("SELECT MAX(id) as max_id FROM status_changes")
            if row and row["max_id"] is not None:
                return int(row["max_id"])
            return 0
        except Exception as e:
            logger.debug(f"Error fetching last status change ID: {e}")
            return 0

    def has_pending_changes(self, cursor_id: int) -> bool:
        """Check if there are pending status changes since cursor."""
        try:
            row = self._db.fetchone(
                "SELECT 1 FROM status_changes WHERE id > ? LIMIT 1",
                (cursor_id,),
            )
            return row is not None
        except Exception as e:
            logger.debug(f"Error checking for pending changes: {e}")
            return False
