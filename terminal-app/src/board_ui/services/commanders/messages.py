"""Board → worker message responses."""

import uuid
from datetime import datetime

from ...logging_config import get_board_logger
from ._context import OrgContext

logger = get_board_logger(__name__)


class MessagesCommander:
    """Send the board's reply to a worker message and mark the original read."""

    def __init__(self, ctx: OrgContext) -> None:
        self._ctx = ctx

    def send_board_response(self, message_id: str, response: str) -> bool:
        """Reply to a board message in-thread as the CEO."""
        msg_row = self._ctx.db.fetchone(
            "SELECT channel_id, thread_id FROM messages WHERE id = ?",
            (message_id,),
        )
        if not msg_row:
            return False

        channel_id = msg_row["channel_id"]
        thread_id = msg_row["thread_id"] or message_id

        ceo = self._ctx.get_ceo()
        if not ceo:
            logger.warning("Cannot send board response: CEO worker not found")
            return False

        response_id = f"msg-{str(uuid.uuid4())[:8]}"
        now = datetime.now()

        try:
            self._ctx.db.execute(
                """INSERT INTO messages
                   (id, channel_id, thread_id, parent_id, from_worker_id, content,
                    priority, time_sensitivity, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 3, 'immediate', ?)""",
                (response_id, channel_id, thread_id, message_id, ceo.id, response, now),
            )
            self._ctx.db.connection.commit()

            self._ctx.mark_message_read(message_id)
            return True
        except Exception as e:
            logger.error(f"Failed to send board response to message {message_id}: {e}")
            return False
