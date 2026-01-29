"""Event system queries for database persistence."""

from datetime import datetime
from typing import Any, Optional

from ..db import Database


def create_event(
    db: Database,
    event_type: str,
    entity_type: str,
    entity_id: str,
    payload: str,
    actor_id: Optional[str],
    created_at: str,
) -> int:
    """Create an event record in the database.

    Args:
        db: Database instance
        event_type: Event type string
        entity_type: Entity type string
        entity_id: Entity ID
        payload: JSON payload string
        actor_id: Optional actor ID
        created_at: ISO format timestamp

    Returns:
        Event ID (lastrowid)
    """
    with db.transaction() as cursor:
        cursor.execute(
            """
            INSERT INTO events (event_type, entity_type, entity_id, payload, actor_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_type, entity_type, entity_id, payload, actor_id, created_at),
        )
        return cursor.lastrowid


def get_events_since(
    db: Database,
    since: str,
) -> list[dict]:
    """Get all events since a timestamp.

    Args:
        db: Database instance
        since: ISO format timestamp

    Returns:
        List of event rows as dicts
    """
    rows = db.fetchall(
        """
        SELECT id, event_type, entity_type, entity_id, payload, actor_id,
               CAST(created_at AS TEXT) as created_at
        FROM events
        WHERE created_at > ?
        ORDER BY created_at ASC, id ASC
        """,
        (since,),
    )
    return [dict(row) for row in rows]


def get_events_for_entity(
    db: Database,
    entity_type: str,
    entity_id: str,
    limit: int = 100,
) -> list[dict]:
    """Get all events for a specific entity.

    Args:
        db: Database instance
        entity_type: Entity type
        entity_id: Entity ID
        limit: Maximum events to return

    Returns:
        List of event rows as dicts, newest first
    """
    rows = db.fetchall(
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
    return [dict(row) for row in rows]


def get_events_by_type(
    db: Database,
    event_type: str,
    since: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """Get events of a specific type.

    Args:
        db: Database instance
        event_type: Event type to filter by
        since: Optional ISO timestamp filter
        limit: Maximum events to return

    Returns:
        List of event rows as dicts, newest first
    """
    if since:
        rows = db.fetchall(
            """
            SELECT id, event_type, entity_type, entity_id, payload, actor_id,
                   CAST(created_at AS TEXT) as created_at
            FROM events
            WHERE event_type = ? AND created_at > ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (event_type, since, limit),
        )
    else:
        rows = db.fetchall(
            """
            SELECT id, event_type, entity_type, entity_id, payload, actor_id,
                   CAST(created_at AS TEXT) as created_at
            FROM events
            WHERE event_type = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (event_type, limit),
        )
    return [dict(row) for row in rows]


def get_events_by_actor(
    db: Database,
    actor_id: str,
    limit: int = 100,
) -> list[dict]:
    """Get events triggered by a specific actor.

    Args:
        db: Database instance
        actor_id: Actor ID
        limit: Maximum events to return

    Returns:
        List of event rows as dicts, newest first
    """
    rows = db.fetchall(
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
    return [dict(row) for row in rows]


def count_events(
    db: Database,
    event_type: Optional[str] = None,
    since: Optional[str] = None,
) -> int:
    """Count events matching criteria.

    Args:
        db: Database instance
        event_type: Optional event type filter
        since: Optional ISO timestamp filter

    Returns:
        Number of matching events
    """
    conditions = []
    params: list[Any] = []

    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)

    if since:
        conditions.append("created_at > ?")
        params.append(since)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    row = db.fetchone(
        f"SELECT COUNT(*) as count FROM events {where_clause}",
        tuple(params),
    )
    return row["count"] if row else 0


__all__ = [
    "create_event",
    "get_events_since",
    "get_events_for_entity",
    "get_events_by_type",
    "get_events_by_actor",
    "count_events",
]
