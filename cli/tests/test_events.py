"""
Unit tests for the event system.
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import pytest

from cli.core.db import init_database
from cli.core.events import (
    ENTITY_TYPES,
    Event,
    EventBus,
    EventType,
)


@pytest.fixture
def db_path():
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "live" / "quinn.db"


@pytest.fixture
def db(db_path):
    """Create and initialize a test database."""
    database = init_database(db_path)
    yield database
    database.close()


@pytest.fixture
def event_bus(db):
    """Create an EventBus with a test database."""
    return EventBus(db)


class TestEventType:
    """Test EventType enum."""

    def test_worker_events_exist(self):
        """Worker event types should be defined."""
        assert EventType.WORKER_HIRED.value == "worker.hired"
        assert EventType.WORKER_FIRED.value == "worker.fired"
        assert EventType.WORKER_PROMOTED.value == "worker.promoted"
        assert EventType.WORKER_STARTED.value == "worker.started"
        assert EventType.WORKER_STOPPED.value == "worker.stopped"

    def test_team_events_exist(self):
        """Team event types should be defined."""
        assert EventType.TEAM_CREATED.value == "team.created"
        assert EventType.TEAM_DELETED.value == "team.deleted"
        assert EventType.TEAM_MEMBER_ADDED.value == "team.member_added"
        assert EventType.TEAM_MEMBER_REMOVED.value == "team.member_removed"

    def test_message_events_exist(self):
        """Message event types should be defined."""
        assert EventType.MESSAGE_SENT.value == "message.sent"
        assert EventType.MESSAGE_THREAD_STARTED.value == "message.thread_started"

    def test_work_events_exist(self):
        """Work event types should be defined."""
        assert EventType.WORK_CREATED.value == "work.created"
        assert EventType.WORK_ASSIGNED.value == "work.assigned"
        assert EventType.WORK_STATUS_CHANGED.value == "work.status_changed"
        assert EventType.WORK_COMPLETED.value == "work.completed"

    def test_okr_events_exist(self):
        """OKR event types should be defined."""
        assert EventType.OKR_CREATED.value == "okr.created"
        assert EventType.OKR_UPDATED.value == "okr.updated"
        assert EventType.OKR_COMPLETED.value == "okr.completed"

    def test_all_event_values_unique(self):
        """All event type values should be unique."""
        values = [e.value for e in EventType]
        assert len(values) == len(set(values))


class TestEntityTypes:
    """Test entity type constants."""

    def test_entity_types_defined(self):
        """Expected entity types should be defined."""
        assert "worker" in ENTITY_TYPES
        assert "team" in ENTITY_TYPES
        assert "okr" in ENTITY_TYPES
        assert "message" in ENTITY_TYPES
        assert "work" in ENTITY_TYPES

    def test_entity_types_frozen(self):
        """Entity types should be immutable."""
        with pytest.raises(AttributeError):
            ENTITY_TYPES.add("invalid")


class TestEvent:
    """Test Event dataclass."""

    def test_create_event(self):
        """Should create event with all fields."""
        event = Event(
            event_type=EventType.WORKER_HIRED,
            entity_type="worker",
            entity_id="worker-123",
            payload={"name": "Alice", "role": "engineer"},
            actor_id="ceo-001",
        )
        assert event.event_type == EventType.WORKER_HIRED
        assert event.entity_type == "worker"
        assert event.entity_id == "worker-123"
        assert event.payload == {"name": "Alice", "role": "engineer"}
        assert event.actor_id == "ceo-001"
        assert event.created_at is not None
        assert event.id is None  # Not persisted yet

    def test_create_event_without_actor(self):
        """Should create event without actor_id."""
        event = Event(
            event_type=EventType.TEAM_CREATED,
            entity_type="team",
            entity_id="team-001",
            payload={"name": "Engineering"},
        )
        assert event.actor_id is None

    def test_create_event_invalid_entity_type(self):
        """Should raise ValueError for invalid entity type."""
        with pytest.raises(ValueError) as exc_info:
            Event(
                event_type=EventType.WORKER_HIRED,
                entity_type="invalid_type",
                entity_id="123",
                payload={},
            )
        assert "Invalid entity_type" in str(exc_info.value)

    def test_event_to_dict(self):
        """Should convert event to dictionary."""
        event = Event(
            event_type=EventType.WORKER_HIRED,
            entity_type="worker",
            entity_id="worker-123",
            payload={"name": "Alice"},
            actor_id="ceo-001",
        )
        result = event.to_dict()
        assert result["event_type"] == "worker.hired"
        assert result["entity_type"] == "worker"
        assert result["entity_id"] == "worker-123"
        assert result["payload"] == {"name": "Alice"}
        assert result["actor_id"] == "ceo-001"
        assert "created_at" in result

    def test_event_from_row(self):
        """Should create event from database row."""
        row = {
            "id": 1,
            "event_type": "worker.hired",
            "entity_type": "worker",
            "entity_id": "worker-123",
            "payload": '{"name": "Alice"}',
            "actor_id": "ceo-001",
            "created_at": "2024-01-15T10:30:00",
        }
        event = Event.from_row(row)
        assert event.id == 1
        assert event.event_type == EventType.WORKER_HIRED
        assert event.entity_type == "worker"
        assert event.entity_id == "worker-123"
        assert event.payload == {"name": "Alice"}
        assert event.actor_id == "ceo-001"
        assert event.created_at == datetime(2024, 1, 15, 10, 30, 0)


class TestEventBusSubscription:
    """Test EventBus subscription functionality."""

    def test_subscribe_handler(self, event_bus):
        """Should subscribe handler to event type."""
        calls: List[Event] = []

        def handler(event: Event):
            calls.append(event)

        event_bus.subscribe(EventType.WORKER_HIRED, handler)
        event_bus.publish(
            EventType.WORKER_HIRED,
            "worker",
            "worker-123",
            {"name": "Alice"},
        )
        assert len(calls) == 1
        assert calls[0].entity_id == "worker-123"

    def test_subscribe_multiple_handlers(self, event_bus):
        """Should call all subscribed handlers."""
        calls1: List[Event] = []
        calls2: List[Event] = []

        def handler1(event: Event):
            calls1.append(event)

        def handler2(event: Event):
            calls2.append(event)

        event_bus.subscribe(EventType.WORKER_HIRED, handler1)
        event_bus.subscribe(EventType.WORKER_HIRED, handler2)
        event_bus.publish(
            EventType.WORKER_HIRED,
            "worker",
            "worker-123",
            {"name": "Alice"},
        )
        assert len(calls1) == 1
        assert len(calls2) == 1

    def test_subscribe_different_event_types(self, event_bus):
        """Handlers should only receive subscribed event types."""
        hired_calls: List[Event] = []
        fired_calls: List[Event] = []

        def hired_handler(event: Event):
            hired_calls.append(event)

        def fired_handler(event: Event):
            fired_calls.append(event)

        event_bus.subscribe(EventType.WORKER_HIRED, hired_handler)
        event_bus.subscribe(EventType.WORKER_FIRED, fired_handler)

        event_bus.publish(
            EventType.WORKER_HIRED,
            "worker",
            "worker-123",
            {"name": "Alice"},
        )
        assert len(hired_calls) == 1
        assert len(fired_calls) == 0

    def test_subscribe_same_handler_twice(self, event_bus):
        """Should not add same handler twice."""
        calls: List[Event] = []

        def handler(event: Event):
            calls.append(event)

        event_bus.subscribe(EventType.WORKER_HIRED, handler)
        event_bus.subscribe(EventType.WORKER_HIRED, handler)

        event_bus.publish(
            EventType.WORKER_HIRED,
            "worker",
            "worker-123",
            {},
        )
        assert len(calls) == 1  # Called only once, not twice

    def test_subscribe_non_callable_raises(self, event_bus):
        """Should raise TypeError for non-callable handler."""
        with pytest.raises(TypeError):
            event_bus.subscribe(EventType.WORKER_HIRED, "not_callable")

    def test_unsubscribe_handler(self, event_bus):
        """Should unsubscribe handler from event type."""
        calls: List[Event] = []

        def handler(event: Event):
            calls.append(event)

        event_bus.subscribe(EventType.WORKER_HIRED, handler)
        event_bus.unsubscribe(EventType.WORKER_HIRED, handler)
        event_bus.publish(
            EventType.WORKER_HIRED,
            "worker",
            "worker-123",
            {},
        )
        assert len(calls) == 0

    def test_unsubscribe_nonexistent_handler(self, event_bus):
        """Should not raise when unsubscribing non-existent handler."""

        def handler(event: Event):
            pass

        # Should not raise
        event_bus.unsubscribe(EventType.WORKER_HIRED, handler)

    def test_clear_handlers(self, event_bus):
        """Should clear all handlers."""
        calls: List[Event] = []

        def handler(event: Event):
            calls.append(event)

        event_bus.subscribe(EventType.WORKER_HIRED, handler)
        event_bus.clear_handlers()
        event_bus.publish(
            EventType.WORKER_HIRED,
            "worker",
            "worker-123",
            {},
        )
        assert len(calls) == 0


class TestEventBusPublish:
    """Test EventBus publish functionality."""

    def test_publish_returns_event(self, event_bus):
        """Publish should return the persisted event."""
        event = event_bus.publish(
            EventType.WORKER_HIRED,
            "worker",
            "worker-123",
            {"name": "Alice"},
            actor_id="ceo-001",
        )
        assert event.id is not None
        assert event.event_type == EventType.WORKER_HIRED
        assert event.entity_type == "worker"
        assert event.entity_id == "worker-123"
        assert event.payload == {"name": "Alice"}
        assert event.actor_id == "ceo-001"

    def test_publish_persists_to_database(self, event_bus, db):
        """Events should be persisted to database."""
        event_bus.publish(
            EventType.WORKER_HIRED,
            "worker",
            "worker-123",
            {"name": "Alice"},
        )

        # Use CAST to avoid SQLite's timestamp parsing issues with ISO format
        row = db.fetchone(
            """
            SELECT id, event_type, entity_type, entity_id, payload, actor_id,
                   CAST(created_at AS TEXT) as created_at
            FROM events WHERE entity_id = ?
            """,
            ("worker-123",),
        )
        assert row is not None
        assert row["event_type"] == "worker.hired"
        assert row["entity_type"] == "worker"

    def test_publish_invalid_entity_type_raises(self, event_bus):
        """Publish should raise ValueError for invalid entity type."""
        with pytest.raises(ValueError):
            event_bus.publish(
                EventType.WORKER_HIRED,
                "invalid_type",
                "123",
                {},
            )

    def test_handler_exception_does_not_stop_others(self, event_bus):
        """Handler exceptions should not stop other handlers."""
        calls: List[Event] = []

        def failing_handler(event: Event):
            raise RuntimeError("Handler failed")

        def success_handler(event: Event):
            calls.append(event)

        event_bus.subscribe(EventType.WORKER_HIRED, failing_handler)
        event_bus.subscribe(EventType.WORKER_HIRED, success_handler)

        # Should not raise, and success_handler should still be called
        event_bus.publish(
            EventType.WORKER_HIRED,
            "worker",
            "worker-123",
            {},
        )
        assert len(calls) == 1


class TestEventBusReplay:
    """Test EventBus replay functionality."""

    def test_replay_events(self, event_bus):
        """Should replay events since timestamp."""
        base_time = datetime.now() - timedelta(hours=1)

        # Publish some events
        event_bus.publish(EventType.WORKER_HIRED, "worker", "w1", {})
        event_bus.publish(EventType.TEAM_CREATED, "team", "t1", {})
        event_bus.publish(EventType.WORKER_FIRED, "worker", "w2", {})

        events = list(event_bus.replay(since=base_time))
        assert len(events) == 3

    def test_replay_filters_by_timestamp(self, event_bus, db):
        """Should only return events after timestamp."""
        # Insert an old event directly
        old_time = datetime.now() - timedelta(days=1)
        db.execute(
            """
            INSERT INTO events (event_type, entity_type, entity_id, payload, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("worker.hired", "worker", "old-worker", "{}", old_time.isoformat()),
        )
        db.connection.commit()

        # Publish a new event
        event_bus.publish(EventType.WORKER_HIRED, "worker", "new-worker", {})

        # Replay since 1 hour ago should only get new event
        since = datetime.now() - timedelta(hours=1)
        events = list(event_bus.replay(since=since))
        assert len(events) == 1
        assert events[0].entity_id == "new-worker"

    def test_replay_empty_when_no_events(self, event_bus):
        """Should return empty iterator when no events."""
        events = list(event_bus.replay(since=datetime.now()))
        assert len(events) == 0


class TestEventBusQueries:
    """Test EventBus query methods."""

    def test_get_events_for_entity(self, event_bus):
        """Should get events for specific entity."""
        event_bus.publish(EventType.WORKER_HIRED, "worker", "w1", {})
        event_bus.publish(EventType.WORKER_PROMOTED, "worker", "w1", {})
        event_bus.publish(EventType.WORKER_HIRED, "worker", "w2", {})

        events = event_bus.get_events_for_entity("worker", "w1")
        assert len(events) == 2
        assert all(e.entity_id == "w1" for e in events)

    def test_get_events_for_entity_limit(self, event_bus):
        """Should respect limit parameter."""
        for i in range(10):
            event_bus.publish(EventType.WORKER_HIRED, "worker", "w1", {"i": i})

        events = event_bus.get_events_for_entity("worker", "w1", limit=5)
        assert len(events) == 5

    def test_get_events_by_type(self, event_bus):
        """Should get events by type."""
        event_bus.publish(EventType.WORKER_HIRED, "worker", "w1", {})
        event_bus.publish(EventType.TEAM_CREATED, "team", "t1", {})
        event_bus.publish(EventType.WORKER_HIRED, "worker", "w2", {})

        events = event_bus.get_events_by_type(EventType.WORKER_HIRED)
        assert len(events) == 2
        assert all(e.event_type == EventType.WORKER_HIRED for e in events)

    def test_get_events_by_type_with_since(self, event_bus, db):
        """Should filter events by type and since timestamp."""
        # Insert an old event
        old_time = datetime.now() - timedelta(days=1)
        db.execute(
            """
            INSERT INTO events (event_type, entity_type, entity_id, payload, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("worker.hired", "worker", "old-worker", "{}", old_time.isoformat()),
        )
        db.connection.commit()

        # Publish new event
        event_bus.publish(EventType.WORKER_HIRED, "worker", "new-worker", {})

        since = datetime.now() - timedelta(hours=1)
        events = event_bus.get_events_by_type(EventType.WORKER_HIRED, since=since)
        assert len(events) == 1
        assert events[0].entity_id == "new-worker"

    def test_get_events_by_actor(self, event_bus):
        """Should get events by actor."""
        event_bus.publish(
            EventType.WORKER_HIRED, "worker", "w1", {}, actor_id="ceo-001"
        )
        event_bus.publish(
            EventType.WORKER_HIRED, "worker", "w2", {}, actor_id="mgr-001"
        )
        event_bus.publish(
            EventType.TEAM_CREATED, "team", "t1", {}, actor_id="ceo-001"
        )

        events = event_bus.get_events_by_actor("ceo-001")
        assert len(events) == 2
        assert all(e.actor_id == "ceo-001" for e in events)

    def test_count_events(self, event_bus):
        """Should count all events."""
        event_bus.publish(EventType.WORKER_HIRED, "worker", "w1", {})
        event_bus.publish(EventType.TEAM_CREATED, "team", "t1", {})
        event_bus.publish(EventType.WORKER_FIRED, "worker", "w2", {})

        assert event_bus.count_events() == 3

    def test_count_events_by_type(self, event_bus):
        """Should count events filtered by type."""
        event_bus.publish(EventType.WORKER_HIRED, "worker", "w1", {})
        event_bus.publish(EventType.TEAM_CREATED, "team", "t1", {})
        event_bus.publish(EventType.WORKER_HIRED, "worker", "w2", {})

        assert event_bus.count_events(event_type=EventType.WORKER_HIRED) == 2
        assert event_bus.count_events(event_type=EventType.TEAM_CREATED) == 1

    def test_count_events_since(self, event_bus, db):
        """Should count events since timestamp."""
        # Insert an old event
        old_time = datetime.now() - timedelta(days=1)
        db.execute(
            """
            INSERT INTO events (event_type, entity_type, entity_id, payload, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("worker.hired", "worker", "old-worker", "{}", old_time.isoformat()),
        )
        db.connection.commit()

        # Publish new events
        event_bus.publish(EventType.WORKER_HIRED, "worker", "new-worker-1", {})
        event_bus.publish(EventType.WORKER_HIRED, "worker", "new-worker-2", {})

        since = datetime.now() - timedelta(hours=1)
        assert event_bus.count_events(since=since) == 2
        assert event_bus.count_events() == 3


class TestEventBusPersistence:
    """Test event persistence and database operations."""

    def test_events_table_created(self, db):
        """Events table should exist after db init."""
        result = db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
        )
        assert result is not None

    def test_events_have_autoincrement_id(self, event_bus):
        """Event IDs should auto-increment."""
        e1 = event_bus.publish(EventType.WORKER_HIRED, "worker", "w1", {})
        e2 = event_bus.publish(EventType.WORKER_HIRED, "worker", "w2", {})
        e3 = event_bus.publish(EventType.WORKER_HIRED, "worker", "w3", {})

        assert e1.id < e2.id < e3.id

    def test_complex_payload_persisted(self, event_bus):
        """Complex payloads should be persisted correctly."""
        payload = {
            "name": "Alice",
            "skills": {"coding": 80, "reasoning": 90},
            "metadata": {"created_by": "system", "version": 1},
            "tags": ["senior", "backend"],
        }
        event = event_bus.publish(
            EventType.WORKER_HIRED,
            "worker",
            "worker-123",
            payload,
        )

        # Retrieve from database
        events = event_bus.get_events_for_entity("worker", "worker-123")
        assert len(events) == 1
        assert events[0].payload == payload

    def test_null_actor_id_persisted(self, event_bus):
        """Null actor_id should be persisted correctly."""
        event = event_bus.publish(
            EventType.WORKER_HIRED,
            "worker",
            "worker-123",
            {},
        )

        events = event_bus.get_events_for_entity("worker", "worker-123")
        assert len(events) == 1
        assert events[0].actor_id is None


class TestEventTypes:
    """Test that all entity types work correctly with event system."""

    def test_worker_entity_type(self, event_bus):
        """Worker entity type should work."""
        event = event_bus.publish(
            EventType.WORKER_HIRED,
            "worker",
            "worker-123",
            {"name": "Alice"},
        )
        assert event.entity_type == "worker"

    def test_team_entity_type(self, event_bus):
        """Team entity type should work."""
        event = event_bus.publish(
            EventType.TEAM_CREATED,
            "team",
            "team-123",
            {"name": "Engineering"},
        )
        assert event.entity_type == "team"

    def test_okr_entity_type(self, event_bus):
        """OKR entity type should work."""
        event = event_bus.publish(
            EventType.OKR_CREATED,
            "okr",
            "okr-123",
            {"title": "Increase revenue"},
        )
        assert event.entity_type == "okr"

    def test_message_entity_type(self, event_bus):
        """Message entity type should work."""
        event = event_bus.publish(
            EventType.MESSAGE_SENT,
            "message",
            "msg-123",
            {"content": "Hello"},
        )
        assert event.entity_type == "message"

    def test_work_entity_type(self, event_bus):
        """Work entity type should work."""
        event = event_bus.publish(
            EventType.WORK_CREATED,
            "work",
            "work-123",
            {"title": "Implement feature X"},
        )
        assert event.entity_type == "work"
