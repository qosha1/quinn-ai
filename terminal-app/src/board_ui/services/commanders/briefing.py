"""CEO briefing: send a high-priority message + update the briefing file."""

import uuid
from datetime import datetime

from ...logging_config import get_board_logger
from ._context import OrgContext

logger = get_board_logger(__name__)


class BriefingCommander:
    """Send and update the CEO briefing.

    Tries the cli.core helpers first (proper notification creation, IDs from
    generate_id) and falls back to direct SQL when running standalone without
    the CLI installed.
    """

    def __init__(self, ctx: OrgContext) -> None:
        self._ctx = ctx

    def send_ceo_briefing(self, briefing_content: str) -> bool:
        """Send briefing to CEO as priority-0 message + notification."""
        try:
            from cli.core.notifications import create_notification_bead
            from cli.core.queries import create_message, generate_id
        except ImportError:
            logger.warning(
                "CLI module not available; falling back to direct SQL for CEO briefing."
            )
            return self._send_fallback(briefing_content)

        try:
            ceo = self._ctx.get_ceo()
            if not ceo:
                return False

            channel_id = self._ctx.get_board_channel_id()
            if not channel_id:
                return False

            content = self._wrap_content(briefing_content)

            message = create_message(
                db=self._ctx.db,
                channel_id=channel_id,
                from_worker_id=ceo.id,
                content=content,
                priority=0,
                time_sensitivity="immediate",
                message_id=generate_id("msg"),
            )

            create_notification_bead(
                db=self._ctx.db,
                worker_id=ceo.id,
                message_id=message.id,
                channel_id=channel_id,
                priority=0,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send CEO briefing: {e}")
            return False

    def update_briefing(self, briefing_content: str) -> bool:
        """Write briefing to config/ceo_briefing.md and notify CEO."""
        try:
            config_path = self._ctx.org_path / "config" / "ceo_briefing.md"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(briefing_content)
            return self.send_ceo_briefing(briefing_content)
        except Exception as e:
            logger.error(f"Failed to update briefing: {e}")
            return False

    def _send_fallback(self, briefing_content: str) -> bool:
        try:
            ceo = self._ctx.get_ceo()
            if not ceo:
                return False

            channel_id = self._ctx.get_board_channel_id()
            if not channel_id:
                return False

            content = self._wrap_content(briefing_content)
            now = datetime.now()
            message_id = f"msg-{str(uuid.uuid4())[:8]}"

            self._ctx.db.execute(
                """INSERT INTO messages
                   (id, channel_id, from_worker_id, content, priority, time_sensitivity, created_at)
                   VALUES (?, ?, ?, ?, 0, 'immediate', ?)""",
                (message_id, channel_id, ceo.id, content, now),
            )

            notification_id = f"nb-{str(uuid.uuid4())[:8]}"
            self._ctx.db.execute(
                """INSERT INTO notification_beads
                   (id, worker_id, message_id, channel_id, status, priority, created_at, read_at, expires_at)
                   VALUES (?, ?, ?, ?, 'pending', 0, ?, NULL, NULL)""",
                (notification_id, ceo.id, message_id, channel_id, now),
            )
            self._ctx.db.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to send CEO briefing (fallback): {e}")
            return False

    @staticmethod
    def _wrap_content(briefing_content: str) -> str:
        if "CEO Briefing" not in briefing_content:
            return f"# CEO Briefing\n\n{briefing_content}"
        return briefing_content
