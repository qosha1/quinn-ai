"""
Event system for QuinnAI CLI.

Provides a central event bus for system-wide state change notifications,
with database persistence for audit trail and recovery.
"""

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Iterator, Optional

from .db import Database


class EventType(Enum):
    """All event types in the QuinnAI system."""

    # Worker events
    WORKER_HIRED = "worker.hired"
    WORKER_FIRED = "worker.fired"
    WORKER_PROMOTED = "worker.promoted"
    WORKER_STARTED = "worker.started"
    WORKER_STOPPED = "worker.stopped"

    # Team events
    TEAM_CREATED = "team.created"
    TEAM_DELETED = "team.deleted"
    TEAM_MEMBER_ADDED = "team.member_added"
    TEAM_MEMBER_REMOVED = "team.member_removed"

    # Message events
    MESSAGE_SENT = "message.sent"
    MESSAGE_THREAD_STARTED = "message.thread_started"

    # Work events
    WORK_CREATED = "work.created"
    WORK_ASSIGNED = "work.assigned"
    WORK_STATUS_CHANGED = "work.status_changed"
    WORK_COMPLETED = "work.completed"

    # Offboarding events
    OFFBOARDING_ASK_CREATED = "offboarding.ask_created"
    OFFBOARDING_ASK_COMPLETED = "offboarding.ask_completed"
    OFFBOARDING_CLEANUP_DONE = "offboarding.cleanup_done"

    # OKR events
    OKR_CREATED = "okr.created"
    OKR_UPDATED = "okr.updated"
    OKR_COMPLETED = "okr.completed"


# Entity types for type safety
ENTITY_TYPES = frozenset({"worker", "team", "okr", "message", "work", "offboarding"})


@dataclass
class Event:
    """Represents a system event.

    Attributes:
        event_type: Type of the event
        entity_type: Type of entity (worker|team|okr|message|work)
        entity_id: ID of the affected entity
        payload: Event-specific data
        actor_id: ID of the worker/user who triggered the event (optional)
        created_at: When the event occurred
        id: Database ID (set after persistence)
    """

    event_type: EventType
    entity_type: str
    entity_id: str
    payload: dict[str, Any]
    actor_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    id: Optional[int] = None

    def __post_init__(self) -> None:
        """Validate event data after initialization."""
        if self.entity_type not in ENTITY_TYPES:
            raise ValueError(
                f"Invalid entity_type '{self.entity_type}'. "
                f"Must be one of: {', '.join(sorted(ENTITY_TYPES))}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary representation.

        Returns:
            Dictionary with event data
        """
        return {
            "id": self.id,
            "event_type": self.event_type.value,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "payload": self.payload,
            "actor_id": self.actor_id,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_row(cls, row: Any) -> "Event":
        """Create an Event from a database row.

        Args:
            row: Database row with event data

        Returns:
            Event instance
        """
        # Handle both dict-like and sqlite3.Row objects
        if hasattr(row, "keys"):
            data = dict(row)
        else:
            data = row

        # Parse payload from JSON
        payload = data["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)

        # Parse created_at timestamp
        created_at = data["created_at"]
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        return cls(
            id=data["id"],
            event_type=EventType(data["event_type"]),
            entity_type=data["entity_type"],
            entity_id=data["entity_id"],
            payload=payload,
            actor_id=data.get("actor_id"),
            created_at=created_at,
        )


# Type alias for event handlers
EventHandler = Callable[[Event], None]


class EventBus:
    """Central event bus for system-wide event publication and subscription.

    The EventBus provides:
    - In-memory pub/sub for immediate event handling
    - Database persistence for audit trail
    - Event replay for recovery scenarios

    Example:
        bus = EventBus(db)

        def on_worker_hired(event: Event):
            print(f"Welcome {event.entity_id}!")

        bus.subscribe(EventType.WORKER_HIRED, on_worker_hired)
        bus.publish(
            event_type=EventType.WORKER_HIRED,
            entity_type="worker",
            entity_id="worker-123",
            payload={"name": "Alice", "role": "engineer"},
            actor_id="ceo-001"
        )
    """

    def __init__(self, db: Database) -> None:
        """Initialize the event bus.

        Args:
            db: Database instance for event persistence
        """
        self._db = db
        self._handlers: dict[EventType, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Subscribe to events of a specific type.

        Args:
            event_type: Type of events to subscribe to
            handler: Callback function to invoke when event occurs

        Raises:
            TypeError: If handler is not callable
        """
        if not callable(handler):
            raise TypeError(f"Handler must be callable, got {type(handler)}")
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Unsubscribe from events of a specific type.

        Args:
            event_type: Type of events to unsubscribe from
            handler: Handler to remove

        Note:
            Does nothing if handler was not subscribed.
        """
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    def publish(
        self,
        event_type: EventType,
        entity_type: str,
        entity_id: str,
        payload: dict[str, Any],
        actor_id: Optional[str] = None,
    ) -> Event:
        """Publish an event to all subscribers.

        The event is first persisted to the database, then all registered
        handlers are invoked synchronously.

        Args:
            event_type: Type of event
            entity_type: Type of entity (worker|team|okr|message|work)
            entity_id: ID of the affected entity
            payload: Event-specific data
            actor_id: ID of the actor who triggered the event

        Returns:
            The persisted Event instance

        Raises:
            ValueError: If entity_type is invalid
        """
        # Create event
        event = Event(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
            actor_id=actor_id,
        )

        # Persist to database
        event = self._persist_event(event)

        # Notify handlers
        self._notify_handlers(event)

        return event

    def replay(self, since: datetime) -> Iterator[Event]:
        """Replay events since a timestamp.

        Useful for recovery scenarios where handlers need to catch up
        on events that occurred while they were offline.

        Args:
            since: Timestamp to replay from (exclusive)

        Yields:
            Events in chronological order
        """
        rows = self._db.fetchall(
            """
            SELECT id, event_type, entity_type, entity_id, payload, actor_id,
                   CAST(created_at AS TEXT) as created_at
            FROM events
            WHERE created_at > ?
            ORDER BY created_at ASC, id ASC
            """,
            (since.isoformat(),),
        )
        for row in rows:
            yield Event.from_row(row)

    def get_events_for_entity(
        self,
        entity_type: str,
        entity_id: str,
        limit: int = 100,
    ) -> list[Event]:
        """Get all events for a specific entity.

        Args:
            entity_type: Type of entity
            entity_id: ID of the entity
            limit: Maximum number of events to return

        Returns:
            List of events in reverse chronological order
        """
        rows = self._db.fetchall(
            """
            SELECT id, event_type, entity_type, entity_id, payload, actor_id,
                   CAST(created_at AS TEXT) as created_at
            FROM events
            WHERE entity_type = ? AND entity_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (entity_type, entity_id, limit),
        )
        return [Event.from_row(row) for row in rows]

    def get_events_by_type(
        self,
        event_type: EventType,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[Event]:
        """Get events of a specific type.

        Args:
            event_type: Type of events to retrieve
            since: Optional timestamp filter (exclusive)
            limit: Maximum number of events to return

        Returns:
            List of events in reverse chronological order
        """
        if since:
            rows = self._db.fetchall(
                """
                SELECT id, event_type, entity_type, entity_id, payload, actor_id,
                       CAST(created_at AS TEXT) as created_at
                FROM events
                WHERE event_type = ? AND created_at > ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (event_type.value, since.isoformat(), limit),
            )
        else:
            rows = self._db.fetchall(
                """
                SELECT id, event_type, entity_type, entity_id, payload, actor_id,
                       CAST(created_at AS TEXT) as created_at
                FROM events
                WHERE event_type = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (event_type.value, limit),
            )
        return [Event.from_row(row) for row in rows]

    def get_events_by_actor(
        self,
        actor_id: str,
        limit: int = 100,
    ) -> list[Event]:
        """Get events triggered by a specific actor.

        Args:
            actor_id: ID of the actor
            limit: Maximum number of events to return

        Returns:
            List of events in reverse chronological order
        """
        rows = self._db.fetchall(
            """
            SELECT id, event_type, entity_type, entity_id, payload, actor_id,
                   CAST(created_at AS TEXT) as created_at
            FROM events
            WHERE actor_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (actor_id, limit),
        )
        return [Event.from_row(row) for row in rows]

    def count_events(
        self,
        event_type: Optional[EventType] = None,
        since: Optional[datetime] = None,
    ) -> int:
        """Count events matching criteria.

        Args:
            event_type: Optional type filter
            since: Optional timestamp filter (exclusive)

        Returns:
            Number of matching events
        """
        conditions = []
        params: list[Any] = []

        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type.value)

        if since:
            conditions.append("created_at > ?")
            params.append(since.isoformat())

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        row = self._db.fetchone(
            f"SELECT COUNT(*) as count FROM events {where_clause}",
            tuple(params),
        )
        return row["count"] if row else 0

    def clear_handlers(self) -> None:
        """Clear all registered handlers.

        Useful for testing or resetting the event bus.
        """
        self._handlers.clear()

    def _persist_event(self, event: Event) -> Event:
        """Persist an event to the database.

        Args:
            event: Event to persist

        Returns:
            Event with id set from database
        """
        with self._db.transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO events (event_type, entity_type, entity_id, payload, actor_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_type.value,
                    event.entity_type,
                    event.entity_id,
                    json.dumps(event.payload),
                    event.actor_id,
                    event.created_at.isoformat(),
                ),
            )
            event.id = cursor.lastrowid
        return event

    def _notify_handlers(self, event: Event) -> None:
        """Notify all handlers subscribed to an event type.

        Args:
            event: Event to notify about
        """
        for handler in self._handlers[event.event_type]:
            try:
                handler(event)
            except Exception:
                # Intentionally swallowed: ensure all handlers get called even if one fails.
                # Handler errors should not break the event notification chain.
                pass


# =============================================================================
# Module-Level Convenience Functions
# =============================================================================

# Event type constants for easy import
WORKER_HIRED = EventType.WORKER_HIRED
WORKER_FIRED = EventType.WORKER_FIRED
WORKER_PROMOTED = EventType.WORKER_PROMOTED
WORKER_STARTED = EventType.WORKER_STARTED
WORKER_STOPPED = EventType.WORKER_STOPPED

TEAM_CREATED = EventType.TEAM_CREATED
TEAM_DELETED = EventType.TEAM_DELETED
TEAM_MEMBER_ADDED = EventType.TEAM_MEMBER_ADDED
TEAM_MEMBER_REMOVED = EventType.TEAM_MEMBER_REMOVED

MESSAGE_SENT = EventType.MESSAGE_SENT
MESSAGE_THREAD_STARTED = EventType.MESSAGE_THREAD_STARTED

WORK_CREATED = EventType.WORK_CREATED
WORK_ASSIGNED = EventType.WORK_ASSIGNED
WORK_STATUS_CHANGED = EventType.WORK_STATUS_CHANGED
WORK_COMPLETED = EventType.WORK_COMPLETED

OKR_CREATED = EventType.OKR_CREATED
OKR_UPDATED = EventType.OKR_UPDATED
OKR_COMPLETED = EventType.OKR_COMPLETED

OFFBOARDING_ASK_CREATED = EventType.OFFBOARDING_ASK_CREATED
OFFBOARDING_ASK_COMPLETED = EventType.OFFBOARDING_ASK_COMPLETED
OFFBOARDING_CLEANUP_DONE = EventType.OFFBOARDING_CLEANUP_DONE


# Global event bus instance (set by init_event_bus)
_event_bus: Optional[EventBus] = None


def init_event_bus(db: Database) -> EventBus:
    """Initialize the global event bus.

    Args:
        db: Database instance for event persistence

    Returns:
        The initialized EventBus instance
    """
    global _event_bus
    _event_bus = EventBus(db)
    return _event_bus


def get_event_bus() -> Optional[EventBus]:
    """Get the global event bus instance.

    Returns:
        The global EventBus, or None if not initialized
    """
    return _event_bus


def publish(
    event_type: EventType,
    payload: dict[str, Any],
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    actor_id: Optional[str] = None,
) -> Optional[Event]:
    """Publish an event using the global event bus.

    Convenience function for publishing events without needing
    to manage the EventBus instance directly.

    Args:
        event_type: Type of event to publish
        payload: Event-specific data
        entity_type: Type of entity (inferred from event_type if not provided)
        entity_id: ID of the affected entity (from payload if not provided)
        actor_id: ID of the actor who triggered the event

    Returns:
        The published Event, or None if event bus not initialized
    """
    if _event_bus is None:
        return None

    # Infer entity_type from event_type if not provided
    if entity_type is None:
        event_prefix = event_type.value.split(".")[0]
        entity_type = event_prefix

    # Try to get entity_id from payload if not provided
    if entity_id is None:
        entity_id = payload.get("worker_id") or payload.get("id") or "unknown"

    return _event_bus.publish(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        actor_id=actor_id,
    )
