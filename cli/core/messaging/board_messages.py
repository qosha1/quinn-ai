"""Board message creation for escalations.

Implements the MessageCreator protocol to allow BoardNotifier to create
messages in board-channel without importing cli/ code directly.
"""

from pathlib import Path
from typing import Optional
import logging

from cli.core.db import Database
from cli.core.queries.channel import get_channel_by_name, create_message

logger = logging.getLogger(__name__)


class BoardMessageCreator:
    """Creates messages in board channels with automatic CEO notifications.

    Implements the MessageCreator protocol from shared/org/interfaces.
    """

    def __init__(self, db_path: Path | str):
        """Initialize with database path.

        Args:
            db_path: Path to org database (org_path/live/quinn.db)
        """
        self.db_path = Path(db_path) if isinstance(db_path, str) else db_path

    def create_board_message(
        self,
        channel_name: str,
        from_worker_id: str,
        content: str,
        priority: int,
        time_sensitivity: str,
    ) -> Optional[str]:
        """Create message in board channel with CEO notifications.

        Implementation details:
        - Opens database connection
        - Finds channel by name
        - Creates message with create_message_with_notifications()
        - Auto-creates notification beads for all subscribers (CEO)

        Args:
            channel_name: Name of channel (e.g., "board-channel")
            from_worker_id: ID of worker sending message
            content: Message content (markdown)
            priority: Message priority (0-4)
            time_sensitivity: When to deliver ("immediate", "hours", "days", "whenever")

        Returns:
            Message ID if successful, None if channel not found or error
        """
        db = None
        try:
            db = Database(self.db_path)

            # Find board channel
            channel = get_channel_by_name(db, channel_name)
            if not channel:
                logger.warning(
                    f"Board channel '{channel_name}' not found, skipping message creation"
                )
                return None

            # Create the message first
            message = create_message(
                db=db,
                channel_id=channel.id,
                from_worker_id=from_worker_id,
                content=content,
                priority=priority,
                time_sensitivity=time_sensitivity,
            )

            # Create notifications for all subscribers (CEO)
            # Import here to avoid circular dependencies
            # Use the SQL-based implementation from queries, not CLI-based utils
            from cli.core.queries.channel import get_channel_subscribers
            from cli.core.queries.notification import create_notification_bead

            subscribers = get_channel_subscribers(db, channel.id)
            for worker_id in subscribers:
                # Don't notify the sender
                if worker_id == from_worker_id:
                    continue

                try:
                    create_notification_bead(
                        db, worker_id, message.id, channel.id, priority
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to create notification for worker {worker_id}: {e}"
                    )

            logger.info(
                f"Created board message {message.id} from {from_worker_id} in {channel_name}"
            )
            return message.id

        except Exception as e:
            logger.error(f"Failed to create board message: {e}", exc_info=True)
            return None

        finally:
            if db:
                db.close()
