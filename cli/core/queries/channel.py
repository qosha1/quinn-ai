"""Channel and message queries."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from ..db import Database
from .common import generate_id

if TYPE_CHECKING:
    from .worker import Worker


@dataclass
class Channel:
    """Communication channel."""
    id: str
    name: str
    type: str
    team_id: Optional[str]
    created_at: datetime


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


def create_channel(
    db: Database,
    name: str,
    channel_type: str,
    team_id: Optional[str] = None,
    channel_id: Optional[str] = None,
) -> Channel:
    """Create a new channel.

    Args:
        db: Database instance
        name: Channel name
        channel_type: 'team', 'topic', or 'direct'
        team_id: Optional team ID for team channels
        channel_id: Optional custom ID

    Returns:
        Created Channel
    """
    if channel_id is None:
        channel_id = generate_id("chan")

    now = datetime.now()
    db.execute(
        "INSERT INTO channels (id, name, type, team_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (channel_id, name, channel_type, team_id, now)
    )
    db.connection.commit()

    return Channel(
        id=channel_id,
        name=name,
        type=channel_type,
        team_id=team_id,
        created_at=now,
    )


def create_direct_channel(
    db: Database,
    worker1_id: str,
    worker2_id: str,
    channel_id: Optional[str] = None,
) -> Channel:
    """Create a direct message channel between two workers.

    Creates a channel and subscribes both workers. Direct channels are
    restricted to only these two participants.

    Args:
        db: Database instance
        worker1_id: First worker ID
        worker2_id: Second worker ID
        channel_id: Optional custom channel ID

    Returns:
        Created Channel with both workers subscribed

    Raises:
        ChannelAccessError: If either worker doesn't exist
    """
    from .worker import get_worker

    # Validate both workers exist
    worker1 = get_worker(db, worker1_id)
    if not worker1:
        raise ChannelAccessError(worker1_id, "new", "Worker not found")

    worker2 = get_worker(db, worker2_id)
    if not worker2:
        raise ChannelAccessError(worker2_id, "new", "Worker not found")

    # Generate consistent channel name (sorted IDs for uniqueness)
    sorted_ids = sorted([worker1_id, worker2_id])
    channel_name = f"dm-{sorted_ids[0][:8]}-{sorted_ids[1][:8]}"

    # Check if channel already exists between these workers
    existing = get_channel_by_name(db, channel_name)
    if existing:
        return existing

    # Create the channel
    channel = create_channel(db, channel_name, "direct", channel_id=channel_id)

    # Subscribe both workers (skip_validation since we just validated)
    subscribe_to_channel(db, channel.id, worker1_id, skip_validation=True)
    subscribe_to_channel(db, channel.id, worker2_id, skip_validation=True)

    return channel


def get_or_create_direct_channel(
    db: Database,
    worker1_id: str,
    worker2_id: str,
) -> Channel:
    """Get an existing direct channel or create one between two workers.

    Args:
        db: Database instance
        worker1_id: First worker ID
        worker2_id: Second worker ID

    Returns:
        Direct channel between the two workers
    """
    # Generate consistent channel name
    sorted_ids = sorted([worker1_id, worker2_id])
    channel_name = f"dm-{sorted_ids[0][:8]}-{sorted_ids[1][:8]}"

    existing = get_channel_by_name(db, channel_name)
    if existing:
        return existing

    return create_direct_channel(db, worker1_id, worker2_id)


def get_channel(db: Database, channel_id: str) -> Optional[Channel]:
    """Get a channel by ID.

    Args:
        db: Database instance
        channel_id: Channel ID

    Returns:
        Channel or None
    """
    row = db.fetchone("SELECT * FROM channels WHERE id = ?", (channel_id,))
    if not row:
        return None

    return Channel(
        id=row["id"],
        name=row["name"],
        type=row["type"],
        team_id=row["team_id"],
        created_at=row["created_at"],
    )


def get_channel_by_name(db: Database, name: str) -> Optional[Channel]:
    """Get a channel by name.

    Args:
        db: Database instance
        name: Channel name (case-insensitive)

    Returns:
        Channel or None
    """
    row = db.fetchone(
        "SELECT * FROM channels WHERE LOWER(name) = LOWER(?)",
        (name,)
    )
    if not row:
        return None

    return Channel(
        id=row["id"],
        name=row["name"],
        type=row["type"],
        team_id=row["team_id"],
        created_at=row["created_at"],
    )


def create_default_org_channels(db: Database) -> list[Channel]:
    """Create default org-wide channels.

    Creates 'general' for org-wide announcements and 'escalations'
    for escalation messages. Skips channels that already exist.

    Args:
        db: Database instance

    Returns:
        List of created channels
    """
    default_channels = [
        ("general", "topic"),      # org-wide announcements
        ("escalations", "topic"),  # for escalation messages
    ]

    created = []
    for name, channel_type in default_channels:
        # Check if channel already exists
        existing = get_channel_by_name(db, name)
        if existing is None:
            channel = create_channel(db, name, channel_type)
            created.append(channel)

    return created


def can_subscribe_to_channel(db: Database, channel_id: str, worker_id: str) -> tuple[bool, str]:
    """Check if a worker can subscribe to a channel.

    Validates channel access based on channel type:
    - topic: Any worker can subscribe (org-wide channels)
    - team: Only team members can subscribe
    - direct: Only the two participants can subscribe

    Args:
        db: Database instance
        channel_id: Channel ID
        worker_id: Worker ID

    Returns:
        Tuple of (can_subscribe: bool, reason: str)
    """
    from .worker import get_worker

    channel = get_channel(db, channel_id)
    if not channel:
        return False, "Channel not found"

    worker = get_worker(db, worker_id)
    if not worker:
        return False, "Worker not found"

    if channel.type == "topic":
        # Topic channels are open to all workers in the org
        return True, "Topic channels are open to all"

    elif channel.type == "team":
        # Team channels require team membership
        if not channel.team_id:
            return False, "Team channel has no team_id"

        # Check if worker is in this team (primary team or team_members)
        if worker.team_id == channel.team_id:
            return True, "Worker is in the team"

        # Check team_members table for additional memberships
        membership = db.fetchone(
            "SELECT 1 FROM team_members WHERE team_id = ? AND worker_id = ?",
            (channel.team_id, worker_id)
        )
        if membership:
            return True, "Worker is a team member"

        return False, "Worker is not a member of the team"

    elif channel.type == "direct":
        # Direct channels: check if worker is one of the two participants
        # Direct channel names follow format "dm-{worker1_id}-{worker2_id}"
        # or we check existing subscribers (should be at most 2)
        subscribers = get_channel_subscribers(db, channel_id)

        if len(subscribers) < 2:
            # Channel not yet fully set up, check if this is an allowed participant
            # For direct channels, the creator and target should both be able to join
            # We allow subscription if there are fewer than 2 subscribers
            if len(subscribers) == 0:
                return True, "First participant in direct channel"
            elif len(subscribers) == 1 and worker_id not in subscribers:
                return True, "Second participant in direct channel"
            elif worker_id in subscribers:
                return True, "Already subscribed"

        # If already 2 subscribers, only they can access
        if worker_id in subscribers:
            return True, "Worker is a direct channel participant"

        return False, "Worker is not a participant in this direct channel"

    else:
        # Unknown channel type - deny by default
        return False, f"Unknown channel type: {channel.type}"


def subscribe_to_channel(
    db: Database,
    channel_id: str,
    worker_id: str,
    skip_validation: bool = False,
) -> None:
    """Subscribe a worker to a channel.

    Validates that the worker is allowed to subscribe based on channel type:
    - topic: Any worker can subscribe
    - team: Only team members can subscribe
    - direct: Only the two participants can subscribe

    Args:
        db: Database instance
        channel_id: Channel ID
        worker_id: Worker ID
        skip_validation: Skip permission checks (for internal/system use only)

    Raises:
        ChannelAccessError: If worker cannot subscribe to this channel
    """
    if not skip_validation:
        can_subscribe, reason = can_subscribe_to_channel(db, channel_id, worker_id)
        if not can_subscribe:
            raise ChannelAccessError(worker_id, channel_id, reason)

    now = datetime.now()
    db.execute(
        "INSERT OR IGNORE INTO channel_subscriptions (channel_id, worker_id, subscribed_at) VALUES (?, ?, ?)",
        (channel_id, worker_id, now)
    )
    db.connection.commit()


def is_subscribed_to_channel(db: Database, channel_id: str, worker_id: str) -> bool:
    """Check if a worker is subscribed to a channel.

    Args:
        db: Database instance
        channel_id: Channel ID
        worker_id: Worker ID

    Returns:
        True if subscribed, False otherwise
    """
    row = db.fetchone(
        "SELECT 1 FROM channel_subscriptions WHERE channel_id = ? AND worker_id = ?",
        (channel_id, worker_id)
    )
    return row is not None


def unsubscribe_from_channel(db: Database, channel_id: str, worker_id: str) -> None:
    """Unsubscribe a worker from a channel.

    Args:
        db: Database instance
        channel_id: Channel ID
        worker_id: Worker ID
    """
    db.execute(
        "DELETE FROM channel_subscriptions WHERE channel_id = ? AND worker_id = ?",
        (channel_id, worker_id)
    )
    db.connection.commit()


def get_channel_subscribers(db: Database, channel_id: str) -> list[str]:
    """Get subscriber worker IDs for a channel.

    Args:
        db: Database instance
        channel_id: Channel ID

    Returns:
        List of worker IDs
    """
    rows = db.fetchall(
        "SELECT worker_id FROM channel_subscriptions WHERE channel_id = ?",
        (channel_id,)
    )
    return [row["worker_id"] for row in rows]


def get_worker_channels(db: Database, worker_id: str) -> list[Channel]:
    """Get channels a worker is subscribed to.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        List of channels
    """
    rows = db.fetchall(
        """SELECT c.* FROM channels c
           JOIN channel_subscriptions cs ON c.id = cs.channel_id
           WHERE cs.worker_id = ?""",
        (worker_id,)
    )
    return [
        Channel(
            id=row["id"],
            name=row["name"],
            type=row["type"],
            team_id=row["team_id"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def unsubscribe_from_all_channels(db: Database, worker_id: str) -> int:
    """Unsubscribe a worker from all channels.

    Used during worker termination to clean up channel subscriptions.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        Number of channels unsubscribed from
    """
    cursor = db.execute(
        "DELETE FROM channel_subscriptions WHERE worker_id = ?",
        (worker_id,)
    )
    db.connection.commit()
    return cursor.rowcount


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
    from core.notifications import create_notifications_for_message

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
    "Channel",
    "Message",
    "ChannelAccessError",
    "create_channel",
    "create_direct_channel",
    "get_or_create_direct_channel",
    "get_channel",
    "get_channel_by_name",
    "create_default_org_channels",
    "can_subscribe_to_channel",
    "subscribe_to_channel",
    "is_subscribed_to_channel",
    "unsubscribe_from_channel",
    "get_channel_subscribers",
    "get_worker_channels",
    "unsubscribe_from_all_channels",
    "create_message",
    "create_message_with_notifications",
    "get_message",
    "get_channel_messages",
    "get_thread_messages",
    "search_messages",
    "add_message_ref",
    "get_message_refs",
]
