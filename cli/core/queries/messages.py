"""Message queries and channel access errors."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..db import Database
from .common import generate_id


@dataclass
class Message:
    """Message in a channel."""
    id: str
    channel_id: str
    thread_id: Optional[str]
    parent_id: Optional[str]
    from_worker_id: str
    content: str
    priority: int
    time_sensitivity: str
    created_at: datetime


class ChannelAccessError(Exception):
    """Raised when a worker cannot access a channel."""

    def __init__(self, worker_id: str, channel_id: str, reason: str):
        self.worker_id = worker_id
        self.channel_id = channel_id
        self.reason = reason
        super().__init__(f"Worker '{worker_id}' cannot access channel '{channel_id}': {reason}")


def create_message(
    db: Database,
    channel_id: str,
    from_worker_id: str,
    content: str,
    thread_id: Optional[str] = None,
    parent_id: Optional[str] = None,
    priority: int = 2,
    time_sensitivity: str = "whenever",
    message_id: Optional[str] = None,
) -> Message:
    """Create a new message.

    Args:
        db: Database instance
        channel_id: Channel ID
        from_worker_id: Sender worker ID
        content: Message content
        thread_id: Optional thread ID
        parent_id: Optional parent message ID
        priority: Priority 0-4 (default 2)
        time_sensitivity: Urgency level
        message_id: Optional custom ID

    Returns:
        Created Message
    """
    from ..constants import SIGNAL_STRENGTH_MESSAGE_SENT
    from .activity import record_activity_signal

    if message_id is None:
        message_id = generate_id("msg")

    now = datetime.now()
    db.execute(
        """INSERT INTO messages
           (id, channel_id, thread_id, parent_id, from_worker_id, content,
            priority, time_sensitivity, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (message_id, channel_id, thread_id, parent_id, from_worker_id,
         content, priority, time_sensitivity, now)
    )
    db.connection.commit()

    # Record activity signal for message sent
    record_activity_signal(
        db=db,
        worker_id=from_worker_id,
        activity_type="message_sent",
        signal_strength=SIGNAL_STRENGTH_MESSAGE_SENT,
        metadata={"channel_id": channel_id, "message_id": message_id},
    )

    return Message(
        id=message_id,
        channel_id=channel_id,
        thread_id=thread_id,
        parent_id=parent_id,
        from_worker_id=from_worker_id,
        content=content,
        priority=priority,
        time_sensitivity=time_sensitivity,
        created_at=now,
    )


def create_message_with_notifications(
    db: Database,
    channel_id: str,
    from_worker_id: str,
    content: str,
    thread_id: Optional[str] = None,
    parent_id: Optional[str] = None,
    priority: int = 2,
    time_sensitivity: str = "whenever",
    message_id: Optional[str] = None,
) -> Message:
    """Create a new message and notify all channel subscribers.

    This is the recommended way to send messages when you want subscribers
    to be notified. It creates the message and then creates notification
    beads for all channel subscribers (except the sender).

    Args:
        db: Database instance
        channel_id: Channel ID
        from_worker_id: Sender worker ID
        content: Message content
        thread_id: Optional thread ID
        parent_id: Optional parent message ID
        priority: Priority 0-4 (default 2)
        time_sensitivity: Urgency level
        message_id: Optional custom ID

    Returns:
        Created Message
    """
    # Import here to avoid circular imports
    from cli.core.notifications import create_notifications_for_message

    # Create the message first
    message = create_message(
        db=db,
        channel_id=channel_id,
        from_worker_id=from_worker_id,
        content=content,
        thread_id=thread_id,
        parent_id=parent_id,
        priority=priority,
        time_sensitivity=time_sensitivity,
        message_id=message_id,
    )

    # Create notifications for all subscribers
    create_notifications_for_message(
        db=db,
        message_id=message.id,
        channel_id=channel_id,
        from_worker_id=from_worker_id,
        priority=priority,
    )

    return message


def get_message(db: Database, message_id: str) -> Optional[Message]:
    """Get a message by ID.

    Args:
        db: Database instance
        message_id: Message ID

    Returns:
        Message or None
    """
    row = db.fetchone("SELECT * FROM messages WHERE id = ?", (message_id,))
    if not row:
        return None

    return Message(
        id=row["id"],
        channel_id=row["channel_id"],
        thread_id=row["thread_id"],
        parent_id=row["parent_id"],
        from_worker_id=row["from_worker_id"],
        content=row["content"],
        priority=row["priority"],
        time_sensitivity=row["time_sensitivity"],
        created_at=row["created_at"],
    )


def get_channel_messages(
    db: Database,
    channel_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[Message]:
    """Get messages in a channel.

    Args:
        db: Database instance
        channel_id: Channel ID
        limit: Max messages to return
        offset: Offset for pagination

    Returns:
        List of messages, newest first
    """
    rows = db.fetchall(
        """SELECT * FROM messages WHERE channel_id = ?
           ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (channel_id, limit, offset)
    )
    return [
        Message(
            id=row["id"],
            channel_id=row["channel_id"],
            thread_id=row["thread_id"],
            parent_id=row["parent_id"],
            from_worker_id=row["from_worker_id"],
            content=row["content"],
            priority=row["priority"],
            time_sensitivity=row["time_sensitivity"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_thread_messages(db: Database, thread_id: str) -> list[Message]:
    """Get all messages in a thread.

    Args:
        db: Database instance
        thread_id: Thread ID

    Returns:
        List of messages in thread order
    """
    rows = db.fetchall(
        "SELECT * FROM messages WHERE thread_id = ? ORDER BY created_at ASC",
        (thread_id,)
    )
    return [
        Message(
            id=row["id"],
            channel_id=row["channel_id"],
            thread_id=row["thread_id"],
            parent_id=row["parent_id"],
            from_worker_id=row["from_worker_id"],
            content=row["content"],
            priority=row["priority"],
            time_sensitivity=row["time_sensitivity"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def search_messages(
    db: Database,
    query: str,
    channel_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Message]:
    """Search messages using full-text search.

    Args:
        db: Database instance
        query: Search query (supports FTS5 syntax: AND, OR, NOT, phrases "like this")
        channel_id: Optional filter to specific channel
        limit: Max messages to return
        offset: Offset for pagination

    Returns:
        List of matching messages, ranked by relevance
    """
    if channel_id:
        rows = db.fetchall(
            """SELECT m.* FROM messages m
               JOIN messages_fts fts ON m.rowid = fts.rowid
               WHERE messages_fts MATCH ? AND m.channel_id = ?
               ORDER BY rank LIMIT ? OFFSET ?""",
            (query, channel_id, limit, offset)
        )
    else:
        rows = db.fetchall(
            """SELECT m.* FROM messages m
               JOIN messages_fts fts ON m.rowid = fts.rowid
               WHERE messages_fts MATCH ?
               ORDER BY rank LIMIT ? OFFSET ?""",
            (query, limit, offset)
        )

    return [
        Message(
            id=row["id"],
            channel_id=row["channel_id"],
            thread_id=row["thread_id"],
            parent_id=row["parent_id"],
            from_worker_id=row["from_worker_id"],
            content=row["content"],
            priority=row["priority"],
            time_sensitivity=row["time_sensitivity"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def add_message_ref(
    db: Database,
    message_id: str,
    ref_type: str,
    ref_id: str,
) -> None:
    """Add a reference from a message to a bead/ask/okr.

    Args:
        db: Database instance
        message_id: Message ID
        ref_type: Type of reference ('bead', 'ask', 'okr')
        ref_id: ID of referenced item
    """
    db.execute(
        "INSERT OR IGNORE INTO message_refs (message_id, ref_type, ref_id) VALUES (?, ?, ?)",
        (message_id, ref_type, ref_id)
    )
    db.connection.commit()


def get_message_refs(db: Database, message_id: str) -> list[tuple[str, str]]:
    """Get references from a message.

    Args:
        db: Database instance
        message_id: Message ID

    Returns:
        List of (ref_type, ref_id) tuples
    """
    rows = db.fetchall(
        "SELECT ref_type, ref_id FROM message_refs WHERE message_id = ?",
        (message_id,)
    )
    return [(row["ref_type"], row["ref_id"]) for row in rows]


__all__ = [
    "Message",
    "ChannelAccessError",
    "create_message",
    "create_message_with_notifications",
    "get_message",
    "get_channel_messages",
    "get_thread_messages",
    "search_messages",
    "add_message_ref",
    "get_message_refs",
]
