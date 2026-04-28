"""Read channels and messages."""

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ...interfaces.org_connection import Message
from ...logging_config import get_board_logger
from ._helpers import parse_datetime

logger = get_board_logger(__name__)


class MessageReader:
    """Read channels, messages, and unread state for the board inbox.

    Tries the configured board channel first, falls back to the legacy
    escalations channel for orgs that haven't migrated yet.
    """

    def __init__(
        self,
        db: Any,
        org_path: Path,
        board_channel: str,
        escalations_channel: str,
    ) -> None:
        self._db = db
        self._org_path = org_path
        self._board_channel = board_channel
        self._escalations_channel = escalations_channel

    def get_board_channel_id(self) -> Optional[str]:
        """Get board channel id, trying board-channel then escalations."""
        channel = self._db.fetchone(
            "SELECT id FROM channels WHERE name = ?", (self._board_channel,)
        )
        if channel:
            return channel["id"]

        channel = self._db.fetchone(
            "SELECT id FROM channels WHERE name = ?", (self._escalations_channel,)
        )
        return channel["id"] if channel else None

    def get_all_channels(self) -> list[dict[str, Any]]:
        """Get all channels with unread counts."""
        rows = self._db.fetchall(
            """SELECT c.id, c.name, c.type, c.team_id
               FROM channels c
               ORDER BY c.name"""
        )

        channels = []
        for row in rows:
            channel_id = row["id"]
            unread_row = self._db.fetchone(
                """SELECT COUNT(DISTINCT m.id) as count
                   FROM messages m
                   JOIN notification_beads nb ON nb.message_id = m.id
                   WHERE m.channel_id = ? AND nb.status = 'pending'""",
                (channel_id,),
            )
            unread_count = unread_row["count"] if unread_row else 0

            channels.append(
                {
                    "id": channel_id,
                    "name": row["name"],
                    "type": row["type"],
                    "team_id": row["team_id"],
                    "unread_count": unread_count,
                }
            )
        return channels

    def get_channel_messages(
        self,
        channel_id: str,
        unread_only: bool = False,
        limit: int = 100,
    ) -> list[Message]:
        """Get messages from a specific channel."""
        if unread_only:
            rows = self._db.fetchall(
                """SELECT DISTINCT m.*,
                          COALESCE(w.name, m.from_worker_id) as from_worker_name,
                          c.name as channel_name
                   FROM messages m
                   LEFT JOIN workers w ON m.from_worker_id = w.id
                   JOIN channels c ON m.channel_id = c.id
                   JOIN notification_beads nb ON nb.message_id = m.id
                   WHERE m.channel_id = ? AND nb.status = 'pending'
                   ORDER BY m.priority DESC, m.created_at DESC
                   LIMIT ?""",
                (channel_id, limit),
            )
        else:
            rows = self._db.fetchall(
                """SELECT m.*,
                          COALESCE(w.name, m.from_worker_id) as from_worker_name,
                          c.name as channel_name
                   FROM messages m
                   LEFT JOIN workers w ON m.from_worker_id = w.id
                   JOIN channels c ON m.channel_id = c.id
                   WHERE m.channel_id = ?
                   ORDER BY m.priority DESC, m.created_at DESC
                   LIMIT ?""",
                (channel_id, limit),
            )
        return [self._row_to_message(row) for row in rows]

    def get_board_messages(self, unread_only: bool = False) -> list[Message]:
        """Get messages escalated to the board (unbounded — no limit)."""
        channel_id = self.get_board_channel_id()
        if not channel_id:
            return []

        if unread_only:
            rows = self._db.fetchall(
                """SELECT DISTINCT m.*,
                          COALESCE(w.name, m.from_worker_id) as from_worker_name,
                          c.name as channel_name
                   FROM messages m
                   LEFT JOIN workers w ON m.from_worker_id = w.id
                   JOIN channels c ON m.channel_id = c.id
                   JOIN notification_beads nb ON nb.message_id = m.id
                   WHERE m.channel_id = ? AND nb.status = 'pending'
                   ORDER BY m.priority DESC, m.created_at DESC""",
                (channel_id,),
            )
        else:
            rows = self._db.fetchall(
                """SELECT m.*,
                          COALESCE(w.name, m.from_worker_id) as from_worker_name,
                          c.name as channel_name
                   FROM messages m
                   LEFT JOIN workers w ON m.from_worker_id = w.id
                   JOIN channels c ON m.channel_id = c.id
                   WHERE m.channel_id = ?
                   ORDER BY m.priority DESC, m.created_at DESC""",
                (channel_id,),
            )
        return [self._row_to_message(row) for row in rows]

    def get_unread_count(self) -> int:
        """Get count of unread board messages."""
        channel_id = self.get_board_channel_id()
        if not channel_id:
            return 0

        count_row = self._db.fetchone(
            """SELECT COUNT(DISTINCT m.id) as count
               FROM messages m
               JOIN notification_beads nb ON nb.message_id = m.id
               WHERE m.channel_id = ? AND nb.status = 'pending'""",
            (channel_id,),
        )
        return count_row["count"] if count_row else 0

    def mark_message_read(self, message_id: str) -> bool:
        """Close all pending notification beads for a message."""
        try:
            now = datetime.now()
            self._db.execute(
                """UPDATE notification_beads
                   SET status = 'read', read_at = ?
                   WHERE message_id = ? AND status = 'pending'""",
                (now, message_id),
            )
            self._db.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to mark message {message_id} as read: {e}")
            return False

    def _row_to_message(self, row: Any) -> Message:
        return Message(
            id=row["id"],
            from_worker_id=row["from_worker_id"],
            from_worker_name=row["from_worker_name"],
            channel_name=row["channel_name"],
            content=row["content"],
            priority=row["priority"],
            created_at=parse_datetime(row["created_at"]) or datetime.now(),
            is_read=self._is_message_read(row["id"]),
            requires_response=row["priority"] >= 3,
        )

    def _is_message_read(self, message_id: str) -> bool:
        row = self._db.fetchone(
            """SELECT COUNT(*) as count FROM notification_beads
               WHERE message_id = ? AND status = 'pending'""",
            (message_id,),
        )
        return row["count"] == 0 if row else True
