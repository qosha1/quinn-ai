"""Status-change poll cursor writes."""

from ...logging_config import get_board_logger
from ._context import OrgContext

logger = get_board_logger(__name__)


class CursorsCommander:
    """Write cursor positions for status-change polling clients."""

    def __init__(self, ctx: OrgContext) -> None:
        self._ctx = ctx

    def update_poll_cursor(self, client_id: str, last_change_id: int) -> None:
        """Upsert the poll cursor position for a client."""
        try:
            self._ctx.db.execute(
                """INSERT INTO status_change_cursors (client_id, last_change_id, updated_at)
                   VALUES (?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(client_id) DO UPDATE SET
                       last_change_id = excluded.last_change_id,
                       updated_at = excluded.updated_at""",
                (client_id, last_change_id),
            )
            self._ctx.db.connection.commit()
        except Exception as e:
            logger.debug(f"Error updating poll cursor: {e}")
