"""
Unit tests for notification bead operations.

Tests notification creation, status transitions, cleanup, and integration
with the message system.
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from cli.core.db import init_database, Database
from cli.core.queries import (
    # Teams & Workers (for setup)
    create_team,
    create_worker,
    # Channels
    create_channel,
    subscribe_to_channel,
    # Messages
    create_message,
    create_message_with_notifications,
)
from cli.core.notifications import (
    NotificationBead,
    create_notification_bead,
    create_notifications_for_message,
    get_notification_bead,
    get_worker_notifications,
    get_pending_notifications,
    count_pending_notifications,
    mark_notification_read,
    mark_notification_actioned,
    close_notification,
    close_notifications_for_message,
    acknowledge_notification,
    cleanup_old_notifications,
    cleanup_expired_notifications,
    cleanup_orphaned_notifications,
    run_notification_cleanup,
    DEFAULT_RETENTION_DAYS,
)
from cli.core.queries import get_message


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
def team(db):
    """Create a test team."""
    return create_team(db, "Engineering")


@pytest.fixture
def worker(db, team):
    """Create a test worker."""
    return create_worker(db, "Alice", "Developer", team.id, 50)


@pytest.fixture
def worker2(db, team):
    """Create a second test worker."""
    return create_worker(db, "Bob", "Developer", team.id, 50)


@pytest.fixture
def worker3(db, team):
    """Create a third test worker."""
    return create_worker(db, "Charlie", "Developer", team.id, 50)


@pytest.fixture
def channel(db):
    """Create a test channel."""
    return create_channel(db, "general", "topic")


class TestNotificationBeadCreation:
    """Test notification bead creation operations."""

    def test_create_notification_bead(self, db, channel, worker, worker2):
        """Should create a notification bead."""
        msg = create_message(db, channel.id, worker.id, "Hello")
        notif = create_notification_bead(db, worker2.id, msg.id, channel.id)

        assert notif.id.startswith("notif-")
        assert notif.worker_id == worker2.id
        assert notif.message_id == msg.id
        assert notif.channel_id == channel.id
        assert notif.status == "pending"
        assert notif.priority == 2  # default
        assert notif.read_at is None
        assert notif.actioned_at is None
        assert notif.closed_at is None

    def test_create_notification_with_custom_id(self, db, channel, worker, worker2):
        """Should allow custom notification ID."""
        msg = create_message(db, channel.id, worker.id, "Hello")
        notif = create_notification_bead(
            db, worker2.id, msg.id, channel.id,
            notification_id="notif-custom-123"
        )
        assert notif.id == "notif-custom-123"

    def test_create_notification_with_priority(self, db, channel, worker, worker2):
        """Should create notification with custom priority."""
        msg = create_message(db, channel.id, worker.id, "Urgent!")
        notif = create_notification_bead(db, worker2.id, msg.id, channel.id, priority=0)
        assert notif.priority == 0

    def test_duplicate_notification_fails(self, db, channel, worker, worker2):
        """Should not allow duplicate notifications for same worker+message."""
        msg = create_message(db, channel.id, worker.id, "Hello")
        create_notification_bead(db, worker2.id, msg.id, channel.id)

        # Second notification for same worker+message should fail
        with pytest.raises(Exception):
            create_notification_bead(db, worker2.id, msg.id, channel.id)


class TestNotificationsForMessage:
    """Test batch notification creation for messages."""

    def test_create_notifications_for_subscribers(self, db, channel, worker, worker2, worker3):
        """Should create notifications for all subscribers except sender."""
        # Subscribe all workers to channel
        subscribe_to_channel(db, channel.id, worker.id)
        subscribe_to_channel(db, channel.id, worker2.id)
        subscribe_to_channel(db, channel.id, worker3.id)

        # Worker sends message
        msg = create_message(db, channel.id, worker.id, "Hello team!")
        notifications = create_notifications_for_message(
            db, msg.id, channel.id, worker.id
        )

        # Should notify worker2 and worker3, not the sender
        assert len(notifications) == 2
        notified_workers = {n.worker_id for n in notifications}
        assert worker.id not in notified_workers
        assert worker2.id in notified_workers
        assert worker3.id in notified_workers

    def test_create_notifications_empty_channel(self, db, channel, worker):
        """Should handle channel with no other subscribers."""
        subscribe_to_channel(db, channel.id, worker.id)

        msg = create_message(db, channel.id, worker.id, "Echo...")
        notifications = create_notifications_for_message(
            db, msg.id, channel.id, worker.id
        )

        assert len(notifications) == 0

    def test_create_notifications_inherits_priority(self, db, channel, worker, worker2):
        """Should pass message priority to notifications."""
        subscribe_to_channel(db, channel.id, worker.id)
        subscribe_to_channel(db, channel.id, worker2.id)

        msg = create_message(db, channel.id, worker.id, "Urgent!", priority=0)
        notifications = create_notifications_for_message(
            db, msg.id, channel.id, worker.id, priority=0
        )

        assert len(notifications) == 1
        assert notifications[0].priority == 0


class TestCreateMessageWithNotifications:
    """Test integrated message + notification creation."""

    def test_creates_message_and_notifications(self, db, channel, worker, worker2, worker3):
        """Should create message and notifications in one call."""
        subscribe_to_channel(db, channel.id, worker.id)
        subscribe_to_channel(db, channel.id, worker2.id)
        subscribe_to_channel(db, channel.id, worker3.id)

        msg = create_message_with_notifications(
            db, channel.id, worker.id, "Hello everyone!"
        )

        # Check message created
        assert msg.id.startswith("msg-")
        assert msg.content == "Hello everyone!"

        # Check notifications created for other subscribers
        notifs_worker2 = get_pending_notifications(db, worker2.id)
        notifs_worker3 = get_pending_notifications(db, worker3.id)
        notifs_sender = get_pending_notifications(db, worker.id)

        assert len(notifs_worker2) == 1
        assert len(notifs_worker3) == 1
        assert len(notifs_sender) == 0  # Sender not notified


class TestNotificationRetrieval:
    """Test notification retrieval operations."""

    def test_get_notification_by_id(self, db, channel, worker, worker2):
        """Should retrieve notification by ID."""
        msg = create_message(db, channel.id, worker.id, "Hello")
        created = create_notification_bead(db, worker2.id, msg.id, channel.id)

        fetched = get_notification_bead(db, created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.worker_id == worker2.id

    def test_get_nonexistent_notification(self, db):
        """Should return None for missing notification."""
        result = get_notification_bead(db, "nonexistent-id")
        assert result is None

    def test_get_worker_notifications(self, db, channel, worker, worker2):
        """Should get all notifications for a worker."""
        # Create multiple messages and notifications
        for i in range(5):
            msg = create_message(db, channel.id, worker.id, f"Message {i}")
            create_notification_bead(db, worker2.id, msg.id, channel.id)

        notifications = get_worker_notifications(db, worker2.id)
        assert len(notifications) == 5

    def test_get_worker_notifications_ordered_by_priority(self, db, channel, worker, worker2):
        """Should order notifications by priority (lowest first) then creation."""
        msg1 = create_message(db, channel.id, worker.id, "Low priority")
        msg2 = create_message(db, channel.id, worker.id, "High priority")
        msg3 = create_message(db, channel.id, worker.id, "Normal priority")

        create_notification_bead(db, worker2.id, msg1.id, channel.id, priority=4)
        create_notification_bead(db, worker2.id, msg2.id, channel.id, priority=0)
        create_notification_bead(db, worker2.id, msg3.id, channel.id, priority=2)

        notifications = get_worker_notifications(db, worker2.id)
        priorities = [n.priority for n in notifications]
        assert priorities == [0, 2, 4]  # Sorted ascending

    def test_get_worker_notifications_by_status(self, db, channel, worker, worker2):
        """Should filter notifications by status."""
        msg1 = create_message(db, channel.id, worker.id, "Msg 1")
        msg2 = create_message(db, channel.id, worker.id, "Msg 2")

        notif1 = create_notification_bead(db, worker2.id, msg1.id, channel.id)
        create_notification_bead(db, worker2.id, msg2.id, channel.id)

        # Mark one as read
        mark_notification_read(db, notif1.id)

        pending = get_worker_notifications(db, worker2.id, status="pending")
        read = get_worker_notifications(db, worker2.id, status="read")

        assert len(pending) == 1
        assert len(read) == 1

    def test_get_pending_notifications(self, db, channel, worker, worker2):
        """Should get only pending notifications."""
        msg1 = create_message(db, channel.id, worker.id, "Msg 1")
        msg2 = create_message(db, channel.id, worker.id, "Msg 2")

        notif1 = create_notification_bead(db, worker2.id, msg1.id, channel.id)
        create_notification_bead(db, worker2.id, msg2.id, channel.id)

        mark_notification_read(db, notif1.id)

        pending = get_pending_notifications(db, worker2.id)
        assert len(pending) == 1

    def test_count_pending_notifications(self, db, channel, worker, worker2):
        """Should count pending notifications."""
        for i in range(3):
            msg = create_message(db, channel.id, worker.id, f"Message {i}")
            create_notification_bead(db, worker2.id, msg.id, channel.id)

        count = count_pending_notifications(db, worker2.id)
        assert count == 3


class TestNotificationStatusTransitions:
    """Test notification status state machine."""

    def test_mark_notification_read(self, db, channel, worker, worker2):
        """Should transition pending -> read."""
        msg = create_message(db, channel.id, worker.id, "Hello")
        notif = create_notification_bead(db, worker2.id, msg.id, channel.id)

        result = mark_notification_read(db, notif.id)
        assert result is True

        updated = get_notification_bead(db, notif.id)
        assert updated.status == "read"
        assert updated.read_at is not None

    def test_mark_read_idempotent(self, db, channel, worker, worker2):
        """Should not update already-read notification."""
        msg = create_message(db, channel.id, worker.id, "Hello")
        notif = create_notification_bead(db, worker2.id, msg.id, channel.id)

        mark_notification_read(db, notif.id)
        result = mark_notification_read(db, notif.id)
        assert result is False  # Already read, no update

    def test_mark_notification_actioned(self, db, channel, worker, worker2):
        """Should transition to actioned status."""
        msg = create_message(db, channel.id, worker.id, "Hello")
        notif = create_notification_bead(db, worker2.id, msg.id, channel.id)

        result = mark_notification_actioned(db, notif.id)
        assert result is True

        updated = get_notification_bead(db, notif.id)
        assert updated.status == "actioned"
        assert updated.actioned_at is not None
        assert updated.read_at is not None  # Also marks as read

    def test_mark_actioned_from_read(self, db, channel, worker, worker2):
        """Should transition read -> actioned."""
        msg = create_message(db, channel.id, worker.id, "Hello")
        notif = create_notification_bead(db, worker2.id, msg.id, channel.id)

        mark_notification_read(db, notif.id)
        result = mark_notification_actioned(db, notif.id)
        assert result is True

        updated = get_notification_bead(db, notif.id)
        assert updated.status == "actioned"

    def test_close_notification(self, db, channel, worker, worker2):
        """Should close notification."""
        msg = create_message(db, channel.id, worker.id, "Hello")
        notif = create_notification_bead(db, worker2.id, msg.id, channel.id)

        result = close_notification(db, notif.id)
        assert result is True

        updated = get_notification_bead(db, notif.id)
        assert updated.status == "closed"
        assert updated.closed_at is not None

    def test_close_notification_idempotent(self, db, channel, worker, worker2):
        """Should not update already-closed notification."""
        msg = create_message(db, channel.id, worker.id, "Hello")
        notif = create_notification_bead(db, worker2.id, msg.id, channel.id)

        close_notification(db, notif.id)
        result = close_notification(db, notif.id)
        assert result is False

    def test_close_notifications_for_message(self, db, channel, worker, worker2, worker3):
        """Should close all notifications for a message+worker."""
        subscribe_to_channel(db, channel.id, worker.id)
        subscribe_to_channel(db, channel.id, worker2.id)
        subscribe_to_channel(db, channel.id, worker3.id)

        msg = create_message(db, channel.id, worker.id, "Hello")
        create_notifications_for_message(db, msg.id, channel.id, worker.id)

        # Close worker2's notification
        closed = close_notifications_for_message(db, worker2.id, msg.id)
        assert closed == 1

        # Worker2's notification should be closed
        notifs_worker2 = get_pending_notifications(db, worker2.id)
        assert len(notifs_worker2) == 0

        # Worker3's notification should still be pending
        notifs_worker3 = get_pending_notifications(db, worker3.id)
        assert len(notifs_worker3) == 1


class TestNotificationCleanup:
    """Test notification cleanup operations."""

    def test_cleanup_old_notifications(self, db, channel, worker, worker2):
        """Should purge closed notifications older than retention period."""
        msg = create_message(db, channel.id, worker.id, "Hello")
        notif = create_notification_bead(db, worker2.id, msg.id, channel.id)

        # Close and manually backdate the closed_at timestamp
        close_notification(db, notif.id)
        old_date = datetime.now() - timedelta(days=DEFAULT_RETENTION_DAYS + 1)
        db.execute(
            "UPDATE notification_beads SET closed_at = ? WHERE id = ?",
            (old_date, notif.id)
        )
        db.connection.commit()

        purged = cleanup_old_notifications(db)
        assert purged == 1

        # Notification should be gone
        assert get_notification_bead(db, notif.id) is None

    def test_cleanup_preserves_recent_closed(self, db, channel, worker, worker2):
        """Should preserve recently closed notifications."""
        msg = create_message(db, channel.id, worker.id, "Hello")
        notif = create_notification_bead(db, worker2.id, msg.id, channel.id)
        close_notification(db, notif.id)

        purged = cleanup_old_notifications(db)
        assert purged == 0

        # Notification should still exist
        assert get_notification_bead(db, notif.id) is not None

    def test_cleanup_preserves_open_notifications(self, db, channel, worker, worker2):
        """Should not purge pending/read/actioned notifications."""
        msg = create_message(db, channel.id, worker.id, "Hello")
        notif = create_notification_bead(db, worker2.id, msg.id, channel.id)

        # Backdate but don't close
        old_date = datetime.now() - timedelta(days=DEFAULT_RETENTION_DAYS + 1)
        db.execute(
            "UPDATE notification_beads SET created_at = ? WHERE id = ?",
            (old_date, notif.id)
        )
        db.connection.commit()

        purged = cleanup_old_notifications(db)
        assert purged == 0  # Not closed, so not purged

    def test_run_notification_cleanup(self, db, channel, worker, worker2):
        """Should run full cleanup and return counts."""
        msg = create_message(db, channel.id, worker.id, "Hello")
        notif = create_notification_bead(db, worker2.id, msg.id, channel.id)
        close_notification(db, notif.id)

        # Backdate
        old_date = datetime.now() - timedelta(days=DEFAULT_RETENTION_DAYS + 1)
        db.execute(
            "UPDATE notification_beads SET closed_at = ? WHERE id = ?",
            (old_date, notif.id)
        )
        db.connection.commit()

        result = run_notification_cleanup(db)
        assert result["old_notifications_purged"] == 1
        assert result["total_purged"] >= 1


class TestNotificationIntegration:
    """Test notification system integration scenarios."""

    def test_full_notification_lifecycle(self, db, channel, worker, worker2):
        """Should handle full lifecycle: create -> read -> action -> close."""
        subscribe_to_channel(db, channel.id, worker.id)
        subscribe_to_channel(db, channel.id, worker2.id)

        # Worker sends message
        msg = create_message_with_notifications(db, channel.id, worker.id, "Task for you")

        # Worker2 checks notifications
        pending = get_pending_notifications(db, worker2.id)
        assert len(pending) == 1
        notif = pending[0]
        assert notif.message_id == msg.id

        # Worker2 reads the notification
        mark_notification_read(db, notif.id)
        updated = get_notification_bead(db, notif.id)
        assert updated.status == "read"

        # Worker2 actions the notification
        mark_notification_actioned(db, notif.id)
        updated = get_notification_bead(db, notif.id)
        assert updated.status == "actioned"

        # Worker2 closes the notification
        close_notification(db, notif.id)
        updated = get_notification_bead(db, notif.id)
        assert updated.status == "closed"

        # No more pending
        pending = get_pending_notifications(db, worker2.id)
        assert len(pending) == 0

    def test_notifications_across_multiple_channels(self, db, worker, worker2, worker3):
        """Should handle notifications across multiple channels."""
        chan1 = create_channel(db, "channel-1", "topic")
        chan2 = create_channel(db, "channel-2", "topic")

        # Worker2 in both channels
        subscribe_to_channel(db, chan1.id, worker.id)
        subscribe_to_channel(db, chan1.id, worker2.id)
        subscribe_to_channel(db, chan2.id, worker.id)
        subscribe_to_channel(db, chan2.id, worker2.id)
        # Worker3 only in chan1
        subscribe_to_channel(db, chan1.id, worker3.id)

        # Send messages in both channels
        create_message_with_notifications(db, chan1.id, worker.id, "Msg in chan1")
        create_message_with_notifications(db, chan2.id, worker.id, "Msg in chan2")

        # Worker2 should have 2 notifications
        pending_worker2 = get_pending_notifications(db, worker2.id)
        assert len(pending_worker2) == 2

        # Worker3 should have 1 notification
        pending_worker3 = get_pending_notifications(db, worker3.id)
        assert len(pending_worker3) == 1

    def test_high_priority_notifications_first(self, db, channel, worker, worker2):
        """Should surface high priority notifications first."""
        subscribe_to_channel(db, channel.id, worker.id)
        subscribe_to_channel(db, channel.id, worker2.id)

        # Send messages with different priorities
        create_message_with_notifications(
            db, channel.id, worker.id, "Low", priority=4
        )
        create_message_with_notifications(
            db, channel.id, worker.id, "High", priority=0
        )
        create_message_with_notifications(
            db, channel.id, worker.id, "Normal", priority=2
        )

        pending = get_pending_notifications(db, worker2.id)
        priorities = [n.priority for n in pending]
        assert priorities == [0, 2, 4]  # Highest priority (lowest number) first


class TestAcknowledgeNotification:
    """Test notification acknowledgment functionality."""

    def test_acknowledge_notification_closes_it(self, db, channel, worker, worker2):
        """Should close notification when acknowledged."""
        msg = create_message(db, channel.id, worker.id, "Hello")
        notif = create_notification_bead(db, worker2.id, msg.id, channel.id)

        result = acknowledge_notification(db, notif.id)
        assert result is True

        updated = get_notification_bead(db, notif.id)
        assert updated.status == "closed"
        assert updated.closed_at is not None

    def test_acknowledge_nonexistent_notification(self, db):
        """Should return False for nonexistent notification."""
        result = acknowledge_notification(db, "nonexistent-id")
        assert result is False

    def test_acknowledge_already_closed_notification(self, db, channel, worker, worker2):
        """Should return False when acknowledging already-closed notification."""
        msg = create_message(db, channel.id, worker.id, "Hello")
        notif = create_notification_bead(db, worker2.id, msg.id, channel.id)

        # Acknowledge once
        acknowledge_notification(db, notif.id)
        # Try to acknowledge again
        result = acknowledge_notification(db, notif.id)
        assert result is False


class TestNotificationExpiration:
    """Test notification expiration and cleanup functionality."""

    def test_create_notification_with_expiration(self, db, channel, worker, worker2):
        """Should create notification with expiration time."""
        msg = create_message(db, channel.id, worker.id, "Hello")
        expires = datetime.now() + timedelta(hours=24)
        notif = create_notification_bead(
            db, worker2.id, msg.id, channel.id, expires_at=expires
        )

        assert notif.expires_at is not None
        # Compare timestamps (allowing small delta for test execution time)
        assert abs((notif.expires_at - expires).total_seconds()) < 1

    def test_cleanup_expired_notifications(self, db, channel, worker, worker2):
        """Should delete notifications that have expired."""
        msg = create_message(db, channel.id, worker.id, "Hello")
        # Create notification that expired an hour ago
        expired_time = datetime.now() - timedelta(hours=1)
        notif = create_notification_bead(
            db, worker2.id, msg.id, channel.id, expires_at=expired_time
        )

        purged = cleanup_expired_notifications(db)
        assert purged == 1

        # Notification should be gone
        assert get_notification_bead(db, notif.id) is None

    def test_cleanup_preserves_unexpired_notifications(self, db, channel, worker, worker2):
        """Should not delete notifications that haven't expired yet."""
        msg = create_message(db, channel.id, worker.id, "Hello")
        future_time = datetime.now() + timedelta(hours=24)
        notif = create_notification_bead(
            db, worker2.id, msg.id, channel.id, expires_at=future_time
        )

        purged = cleanup_expired_notifications(db)
        assert purged == 0

        # Notification should still exist
        assert get_notification_bead(db, notif.id) is not None

    def test_cleanup_preserves_notifications_without_expiration(self, db, channel, worker, worker2):
        """Should not delete notifications without expiration."""
        msg = create_message(db, channel.id, worker.id, "Hello")
        notif = create_notification_bead(db, worker2.id, msg.id, channel.id)
        assert notif.expires_at is None

        purged = cleanup_expired_notifications(db)
        assert purged == 0

        # Notification should still exist
        assert get_notification_bead(db, notif.id) is not None

    def test_run_cleanup_includes_expired(self, db, channel, worker, worker2):
        """Should include expired notifications in full cleanup."""
        msg = create_message(db, channel.id, worker.id, "Hello")
        expired_time = datetime.now() - timedelta(hours=1)
        notif = create_notification_bead(
            db, worker2.id, msg.id, channel.id, expires_at=expired_time
        )

        result = run_notification_cleanup(db)
        assert result["expired_notifications_purged"] == 1
        assert result["total_purged"] >= 1


class TestMessagesPermanentAfterNotificationCleanup:
    """Test that messages remain permanent after notification cleanup.

    Per CLAUDE.md: "Messages = permanent knowledge (searchable forever).
    Notifications = ephemeral tasks (beads pointing to messages)."
    """

    def test_messages_persist_after_notification_cleanup(self, db, channel, worker, worker2):
        """Messages should persist after their notifications are cleaned up."""
        # Create a message with notifications
        subscribe_to_channel(db, channel.id, worker.id)
        subscribe_to_channel(db, channel.id, worker2.id)

        msg = create_message_with_notifications(
            db, channel.id, worker.id, "Permanent knowledge"
        )

        # Verify notification exists
        pending = get_pending_notifications(db, worker2.id)
        assert len(pending) == 1

        # Acknowledge and close the notification
        acknowledge_notification(db, pending[0].id)

        # Backdate the closed_at to trigger cleanup
        old_date = datetime.now() - timedelta(days=DEFAULT_RETENTION_DAYS + 1)
        db.execute(
            "UPDATE notification_beads SET closed_at = ? WHERE id = ?",
            (old_date, pending[0].id)
        )
        db.connection.commit()

        # Run cleanup
        result = run_notification_cleanup(db)
        assert result["old_notifications_purged"] == 1

        # Message should still exist
        fetched_msg = get_message(db, msg.id)
        assert fetched_msg is not None
        assert fetched_msg.content == "Permanent knowledge"

    def test_messages_persist_after_expired_notification_cleanup(self, db, channel, worker, worker2):
        """Messages should persist after their expired notifications are removed."""
        msg = create_message(db, channel.id, worker.id, "Important data")

        # Create an expired notification
        expired_time = datetime.now() - timedelta(hours=1)
        notif = create_notification_bead(
            db, worker2.id, msg.id, channel.id, expires_at=expired_time
        )

        # Run cleanup
        purged = cleanup_expired_notifications(db)
        assert purged == 1

        # Notification should be gone
        assert get_notification_bead(db, notif.id) is None

        # Message should still exist
        fetched_msg = get_message(db, msg.id)
        assert fetched_msg is not None
        assert fetched_msg.content == "Important data"

    def test_messages_persist_after_acknowledged_notification_cleanup(self, db, channel, worker, worker2):
        """Messages should persist after acknowledged notifications are cleaned."""
        msg = create_message(db, channel.id, worker.id, "Knowledge forever")
        notif = create_notification_bead(db, worker2.id, msg.id, channel.id)

        # Acknowledge the notification
        acknowledge_notification(db, notif.id)

        # Force immediate cleanup by backdating
        old_date = datetime.now() - timedelta(days=DEFAULT_RETENTION_DAYS + 1)
        db.execute(
            "UPDATE notification_beads SET closed_at = ? WHERE id = ?",
            (old_date, notif.id)
        )
        db.connection.commit()

        # Run cleanup
        cleanup_old_notifications(db)

        # Notification should be gone
        assert get_notification_bead(db, notif.id) is None

        # Message should still exist
        fetched_msg = get_message(db, msg.id)
        assert fetched_msg is not None
        assert fetched_msg.content == "Knowledge forever"

    def test_multiple_notifications_same_message(self, db, channel, worker, worker2, worker3):
        """Messages should persist even after all notifications are cleaned."""
        subscribe_to_channel(db, channel.id, worker.id)
        subscribe_to_channel(db, channel.id, worker2.id)
        subscribe_to_channel(db, channel.id, worker3.id)

        msg = create_message_with_notifications(
            db, channel.id, worker.id, "Shared knowledge"
        )

        # Get all notifications
        notifs_w2 = get_pending_notifications(db, worker2.id)
        notifs_w3 = get_pending_notifications(db, worker3.id)
        assert len(notifs_w2) == 1
        assert len(notifs_w3) == 1

        # Acknowledge all notifications
        acknowledge_notification(db, notifs_w2[0].id)
        acknowledge_notification(db, notifs_w3[0].id)

        # Backdate for cleanup
        old_date = datetime.now() - timedelta(days=DEFAULT_RETENTION_DAYS + 1)
        db.execute(
            "UPDATE notification_beads SET closed_at = ?",
            (old_date,)
        )
        db.connection.commit()

        # Run cleanup
        result = run_notification_cleanup(db)
        assert result["old_notifications_purged"] == 2

        # Message should still exist
        fetched_msg = get_message(db, msg.id)
        assert fetched_msg is not None
        assert fetched_msg.content == "Shared knowledge"
